using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace KKMaps.Capture
{
    /// <summary>
    /// Renders the game camera into textures of a fixed size and writes them. The camera's effects named
    /// in "disable" are off for every frame (the look check matches fog, the Grade and the sun shafts only).
    /// Two files per view: the Reference Capture as the game shows it (PNG, sRGB), and the same frame
    /// before AmplifyColor (EXR, linear half floats, as the HDR camera renders; 32-bit floats crashed park under DXVK), so lighting can be told apart from grading.
    /// </summary>
    internal sealed class Frames
    {
        private readonly Camera cam;
        private readonly int width;
        private readonly int height;
        private readonly HashSet<string> disable;
        private readonly List<string> warnings = new List<string>();

        public Frames(Camera cam, int width, int height, HashSet<string> disable)
        {
            this.cam = cam;
            this.width = width;
            this.height = height;
            this.disable = disable;
        }

        /// <summary>How far ahead of the last placed camera its target was.</summary>
        public float Distance { get; private set; }

        public void Place(Vector3 position, Vector3 target, float fov)
        {
            Distance = Mathf.Max((target - position).magnitude, 0.01f);
            cam.transform.position = position;
            cam.transform.LookAt(target, Vector3.up);
            cam.fieldOfView = fov;
        }

        public List<string> Capture(string stem)
        {
            var written = new List<string>();
            var restore = new List<Behaviour>();
            Behaviour grade = null;
            foreach (var c in cam.GetComponents<Behaviour>())
            {
                string name = c.GetType().Name;
                if (name == "AmplifyColorEffect") grade = c;
                if (disable.Contains(name) && c.enabled)
                {
                    c.enabled = false;
                    restore.Add(c);
                }
            }
            if (grade == null || !grade.enabled)
            {
                warnings.Add(stem + ": the camera has no enabled AmplifyColorEffect");
            }

            string png = stem + ".png";
            Save(png, Render(RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB, TextureFormat.RGB24), false);
            written.Add(png);

            if (grade != null && grade.enabled)
            {
                grade.enabled = false;
                restore.Add(grade);
            }
            string exr = stem + ".pregrade.exr";
            Save(exr, Render(RenderTextureFormat.ARGBHalf, RenderTextureReadWrite.Linear, TextureFormat.RGBAHalf), true);
            written.Add(exr);

            foreach (var c in restore) c.enabled = true;
            return written;
        }

        private static void Save(string path, Texture2D tex, bool exr)
        {
            try
            {
                File.WriteAllBytes(path, exr ? tex.EncodeToEXR() : tex.EncodeToPNG());
            }
            finally
            {
                Object.Destroy(tex);
            }
        }

        private Texture2D Render(RenderTextureFormat format, RenderTextureReadWrite space, TextureFormat read)
        {
            var rt = RenderTexture.GetTemporary(width, height, 24, format, space, 1);
            var previous = RenderTexture.active;
            var target = cam.targetTexture;
            var aspect = cam.aspect;
            cam.targetTexture = rt;
            cam.aspect = (float)width / height;
            cam.Render();
            RenderTexture.active = rt;
            var tex = new Texture2D(width, height, read, false, space == RenderTextureReadWrite.Linear);
            tex.ReadPixels(new Rect(0, 0, width, height), 0, 0, false);
            tex.Apply(false);
            RenderTexture.active = previous;
            cam.targetTexture = target;
            cam.aspect = aspect;
            RenderTexture.ReleaseTemporary(rt);
            return tex;
        }

        public List<string> TakeWarnings()
        {
            var w = new List<string>(warnings);
            warnings.Clear();
            return w;
        }
    }
}
