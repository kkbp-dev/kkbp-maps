using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using BepInEx;
using KKAPI.Studio;
using UnityEngine;

namespace KKMaps.Capture
{
    /// <summary>
    /// One capture run from a request file, after KKBP's auto-export (its ADR 0012). The request is
    /// BepInEx/config/kkbp-maps-capture.json, written by tools/capture.py, all positions in Unity space:
    /// <code>
    /// { "output": "Z:\\path\\folder", "width": 1280, "height": 720,
    ///   "disable": [ "DepthOfField", "BloomAndFlares", ... ],
    ///   "maps": [ { "folder": "map/scene/1f", "bundle": "map/scene/1f.unity3d",
    ///     "variants": [ { "name": "day", "type": 0,
    ///       "views": [ { "name": "hall", "position": [x, y, z], "target": [x, y, z], "fov": 40 },
    ///                  { "name": "studio-90", "studio_default": 90 }, { "name": "eye-90", "studio_default": 90, "eye": 1.6 } ] } ] } ] }
    /// </code>
    /// A view with "studio_default" starts from Studio's own camera for the Map (CameraControl.Reset)
    /// and turns it about its target by that yaw in degrees. The result lists every view as placed, in
    /// Unity space, so tools/capture.py can keep them as Capture Views.
    /// <code>
    /// </code>
    /// It writes &lt;output&gt;/camera-studio.json (the Camera Profile's raw settings, Dump), and for each view
    /// &lt;output&gt;/&lt;folder&gt;/&lt;variant&gt;/&lt;view&gt;.png (the Reference Capture) and .pregrade.exr, and for each
    /// variant &lt;folder&gt;/&lt;variant&gt;/lights.json (Dump.Lights: every light, and the renderers the request
    /// names under "renderers"). With "frames": false it writes only the lights. The result goes
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

            while (!StudioAPI.StudioLoaded)
            {
                yield return new WaitForSecondsRealtime(0.5f);
            }
            yield return new WaitForSecondsRealtime(2f);

            string error = null;
            IEnumerator work = null;
            try
            {
                work = Work(request);
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

        private IEnumerator Work(Dictionary<string, object> request)
        {
            string output = (string)request["output"];
            int width = Int(request, "width", 1280);
            int height = Int(request, "height", 720);
            var disable = new HashSet<string>(List(request, "disable").Cast<string>());
            bool takeFrames = !request.ContainsKey("frames") || (bool)request["frames"];
            var rendererNames = List(request, "renderers").Cast<string>().ToList();

            var studio = Singleton<Studio.Studio>.Instance;
            Camera cam = studio.cameraCtrl.mainCmaera;
            var frames = new Frames(cam, width, height, disable);

            foreach (Dictionary<string, object> map in List(request, "maps"))
            {
                string bundle = (string)map["bundle"];
                int no = MapNumber(bundle);
                Plugin.Log.LogInfo("Loading " + bundle + " (Studio map " + no + ")");
                yield return plugin.StartCoroutine(Singleton<Studio.Map>.Instance.LoadMapCoroutine(no));
                yield return new WaitForSecondsRealtime(2f);

                foreach (Dictionary<string, object> variant in List(map, "variants"))
                {
                    string vname = (string)variant["name"];
                    var type = (SunLightInfo.Info.Type)Int(variant, "type", 0);
                    Singleton<Studio.Map>.Instance.sunType = type;
                    yield return new WaitForSecondsRealtime(1f);
                    Resources.UnloadUnusedAssets();
                    System.GC.Collect();

                    string lightsFolder = Path.Combine(Path.Combine(output, (string)map["folder"]), vname);
                    Directory.CreateDirectory(lightsFolder);
                    string lightsPath = Path.Combine(lightsFolder, "lights.json");
                    File.WriteAllText(lightsPath, Json.Write(Dump.Lights(cam, rendererNames)));
                    files.Add(lightsPath);
                    Write("running", null);
                    if (!takeFrames) continue;

                    if (!files.Any(f => ((string)f).EndsWith("camera-studio.json")))
                    {
                        string dump = Path.Combine(output, "camera-studio.json");
                        File.WriteAllText(dump, Json.Write(Dump.Camera(cam)));
                        files.Add(dump);
                    }

                    string folder = Path.Combine(Path.Combine(output, (string)map["folder"]), vname);
                    Directory.CreateDirectory(folder);
                    studio.cameraCtrl.enabled = false;
                    foreach (Dictionary<string, object> view in List(variant, "views"))
                    {
                        if (view.ContainsKey("studio_default"))
                        {
                            // From Studio's own camera for the Map (CameraControl.Reset): with "eye", stand
                            // that high above its target and look out level-ish along the camera's heading
                            // turned by "studio_default" degrees; without, Studio's camera turned about its target.
                            studio.cameraCtrl.enabled = true;
                            studio.cameraCtrl.Reset(0);
                            yield return null;
                            yield return null;
                            studio.cameraCtrl.enabled = false;
                            Vector3 target = studio.cameraCtrl.targetPos;
                            var yaw = Quaternion.AngleAxis((float)(double)view["studio_default"], Vector3.up);
                            if (view.ContainsKey("eye"))
                            {
                                Vector3 heading = cam.transform.forward;
                                heading.y = 0f;
                                heading = yaw * heading.normalized;
                                Vector3 eye = target + Vector3.up * (float)(double)view["eye"];
                                frames.Place(eye, eye + heading * 10f + Vector3.down * 1f, cam.fieldOfView);
                            }
                            else
                            {
                                frames.Place(target + yaw * (cam.transform.position - target), target, cam.fieldOfView);
                            }
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
                    studio.cameraCtrl.enabled = true;
                    warnings.AddRange(frames.TakeWarnings().Cast<object>());
                }
            }
        }

        /// <summary>The Studio map that loads this Scene Bundle.</summary>
        private static int MapNumber(string bundle)
        {
            var maps = Singleton<Studio.Info>.Instance.dicMapLoadInfo;
            string scene = Path.GetFileNameWithoutExtension(bundle);
            foreach (var kv in maps)
            {
                if (kv.Value.bundlePath == bundle) return kv.Key;
            }
            foreach (var kv in maps)
            {
                if (string.Equals(kv.Value.fileName, scene, StringComparison.OrdinalIgnoreCase)) return kv.Key;
            }
            throw new Exception("No Studio map loads " + bundle + "; Studio has: " +
                string.Join(", ", maps.Select(kv => kv.Key + " " + kv.Value.bundlePath + " " + kv.Value.fileName).ToArray()));
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
