using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using BepInEx;
using UnityEngine;

namespace KKMaps.Capture
{
    /// <summary>
    /// One capture run from a request file, after KKBP's auto-export (its ADR 0012). The request is
    /// BepInEx/config/kkbp-maps-capture.json, written by tools/capture.py, all positions in Unity space:
    /// <code>
    /// { "camera": "studio", "output": "Z:\\path\\folder", "width": 1280, "height": 720,
    ///   "disable": [ "DepthOfField", "BloomAndFlares", ... ],
    ///   "maps": [ { "folder": "map/scene/1f", "bundle": "map/scene/1f.unity3d",
    ///     "variants": [ { "name": "day", "type": 0,
    ///       "views": [ { "name": "hall", "position": [x, y, z], "target": [x, y, z], "fov": 40 },
    ///                  { "name": "studio-90", "studio_default": 90 }, { "name": "eye-90", "studio_default": 90, "eye": 1.6 } ] } ] } ] }
    /// </code>
    /// "camera" is the Camera Profile, and so the game the request runs in (Hosts.cs): "studio" (CharaStudio,
    /// the default) or "game" (the story game, Koikatu.exe). A view with "studio_default" (Studio only)
    /// starts from Studio's own camera for the Map (CameraControl.Reset) and turns it about its target by
    /// that yaw in degrees. The result lists every view as placed, in Unity space, so tools/capture.py can
    /// keep them as Capture Views.
    ///
    /// It writes &lt;output&gt;/camera-&lt;profile&gt;.json (the Camera Profile's raw settings, Dump), and for each view
    /// &lt;output&gt;/&lt;folder&gt;/&lt;variant&gt;/&lt;view&gt;.png (the Reference Capture) and .pregrade.exr, and for each
    /// variant &lt;folder&gt;/&lt;variant&gt;/lights.json (Dump.Lights: every light, and the renderers the request
    /// names under "renderers") and camera.json (the camera at that Time of Day: its fog and sun shafts).
    /// With "frames": false it writes no frames; with "sun_off": true the
    /// Map's sun (RenderSettings.sun) is switched off after each Time of Day is set, and with
    /// "sun_shadows_off": true it casts no shadows. The result goes
    /// to kkbp-maps-capture.result.json next to the request:
    /// { "state": "running" | "succeeded" | "failed", "error": …, "files": […], "warnings": […], "views": […] },
    /// rewritten after each view while "running", then the game quits.
    /// </summary>
    internal sealed class Request
    {
        private static readonly string RequestPath = Path.Combine(Paths.ConfigPath, "kkbp-maps-capture.json");
        private static readonly string ResultPath = Path.Combine(Paths.ConfigPath, "kkbp-maps-capture.result.json");

        private readonly Plugin plugin;
        private readonly List<object> files = new List<object>();
        private readonly List<object> warnings = new List<object>();
        private readonly List<object> placed = new List<object>();

        public Request(Plugin plugin)
        {
            this.plugin = plugin;
        }

        public static bool Pending
        {
            get { return File.Exists(RequestPath); }
        }

        public IEnumerator Run()
        {
            Dictionary<string, object> request;
            try
            {
                request = (Dictionary<string, object>)Json.Parse(File.ReadAllText(RequestPath));
                File.Delete(RequestPath);
            }
            catch (Exception e)
            {
                Finish("The request couldn't be read: " + e.Message);
                yield break;
            }
            Plugin.Log.LogInfo("Capture requested by " + RequestPath);

            IHost host;
            string camera = request.ContainsKey("camera") ? (string)request["camera"] : "studio";
            if (camera == "studio") host = new StudioHost(plugin);
            else if (camera == "game") host = new GameHost(plugin);
            else
            {
                Finish("Unknown camera " + camera + ": \"studio\" or \"game\"");
                yield break;
            }

            string error = null;
            IEnumerator work = null;
            try
            {
                work = Sequence(host.Ready(), Work(request, host));
            }
            catch (Exception e)
            {
                error = e.ToString();
            }
            while (error == null)
            {
                try
                {
                    if (!work.MoveNext()) break;
                }
                catch (Exception e)
                {
                    error = e.ToString();
                    break;
                }
                yield return work.Current;
            }
            Finish(error);
        }

        private IEnumerator Work(Dictionary<string, object> request, IHost host)
        {
            string output = (string)request["output"];
            int width = Int(request, "width", 1280);
            int height = Int(request, "height", 720);
            var disable = new HashSet<string>(List(request, "disable").Cast<string>());
            bool takeFrames = !request.ContainsKey("frames") || (bool)request["frames"];
            var rendererNames = List(request, "renderers").Cast<string>().ToList();
            bool sunOff = request.ContainsKey("sun_off") && (bool)request["sun_off"];
            bool sunShadowsOff = request.ContainsKey("sun_shadows_off") && (bool)request["sun_shadows_off"];

            Camera cam = host.Camera;
            var frames = new Frames(cam, width, height, disable);
            string profileDump = Path.Combine(output, "camera-" + host.Profile + ".json");

            foreach (Dictionary<string, object> map in List(request, "maps"))
            {
                for (var load = host.Load((string)map["bundle"]); load.MoveNext();) yield return load.Current;

                foreach (Dictionary<string, object> variant in List(map, "variants"))
                {
                    string vname = (string)variant["name"];
                    for (var set = host.SetTime((SunLightInfo.Info.Type)Int(variant, "type", 0)); set.MoveNext();) yield return set.Current;
                    if (sunOff && RenderSettings.sun != null)
                    {
                        RenderSettings.sun.enabled = false;   // to measure what the sun adds (look check)
                        yield return new WaitForSecondsRealtime(0.5f);
                    }
                    if (sunShadowsOff && RenderSettings.sun != null)
                    {
                        RenderSettings.sun.shadows = LightShadows.None;   // to measure what its shadows take away
                        yield return new WaitForSecondsRealtime(0.5f);
                    }
                    Resources.UnloadUnusedAssets();
                    System.GC.Collect();

                    string folder = Path.Combine(Path.Combine(output, (string)map["folder"]), vname);
                    Directory.CreateDirectory(folder);
                    string lightsPath = Path.Combine(folder, "lights.json");
                    File.WriteAllText(lightsPath, Json.Write(Dump.Lights(cam, rendererNames)));
                    files.Add(lightsPath);
                    string cameraPath = Path.Combine(folder, "camera.json");   // this Time of Day's fog and sun shafts
                    File.WriteAllText(cameraPath, Json.Write(Dump.Camera(cam)));
                    files.Add(cameraPath);
                    var globals = List(request, "globals").Cast<string>().ToList();
                    if (globals.Count > 0)   // the shader globals the game has set, such as Koikano's
                    {
                        string globalsPath = Path.Combine(folder, "globals.json");
                        File.WriteAllText(globalsPath, Json.Write(Dump.Globals(globals)));
                        files.Add(globalsPath);
                    }
                    Write("running", null);
                    if (!takeFrames) continue;

                    if (!files.Contains(profileDump))
                    {
                        File.WriteAllText(profileDump, Json.Write(Dump.Camera(cam)));
                        files.Add(profileDump);
                    }

                    host.Hold(true);
                    foreach (Dictionary<string, object> view in List(variant, "views"))
                    {
                        if (view.ContainsKey("studio_default"))
                        {
                            for (var place = host.PlaceDefault(frames, view); place.MoveNext();) yield return place.Current;
                        }
                        else
                        {
                            frames.Place(Vector(view, "position"), Vector(view, "target"), (float)(double)view["fov"]);
                        }
                        yield return null;
                        yield return null;
                        string stem = Path.Combine(folder, (string)view["name"]);
                        files.AddRange(frames.Capture(stem).Cast<object>());
                        placed.Add(new Dictionary<string, object>
                        {
                            { "map", map["folder"] }, { "variant", vname }, { "name", view["name"] },
                            { "position", Triple(cam.transform.position) },
                            { "target", Triple(cam.transform.position + cam.transform.forward * frames.Distance) },
                            { "fov", (double)cam.fieldOfView },
                        });
                        Write("running", null);
                    }
                    host.Hold(false);
                    warnings.AddRange(frames.TakeWarnings().Cast<object>());
                }
            }
        }

        private static IEnumerator Sequence(params IEnumerator[] steps)
        {
            foreach (var step in steps)
            {
                while (step.MoveNext()) yield return step.Current;
            }
        }

        private void Finish(string error)
        {
            Write(error == null ? "succeeded" : "failed", error);
            Application.Quit();
        }

        /// <summary>The result so far: "running" after each view, so a crash keeps what was captured.</summary>
        private void Write(string state, string error)
        {
            var result = new Dictionary<string, object>
            {
                { "state", state },
                { "files", files },
                { "warnings", warnings },
                { "views", placed },
            };
            if (error != null)
            {
                result["error"] = error;
                Plugin.Log.LogError(error);
            }
            string partial = ResultPath + ".part";
            File.WriteAllText(partial, Json.Write(result));
            if (File.Exists(ResultPath)) File.Delete(ResultPath);
            File.Move(partial, ResultPath);
        }

        private static List<object> List(Dictionary<string, object> o, string key)
        {
            object v;
            return o.TryGetValue(key, out v) && v != null ? (List<object>)v : new List<object>();
        }

        private static int Int(Dictionary<string, object> o, string key, int fallback)
        {
            object v;
            return o.TryGetValue(key, out v) && v != null ? (int)(double)v : fallback;
        }

        private static List<object> Triple(Vector3 v)
        {
            return new List<object> { (double)v.x, (double)v.y, (double)v.z };
        }

        private static Vector3 Vector(Dictionary<string, object> o, string key)
        {
            var a = (List<object>)o[key];
            return new Vector3((float)(double)a[0], (float)(double)a[1], (float)(double)a[2]);
        }
    }
}
