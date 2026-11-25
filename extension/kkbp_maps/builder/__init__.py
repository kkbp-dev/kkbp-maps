"""The Builder: turns Map Bundles into a Map Library in Blender.

    from kkbp_maps.builder.plan import plan_library
    plan = plan_library(bundles, NameTables.load("KK"))      # no bpy: every decision, host-tested
    from kkbp_maps.builder.build import build_library      # bpy: makes and saves the files
    build_library(plan, "out/KK Maps")

The plan (plan.py, names.py, shaders.py, catalogs.py, report.py) never imports bpy; blender/ does,
and Blender version checks live in compat/.
"""

from .. import NAME, VERSION  # noqa: F401  (one version for the whole extension)
