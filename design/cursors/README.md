# Original OpenScreen cursor themes

These five themes replace the removed Sweezy packs. Their arrow and hand are
editable Blender meshes in `original-cursor-models.blend`; the rendered PNGs in
each theme directory are the high-resolution masters. There is no SVG conversion
step.

| Theme | Intent |
| --- | --- |
| Studio Ink | Quiet, high-contrast choice for product demos |
| Prism Glow | Vivid color without losing the cursor silhouette |
| Pop Coral | Warm, playful choice for casual recordings |
| Pixel Candy | A small retro option for people who liked pixel packs |
| Star Sprout | An original tiny character for people who liked mascot packs |

Each `source.png` contains an arrow on the left and a hand on the right. Run
`blender --background --python scripts/model-original-cursors.py` to rebuild the
editable scenes, transparent masters, projected hotspots, and low-resolution
SDF/color volumes. The volume atlases are baked from evaluated Blender meshes;
the compositor samples them in its existing raymarcher, so the same cursor pose,
lighting, and shadows apply on Windows, macOS, and Linux. Each model stays under
2,000 triangles before baking.

The cursor has two separate render modes. The 2D option and theme picker use the
transparent PNGs. The 3D option uses the mesh-derived SDF and material atlases;
other cursor states continue to use the shared extrusion of their PNG.

To replace a model with a mesh, import an `.obj`, `.stl`, or `.ply` in Blender and
run the bake command against the saved scene:

```powershell
blender design/cursors/original-cursor-models.blend --background `
  --python scripts/model-original-cursors.py -- `
  --import-mesh C:/models/my-cursor.obj --theme studio-ink --state arrow
```

The imported mesh is placed relative to the model root and uses its Blender
materials for the 3D mode. Keep the mesh around the existing cursor origin:
`+Z` points up, `-Y` faces the camera, and the root's `hotspot_local` property is
the point that must remain under the OS cursor. This command saves the updated
`.blend` and rewrites that model's SDF/color atlases. To rebake geometry edited
directly in the `.blend`, run `blender design/cursors/original-cursor-models.blend
--background --python scripts/model-original-cursors.py -- --bake-current`.

Then run `node scripts/generate-original-cursor-themes.mjs` to crop, remove
low-alpha fringe pixels, and resize the transparent 2D sprites to 128 × 128 under
`public/cursors/<theme>/`. It also copies the SDF/color volumes and JSON metadata
for the 3D mode. The generator prints normalized 2D hotspot values; copy those
into `src/lib/cursor/cursorThemes.ts` after changing a rendered sprite.

`contact-sheet.png` shows the sprites enlarged on a light background;
`dark-32px.png` shows them at their 32-pixel reference size on a dark background.
The 3D modeling direction and concept image are in `3d-direction.md` and
`3d-concept.png`.
The consolidated acceptance list is in `requirements.md`.
