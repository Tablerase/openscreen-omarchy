"""Export the Prism Glow study at the cursor's scene scale for the Blender importer."""

from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "design/cursors/prism-hand/prism-glow-hand.blend"
OUTPUT = ROOT / "design/cursors/prism-hand/prism-glow-hand.obj"

bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene = bpy.context.scene
source = bpy.data.objects["Prism Glow - Hand"]
export_object = source.copy()
export_object.data = source.data.copy()
scene.collection.objects.link(export_object)

# Keep the same scale and cursor contact offset as the compositor's existing hand model.
export_object.scale = (0.75, 0.75, 0.75)
export_object.location.z = -0.4
export_object.name = "Prism Glow - Hand (cursor scale)"

bpy.ops.object.select_all(action="DESELECT")
export_object.select_set(True)
bpy.context.view_layer.objects.active = export_object
bpy.ops.wm.obj_export(filepath=str(OUTPUT), export_selected_objects=True)
print(f"Exported cursor-scale Prism Glow hand: {OUTPUT}")
