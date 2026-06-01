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
# STEP: Create new UV map with quadrant layout
# ---------------------------------------------------------------------------
def create_quadrant_uv_map(obj, segments):
    """
    Creates a NEW UV map called 'QuadrantUV' on the mesh.
    Each body region's faces are Smart UV Projected and placed into
    their designated quadrant.

    The original UV map (used by the TRELLIS texture) is left untouched.
    """
    mesh = obj.data

    # Rename the original UV map so we can reference it later
    if mesh.uv_layers:
        mesh.uv_layers[0].name = "OriginalUV"
        print(f"  Renamed original UV map to 'OriginalUV'")

    # Create the new quadrant UV map
    new_uv = mesh.uv_layers.new(name="QuadrantUV")
    # Set the NEW UV map as active (this is where the bake will write)
    mesh.uv_layers.active = new_uv
    print(f"  Created new UV map 'QuadrantUV' (active for bake output)")

    # UV unwrap each segment into its quadrant
    for region_name, face_indices in segments.items():
        if not face_indices:
            print(f"  Segment '{region_name}' has no faces — skipping.")
            continue

        quadrant = QUADRANTS[region_name]
        offset_u, offset_v = quadrant["offset"]
        scale = quadrant["scale"]

        # Enter edit mode, select only this segment's faces
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

        bpy.ops.object.mode_set(mode='EDIT')

        # CRITICAL: Force QuadrantUV as active INSIDE edit mode
        # Entering edit mode can reset the active UV layer
        for i, uv_layer in enumerate(mesh.uv_layers):
            if uv_layer.name == "QuadrantUV":
                mesh.uv_layers.active_index = i
                break

        bpy.ops.mesh.select_all(action='DESELECT')

        bm = bmesh.from_edit_mesh(mesh)
        bm.faces.ensure_lookup_table()

        face_index_set = set(face_indices)
        for face in bm.faces:
            face.select = face.index in face_index_set

        bmesh.update_edit_mesh(mesh)

        # Smart UV Project with WIDE angle (89° ≈ 1.553 rad) to merge more
        # faces into larger connected islands. The wider the angle, the fewer
        # seam cuts, giving fewer but larger UV islands = better texture quality.
        bpy.ops.uv.smart_project(angle_limit=1.553, island_margin=0.005)

        # Normalize and place UVs into the target quadrant
        bm = bmesh.from_edit_mesh(mesh)
        bm.faces.ensure_lookup_table()

        # Explicitly get the QuadrantUV layer by NAME, not .active
        uv_lay = None
        for layer in bm.loops.layers.uv:
            if layer.name == "QuadrantUV":
                uv_lay = layer
                break
        if uv_lay is None:
            uv_lay = bm.loops.layers.uv.active

        if uv_lay is None:
            print(f"  WARNING: No UV layer found for '{region_name}'")
            bpy.ops.object.mode_set(mode='OBJECT')
            continue

        # Collect UV coords for selected faces
        selected_uvs = []
        for face in bm.faces:
            if face.index in face_index_set:
                for loop in face.loops:
                    selected_uvs.append(loop[uv_lay].uv)

        if not selected_uvs:
            print(f"  WARNING: No UV data for '{region_name}'")
            bpy.ops.object.mode_set(mode='OBJECT')
            continue

        # Find bounds
        min_u = min(uv.x for uv in selected_uvs)
        max_u = max(uv.x for uv in selected_uvs)
        min_v = min(uv.y for uv in selected_uvs)
        max_v = max(uv.y for uv in selected_uvs)
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

        print(f"  Unwrapped '{region_name}' → quadrant ({offset_u:.2f}, {offset_v:.2f})")


# ---------------------------------------------------------------------------
# STEP: Self-bake from OriginalUV → QuadrantUV
# ---------------------------------------------------------------------------
def self_bake_uv_transfer(obj, output_image_path, tex_size=2048):
    """
    Sets up an Emission material that reads the TRELLIS texture via the
    ORIGINAL UV map, then bakes onto a new image using the QUADRANT UV map.

    This is a SELF-BAKE (single object, no ray-casting between objects).
    The bake reads from one UV set and writes to another.
    """
    print("Setting up self-bake UV transfer...")

    mesh = obj.data

    # --- Find the original TRELLIS texture ---
    source_image = None
    for mat in obj.data.materials:
        if mat and mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    source_image = node.image
                    print(f"  Found source texture: '{node.image.name}' "
                          f"({node.image.size[0]}x{node.image.size[1]})")
                    break
        if source_image:
            break

    if not source_image:
        print("  WARNING: No source texture found! Checking vertex colors...")

    # --- Build emission material that reads from OriginalUV ---
    obj.data.materials.clear()
    mat = bpy.data.materials.new(name="BakeTransferMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Clear default nodes
    for node in nodes:
        nodes.remove(node)

    output_node = nodes.new(type='ShaderNodeOutputMaterial')
    output_node.location = (600, 0)

    emit_node = nodes.new(type='ShaderNodeEmission')
    emit_node.location = (300, 0)
    emit_node.inputs['Strength'].default_value = 1.0
    links.new(emit_node.outputs['Emission'], output_node.inputs['Surface'])

    if source_image:
        # Texture node reads from the ORIGINAL UV map
        tex_node = nodes.new(type='ShaderNodeTexImage')
        tex_node.location = (-100, 0)
        tex_node.image = source_image
        links.new(tex_node.outputs['Color'], emit_node.inputs['Color'])

        # UV Map node explicitly pointing to OriginalUV
        uv_node = nodes.new(type='ShaderNodeUVMap')
        uv_node.location = (-400, 0)
        uv_node.uv_map = "OriginalUV"
        links.new(uv_node.outputs['UV'], tex_node.inputs['Vector'])

        print(f"  Emission material: texture '{source_image.name}' via 'OriginalUV'")
    elif obj.data.color_attributes:
        vcol_node = nodes.new(type='ShaderNodeVertexColor')
        vcol_node.location = (-100, 0)
        vcol_node.layer_name = obj.data.color_attributes[0].name
        links.new(vcol_node.outputs['Color'], emit_node.inputs['Color'])
        print(f"  Emission material: vertex colors '{obj.data.color_attributes[0].name}'")
    else:
        print("  WARNING: No color source found. Bake will produce flat white.")

    # --- Create the bake target image ---
    bake_img_name = "BakedTexture"
    if bake_img_name in bpy.data.images:
        bpy.data.images.remove(bpy.data.images[bake_img_name])
    bake_image = bpy.data.images.new(bake_img_name, width=tex_size, height=tex_size,
                                      alpha=True)

    # Add a SECOND image texture node for the bake target and make it ACTIVE
    bake_target_node = nodes.new(type='ShaderNodeTexImage')
    bake_target_node.location = (-100, -300)
    bake_target_node.image = bake_image
    # Do NOT connect it to anything — it's just the bake target
    nodes.active = bake_target_node
    bake_target_node.select = True

    obj.data.materials.append(mat)

    # --- Ensure QuadrantUV is the ACTIVE UV map (bake writes here) ---
    for uv_layer in mesh.uv_layers:
        if uv_layer.name == "QuadrantUV":
            uv_layer.active_render = True
            mesh.uv_layers.active = uv_layer
            print(f"  Active UV for bake output: 'QuadrantUV'")
            break

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

    # --- Self-bake (NOT selected-to-active) ---
    bake = bpy.context.scene.render.bake
    bake.use_selected_to_active = False   # <-- KEY: self-bake!
    bake.margin = 8

    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    print("  Baking EMIT (self-bake: OriginalUV → QuadrantUV)...")
    bpy.ops.object.bake(type='EMIT')

    # --- Save baked texture ---
    bake_image.filepath_raw = output_image_path
    bake_image.file_format = 'PNG'
    bake_image.save()
    print(f"  Baked texture saved to: {output_image_path}")

    # --- Clean up: remove OriginalUV, keep only QuadrantUV ---
    for uv_layer in list(mesh.uv_layers):
        if uv_layer.name == "OriginalUV":
            mesh.uv_layers.remove(uv_layer)
            print("  Removed 'OriginalUV' — only 'QuadrantUV' remains")
            break

    # --- Update material to use the baked texture with QuadrantUV ---
    for node in nodes:
        nodes.remove(node)

    output_node = nodes.new(type='ShaderNodeOutputMaterial')
    output_node.location = (300, 0)

    bsdf_node = nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf_node.location = (0, 0)

    tex_node = nodes.new(type='ShaderNodeTexImage')
    tex_node.location = (-300, 0)
    tex_node.image = bake_image

    links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])
    links.new(tex_node.outputs['Color'], bsdf_node.inputs['Base Color'])

    print("  Material updated to use baked texture with QuadrantUV")


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
def export_fbx(obj, output_path):
    """Exports the given mesh object as FBX."""
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
    )
    print(f"FBX exported to: {output_path}")


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
    print("Blender Headless: Silhouette-Preserving UV Remapping")
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

    # Step 4: Segment faces by body region
    print("\n--- Segmenting faces by body region ---")
    segments = segment_faces_by_body_region(mesh_obj)

    # Step 5: Create new QuadrantUV map (keeps OriginalUV intact)
    print("\n--- Creating quadrant UV layout ---")
    create_quadrant_uv_map(mesh_obj, segments)

    # Step 6: Self-bake from OriginalUV → QuadrantUV
    print("\n--- Baking texture (self-bake UV transfer) ---")
    output_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.basename(args.output).split('.')[0]
    tex_path = os.path.join(output_dir, f"{base_name}_tex.png")

    self_bake_uv_transfer(mesh_obj, tex_path, args.tex_size)

    # Step 7: Optional post-bake subdivision
    if args.subdiv_levels > 0:
        print("\n--- Applying post-bake subdivision ---")
        subdivide_mesh(mesh_obj, args.subdiv_levels)

    # Step 8: Export
    print("\n--- Exporting final FBX ---")
    export_fbx(mesh_obj, args.output)

    final_faces = len(mesh_obj.data.polygons)
    print("\n" + "=" * 60)
    print("COMPLETED SUCCESSFULLY!")
    print(f"  Output FBX:    {args.output}")
    print(f"  Baked Texture: {tex_path}")
    print(f"  Final Faces:   {final_faces}")
    print("=" * 60)


if __name__ == "__main__":
    main()
