using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using KKAPI.Studio;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityStandardAssets.ImageEffects;

namespace KKMaps.Capture
{
    /// <summary>
    /// Where a capture runs: the game camera of one Camera Profile, and how that game loads a Map and sets
    /// its Time of Day. Studio's and the story game's types are both in each build's Assembly-CSharp, so one
    /// plugin serves both; a request names its host by "camera" ("studio" unless given).
    /// </summary>
    internal interface IHost
    {
        string Profile { get; }
        Camera Camera { get; }
        IEnumerator Ready();
        IEnumerator Load(string bundle);
        IEnumerator SetTime(SunLightInfo.Info.Type type);
        /// <summary>Stops whatever moves the camera, so views can be placed; false gives it back.</summary>
        void Hold(bool held);
        /// <summary>The camera the game itself starts the Map's views from (Studio only).</summary>
        IEnumerator PlaceDefault(Frames frames, Dictionary<string, object> view);
    }

    /// <summary>CharaStudio: its own camera, Studio.Map's loading and its sunType setter.</summary>
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
            // From Studio's own camera for the Map (CameraControl.Reset): with "eye", stand that high above
            // its target and look out level-ish along the camera's heading turned by "studio_default"
            // degrees; without, Studio's camera turned about its target.
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
    /// The story game (Koikatu.exe), from its title screen with no save: the ActionCamera prefab its talk
    /// and ADV scenes load when there is no camera (camera/action.unity3d; free roam's camera in
    /// Action.unity is a copy of it), each Map loaded as ActionMap.Change does (Manager.Scene.LoadBaseScene
    /// with the story list's level name), and each Time of Day set as ActionMap.SetCycleToSunLight does:
    /// SunLightInfo.Set with this camera, then the camera's GlobalFog follows RenderSettings.fog
    /// (UpdateCameraFog). The player's effect settings are left out: CameraEffectorConfig is switched off and
    /// GlobalFog and SunShafts are on as by default; the request's "disable" turns off the others.
    /// </summary>
    internal sealed class GameHost : IHost
    {
        private const string CameraBundle = "camera/action.unity3d";
        private const string CameraAsset = "ActionCamera";
        private const string TitleScene = "Title";

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
            while (!Singleton<Manager.Scene>.IsInstance() || Singleton<Manager.Scene>.Instance.LoadSceneName != TitleScene
                   || Singleton<Manager.Scene>.Instance.IsNowLoadingFade)
            {
                yield return new WaitForSecondsRealtime(0.5f);
            }
            yield return new WaitForSecondsRealtime(2f);

            var go = CommonLib.LoadAsset<GameObject>(CameraBundle, CameraAsset, true);
            AssetBundleManager.UnloadAssetBundle(CameraBundle, false);
            if (go == null) throw new Exception("No " + CameraAsset + " in " + CameraBundle);
            UnityEngine.Object.DontDestroyOnLoad(go);
            cam = go.GetComponent<Camera>();
            foreach (var b in go.GetComponentsInChildren<Behaviour>(true))
            {
                string name = b.GetType().Name;
                if (name == "CameraEffectorConfig" || name == "CorrectLightAngle") b.enabled = false;
            }
            // The title screen stays loaded under a base scene: hide it, its cameras and any light it has.
            foreach (var root in SceneManager.GetSceneByName(TitleScene).GetRootGameObjects())
            {
                root.SetActive(false);
            }
        }

        public IEnumerator Load(string bundle)
        {
            level = LevelName(bundle);
            Plugin.Log.LogInfo("Loading " + bundle + " (level " + level + ")");
            yield return plugin.StartCoroutine(Singleton<Manager.Scene>.Instance.LoadBaseSceneCoroutine(new Manager.Scene.Data
            {
                assetBundleName = bundle,
                levelName = level,
                fadeType = Manager.Scene.Data.FadeType.None,
            }));
            yield return new WaitForSecondsRealtime(2f);
        }

        public IEnumerator SetTime(SunLightInfo.Info.Type type)
        {
            var info = Manager.Scene.GetRootComponent<SunLightInfo>(level);
            if (info == null) throw new Exception("The level " + level + " has no SunLightInfo");
            if (!info.Set(type, cam)) throw new Exception("The level " + level + " has no Time of Day " + type);
            var fog = cam.GetComponent<GlobalFog>();
            if (fog != null) fog.enabled = RenderSettings.fog;
            var shafts = cam.GetComponent<SunShafts>();
            if (shafts != null) shafts.enabled = true;
            yield return new WaitForSecondsRealtime(1f);
        }

        public void Hold(bool held)
        {
        }

        public IEnumerator PlaceDefault(Frames frames, Dictionary<string, object> view)
        {
            throw new Exception("View " + view["name"] + ": \"studio_default\" views need Studio");
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
