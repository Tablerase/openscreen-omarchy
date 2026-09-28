"""Standalone Prism Glow hand, reconstructed from 3d-concept.png in Blender.
Run: blender --background --python scripts/model-prism-hand.py
"""
from pathlib import Path
import math
import random
import json
import bpy
import bmesh
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'design/cursors/prism-hand'
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
# Landmarks in the reference image's pixel coordinates, clockwise.
outline = [(659,435),(659,339),(672,323),(694,317),(718,319),(734,332),
 (738,394),(750,393),(766,402),(773,411),(783,408),(799,416),(806,428),
 (816,425),(834,434),(842,444),(841,494),(825,532),(798,572),
 (678,577),(663,569),(630,515),(596,464),(592,425),(613,407),(633,408),(648,422)]
# Deliberately sparse gemstone ridges; no radial fan or automatic decimation.
landmarks = [(675,341),(695,335),(716,340),(704,357),(675,399),(695,407),
 (722,426),(675,446),(700,455),(681,486),(759,508),(711,538),(688,560),
 (744,561),(786,561),(811,502),(792,476),(755,453),(741,409),(754,421),
 (781,427),(781,453),(812,442),(825,464),(612,425),(628,433),(615,458),
 (649,467),(650,496),(670,538)]
n = len(outline)
points = outline + landmarks
uv, edges, faces, *_ = delaunay_2d_cdt([Vector(p) for p in points],
 [(i,(i+1)%n) for i in range(n)], [list(range(n))], 1, 1e-6)
# CDT may reorder vertices. Associate reference landmarks geometrically.
def front_depth(x,y):
 if y < 435 and 655 < x < 740:
  return -.19 - .22 * max(0,1-abs(x-698)/43)
 return -.20 - .28 * max(0,1-((x-716)/130)**2) * max(.3,1-((y-492)/110)**2)
vertices=[]
for p in uv:
 is_boundary = any((p-Vector(q)).length < .001 for q in outline)
 vertices.append(((p.x-717)/100, -.12 if is_boundary else front_depth(p.x,p.y), (577-p.y)/100+.035))
mesh_faces=[tuple(f) for f in faces]
front_count=len(mesh_faces)
boundary_ids=[min(range(len(uv)),key=lambda i:(uv[i]-Vector(p)).length) for p in outline]
# A narrow crown bevel and a deep, faceted pavilion make a solid cut gemstone.
previous=boundary_ids
for depth,shrink in [(.025,1.035),(.28,.97),(.46,.83)]:
 ids=[]
 for x,y in outline:
  ids.append(len(vertices))
  vertices.append(((x-717)/100*shrink,depth,(577-y)/100*shrink+.035+(1-shrink)*1.1))
 for i in range(n):
  j=(i+1)%n
  mesh_faces.extend([(previous[i],previous[j],ids[j]),(previous[i],ids[j],ids[i])])
 previous=ids
# Back follows the same constrained topology, so finger valleys remain intact.
backmap={}
for i,p in enumerate(uv):
 if i in boundary_ids:
  backmap[i]=previous[boundary_ids.index(i)]
 else:
  backmap[i]=len(vertices)
  vertices.append(((p.x-717)/100*.83,.49,(577-p.y)/100*.83+.222))
mesh_faces.extend([tuple(backmap[i] for i in reversed(f)) for f in faces])
mesh=bpy.data.meshes.new('Hand-cut crystal topology')
mesh.from_pydata(vertices,[],mesh_faces)
mesh.update()
obj=bpy.data.objects.new('Prism Glow - Hand',mesh)
scene.collection.objects.link(obj)
bm=bmesh.new(); bm.from_mesh(mesh)
bmesh.ops.recalc_face_normals(bm,faces=bm.faces)
bm.to_mesh(mesh); bm.free()
colors=[('Sapphire',(.008,.035,.62)),('Electric blue',(.008,.17,.95)),
 ('Cyan',(.005,.7,.95)),('Ice',(.18,.79,1)),('Violet',(.20,.012,.72)),
 ('Amethyst',(.43,.035,.88)),('Deep blue',(.003,.013,.19))]
for name,color in colors:
 mat=bpy.data.materials.new(name); mat.diffuse_color=(*color,1); mat.use_nodes=True
 bs=mat.node_tree.nodes.get('Principled BSDF')
 bs.inputs['Base Color'].default_value=(*color,1)
 bs.inputs['Metallic'].default_value=.0
 bs.inputs['Roughness'].default_value=.025
 bs.inputs['IOR'].default_value=1.65
 bs.inputs['Transmission Weight'].default_value=.82
 bs.inputs['Coat Weight'].default_value=.35
 bs.inputs['Emission Color'].default_value=(*color,1)
 bs.inputs['Emission Strength'].default_value=.18
 mesh.materials.append(mat)
rng=random.Random(28)
for p in mesh.polygons:
 center=sum((mesh.vertices[v].co for v in p.vertices),Vector())/len(p.vertices)
 if center.x<-.35: choices=[0,1,2,3,6]
 elif center.x>.6: choices=[0,1,4,5,6]
 else: choices=[0,1,2,3,4]
 p.material_index=rng.choice(choices)
 p.use_smooth=False
# Reference packed in the file and available in an image editor.
ref=bpy.data.images.load(str(ROOT/'design/cursors/3d-concept.png')); ref.use_fake_user=True; ref.pack()
obj['reference']='3d-concept.png: Prism Glow hand, second row'
obj['design']='Closed faceted gemstone; manually traced silhouette and crown landmarks'
mesh.calc_loop_triangles()
report={'vertices':len(mesh.vertices),'triangles':len(mesh.loop_triangles)}
bm=bmesh.new();bm.from_mesh(mesh)
report['non_manifold_edges']=sum(not e.is_manifold for e in bm.edges);bm.free()
(OUT/'mesh-info.json').write_text(json.dumps(report,indent=2))
print('MESH_REPORT',report)

def aim(ob,point): ob.rotation_euler=(Vector(point)-ob.location).to_track_quat('-Z','Y').to_euler()
def area(name,loc,power,color,size,target=(0,0,1.3)):
 data=bpy.data.lights.new(name,'AREA');data.energy=power;data.color=color;data.shape='DISK';data.size=size
 light=bpy.data.objects.new(name,data);scene.collection.objects.link(light);light.location=loc;aim(light,target)
area('Large white softbox',(-3,-4,6),650,(.8,.9,1),4)
area('Cyan edge',(-3,1,2.5),500,(.08,.7,1),2)
area('Violet rim',(3,1,3.5),700,(.48,.12,1),2)
area('Front strip',(2,-4,1),100,(.7,.87,1),.65)
area('Cyan foot',(-.5,-.15,.15),35,(.01,.8,1),.3,target=(0,0,1))
area('Broad transmitted light',(0,3,3),700,(.25,.65,1),3)
area('Top glint',(0,0,5),350,(1,1,1),1)
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,0))
floor=bpy.context.object;floor.name='Studio floor (render only)'
mat=bpy.data.materials.new('Charcoal studio');mat.use_nodes=True
bs=mat.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(.018,.024,.038,1);bs.inputs['Roughness'].default_value=.28
floor.data.materials.append(mat)
world=bpy.data.worlds.new('Studio');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.16,.2,.3,1);world.node_tree.nodes['Background'].inputs[1].default_value=.35;scene.world=world
bpy.ops.object.camera_add(location=(0,-9,3.0));cam=bpy.context.object;aim(cam,(0,0,1.36));cam.data.type='ORTHO';cam.data.ortho_scale=3.55;scene.camera=cam
scene.render.engine='CYCLES';scene.cycles.samples=128;scene.cycles.use_denoising=True
scene.cycles.max_bounces=12;scene.cycles.transmission_bounces=8
scene.render.resolution_x=1000;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
scene.view_settings.view_transform='Standard'
scene.view_settings.look='None'
scene.view_settings.exposure=-.8
# Open directly on the selected hand in material preview.
bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
for screen in bpy.data.screens:
 for a in screen.areas:
  if a.type=='VIEW_3D':
   a.spaces.active.region_3d.view_distance=5.5
   a.spaces.active.region_3d.view_location=(0,0,1.3)
   a.spaces.active.region_3d.view_rotation=cam.rotation_euler.to_quaternion()
   a.spaces.active.shading.type='MATERIAL'
floor.hide_set(True)
for ob in scene.objects:
 if ob.type in {'LIGHT','CAMERA'}: ob.hide_set(True)
scene.render.filepath=str(OUT/'prism-hand-render.png')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'prism-glow-hand.blend'))
bpy.ops.render.render(write_still=True)
# Export only the editable hand, with its materials.
export_obj = obj.copy()
export_obj.data = obj.data.copy()
scene.collection.objects.link(export_obj)
export_obj.scale = (0.75, 0.75, 0.75)
export_obj.location.z = -0.4
export_obj.name = 'Prism Glow - Hand (cursor scale)'
bpy.ops.object.select_all(action='DESELECT')
export_obj.select_set(True)
bpy.context.view_layer.objects.active = export_obj
bpy.ops.wm.obj_export(filepath=str(OUT/'prism-glow-hand.obj'),export_selected_objects=True)
