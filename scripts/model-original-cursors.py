"""Model and render OpenScreen's original cursor themes in Blender.

From the repository root:
    blender --background --python scripts/model-original-cursors.py

The editable .blend has a scene per theme. Each scene contains a 3D arrow and hand,
and renders a transparent 1774 x 887 source.png plus projected hotspot coordinates.
"""

import argparse
import json
import math
import os
import struct
import sys
import zlib

import bpy
import bmesh
from bpy_extras.object_utils import world_to_camera_view
from mathutils.bvhtree import BVHTree
from mathutils import Vector


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CURSOR_DIR = os.path.join(ROOT, "design", "cursors")
BLEND_PATH = os.path.join(CURSOR_DIR, "original-cursor-models.blend")
RENDER_WIDTH = 1774
RENDER_HEIGHT = 887
CAMERA_WIDTH = 7.6
VOLUME_XY = 64
VOLUME_Z = 48
VOLUME_TILES_X = 8
VOLUME_TILES_Y = 6
VOLUME_SDF_RANGE = 0.14

ARROW = [
	(-0.78, 1.24),
	(0.65, -0.03),
	(0.02, -0.05),
	(0.29, -0.66),
	(-0.03, -0.80),
	(-0.33, -0.18),
	(-0.72, -0.54),
]

HAND = [
	(-0.43, -0.23), (-0.52, 0.00), (-0.67, 0.34), (-0.65, 0.50),
	(-0.55, 0.61), (-0.43, 0.61), (-0.15, 0.34), (-0.13, 0.37),
	(-0.13, 1.28), (-0.09, 1.43), (0.02, 1.50), (0.14, 1.47),
	(0.20, 1.38), (0.21, 0.60), (0.30, 0.82), (0.40, 0.88),
	(0.50, 0.83), (0.53, 0.73), (0.48, 0.48), (0.59, 0.68),
	(0.69, 0.73), (0.79, 0.68), (0.82, 0.56), (0.76, 0.31),
	(0.87, 0.48), (0.97, 0.49), (1.06, 0.41), (1.04, 0.29),
	(0.95, -0.04), (0.79, -0.28), (0.61, -0.37), (-0.17, -0.37),
]


def ccw(points):
	area = sum(
		points[i][0] * points[(i + 1) % len(points)][1]
		- points[(i + 1) % len(points)][0] * points[i][1]
		for i in range(len(points))
	)
	return points if area > 0 else list(reversed(points))


def material(name, color, roughness=0.32, metallic=0.0, coat=0.0):
	mat = bpy.data.materials.new(name)
	mat.diffuse_color = (*color, 1.0)
	mat.use_nodes = True
	shader = mat.node_tree.nodes.get("Principled BSDF")
	shader.inputs["Base Color"].default_value = (*color, 1.0)
	shader.inputs["Roughness"].default_value = roughness
	shader.inputs["Metallic"].default_value = metallic
	if "Coat Weight" in shader.inputs:
		shader.inputs["Coat Weight"].default_value = coat
	if "Coat Roughness" in shader.inputs:
		shader.inputs["Coat Roughness"].default_value = 0.2
	return mat


def finish_mesh(name, vertices, faces, materials, material_ids=None, bevel=0.0, segments=3):
	mesh = bpy.data.meshes.new(name + " Mesh")
	mesh.from_pydata(vertices, [], faces)
	for mat in materials:
		mesh.materials.append(mat)
	mesh.update()
	if material_ids:
		for index, polygon in enumerate(mesh.polygons):
			polygon.material_index = material_ids[index]
	bm = bmesh.new()
	bm.from_mesh(mesh)
	bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
	bm.to_mesh(mesh)
	bm.free()
	mesh.update()
	obj = bpy.data.objects.new(name, mesh)
	bpy.context.scene.collection.objects.link(obj)
	if bevel > 0:
		modifier = obj.modifiers.new("Soft machined edges", "BEVEL")
		modifier.width = bevel
		modifier.segments = segments
		modifier.limit_method = "ANGLE"
		modifier.angle_limit = math.radians(28)
		modifier.harden_normals = True
		obj.modifiers.new("Weighted face normals", "WEIGHTED_NORMAL")
	return obj


def extruded_polygon(name, points, depth, materials, bevel=0.0, facet_ids=None, dome=0.0):
	points = ccw(points)
	count = len(points)
	front_y, back_y = -depth / 2, depth / 2
	vertices = [(x, front_y, z) for x, z in points]
	vertices.extend((x, back_y, z) for x, z in points)
	faces, material_ids = [], []
	if facet_ids is None:
		if dome > 0:
			cx = sum(x for x, _ in points) / count
			cz = sum(z for _, z in points) / count
			for factor, height in [(0.72, dome * 0.72), (0.4, dome * 0.94)]:
				ring_start = len(vertices)
				vertices.extend((cx + (x - cx) * factor, front_y - height, cz + (z - cz) * factor) for x, z in points)
				for index in range(count):
					next_index = (index + 1) % count
					faces.append((index, next_index, ring_start + next_index, ring_start + index))
					material_ids.append(0)
				inner_start = ring_start
			center = (cx, front_y - dome, cz)
			center_index = len(vertices)
			vertices.append(center)
			for index in range(count):
				next_index = (index + 1) % count
				faces.append((inner_start + index, inner_start + next_index, center_index))
				material_ids.append(0)
		else:
			faces.append(tuple(range(count)))
			material_ids.append(0)
		faces.append(tuple(reversed(range(count, count * 2))))
		material_ids.append(min(1, len(materials) - 1))
	else:
		center = (sum(x for x, _ in points) / count, front_y, sum(z for _, z in points) / count)
		center_index = len(vertices)
		vertices.append(center)
		back_center_index = len(vertices)
		vertices.append((center[0], back_y, center[2]))
		for index in range(count):
			next_index = (index + 1) % count
			faces.append((center_index, index, next_index))
			material_ids.append(facet_ids[index % len(facet_ids)])
			faces.append((back_center_index, count + next_index, count + index))
			material_ids.append(min(1, len(materials) - 1))
	for index in range(count):
		next_index = (index + 1) % count
		faces.append((index, next_index, count + next_index, count + index))
		material_ids.append(min(1, len(materials) - 1))
	return finish_mesh(name, vertices, faces, materials, material_ids, bevel, 2)


def curve_line(name, points, mat, depth=0.018, y=-0.13, location_x=0.0):
	curve = bpy.data.curves.new(name + " Curve", "CURVE")
	curve.dimensions = "3D"
	curve.resolution_u = 1
	curve.bevel_depth = depth
	curve.bevel_resolution = 3
	spline = curve.splines.new("POLY")
	spline.points.add(len(points) - 1)
	for item, (x, z) in zip(spline.points, points):
		item.co = (x, y, z, 1)
	spline.use_cyclic_u = True
	obj = bpy.data.objects.new(name, curve)
	bpy.context.scene.collection.objects.link(obj)
	obj.location.x = location_x
	obj.data.materials.append(mat)
	return obj


def rounded_box(name, location, scale, mat, bevel=0.07):
	bpy.ops.mesh.primitive_cube_add(size=1, location=location)
	obj = bpy.context.object
	obj.name = name
	obj.dimensions = scale
	bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
	obj.data.materials.append(mat)
	modifier = obj.modifiers.new("Rounded molded edges", "BEVEL")
	modifier.width = bevel
	modifier.segments = 3
	modifier.limit_method = "ANGLE"
	obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
	return obj


def sphere(name, location, scale, mat):
	bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, location=location)
	obj = bpy.context.object
	obj.name = name
	obj.scale = scale
	obj.data.materials.append(mat)
	for face in obj.data.polygons:
		face.use_smooth = True
	return obj


def star_points(cx, cz, outer, inner, count=5, rotation=math.pi / 2):
	points = []
	for index in range(count * 2):
		radius = outer if index % 2 == 0 else inner
		angle = rotation + math.pi * index / count
		points.append((cx + math.cos(angle) * radius, cz + math.sin(angle) * radius))
	return ccw(points)


def inside_polygon(x, z, points):
	inside = False
	previous = len(points) - 1
	for current in range(len(points)):
		x1, z1 = points[current]
		x2, z2 = points[previous]
		if (z1 > z) != (z2 > z) and x < (x2 - x1) * (z - z1) / (z2 - z1) + x1:
			inside = not inside
		previous = current
	return inside


def voxel_volume(name, points, front_materials, side_material, cell_count=14, backing=True):
	points = ccw(points)
	xmin, xmax = min(x for x, _ in points), max(x for x, _ in points)
	zmin, zmax = min(z for _, z in points), max(z for _, z in points)
	cell = max(xmax - xmin, zmax - zmin) / cell_count
	columns, rows = math.ceil((xmax - xmin) / cell), math.ceil((zmax - zmin) / cell)
	occupied = {
		(column, row)
		for row in range(rows)
		for column in range(columns)
		if inside_polygon(xmin + (column + 0.5) * cell, zmin + (row + 0.5) * cell, points)
	}
	depth = cell * 0.72
	vertices, vertex_index, faces, mat_ids = [], {}, [], []

	def vertex(x, y, z):
		key = (round(x, 6), round(y, 6), round(z, 6))
		if key not in vertex_index:
			vertex_index[key] = len(vertices)
			vertices.append(key)
		return vertex_index[key]

	front_y, back_y = -depth / 2, depth / 2
	for column, row in sorted(occupied):
		x0, x1 = xmin + column * cell, xmin + (column + 1) * cell
		z0, z1 = zmin + row * cell, zmin + (row + 1) * cell
		faces.append((
			vertex(x0, front_y, z0), vertex(x1, front_y, z0),
			vertex(x1, front_y, z1), vertex(x0, front_y, z1),
		))
		mat_ids.append((column * 3 + row) % len(front_materials))
		faces.append((
			vertex(x0, back_y, z0), vertex(x0, back_y, z1),
			vertex(x1, back_y, z1), vertex(x1, back_y, z0),
		))
		mat_ids.append(len(front_materials))
		neighbors = [
			((0, -1), [(x0, front_y, z0), (x0, back_y, z0), (x1, back_y, z0), (x1, front_y, z0)]),
			((1, 0), [(x1, front_y, z0), (x1, back_y, z0), (x1, back_y, z1), (x1, front_y, z1)]),
			((0, 1), [(x1, front_y, z1), (x1, back_y, z1), (x0, back_y, z1), (x0, front_y, z1)]),
			((-1, 0), [(x0, front_y, z1), (x0, back_y, z1), (x0, back_y, z0), (x0, front_y, z0)]),
		]
		for (dx, dz), corners in neighbors:
			if (column + dx, row + dz) not in occupied:
				faces.append(tuple(vertex(*point) for point in corners))
				mat_ids.append(len(front_materials))
	obj = finish_mesh(name, vertices, faces, list(front_materials) + [side_material], mat_ids)
	obj["voxel_count"] = len(occupied)
	if backing and len(front_materials) > 1:
		cx = sum(x for x, _ in points) / len(points)
		cz = sum(z for _, z in points) / len(points)
		expanded = [(cx + (x - cx) * 1.09, cz + (z - cz) * 1.09) for x, z in points]
		back = voxel_volume(name + " | grape back layer", expanded, [side_material], side_material, cell_count, False)
		back.parent = obj
		back.location = (cell * 0.45, depth, -cell * 0.3)
	return obj


def make_palette(theme):
	if theme == "studio-ink":
		return {
			"body": material("Studio Ink | graphite ceramic", (0.018, 0.023, 0.032), 0.27, 0.12, 0.28),
			"side": material("Studio Ink | shadow graphite", (0.006, 0.008, 0.014), 0.24, 0.1, 0.3),
			"accent": material("Studio Ink | warm ivory piping", (0.98, 0.88, 0.68), 0.24, 0.03, 0.22),
			"cuff": material("Studio Ink | cuff", (0.045, 0.052, 0.07), 0.31, 0.05, 0.12),
		}
	if theme == "prism-glow":
		colors = [
			(0.015, 0.83, 0.98), (0.07, 0.28, 0.98), (0.28, 0.07, 0.85),
			(0.08, 0.55, 0.93), (0.55, 0.16, 0.98), (0.02, 0.68, 0.77),
		]
		return {"facets": [material(f"Prism | facet {i + 1}", c, 0.16, 0.36, 0.55) for i, c in enumerate(colors)]}
	if theme == "pop-coral":
		return {
			"body": material("Pop Coral | tangerine rubber", (0.98, 0.12, 0.085), 0.37, 0.0, 0.12),
			"side": material("Pop Coral | deep coral side", (0.72, 0.055, 0.05), 0.34, 0.0, 0.1),
			"hand": material("Pop Coral | golden rubber", (1.0, 0.54, 0.025), 0.36, 0.0, 0.14),
		}
	if theme == "pixel-candy":
		return {
			"front": [
				material("Pixel Candy | strawberry", (0.98, 0.19, 0.48), 0.25, 0.05, 0.3),
				material("Pixel Candy | sugar pink", (1.0, 0.35, 0.63), 0.25, 0.03, 0.32),
				material("Pixel Candy | rose", (0.86, 0.11, 0.40), 0.27, 0.05, 0.25),
			],
			"side": material("Pixel Candy | grape voxel sides", (0.25, 0.055, 0.52), 0.24, 0.08, 0.34),
		}
	return {
		"body": material("Star Sprout | mint ceramic", (0.18, 0.80, 0.56), 0.24, 0.0, 0.4),
		"side": material("Star Sprout | deep mint edge", (0.055, 0.40, 0.31), 0.26, 0.0, 0.32),
		"accent": material("Star Sprout | marigold star", (1.0, 0.56, 0.035), 0.24, 0.0, 0.35),
		"accent_side": material("Star Sprout | golden edge", (0.72, 0.29, 0.015), 0.26, 0.0, 0.26),
		"leaf": material("Star Sprout | fresh leaf", (0.08, 0.62, 0.35), 0.25, 0.0, 0.3),
		"eye": material("Star Sprout | ink eyes", (0.06, 0.07, 0.09), 0.3),
		"cuff": material("Star Sprout | mint cuff", (0.13, 0.63, 0.43), 0.3, 0.0, 0.25),
	}


def make_arrow(theme, center_x, mats):
	if theme == "studio-ink":
		obj = extruded_polygon("Studio Ink Arrow", ARROW, 0.19, [mats["body"], mats["side"]], bevel=0.035, dome=0.025)
		cx = sum(x for x, _ in ARROW) / len(ARROW)
		cz = sum(z for _, z in ARROW) / len(ARROW)
		inset = [(cx + (x - cx) * 0.78, cz + (z - cz) * 0.78) for x, z in ARROW]
		pipe = curve_line("Ivory inset piping", inset, mats["accent"], depth=0.024, y=-0.125, location_x=center_x)
	elif theme == "prism-glow":
		palette = mats["facets"]
		obj = extruded_polygon("Prism Arrow Crystal", ARROW, 0.25, palette, bevel=0.01, facet_ids=[0, 1, 4, 2, 3, 0, 5])
	elif theme == "pop-coral":
		obj = extruded_polygon("Pop Coral Rubber Arrow", ARROW, 0.24, [mats["body"], mats["side"]], bevel=0.10, dome=0.08)
	elif theme == "pixel-candy":
		obj = voxel_volume("Pixel Candy Arrow Voxels", ARROW, mats["front"], mats["side"])
	else:
		obj = extruded_polygon("Star Sprout Ceramic Arrow", ARROW, 0.22, [mats["body"], mats["side"]], bevel=0.06, dome=0.045)
		charm = extruded_polygon("Raised star charm", star_points(0.43, -0.30, 0.23, 0.105), 0.075, [mats["accent"], mats["accent_side"]], bevel=0.02)
		charm.location = (center_x, -0.17, 0)
		sphere("Star eye left", (center_x + 0.385, -0.225, -0.295), (0.025, 0.018, 0.032), mats["eye"])
		sphere("Star eye right", (center_x + 0.465, -0.225, -0.295), (0.025, 0.018, 0.032), mats["eye"])
		leaf_a = sphere("Mint leaf left", (center_x + 0.22, -0.18, 0.03), (0.095, 0.035, 0.055), mats["leaf"])
		leaf_a.rotation_euler[1] = math.radians(-28)
		leaf_b = sphere("Mint leaf right", (center_x + 0.58, -0.18, 0.025), (0.095, 0.035, 0.055), mats["leaf"])
		leaf_b.rotation_euler[1] = math.radians(28)
	obj.location.x = center_x
	obj["cursor_state"] = "arrow"
	obj["theme"] = theme
	obj["hotspot_local"] = [ARROW[0][0], ARROW[0][1]]
	return obj


def make_hand(theme, center_x, mats):
	if theme == "studio-ink":
		obj = extruded_polygon("Studio Ink Gloved Hand", HAND, 0.18, [mats["accent"], mats["side"]], bevel=0.038, dome=0.10)
		rounded_box("Studio Ink wrist cuff", (center_x, -0.15, -0.30), (0.77, 0.24, 0.23), mats["cuff"], bevel=0.085)
	elif theme == "prism-glow":
		palette = mats["facets"]
		facets = [3, 1, 0, 4, 2, 5, 1, 0, 3, 4, 2, 5, 1, 3, 0, 4, 2, 5, 1, 0, 3, 4, 2, 5, 1, 0, 4, 2, 3, 5, 1, 0]
		obj = extruded_polygon("Prism Hand Crystal", HAND, 0.24, palette, bevel=0.008, facet_ids=facets)
	elif theme == "pop-coral":
		obj = extruded_polygon("Pop Coral Rubber Hand", HAND, 0.25, [mats["hand"], mats["side"]], bevel=0.105, dome=0.12)
	elif theme == "pixel-candy":
		obj = voxel_volume("Pixel Candy Hand Voxels", HAND, mats["front"], mats["side"])
	else:
		obj = extruded_polygon("Star Sprout Ivory Hand", HAND, 0.19, [mats["accent"], mats["side"]], bevel=0.05, dome=0.09)
		rounded_box("Star Sprout mint cuff", (center_x, -0.15, -0.30), (0.80, 0.24, 0.23), mats["cuff"], bevel=0.08)
		charm = extruded_polygon("Star Sprout cuff charm", star_points(0.32, -0.29, 0.19, 0.085), 0.065, [mats["accent"], mats["accent_side"]], bevel=0.016)
		charm.location = (center_x, -0.30, 0)
		sphere("Cuff star eye left", (center_x + 0.285, -0.345, -0.285), (0.020, 0.014, 0.026), mats["eye"])
		sphere("Cuff star eye right", (center_x + 0.350, -0.345, -0.285), (0.020, 0.014, 0.026), mats["eye"])
		leaf_a = sphere("Cuff leaf left", (center_x + 0.16, -0.26, -0.08), (0.075, 0.032, 0.045), mats["leaf"])
		leaf_a.rotation_euler[1] = math.radians(-28)
		leaf_b = sphere("Cuff leaf right", (center_x + 0.48, -0.26, -0.075), (0.075, 0.032, 0.045), mats["leaf"])
		leaf_b.rotation_euler[1] = math.radians(28)
	obj.location.x = center_x
	obj["cursor_state"] = "pointer"
	obj["theme"] = theme
	obj["hotspot_local"] = [0.02, 1.50]
	return obj


def add_camera_and_lights(scene):
	bpy.context.window.scene = scene
	target = Vector((0.0, 0.0, 0.30))
	camera_data = bpy.data.cameras.new("Cursor studio camera")
	camera_data.type = "ORTHO"
	camera_data.ortho_scale = CAMERA_WIDTH
	camera = bpy.data.objects.new("Camera", camera_data)
	scene.collection.objects.link(camera)
	camera.location = (-2.45, -11.0, 2.15)
	camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
	scene.camera = camera
	world = bpy.data.worlds.new(scene.name + " soft studio")
	world.use_nodes = True
	world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.18, 0.20, 0.24, 1)
	world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.45
	scene.world = world

	def area(name, location, energy, size, color):
		data = bpy.data.lights.new(name, "AREA")
		data.energy, data.shape, data.size, data.color = energy, "DISK", size, color
		light = bpy.data.objects.new(name, data)
		scene.collection.objects.link(light)
		light.location = location
		light.rotation_euler = (target - light.location).to_track_quat("-Z", "Y").to_euler()

	area("Large warm key", (-4.8, -5.5, 6.5), 680, 4.3, (1.0, 0.86, 0.72))
	area("Cool soft fill", (4.6, -4.0, 2.6), 360, 3.4, (0.60, 0.78, 1.0))
	area("Cyan rim", (1.2, 3.0, 4.8), 800, 3.2, (0.46, 0.72, 1.0))
	scene.render.engine = "BLENDER_EEVEE"
	scene.eevee.taa_render_samples = 64
	scene.render.resolution_x, scene.render.resolution_y = RENDER_WIDTH, RENDER_HEIGHT
	scene.render.resolution_percentage = 100
	scene.render.film_transparent = True
	scene.render.image_settings.file_format = "PNG"
	scene.render.image_settings.color_mode = "RGBA"
	scene.render.image_settings.color_depth = "8"
	scene.render.image_settings.compression = 12
	scene.view_settings.view_transform = "AgX"
	try:
		scene.view_settings.look = "AgX - Medium High Contrast"
	except TypeError:
		pass
	return camera


def projected_pixel(scene, camera, center_x, point, y=-0.12):
	world = Vector((center_x + point[0], y, point[1]))
	uv = world_to_camera_view(scene, camera, world)
	return [round(uv.x * RENDER_WIDTH, 2), round((1.0 - uv.y) * RENDER_HEIGHT, 2)]


def evaluated_triangles(objects):
	depsgraph = bpy.context.evaluated_depsgraph_get()
	triangle_count = 0
	for obj in objects:
		if obj.type not in {"MESH", "CURVE"}:
			continue
		mesh = obj.evaluated_get(depsgraph).to_mesh()
		try:
			triangle_count += sum(max(0, len(poly.vertices) - 2) for poly in mesh.polygons)
		finally:
			obj.evaluated_get(depsgraph).to_mesh_clear()
	return triangle_count


def write_png(path, width, height, color_type, pixels):
	"""Write a small 8-bit PNG without adding a Python imaging dependency."""
	channels = 1 if color_type == 0 else 4
	stride = width * channels
	rows = b"".join(b"\0" + pixels[y * stride:(y + 1) * stride] for y in range(height))

	def chunk(kind, data):
		return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

	data = b"\x89PNG\r\n\x1a\n"
	data += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0))
	data += chunk(b"IDAT", zlib.compress(rows, 7))
	data += chunk(b"IEND", b"")
	with open(path, "wb") as file:
		file.write(data)


def linear_to_srgb(value):
	value = max(0.0, min(1.0, value))
	return 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1.0 / 2.4) - 0.055


def model_geometry(scene, root):
	"""Collect evaluated mesh triangles in the compositor's x-right/y-down/z-toward-camera axes."""
	depsgraph = bpy.context.evaluated_depsgraph_get()
	vertices, triangles, face_colors = [], [], []
	for obj in scene.objects:
		if obj == root and root.get("cursor_volume_ignore"):
			continue
		parent = obj.parent
		while parent is not None and parent != root:
			parent = parent.parent
		if obj != root and obj.get("model_root") != root.name and parent != root:
			continue
		evaluated = obj.evaluated_get(depsgraph)
		mesh = evaluated.to_mesh()
		if mesh is None:
			continue
		try:
			mesh.calc_loop_triangles()
			base = len(vertices)
			for vertex in mesh.vertices:
				world = obj.matrix_world @ vertex.co
				vertices.append(Vector((world.x, -world.z, -world.y)))
			materials = [slot.material for slot in evaluated.material_slots]
			for triangle in mesh.loop_triangles:
				triangles.append(tuple(base + index for index in triangle.vertices))
				polygon = mesh.polygons[triangle.polygon_index]
				material_index = polygon.material_index
				mat = materials[material_index] if material_index < len(materials) else None
				color = mat.diffuse_color[:3] if mat else (0.72, 0.76, 0.82)
				face_colors.append(tuple(round(linear_to_srgb(channel) * 255) for channel in color))
		finally:
			evaluated.to_mesh_clear()
	if not triangles:
		raise RuntimeError(f"No mesh triangles found for {root.name}")
	return vertices, triangles, face_colors


def export_model_volume(scene, root, state, output_dir):
	"""Bake one editable Blender mesh into a compact SDF and material-color slice atlas."""
	vertices, triangles, face_colors = model_geometry(scene, root)
	tree = BVHTree.FromPolygons(vertices, triangles, all_triangles=True)
	local_hotspot = root.get("hotspot_local", [0.0, 0.0])
	hotspot_world = root.matrix_world @ Vector((local_hotspot[0], 0.0, local_hotspot[1]))
	hx, hy = hotspot_world.x, -hotspot_world.z
	z_min = min(vertex.z for vertex in vertices)
	z_max = max(vertex.z for vertex in vertices)
	hit = tree.ray_cast(Vector((hx, hy, z_min - 1.0)), Vector((0.0, 0.0, 1.0)), z_max - z_min + 2.0)
	hotspot_z = hit[0].z if hit[0] is not None else 0.12

	def model_point(point):
		return ((point.x - hx), (point.y - hy), (point.z - hotspot_z))

	model_vertices = [model_point(point) for point in vertices]
	x0, x1 = min(p[0] for p in model_vertices), max(p[0] for p in model_vertices)
	y0, y1 = min(p[1] for p in model_vertices), max(p[1] for p in model_vertices)
	z0, z1 = min(p[2] for p in model_vertices), max(p[2] for p in model_vertices)
	raw_extent = max(x1 - x0, y1 - y0)
	if raw_extent <= 1e-6:
		raise RuntimeError(f"Degenerate cursor geometry for {root.name}")
	pad = raw_extent * (2.0 / VOLUME_XY)
	model_scale = raw_extent + 2.0 * pad
	lo = [x0 / model_scale - pad / model_scale, y0 / model_scale - pad / model_scale,
	      z0 / model_scale - pad / model_scale]
	hi = [x1 / model_scale + pad / model_scale, y1 / model_scale + pad / model_scale,
	      z1 / model_scale + pad / model_scale]
	size = [hi[0] - lo[0], hi[1] - lo[1]]
	hotspot = [-lo[0] / size[0], -lo[1] / size[1]]
	thick, max_height = max(0.001, -lo[2]), max(0.001, hi[2])

	atlas_width = VOLUME_XY * VOLUME_TILES_X
	atlas_height = VOLUME_XY * VOLUME_TILES_Y
	sdf_pixels = bytearray(atlas_width * atlas_height)
	color_pixels = bytearray(atlas_width * atlas_height * 4)
	grid_lo = (lo[0], lo[1], lo[2])
	grid_size = (size[0], size[1], hi[2] - lo[2])
	ray_direction = Vector((1.0, 0.000173, 0.000271)).normalized()
	step_eps = model_scale * 1e-5
	progress_stride = max(1, VOLUME_Z // 8)

	for iz in range(VOLUME_Z):
		tile_x, tile_y = iz % VOLUME_TILES_X, iz // VOLUME_TILES_X
		for iy in range(VOLUME_XY):
			y = grid_lo[1] + (iy + 0.5) / VOLUME_XY * grid_size[1]
			for ix in range(VOLUME_XY):
				x = grid_lo[0] + (ix + 0.5) / VOLUME_XY * grid_size[0]
				z = grid_lo[2] + (iz + 0.5) / VOLUME_Z * grid_size[2]
				point_raw = Vector((hx + x * model_scale, hy + y * model_scale,
				                    hotspot_z + z * model_scale))
				nearest = tree.find_nearest(point_raw)
				if nearest[0] is None:
					distance = VOLUME_SDF_RANGE
					color = (0, 0, 0)
				else:
					distance = min(nearest[3] / model_scale, VOLUME_SDF_RANGE)
					color = face_colors[nearest[2]]

				# Count crossings from outside along +X. A tiny skew avoids rays through shared edges.
				ray_y = point_raw.y + (iz % 3 - 1) * step_eps
				ray_z = point_raw.z + (iy % 3 - 1) * step_eps
				ray_origin = Vector((hx + lo[0] * model_scale - model_scale, ray_y, ray_z))
				inside = False
				for _ in range(64):
					ray_hit = tree.ray_cast(ray_origin, ray_direction, 4.0 * model_scale)
					if ray_hit[0] is None or (ray_hit[0] - point_raw).dot(ray_direction) >= -step_eps:
						break
					inside = not inside
					ray_origin = ray_hit[0] + ray_direction * step_eps
				if inside:
					distance = -distance

				encoded = max(0, min(255, round(127.5 + 127.5 * distance / VOLUME_SDF_RANGE)))
				px = tile_x * VOLUME_XY + ix
				py = tile_y * VOLUME_XY + iy
				index = py * atlas_width + px
				sdf_pixels[index] = encoded
				color_index = index * 4
				color_pixels[color_index:color_index + 4] = bytes((*color, 255))
		if iz % progress_stride == 0:
			print(f"[cursor-model] {root.name}: baked SDF slice {iz + 1}/{VOLUME_Z}")

	stem = f"{state}-sdf"
	write_png(os.path.join(output_dir, stem + ".png"), atlas_width, atlas_height, 0, sdf_pixels)
	write_png(os.path.join(output_dir, f"{state}-color.png"), atlas_width, atlas_height, 6, color_pixels)
	metadata = {
		"width": VOLUME_XY,
		"height": VOLUME_XY,
		"depth": VOLUME_Z,
		"tilesX": VOLUME_TILES_X,
		"tilesY": VOLUME_TILES_Y,
		"distanceRange": VOLUME_SDF_RANGE,
		"size": size,
		"hotspot": hotspot,
		"top": 0.0,
		"thick": thick,
		"maxHeight": max_height,
	}
	with open(os.path.join(output_dir, stem + ".json"), "w", encoding="utf-8", newline="\n") as file:
		json.dump(metadata, file, indent=2)
		file.write("\n")
	return metadata


def bake_current_models():
	"""Bake the currently opened .blend after an artist imports or edits cursor meshes."""
	count = 0
	for scene in bpy.data.scenes:
		for root in scene.objects:
			theme, state = root.get("theme"), root.get("cursor_state")
			if theme not in {"studio-ink", "prism-glow", "pop-coral", "pixel-candy", "star-sprout"}:
				continue
			if state not in {"arrow", "pointer"} or "hotspot_local" not in root:
				continue
			output_dir = os.path.join(CURSOR_DIR, theme)
			os.makedirs(output_dir, exist_ok=True)
			metadata = export_model_volume(scene, root, state, output_dir)
			count += 1
			print(
				f"[cursor-model] baked {theme}/{state}: {metadata['width']}x{metadata['height']}x"
				f"{metadata['depth']} SDF"
			)
	if not count:
		raise RuntimeError("No cursor roots with theme, cursor_state and hotspot_local metadata found")


def import_mesh_and_bake(mesh_path, theme, state):
	"""Replace one cursor's generated geometry with an imported OBJ, STL, or PLY mesh."""
	mesh_path = os.path.abspath(mesh_path)
	if not os.path.isfile(mesh_path):
		raise RuntimeError(f"Mesh file does not exist: {mesh_path}")
	scene = next((s for s in bpy.data.scenes if any(
		o.get("theme") == theme and o.get("cursor_state") == state and "hotspot_local" in o
		for o in s.objects
	)), None)
	if scene is None:
		raise RuntimeError(f"No {theme}/{state} cursor root in the opened .blend")
	bpy.context.window.scene = scene
	root = next(
		o for o in scene.objects
		if o.get("theme") == theme and o.get("cursor_state") == state and "hotspot_local" in o
	)
	for obj in list(scene.objects):
		if obj != root and (
			obj.get("model_root") == root.name
			or (obj.parent == root and obj.get("cursor_imported"))
		):
			bpy.data.objects.remove(obj, do_unlink=True)
	root["cursor_volume_ignore"] = True
	root.hide_render = True
	if root.type == "MESH":
		root.data.clear_geometry()
	before = set(scene.objects)
	if mesh_path.lower().endswith(".obj"):
		bpy.ops.wm.obj_import(filepath=mesh_path)
	elif mesh_path.lower().endswith(".stl"):
		bpy.ops.wm.stl_import(filepath=mesh_path)
	elif mesh_path.lower().endswith(".ply"):
		bpy.ops.wm.ply_import(filepath=mesh_path)
	else:
		raise RuntimeError("Supported import formats are .obj, .stl, and .ply")
	imported = [obj for obj in set(scene.objects) - before if obj.type in {"MESH", "CURVE", "SURFACE", "FONT"}]
	if not imported:
		raise RuntimeError(f"The importer found no mesh objects in {mesh_path}")
	for obj in imported:
		world_matrix = root.matrix_world @ obj.matrix_world
		obj.parent = root
		obj.matrix_world = world_matrix
		obj["cursor_imported"] = True
		obj["model_root"] = root.name
		obj["theme"] = theme
		obj["cursor_state"] = state
	output_dir = os.path.join(CURSOR_DIR, theme)
	metadata = export_model_volume(scene, root, state, output_dir)
	bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
	print(
		f"[cursor-model] imported {os.path.basename(mesh_path)} as {theme}/{state}; "
		f"baked {metadata['width']}x{metadata['height']}x{metadata['depth']} SDF"
	)


def build():
	bpy.ops.object.select_all(action="SELECT")
	bpy.ops.object.delete(use_global=False)
	for scene in list(bpy.data.scenes):
		if scene.name != "Scene":
			bpy.data.scenes.remove(scene)
	base_scene = bpy.context.scene
	results = []
	themes = ["studio-ink", "prism-glow", "pop-coral", "pixel-candy", "star-sprout"]
	for theme_index, theme in enumerate(themes):
		if theme_index == 0:
			scene = base_scene
			scene.name = "01 Studio Ink"
		else:
			scene = bpy.data.scenes.new(f"{theme_index + 1:02d} {theme.replace('-', ' ').title()}")
			bpy.context.window.scene = scene
		bpy.ops.object.select_all(action="SELECT")
		bpy.ops.object.delete(use_global=False)
		mats = make_palette(theme)
		arrow_x, hand_x = -1.9, 1.9
		before_arrow = set(scene.objects)
		arrow = make_arrow(theme, arrow_x, mats)
		arrow_parts = set(scene.objects) - before_arrow
		for part in arrow_parts:
			part["model_root"] = arrow.name
			part["theme"] = theme
			part["cursor_state"] = "arrow"
		before_hand = set(scene.objects)
		hand = make_hand(theme, hand_x, mats)
		hand_parts = set(scene.objects) - before_hand
		for part in hand_parts:
			part["model_root"] = hand.name
			part["theme"] = theme
			part["cursor_state"] = "pointer"
		camera = add_camera_and_lights(scene)
		arrow["polygon_budget"] = evaluated_triangles(arrow_parts)
		hand["polygon_budget"] = evaluated_triangles(hand_parts)
		results.append((
			theme,
			scene,
			camera,
			projected_pixel(scene, camera, arrow_x, ARROW[0]),
			projected_pixel(scene, camera, hand_x, (0.02, 1.50)),
			arrow,
			hand,
		))

	bpy.context.window.scene = results[0][1]
	for screen in bpy.data.screens:
		for area in screen.areas:
			if area.type == "VIEW_3D":
				area.spaces.active.region_3d.view_perspective = "CAMERA"
	os.makedirs(CURSOR_DIR, exist_ok=True)
	bpy.context.preferences.filepaths.save_version = 0
	bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
	for theme, scene, camera, arrow_tip, fingertip, arrow, hand in results:
		bpy.context.window.scene = scene
		output_dir = os.path.join(CURSOR_DIR, theme)
		os.makedirs(output_dir, exist_ok=True)
		export_model_volume(scene, arrow, "arrow", output_dir)
		export_model_volume(scene, hand, "pointer", output_dir)
		scene.render.filepath = os.path.join(output_dir, "source.png")
		bpy.ops.render.render(write_still=True)
		with open(os.path.join(output_dir, "hotspots.json"), "w", encoding="utf-8", newline="\n") as file:
			json.dump({"arrow": arrow_tip, "pointer": fingertip}, file, indent=2)
			file.write("\n")
		print(
			f"[cursor-model] {theme}: arrow={arrow['polygon_budget']} tris, "
			f"pointer={hand['polygon_budget']} tris; hotspots={arrow_tip}, {fingertip}"
		)
	bpy.context.window.scene = results[0][1]
	print(f"[cursor-model] saved editable scene: {BLEND_PATH}")


if "--bake-current" in sys.argv:
	bake_current_models()
elif "--import-mesh" in sys.argv:
	try:
		separator = sys.argv.index("--")
		arguments = sys.argv[separator + 1:]
	except ValueError:
		arguments = []
	parser = argparse.ArgumentParser()
	parser.add_argument("--import-mesh", required=True)
	parser.add_argument(
		"--theme",
		choices=["studio-ink", "prism-glow", "pop-coral", "pixel-candy", "star-sprout"],
		required=True,
	)
	parser.add_argument("--state", choices=["arrow", "pointer"], required=True)
	args = parser.parse_args(arguments)
	import_mesh_and_bake(args.import_mesh, args.theme, args.state)
else:
	build()
