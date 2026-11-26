using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using KKAPI.Studio;
using UnityEngine;
using UnityStandardAssets.ImageEffects;

namespace KKMaps.Capture
{
    /// <summary>
    /// Where a KKS capture runs: the story game (KoikatsuSunshine.exe) for the story Maps, CharaStudio for
    /// the Studio Maps, its own *_studio builds of them (kks-spike.md, section 10).
    /// </summary>
    internal interface IHost
    {
        string Profile { get; }
        Camera Camera { get; }
        IEnumerator Ready();
        IEnumerator Load(string bundle);
        IEnumerator SetTime(SunLightInfo.Info.Type type);
        void Hold(bool held);
        /// <summary>A seed view about the Map's own anchor: its free-H point (h_free), at eye height.</summary>
        IEnumerator PlaceDefault(Frames frames, Dictionary<string, object> view);
    }

    /// <summary>CharaStudio: its own camera, Studio.Map's loading and its sunType setter, as KK's.</summary>
    internal sealed class StudioHost : IHost
    {
        private readonly MonoBehaviour plugin;

        public StudioHost(MonoBehaviour plugin)
        {
            this.plugin = plugin;
        }

        public string Profile { get { return "studio"; } }

        public Camera Camera { get { return Singleton<Studio.Studio>.Instance.cameraCtrl.mainCmaera; } }

        public IEnumerator Ready()
        {
            while (!StudioAPI.StudioLoaded) yield return new WaitForSecondsRealtime(0.5f);
            yield return new WaitForSecondsRealtime(2f);
        }

        public IEnumerator Load(string bundle)
        {
            int no = MapNumber(bundle);
            Plugin.Log.LogInfo("Loading " + bundle + " (Studio map " + no + ")");
            yield return plugin.StartCoroutine(Singleton<Studio.Map>.Instance.LoadMapCoroutine(no));
            yield return new WaitForSecondsRealtime(2f);
        }

        public IEnumerator SetTime(SunLightInfo.Info.Type type)
        {
            Singleton<Studio.Map>.Instance.sunType = type;
            yield return new WaitForSecondsRealtime(1f);
        }

        public void Hold(bool held)
        {
            Singleton<Studio.Studio>.Instance.cameraCtrl.enabled = !held;
        }

        public IEnumerator PlaceDefault(Frames frames, Dictionary<string, object> view)
        {
            // As KK's: from Studio's own camera for the Map (CameraControl.Reset).
            var ctrl = Singleton<Studio.Studio>.Instance.cameraCtrl;
            Camera cam = Camera;
            ctrl.enabled = true;
            ctrl.Reset(0);
            yield return null;
            yield return null;
            ctrl.enabled = false;
            Vector3 target = ctrl.targetPos;
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
    }

    /// <summary>
    /// KKS's story game from its title screen with no save: the ActionCamera prefab its talk and ADV scenes
    /// load (camera/action.unity3d), each Map loaded as ActionMap.Change does (Manager.Scene.LoadBaseScene with
    /// the story list's level name), and each Time of Day set as ActionMap.SetCycleToSunLight does:
    /// SunLightInfo.Set with this camera, or Set(null) (the first info) where the Map has none of that type,
    /// then the camera's GlobalFog follows RenderSettings.fog (UpdateCameraFog), and MapSkyInfo.Change(type)
    /// gives SkyStudio the Time of Day's profile. The camera clears to the skybox, as the story list's isSky
    /// says for every Map. The player's effect settings are left out, as in KK.
    /// </summary>
    internal sealed class GameHost : IHost
    {
        private const string CameraBundle = "camera/action.unity3d";
        private const string CameraAsset = "ActionCamera";
        private const string TitleScene = "Title";
        private const float Eye = 1.6f;

        private readonly MonoBehaviour plugin;
        private Camera cam;
        private string level;

        public GameHost(MonoBehaviour plugin)
        {
            this.plugin = plugin;
        }

        public string Profile { get { return "game"; } }

        public Camera Camera { get { return cam; } }

        public IEnumerator Ready()
        {
            while (!AtTitle())
            {
                yield return new WaitForSecondsRealtime(0.5f);
            }
            yield return new WaitForSecondsRealtime(2f);

            var go = CommonLib.LoadAsset<GameObject>(CameraBundle, CameraAsset, true);
            AssetBundleManager.UnloadAssetBundle(CameraBundle, false);
            if (go == null) throw new Exception("No " + CameraAsset + " in " + CameraBundle);
            UnityEngine.Object.DontDestroyOnLoad(go);
            cam = go.GetComponent<Camera>();
            cam.clearFlags = CameraClearFlags.Skybox;
            foreach (var b in go.GetComponentsInChildren<Behaviour>(true))
            {
                string name = b.GetType().Name;
                if (name == "CameraEffectorConfig" || name == "CorrectLightAngle") b.enabled = false;
            }
        }

        /// <summary>The title screen is up and still: Manager.Scene throws until its scene stack exists.</summary>
        private static bool AtTitle()
        {
            try
            {
                return Manager.Scene.LoadSceneName == TitleScene && !Manager.Scene.IsNowLoadingFade;
            }
            catch (NullReferenceException)
            {
                return false;
            }
        }

        public IEnumerator Load(string bundle)
        {
            level = LevelName(bundle);
            Plugin.Log.LogInfo("Loading " + bundle + " (level " + level + ")");
            Manager.Scene.LoadBaseScene(new Manager.Scene.Data
            {
                bundleName = bundle,
                levelName = level,
                fadeType = FadeCanvas.Fade.None,
            });
            float until = Time.realtimeSinceStartup + 120f;
            while (Manager.Scene.GetRootComponent<SunLightInfo>(level) == null || Manager.Scene.IsNowLoadingFade)
            {
                if (Time.realtimeSinceStartup > until) throw new Exception("The level " + level + " didn't load in 120 s");
                yield return new WaitForSecondsRealtime(0.5f);
            }
            yield return new WaitForSecondsRealtime(3f);
        }

        public IEnumerator SetTime(SunLightInfo.Info.Type type)
        {
            var info = Manager.Scene.GetRootComponent<SunLightInfo>(level);
            if (info == null) throw new Exception("The level " + level + " has no SunLightInfo");
            if (!info.Set(type, cam) && !info.Set(null, cam)) throw new Exception("The level " + level + " has no SunLightInfo infos");
            var fog = cam.GetComponent<GlobalFog>();
            if (fog != null) fog.enabled = RenderSettings.fog;
            var shafts = cam.GetComponent<SunShafts>();
            if (shafts != null) shafts.enabled = true;
            var sky = info.GetComponent<MapSkyInfo>();
            if (sky != null) sky.Change((int)type);
            yield return new WaitForSecondsRealtime(1.5f);   // SkyStudio sets the sky in its Update
        }

        public void Hold(bool held)
        {
        }

        public IEnumerator PlaceDefault(Frames frames, Dictionary<string, object> view)
        {
            // About the Map's free-H point: with "eye", stand on it at eye height and look out level-ish
            // along its heading turned by "studio_default" degrees; without, an overview from behind and above.
            var root = Manager.Scene.GetRootComponent<SunLightInfo>(level).transform;
            Transform anchor = FindLoop(root, "h_free");
            if (anchor == null) throw new Exception("The level " + level + " has no h_free");
            if (anchor.childCount > 0) anchor = anchor.GetChild(0);
            var yaw = Quaternion.AngleAxis((float)(double)view["studio_default"], Vector3.up);
            Vector3 heading = anchor.forward;
            heading.y = 0f;
            heading = yaw * (heading.sqrMagnitude > 1e-6f ? heading.normalized : Vector3.forward);
            if (view.ContainsKey("eye"))
            {
                Vector3 eye = anchor.position + Vector3.up * (float)(double)view["eye"];
                frames.Place(eye, eye + heading * 10f + Vector3.down * 1f, 40f);
            }
            else
            {
                Vector3 target = anchor.position + Vector3.up * 1f;
                frames.Place(target - heading * 6f + Vector3.up * 2.5f, target, 40f);
            }
            yield return null;
        }

        private static Transform FindLoop(Transform t, string name)
        {
            if (t.name == name) return t;
            for (int i = 0; i < t.childCount; i++)
            {
                var found = FindLoop(t.GetChild(i), name);
                if (found != null) return found;
            }
            return null;
        }

        /// <summary>The level the story list's entry for this Scene Bundle loads (BaseMap.LoadMapInfo).</summary>
        private static string LevelName(string bundle)
        {
            foreach (string file in CommonLib.GetAssetBundleNameListFromPath("map/list/mapinfo/", true))
            {
                var op = AssetBundleManager.LoadAllAsset(file, typeof(MapInfo));
                try
                {
                    foreach (var info in op.GetAllAssets<MapInfo>())
                    {
                        foreach (var p in info.param)
                        {
                            if (p.AssetBundleName == bundle && !p.is2D) return p.AssetName;
                        }
                    }
                }
                finally
                {
                    AssetBundleManager.UnloadAssetBundle(file, false);
                }
            }
            throw new Exception("No story map loads " + bundle);
        }
    }
}
