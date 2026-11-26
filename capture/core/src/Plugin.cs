using BepInEx;
using BepInEx.Logging;

namespace KKMaps.Capture
{
    /// <summary>
    /// The developer-only capture plugin (ADR 0006, 0010). It does nothing unless a request file is
    /// there when the game starts; then it runs the request, writes the result and quits the game.
    /// </summary>
    [BepInPlugin(Guid, "kkbp-maps capture", "0.1.0")]
    public sealed class Plugin : BaseUnityPlugin
    {
        public const string Guid = "kkbp-maps.capture";
        internal static ManualLogSource Log;

        private void Awake()
        {
            Log = Logger;
            if (Request.Pending)
            {
                StartCoroutine(new Request(this).Run());
            }
        }
    }
}
