using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityStandardAssets.ImageEffects;

namespace KKMaps.Capture
{
    /// <summary>
    /// Where a KKS capture runs. Only the story game (KoikatsuSunshine.exe): KKS's Studio loads its own
    /// *_studio builds of the Maps, not the story Scene Bundles the Golden Maps are (kks-spike.md, section
    /// 10), so the "studio" Camera Profile waits for a Studio Golden Map.
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

    internal sealed class StudioHost : IHost
    {
        public StudioHost(MonoBehaviour plugin)
        {
            throw new Exception("KKS's Studio loads its own builds of the Maps; capture KKS's Golden Maps with \"camera\": \"game\"");
        }

        public string Profile { get { return "studio"; } }
        public Camera Camera { get { return null; } }
        public IEnumerator Ready() { yield break; }
        public IEnumerator Load(string bundle) { yield break; }
        public IEnumerator SetTime(SunLightInfo.Info.Type type) { yield break; }
        public void Hold(bool held) { }
        public IEnumerator PlaceDefault(Frames frames, Dictionary<string, object> view) { yield break; }
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
            while (Manager.Scene.LoadSceneName != TitleScene || Manager.Scene.IsNowLoadingFade)
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
