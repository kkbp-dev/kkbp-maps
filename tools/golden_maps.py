"""The Golden Maps of each Game: the fixed Maps the tests extract, build and compare (ADR 0006, 0007).

One list for every tool (golden.py, build_golden.py, look.py, capture.py, product_check.py), in key order.
"""

GOLDEN = {
    "KK": ["map/scene/1f", "map/scene/ground", "map/scene/park"],
    # hoteloutside: outdoors, SpeedTree, a SkyStudio sky, point and spot lights, realtime probes;
    # minsyukulobby: an interior with batching, flat ambient, a custom reflection, mixed lights;
    # aquariuminside: one Time of Day, the most batching, a blended Grade (kks-spike.md);
    # minsyukulobby_studio: the Studio Map, Studio's own build of minsyukulobby with its 28
    # SetRenderQueue_Custom (its geometry differs from the story Map's, so it is a Map of its own, D22).
    "KKS": ["map/scene/aquariuminside", "map/scene/hoteloutside", "map/scene/minsyukulobby",
            "studio/map/minsyukulobby_studio"],
}
GAME_FOLDERS = {"KK": "Koikatsu", "KKS": "Koikatsu Sunshine", "SVS": "Summer Vacation Scramble"}
