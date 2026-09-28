# Prism Glow — standalone hand study

Open `prism-glow-hand.blend`. The selected object is the complete, editable hand.
This study reconstructs only the Prism Glow hand from the second row of
`../3d-concept.png`. Its silhouette and principal crown vertices were placed
from reference-image landmarks. The hand has a crown, a narrow girdle and a
faceted back; it is a closed volume, not an image on a plane. The cursor-scale
OBJ from this file feeds both the 2D sprite render and the 3D SDF bake in the app.

- 168 vertices / 332 triangles; zero non-manifold edges.
- Flat polygon normals retain the cut-crystal facets.
- Seven tinted transmissive materials with a small emission contribution, lit by a Cycles studio setup. The reference PNG is packed into the Blender file.
- `prism-hand-render.png`: actual Blender render.
- `prism-glow-hand-runtime.png`: frame rendered by the Windows D3D11 compositor,
  with the mesh's shadow on a synthetic screen.
- `prism-glow-hand.obj` + `.mtl`: mesh interchange export at the app's cursor
  scale. OBJ does not preserve Blender's transmission shader; the app bakes the
  face colors into its material atlas.
- `mesh-info.json`: topology statistics from the generated mesh.

Rebuild from the repository root:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --python scripts/model-prism-hand.py
```

To update the application's Blender scene and bake both cursor modes, first
generate the editable theme scenes, then run:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --python scripts/model-original-cursors.py
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --python scripts/export-prism-hand-cursor.py
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' design/cursors/original-cursor-models.blend --background --python scripts/model-original-cursors.py -- --import-mesh design/cursors/prism-hand/prism-glow-hand.obj --theme prism-glow --state pointer
node scripts/generate-original-cursor-themes.mjs
```

The 2D sprite is rendered in Blender's cursor scene. The 3D mode uses the
resulting 64 x 64 x 48 SDF and color atlases; the app does not use Cycles
refraction at runtime.
