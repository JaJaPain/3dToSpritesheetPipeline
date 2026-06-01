import os
import sys
import argparse
import bmesh
import bpy
from mathutils import Vector

# ---------------------------------------------------------------------------
# UV Quadrant layout matching UVGuide.png:
#   Top-Left  (Red)    = Skin  (Head, Neck, Hands)
#   Top-Right (Blue)   = Shirt (Torso, Arms)
#   Bot-Left  (Green)  = Pants (Hips, Legs)
#   Bot-Right (Yellow) = Shoes (Feet)
# ---------------------------------------------------------------------------
QUADRANTS = {
    "skin":  {"offset": (0.01, 0.51), "scale": 0.48},   # Top-Left
    "shirt": {"offset": (0.51, 0.51), "scale": 0.48},   # Top-Right
    "pants": {"offset": (0.01, 0.01), "scale": 0.48},   # Bottom-Left
    "shoes": {"offset": (0.51, 0.01), "scale": 0.48},   # Bottom-Right
}

# Height thresholds as fractions of total model height (Z-axis)
# These are tuned for standard humanoid A-pose / T-pose models
SEGMENT_THRESHOLDS = {
    "head_min":  0.82,   # Everything above 82% height = head/neck
    "torso_min": 0.50,   # 50% to 82% = torso / upper body
    "pants_min": 0.12,   # 12% to 50% = hips / legs
    # Below 12% = shoes/feet
    "hand_z_min": 0.35,  # Hand detection: Z range for arms
    "hand_z_max": 0.65,
    "hand_x_threshold": 0.25,  # Hands are outer 25% of width on each side
}


def clear_scene():
    """Removes all objects from the scene for a clean start."""
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    # Clean orphan data
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for block in bpy.data.materials:
        if block.users == 0:
            bpy.data.materials.remove(block)


def import_glb(filepath):
    """Imports a GLB file and returns the mesh object (joins multiple meshes if needed)."""
    before_objs = set(bpy.data.objects)
    print(f"Importing GLB: {filepath}")
    bpy.ops.import_scene.gltf(filepath=filepath)
    after_objs = set(bpy.data.objects)

    new_objs = after_objs - before_objs
    mesh_objs = [obj for obj in new_objs if obj.type == 'MESH']

    if not mesh_objs:
        raise ValueError(f"No mesh objects found in imported GLB: {filepath}")

    # Join multiple meshes into one
    if len(mesh_objs) > 1:
        print(f"Joining {len(mesh_objs)} imported mesh objects...")
        bpy.ops.object.select_all(action='DESELECT')
        for mesh in mesh_objs:
            mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh_objs[0]
        bpy.ops.object.join()
        joined = bpy.context.view_layer.objects.active
    else:
        joined = mesh_objs[0]

    # Apply all transforms so coordinates are in world space
    bpy.ops.object.select_all(action='DESELECT')
    joined.select_set(True)
    bpy.context.view_layer.objects.active = joined
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    print(f"Imported mesh '{joined.name}' — {len(joined.data.polygons)} faces, "
          f"{len(joined.data.vertices)} verts")
    return joined


# ---------------------------------------------------------------------------
# STEP: Decimate in-place
# ---------------------------------------------------------------------------
def decimate_mesh(obj, target_faces=15000):
    """
    Decimates the mesh IN-PLACE if face count exceeds target.
    The original UV map is preserved (just with fewer faces).
    """
    current_faces = len(obj.data.polygons)
    print(f"  Current face count: {current_faces}")

    if current_faces > target_faces:
        ratio = target_faces / current_faces
        print(f"  Decimating to ~{target_faces} faces (ratio: {ratio:.4f})...")

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

        mod = obj.modifiers.new(name="Decimate", type='DECIMATE')
        mod.ratio = ratio
        bpy.ops.object.modifier_apply(modifier=mod.name)

        print(f"  After decimation: {len(obj.data.polygons)} faces")
    else:
        print(f"  Mesh at {current_faces} faces — under target {target_faces}, "
              f"no decimation needed.")


# ---------------------------------------------------------------------------
# STEP: Body region segmentation
# ---------------------------------------------------------------------------
def get_mesh_bounds(obj):
    """Returns (min_corner, max_corner) Vectors in world space."""
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    min_c = Vector((
        min(c[0] for c in corners),
        min(c[1] for c in corners),
        min(c[2] for c in corners),
    ))
    max_c = Vector((
        max(c[0] for c in corners),
        max(c[1] for c in corners),
        max(c[2] for c in corners),
    ))
    return min_c, max_c


def segment_faces_by_body_region(obj):
    """
    Classifies every face into one of four body regions based on its center
    position relative to the mesh bounding box.

    Returns dict: {"skin": [face_indices], "shirt": [...], "pants": [...], "shoes": [...]}
    """
    min_c, max_c = get_mesh_bounds(obj)
    height = max_c.z - min_c.z
    width = max_c.x - min_c.x
    z_min = min_c.z
    x_center = (min_c.x + max_c.x) / 2.0

    t = SEGMENT_THRESHOLDS

    segments = {"skin": [], "shirt": [], "pants": [], "shoes": []}

    mesh = obj.data
    for face in mesh.polygons:
        fc = face.center
        z_frac = (fc.z - z_min) / height if height > 0.001 else 0.5

        # Check if this face is a "hand" — at arm height but far out on X
        x_offset = abs(fc.x - x_center)
        x_frac = x_offset / (width / 2.0) if width > 0.001 else 0.0
        is_hand = (t["hand_z_min"] <= z_frac <= t["hand_z_max"]
                   and x_frac >= t["hand_x_threshold"])

        if z_frac >= t["head_min"] or is_hand:
            segments["skin"].append(face.index)
        elif z_frac >= t["torso_min"]:
            segments["shirt"].append(face.index)
        elif z_frac >= t["pants_min"]:
            segments["pants"].append(face.index)
        else:
            segments["shoes"].append(face.index)

    for region, indices in segments.items():
        print(f"  Segment '{region}': {len(indices)} faces")

    return segments


# ---------------------------------------------------------------------------
# STEP: Duplicate mesh to create bake source
# ---------------------------------------------------------------------------
def duplicate_as_bake_source(obj):
    """
    Duplicates the mesh object. The duplicate keeps the original UV layout
    and material, and will be used as the color source for baking.
    Returns the duplicate (source) object.
    """
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.duplicate()
    source_obj = bpy.context.view_layer.objects.active
    source_obj.name = "BakeSource"
    print(f"  Created bake source: '{source_obj.name}'")
    return source_obj


# ---------------------------------------------------------------------------
# STEP: Set up emission material on source for baking
# ---------------------------------------------------------------------------
def setup_source_emission_material(source_obj):
    """
    Replaces the source object's material with a simple Emission shader
    that reads the original TRELLIS texture via the original UV map.
    This ensures the bake captures the correct colors.
    """
    mesh = source_obj.data

    # Find the original texture image
    source_image = None
    for mat in mesh.materials:
        if mat and mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    source_image = node.image
                    print(f"  Source texture: '{node.image.name}' "
                          f"({node.image.size[0]}x{node.image.size[1]})")
                    break
        if source_image:
            break

    # Find the original UV layer name
    original_uv_name = mesh.uv_layers[0].name if mesh.uv_layers else "UVMap"
    print(f"  Source UV layer: '{original_uv_name}'")

    # Build emission material
    mesh.materials.clear()
    mat = bpy.data.materials.new(name="SourceEmission")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    for node in nodes:
        nodes.remove(node)

    output_node = nodes.new(type='ShaderNodeOutputMaterial')
    output_node.location = (600, 0)

    emit_node = nodes.new(type='ShaderNodeEmission')
    emit_node.location = (300, 0)
    emit_node.inputs['Strength'].default_value = 1.0
    links.new(emit_node.outputs['Emission'], output_node.inputs['Surface'])

    if source_image:
        tex_node = nodes.new(type='ShaderNodeTexImage')
        tex_node.location = (-100, 0)
        tex_node.image = source_image
        links.new(tex_node.outputs['Color'], emit_node.inputs['Color'])

        uv_node = nodes.new(type='ShaderNodeUVMap')
        uv_node.location = (-400, 0)
        uv_node.uv_map = original_uv_name
        links.new(uv_node.outputs['UV'], tex_node.inputs['Vector'])
        print(f"  Emission material reads '{source_image.name}' via '{original_uv_name}'")
    elif mesh.color_attributes:
        vcol_node = nodes.new(type='ShaderNodeVertexColor')
        vcol_node.location = (-100, 0)
        vcol_node.layer_name = mesh.color_attributes[0].name
        links.new(vcol_node.outputs['Color'], emit_node.inputs['Color'])
        print(f"  Emission material reads vertex colors '{mesh.color_attributes[0].name}'")
    else:
        print("  WARNING: No color source found on source mesh.")

    mesh.materials.append(mat)


# ---------------------------------------------------------------------------
# STEP: Create fresh quadrant UV layout on the target mesh
# ---------------------------------------------------------------------------
def create_quadrant_uv_on_target(target_obj, segments):
    """
    Removes all existing UV layers on the target and creates a single fresh
    UV layer. For each body segment, runs Smart UV Project and places the
    result into the designated quadrant.

    This is done on the TARGET object (which will receive the baked texture).
    The SOURCE object (with original UVs) is untouched.
    """
    mesh = target_obj.data

    # Remove ALL existing UV layers — start completely fresh
    while mesh.uv_layers:
        mesh.uv_layers.remove(mesh.uv_layers[0])

    # Create one fresh UV layer
    uv_layer = mesh.uv_layers.new(name="UVMap")
    mesh.uv_layers.active = uv_layer
    print(f"  Created fresh UV layer 'UVMap'")

    # First pass: mark seams at segment boundaries so unwrap respects them
    bpy.ops.object.select_all(action='DESELECT')
    target_obj.select_set(True)
    bpy.context.view_layer.objects.active = target_obj
    bpy.ops.object.mode_set(mode='EDIT')

    bm = bmesh.from_edit_mesh(mesh)
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()

    # Build face→region lookup
    face_region = {}
    for region_name, face_indices in segments.items():
        for fi in face_indices:
            face_region[fi] = region_name

    # Mark seams where adjacent faces belong to different regions
    for edge in bm.edges:
        if len(edge.link_faces) == 2:
            f0, f1 = edge.link_faces
            if face_region.get(f0.index) != face_region.get(f1.index):
                edge.seam = True

    bmesh.update_edit_mesh(mesh)
    bpy.ops.object.mode_set(mode='OBJECT')

    # Second pass: unwrap each segment and place into its quadrant
    for region_name, face_indices in segments.items():
        if not face_indices:
            print(f"  Segment '{region_name}' has no faces — skipping.")
            continue

        quadrant = QUADRANTS[region_name]
        offset_u, offset_v = quadrant["offset"]
        scale = quadrant["scale"]
        face_index_set = set(face_indices)

        # --- Enter Edit Mode, select segment faces ---
        bpy.ops.object.select_all(action='DESELECT')
        target_obj.select_set(True)
        bpy.context.view_layer.objects.active = target_obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')

        bm = bmesh.from_edit_mesh(mesh)
        bm.faces.ensure_lookup_table()
        for face in bm.faces:
            face.select = face.index in face_index_set
        bmesh.update_edit_mesh(mesh)

        # --- Unwrap selected faces ---
        # Standard unwrap follows mesh connectivity → far fewer islands than smart_project
        # The seams we marked above ensure segments don't bleed into each other
        bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=0.02)

        # --- Normalize and place into quadrant ---
        bm = bmesh.from_edit_mesh(mesh)
        bm.faces.ensure_lookup_table()
        uv_lay = bm.loops.layers.uv.active

        if uv_lay is None:
            print(f"  WARNING: No UV layer for '{region_name}'")
            bpy.ops.object.mode_set(mode='OBJECT')
            continue

        # Collect UV bounds for this segment
        min_u, max_u = float('inf'), float('-inf')
        min_v, max_v = float('inf'), float('-inf')
        for face in bm.faces:
            if face.index in face_index_set:
                for loop in face.loops:
                    u, v = loop[uv_lay].uv
                    min_u = min(min_u, u)
                    max_u = max(max_u, u)
                    min_v = min(min_v, v)
                    max_v = max(max_v, v)

        range_u = max_u - min_u
        range_v = max_v - min_v

        # Normalize to [0,1] then scale and offset into quadrant
        for face in bm.faces:
            if face.index in face_index_set:
                for loop in face.loops:
                    uv = loop[uv_lay].uv
                    norm_u = (uv.x - min_u) / range_u if range_u > 0.0001 else 0.5
                    norm_v = (uv.y - min_v) / range_v if range_v > 0.0001 else 0.5
                    uv.x = offset_u + norm_u * scale
                    uv.y = offset_v + norm_v * scale

        bmesh.update_edit_mesh(mesh)
        bpy.ops.object.mode_set(mode='OBJECT')

        print(f"  UV'd '{region_name}' ({len(face_indices)} faces) → "
              f"quadrant ({offset_u:.2f}, {offset_v:.2f})")


# ---------------------------------------------------------------------------
# STEP: Two-object bake (source → target)
# ---------------------------------------------------------------------------
def bake_texture_transfer(source_obj, target_obj, output_image_path, tex_size=2048):
    """
    Industry-standard two-object bake:
      - SOURCE has original UV + original TRELLIS texture (emission material)
      - TARGET has fresh quadrant UV layout + empty bake target image
      - Blender ray-casts from target surface to source surface, sampling
        the source's emission color, and writes it to the target's bake image.

    After baking, the source is deleted and the target's material is updated
    to use the baked texture.
    """
    print("Setting up two-object bake...")

    target_mesh = target_obj.data

    # --- Create the bake target image ---
    bake_img_name = "BakedTexture"
    if bake_img_name in bpy.data.images:
        bpy.data.images.remove(bpy.data.images[bake_img_name])
    bake_image = bpy.data.images.new(
        bake_img_name, width=tex_size, height=tex_size, alpha=True
    )

    # --- Set up target material with bake target image ---
    target_obj.data.materials.clear()
    tgt_mat = bpy.data.materials.new(name="BakeTargetMaterial")
    tgt_mat.use_nodes = True
    tgt_nodes = tgt_mat.node_tree.nodes
    tgt_links = tgt_mat.node_tree.links

    for node in tgt_nodes:
        tgt_nodes.remove(node)

    # Output + Principled BSDF (placeholder — bake target image is what matters)
    tgt_output = tgt_nodes.new(type='ShaderNodeOutputMaterial')
    tgt_output.location = (300, 0)
    tgt_bsdf = tgt_nodes.new(type='ShaderNodeBsdfPrincipled')
    tgt_bsdf.location = (0, 0)
    tgt_links.new(tgt_bsdf.outputs['BSDF'], tgt_output.inputs['Surface'])

    # Bake target image node — must be ACTIVE (selected) and NOT connected
    tgt_img_node = tgt_nodes.new(type='ShaderNodeTexImage')
    tgt_img_node.location = (-300, -200)
    tgt_img_node.image = bake_image
    tgt_nodes.active = tgt_img_node
    tgt_img_node.select = True

    target_obj.data.materials.append(tgt_mat)

    # --- Configure Cycles ---
    bpy.context.scene.render.engine = 'CYCLES'

    cycles_prefs = bpy.context.preferences.addons['cycles'].preferences
    cycles_prefs.compute_device_type = 'CUDA'
    cycles_prefs.get_devices()
    gpu_enabled = False
    for device in cycles_prefs.devices:
        if device.type == 'CUDA':
            device.use = True
            gpu_enabled = True

    if gpu_enabled:
        bpy.context.scene.cycles.device = 'GPU'
        print("  Using GPU (CUDA)")
    else:
        bpy.context.scene.cycles.device = 'CPU'
        print("  Falling back to CPU")

    try:
        bpy.context.scene.cycles.bake_samples = 4
    except AttributeError:
        pass

    # --- Selected-to-Active bake ---
    bake = bpy.context.scene.render.bake
    bake.use_selected_to_active = True   # KEY: two-object bake!
    bake.cage_extrusion = 0.05           # Ray-cast distance
    bake.margin = 4                      # Must be < island_margin (~20px)

    # Select source, make target active
    bpy.ops.object.select_all(action='DESELECT')
    source_obj.select_set(True)    # SOURCE is "selected"
    target_obj.select_set(True)    # TARGET is also selected
    bpy.context.view_layer.objects.active = target_obj  # TARGET is "active"

    print("  Baking EMIT (selected-to-active: source → target)...")
    bpy.ops.object.bake(type='EMIT')

    # --- Save baked texture ---
    bake_image.filepath_raw = output_image_path
    bake_image.file_format = 'PNG'
    bake_image.save()
    print(f"  Baked texture saved to: {output_image_path}")

    # --- Delete source object ---
    bpy.ops.object.select_all(action='DESELECT')
    source_obj.select_set(True)
    bpy.context.view_layer.objects.active = source_obj
    bpy.ops.object.delete()
    print("  Deleted bake source object")

    # --- Clean up ALL orphan data to prevent FBX exporter confusion ---
    # Remove the in-memory bake image (we'll reload from disk)
    bpy.data.images.remove(bake_image)
    # Purge all orphan datablocks (materials, images, meshes from source)
    bpy.ops.outliner.orphans_purge(do_recursive=True)
    print("  Purged orphan datablocks")

    # --- Reload the saved image from disk (only image in scene) ---
    saved_image = bpy.data.images.load(output_image_path)

    # --- Update target material to use baked texture ---
    for node in tgt_nodes:
        tgt_nodes.remove(node)

    out_node = tgt_nodes.new(type='ShaderNodeOutputMaterial')
    out_node.location = (400, 0)

    bsdf_node = tgt_nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf_node.location = (100, 0)

    tex_node = tgt_nodes.new(type='ShaderNodeTexImage')
    tex_node.location = (-300, 0)
    tex_node.image = saved_image

    # Explicit UV Map node — forces the texture to use 'UVMap' even after
    # FBX round-trip, instead of relying on Blender's default UV selection
    uv_node = tgt_nodes.new(type='ShaderNodeUVMap')
    uv_node.location = (-500, -150)
    uv_node.uv_map = "UVMap"

    tgt_links.new(uv_node.outputs['UV'], tex_node.inputs['Vector'])
    tgt_links.new(bsdf_node.outputs['BSDF'], out_node.inputs['Surface'])
    tgt_links.new(tex_node.outputs['Color'], bsdf_node.inputs['Base Color'])

    print("  Target material updated with baked texture + explicit UV Map node")


# ---------------------------------------------------------------------------
# STEP: Optional post-bake subdivision
# ---------------------------------------------------------------------------
def subdivide_mesh(obj, subdiv_levels=1):
    """
    Applies Catmull-Clark Subdivision Surface to smooth geometry.
    UVs are interpolated automatically.
    Should only be called AFTER baking.
    """
    if subdiv_levels <= 0:
        return

    before_faces = len(obj.data.polygons)
    print(f"  Applying Subdivision Surface (levels={subdiv_levels})...")

    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    sub_mod = obj.modifiers.new(name="Subdivision", type='SUBSURF')
    sub_mod.levels = subdiv_levels
    sub_mod.render_levels = subdiv_levels
    sub_mod.subdivision_type = 'CATMULL_CLARK'
    bpy.ops.object.modifier_apply(modifier=sub_mod.name)

    after_faces = len(obj.data.polygons)
    print(f"  Subdivision: {before_faces} → {after_faces} faces")


# ---------------------------------------------------------------------------
# STEP: Export
# ---------------------------------------------------------------------------
def export_fbx(obj, output_path, tex_path):
    """Exports the given mesh object as FBX with embedded texture."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    bpy.ops.export_scene.fbx(
        filepath=output_path,
        use_selection=True,
        object_types={'MESH'},
        use_mesh_modifiers=True,
        add_leaf_bones=False,
        bake_anim=False,
        path_mode='COPY',
        embed_textures=True,
    )
    print(f"FBX exported to: {output_path}")
    print(f"  (texture '{tex_path}' embedded in FBX)")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    # Parse arguments after the '--' separator
    if '--' in sys.argv:
        args_start = sys.argv.index('--') + 1
        script_args = sys.argv[args_start:]
    else:
        script_args = []

    parser = argparse.ArgumentParser(
        description="Blender Headless: TRELLIS Mesh → Decimated + Clean UV FBX"
    )
    parser.add_argument("--input", required=True,
                        help="Path to raw TRELLIS .glb file")
    parser.add_argument("--output", required=True,
                        help="Path to output .fbx file")
    parser.add_argument("--decimate-faces", type=int, default=15000,
                        help="Target face count for decimation (default: 15000)")
    parser.add_argument("--subdiv-levels", type=int, default=0,
                        help="Subdivision Surface levels to apply AFTER baking "
                             "(default: 0). Use 1+ only if output is too blocky.")
    parser.add_argument("--tex-size", type=int, default=2048,
                        help="Baked texture resolution (default: 2048)")
    # Keep --template arg for backwards compatibility but ignore it
    parser.add_argument("--template", required=False, default=None,
                        help="(DEPRECATED — ignored.)")

    args = parser.parse_args(script_args)

    print("=" * 60)
    print("Blender Headless: Two-Object Bake UV Remapping")
    print(f"  Input:   {args.input}")
    print(f"  Output:  {args.output}")
    print(f"  Target faces: {args.decimate_faces}")
    print(f"  Subdiv levels: {args.subdiv_levels}")
    print(f"  Texture size:  {args.tex_size}x{args.tex_size}")
    print("=" * 60)

    # Step 1: Clean scene
    clear_scene()

    # Step 2: Import the TRELLIS GLB
    mesh_obj = import_glb(args.input)

    # Step 3: Decimate in-place (preserves original UVs)
    print("\n--- Decimating mesh ---")
    decimate_mesh(mesh_obj, args.decimate_faces)

    # Step 4: Duplicate BEFORE any UV changes — this becomes the bake source
    print("\n--- Creating bake source (duplicate with original UV + texture) ---")
    source_obj = duplicate_as_bake_source(mesh_obj)

    # Step 5: Set up emission material on source
    setup_source_emission_material(source_obj)

    # Step 6: Segment faces by body region (on the target)
    print("\n--- Segmenting faces by body region ---")
    segments = segment_faces_by_body_region(mesh_obj)

    # Step 7: Create fresh quadrant UV layout on target
    print("\n--- Creating quadrant UV layout on target ---")
    create_quadrant_uv_on_target(mesh_obj, segments)

    # Step 8: Two-object bake (source → target)
    print("\n--- Baking texture (two-object: source → target) ---")
    output_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.basename(args.output).split('.')[0]
    tex_path = os.path.join(output_dir, f"{base_name}_tex.png")

    bake_texture_transfer(source_obj, mesh_obj, tex_path, args.tex_size)

    # Step 9: Optional post-bake subdivision
    if args.subdiv_levels > 0:
        print("\n--- Applying post-bake subdivision ---")
        subdivide_mesh(mesh_obj, args.subdiv_levels)

    # Step 10: Export
    print("\n--- Exporting final FBX ---")
    export_fbx(mesh_obj, args.output, tex_path)

    final_faces = len(mesh_obj.data.polygons)
    print("\n" + "=" * 60)
    print("COMPLETED SUCCESSFULLY!")
    print(f"  Output FBX:    {args.output}")
    print(f"  Baked Texture: {tex_path}")
    print(f"  Final Faces:   {final_faces}")
    print("=" * 60)


if __name__ == "__main__":
    main()
