using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;

namespace KKMaps.Capture
{
    /// <summary>
    /// The raw settings behind a Camera Profile (ADR 0010): every component on the game camera with its
    /// public and serialized fields, the camera itself, QualitySettings, RenderSettings and the sun.
    /// tools/camera_profile.py reads the few numbers the Builder uses from it.
    /// </summary>
    internal static class Dump
    {
        public static Dictionary<string, object> Camera(Camera cam)
        {
            var components = new List<object>();
            foreach (var c in cam.GetComponents<Component>())
            {
                var entry = new Dictionary<string, object> { { "type", c.GetType().FullName } };
                var b = c as Behaviour;
                if (b != null) entry["enabled"] = b.enabled;
                if (!(c is Transform) && !(c is UnityEngine.Camera)) entry["fields"] = Fields(c);
                components.Add(entry);
            }
            var sun = RenderSettings.sun;
            return new Dictionary<string, object>
            {
                { "unity", Application.unityVersion },
                { "camera", new Dictionary<string, object>
                    {
                        { "fov", cam.fieldOfView }, { "near", cam.nearClipPlane }, { "far", cam.farClipPlane },
                        { "hdr", cam.allowHDR }, { "msaa", cam.allowMSAA }, { "rendering_path", cam.actualRenderingPath.ToString() },
                        { "clear_flags", cam.clearFlags.ToString() }, { "culling_mask", (double)cam.cullingMask },
                    } },
                { "components", components },
                { "quality", new Dictionary<string, object>
                    {
                        { "level", QualitySettings.names[QualitySettings.GetQualityLevel()] },
                        { "color_space", QualitySettings.activeColorSpace.ToString() },
                        { "shadows", QualitySettings.shadows.ToString() },
                        { "shadow_resolution", QualitySettings.shadowResolution.ToString() },
                        { "shadow_distance", QualitySettings.shadowDistance },
                        { "shadow_cascades", QualitySettings.shadowCascades },
                        { "shadow_projection", QualitySettings.shadowProjection.ToString() },
                        { "anisotropic", QualitySettings.anisotropicFiltering.ToString() },
                        { "msaa", QualitySettings.antiAliasing },
                        { "pixel_lights", QualitySettings.pixelLightCount },
                    } },
                { "render_settings", new Dictionary<string, object>
                    {
                        { "fog", RenderSettings.fog }, { "fog_mode", RenderSettings.fogMode.ToString() },
                        { "fog_color", Value(RenderSettings.fogColor) },
                        { "fog_start", RenderSettings.fogStartDistance }, { "fog_end", RenderSettings.fogEndDistance },
                        { "fog_density", RenderSettings.fogDensity },
                        { "ambient_mode", RenderSettings.ambientMode.ToString() },
                        { "ambient_intensity", RenderSettings.ambientIntensity },
                        { "reflection_intensity", RenderSettings.reflectionIntensity },
                    } },
                { "sun", sun == null ? null : new Dictionary<string, object>
                    {
                        { "color", Value(sun.color) }, { "intensity", sun.intensity },
                        { "shadows", sun.shadows.ToString() }, { "shadow_strength", sun.shadowStrength },
                        { "shadow_bias", sun.shadowBias }, { "shadow_normal_bias", sun.shadowNormalBias },
                        { "rotation", Value(sun.transform.eulerAngles) },
                    } },
            };
        }

        private static Dictionary<string, object> Fields(Component c)
        {
            var fields = new Dictionary<string, object>();
            for (Type t = c.GetType(); t != null && t != typeof(MonoBehaviour); t = t.BaseType)
            {
                foreach (var f in t.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly))
                {
                    if (!f.IsPublic && f.GetCustomAttributes(typeof(SerializeField), true).Length == 0) continue;
                    if (fields.ContainsKey(f.Name)) continue;
                    try
                    {
                        fields[f.Name] = Value(f.GetValue(c));
                    }
                    catch (Exception e)
                    {
                        fields[f.Name] = "<" + e.GetType().Name + ">";
                    }
                }
            }
            return fields;
        }

        private static object Value(object v)
        {
            if (v == null) return null;
            if (v is bool || v is string) return v;
            if (v is float || v is double || v is int || v is long || v is short || v is byte || v is uint)
                return Convert.ToDouble(v);
            if (v is Enum) return v.ToString();
            if (v is Color) { var c = (Color)v; return new List<object> { (double)c.r, (double)c.g, (double)c.b, (double)c.a }; }
            if (v is Vector3) { var p = (Vector3)v; return new List<object> { (double)p.x, (double)p.y, (double)p.z }; }
            if (v is Vector4) { var p = (Vector4)v; return new List<object> { (double)p.x, (double)p.y, (double)p.z, (double)p.w }; }
            if (v is Vector2) { var p = (Vector2)v; return new List<object> { (double)p.x, (double)p.y }; }
            if (v is UnityEngine.Object)
            {
                var o = (UnityEngine.Object)v;
                return o == null ? null : "<" + o.GetType().Name + " " + o.name + ">";
            }
            if (v is AnimationCurve)
            {
                var keys = new List<object>();
                foreach (var k in ((AnimationCurve)v).keys) keys.Add(new List<object> { (double)k.time, (double)k.value });
                return keys;
            }
            return "<" + v.GetType().Name + ">";
        }
    }
}
