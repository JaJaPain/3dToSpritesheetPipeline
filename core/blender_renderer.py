import os
import sys
import json
import argparse
import bpy
from math import radians

def clear_scene_except_templates(keep_objects=None):
    """Deletes all objects in the scene except those in keep_objects list."""
    if keep_objects is None:
        keep_objects = []
        
    # Ensure object mode
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
        
    bpy.ops.object.select_all(action='DESELECT')
    for obj in bpy.data.objects:
        if obj not in keep_objects:
            obj.select_set(True)
    bpy.ops.object.delete()

def find_head_bone(armature_obj):
    """Finds a head bone in the armature using case-insensitive keyword matching."""
    for bone in armature_obj.data.bones:
        if "head" in bone.name.lower():
            return bone.name
    return None

def attach_accessory(armature_obj, file_path):
    """Imports an accessory model and mounts it to the armature's Head bone space."""
    if not os.path.exists(file_path):
        print(f"Warning: Attachment file not found at {file_path}. Skipping.")
        return None
        
    # Discover head bone
    bone_name = find_head_bone(armature_obj)
    if not bone_name:
        print(f"Warning: Could not find head bone in armature {armature_obj.name}. Skipping attachment.")
        return None
        
    print(f"Mounting attachment {file_path} to bone: {bone_name}")
    
    before_objs = set(bpy.data.objects)
    if file_path.lower().endswith('.obj'):
        try:
            bpy.ops.wm.obj_import(filepath=file_path)
        except AttributeError:
            bpy.ops.import_scene.obj(filepath=file_path)
    elif file_path.lower().endswith('.fbx'):
        bpy.ops.import_scene.fbx(filepath=file_path)
    else:
        print(f"Warning: Unsupported attachment format: {file_path}. Skipping.")
        return None
        
    after_objs = set(bpy.data.objects)
    mesh_objs = [obj for obj in (after_objs - before_objs) if obj.type == 'MESH']
    
    if not mesh_objs:
        print("Warning: No meshes found in imported attachment.")
        return None
        
    # Join multiple meshes if necessary
    if len(mesh_objs) > 1:
        bpy.ops.object.select_all(action='DESELECT')
        for m in mesh_objs:
            m.select_set(True)
        bpy.context.view_layer.objects.active = mesh_objs[0]
        bpy.ops.object.join()
        attachment = bpy.context.view_layer.objects.active
    else:
        attachment = mesh_objs[0]
        
    # Attach to bone
    bpy.ops.object.select_all(action='DESELECT')
    attachment.select_set(True)
    bpy.context.view_layer.objects.active = attachment
    
    attachment.parent = armature_obj
    attachment.parent_type = 'BONE'
    attachment.parent_bone = bone_name
    
    # Align to head bone center
    attachment.location = (0, 0, 0)
    attachment.rotation_euler = (0, 0, 0)
    attachment.scale = (1, 1, 1)
    
    print(f"Successfully mounted {attachment.name} to {armature_obj.name}:{bone_name}")
    return attachment

def inject_colors(profile_data):
    """Injects color profiles into named material shader sockets."""
    print("Scanning materials for custom color injection...")
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
            
        nodes = mat.node_tree.nodes
        for node in nodes:
            for input_socket in node.inputs:
                if input_socket.name == "Injected_Skin_RGB" and "skin_tone" in profile_data:
                    input_socket.default_value = profile_data["skin_tone"]
                    print(f"Injected Skin color into material {mat.name}")
                elif input_socket.name == "Injected_Shirt_RGB" and "shirt_color" in profile_data:
                    input_socket.default_value = profile_data["shirt_color"]
                    print(f"Injected Shirt color into material {mat.name}")
                elif input_socket.name == "Injected_Pants_RGB" and "pants_color" in profile_data:
                    input_socket.default_value = profile_data["pants_color"]
                    print(f"Injected Pants color into material {mat.name}")

def setup_camera_and_lights(scene):
    """Aligns camera and light sources for consistent diffuse and normal outputs."""
    # Check camera
    camera_obj = None
    for obj in bpy.data.objects:
        if obj.type == 'CAMERA':
            camera_obj = obj
            break
            
    if not camera_obj:
        print("Creating rendering camera...")
        bpy.ops.object.camera_add(location=(0, -2.8, 1.05), rotation=(radians(85), 0, 0))
        camera_obj = bpy.context.view_layer.objects.active
        scene.camera = camera_obj
    else:
        camera_obj.location = (0, -2.8, 1.05)
        camera_obj.rotation_euler = (radians(85), 0, 0)
        scene.camera = camera_obj

    # Orthographic camera is much better for 2D sprites
    camera_obj.data.type = 'ORTHO'
    camera_obj.data.ortho_scale = 2.2

    # Lights
    light_exists = False
    for obj in bpy.data.objects:
        if obj.type == 'LIGHT':
            light_exists = True
            break
            
    if not light_exists:
        print("Creating rendering lighting setup...")
        bpy.ops.object.light_add(type='SUN', radius=1.0, location=(3, -3, 5))
        sun = bpy.context.view_layer.objects.active
        sun.data.energy = 3.0
        sun.rotation_euler = (radians(40), 0, radians(45))
        
        bpy.ops.object.light_add(type='AREA', radius=2.0, location=(-3, 3, 3))
        area = bpy.context.view_layer.objects.active
        area.data.energy = 40.0
        area.rotation_euler = (radians(-45), 0, radians(-45))

def create_normal_material():
    """Generates a custom emission material that outputs camera-space normals."""
    mat = bpy.data.materials.new(name="PipelineNormalShader")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    
    # Geometry input node
    geom = nodes.new(type='ShaderNodeNewGeometry')
    
    # Vector Transform (World -> Camera Space Normal)
    trans = nodes.new(type='ShaderNodeVectorTransform')
    trans.vector_type = 'NORMAL'
    trans.convert_from = 'WORLD'
    trans.convert_to = 'CAMERA'
    links.new(geom.outputs['Normal'], trans.inputs[0])
    
    # Map [-1, 1] to [0, 1]
    # Multiply by 0.5
    v_mult = nodes.new(type='ShaderNodeVectorMath')
    v_mult.operation = 'MULTIPLY'
    v_mult.inputs[1].default_value = (0.5, 0.5, 0.5)
    links.new(trans.outputs[0], v_mult.inputs[0])
    
    # Add 0.5
    v_add = nodes.new(type='ShaderNodeVectorMath')
    v_add.operation = 'ADD'
    v_add.inputs[1].default_value = (0.5, 0.5, 0.5)
    links.new(v_mult.outputs[0], v_add.inputs[0])
    
    # Material Output node
    out_node = nodes.new(type='ShaderNodeOutputMaterial')
    
    # Emission shader to render pure color vectors without shading
    emis = nodes.new(type='ShaderNodeEmission')
    links.new(v_add.outputs[0], emis.inputs['Color'])
    links.new(emis.outputs['Emission'], out_node.inputs['Surface'])
    
    return mat

def main():
    if '--' in sys.argv:
        args_start = sys.argv.index('--') + 1
        script_args = sys.argv[args_start:]
    else:
        script_args = []
        
    parser = argparse.ArgumentParser(description="Headless 8-directional rendering camera loop")
    parser.add_argument("--input", required=True, help="Path to template mesh (.blend, .fbx, or .obj)")
    parser.add_argument("--profile", required=True, help="Path to JSON color profile config")
    parser.add_argument("--output-dir", required=True, help="Base directory for frame exports")
    
    args = parser.parse_args(script_args)
    
    print("=========================================")
    print("Starting Headless Sprite Renderer...")
    print(f"Input model: {args.input}")
    print(f"Profile: {args.profile}")
    print(f"Output folder: {args.output_dir}")
    print("=========================================")
    
    # Load profile data
    with open(args.profile, 'r') as f:
        profile_data = json.load(f)
        
    citizen_id = profile_data.get("citizen_id", "character")
    
    # Load template model
    target_mesh = None
    armature_obj = None
    
    if args.input.lower().endswith('.blend'):
        print(f"Opening template blend file: {args.input}")
        bpy.ops.wm.open_mainfile(filepath=args.input)
    elif args.input.lower().endswith('.fbx'):
        print(f"Importing template FBX file: {args.input}")
        clear_scene_except_templates([])
        bpy.ops.import_scene.fbx(filepath=args.input)
    elif args.input.lower().endswith('.obj'):
        print(f"Importing template OBJ file: {args.input}")
        clear_scene_except_templates([])
        try:
            bpy.ops.wm.obj_import(filepath=args.input)
        except AttributeError:
            bpy.ops.import_scene.obj(filepath=args.input)
            
    # Locate imported objects
    template_meshes = [obj for obj in bpy.data.objects if obj.type == 'MESH']
    armatures = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']
    
    if not template_meshes:
        raise ValueError("No mesh objects found after loading template.")
        
    target_mesh = template_meshes[0]
    if armatures:
        armature_obj = armatures[0]
        print(f"Armature target located: {armature_obj.name}")
    else:
        # Fallback: if unrigged, we will treat the target mesh itself as the object to rotate
        armature_obj = target_mesh
        print("Unrigged fallback: Camera loop will rotate mesh directly.")
        
    # 1. Mount accessory attachment if provided
    attach_file = profile_data.get("attachment_file")
    if attach_file and os.path.exists(attach_file) and armatures:
        attach_accessory(armature_obj, attach_file)
        
    # 2. Inject skin/clothing colors into material shaders
    inject_colors(profile_data)
    
    # Set up scene camera and rendering properties
    scene = bpy.context.scene
    setup_camera_and_lights(scene)
    
    # Configure Eevee for transparency & sizing
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.film_transparent = True
    scene.render.resolution_x = 256
    scene.render.resolution_y = 256
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    
    # Get animations to render
    actions = []
    if armatures and armature_obj.animation_data and armature_obj.animation_data.nla_tracks:
        actions = list(bpy.data.actions)
    
    if not actions:
        actions = [None]
        print("No animation actions found. Running static pose rendering.")
        
    # Generate the camera-space normal shader material
    norm_mat = create_normal_material()
    
    # Execute the 8-way camera loop
    original_rotation = armature_obj.rotation_euler.copy()
    
    try:
        for action in actions:
            action_name = action.name if action else "static"
            print(f"Processing action sequence: {action_name}")
            
            if action and armature_obj.animation_data:
                armature_obj.animation_data.action = action
                frame_start = int(action.frame_range[0])
                frame_end = int(action.frame_range[1])
            else:
                frame_start = 1
                frame_end = 1
                
            # Loop through 8 directions (every 45 degrees)
            for angle_idx in range(8):
                angle_degrees = angle_idx * 45
                print(f"  Rendering direction: {angle_degrees} degrees...")
                
                # Rotate target armature on Z axis
                armature_obj.rotation_euler.z = radians(angle_degrees)
                bpy.context.view_layer.update()
                
                # Set output directories
                action_dir = f"{citizen_id}/{action_name}_angle{angle_degrees}"
                diffuse_dir = os.path.abspath(os.path.join(args.output_dir, action_dir, "diffuse"))
                normal_dir = os.path.abspath(os.path.join(args.output_dir, action_dir, "normal"))
                
                os.makedirs(diffuse_dir, exist_ok=True)
                os.makedirs(normal_dir, exist_ok=True)
                
                # Render animation frames
                for frame in range(frame_start, frame_end + 1):
                    scene.frame_set(frame)
                    
                    # Discover all meshes currently in the scene to apply/restore materials
                    meshes = [obj for obj in bpy.data.objects if obj.type == 'MESH']
                    
                    # --- Pass 1: Render Normal Map ---
                    original_mats = {}
                    for obj in meshes:
                        original_mats[obj] = [slot.material for slot in obj.material_slots]
                        if not obj.material_slots:
                            obj.data.materials.append(norm_mat)
                        else:
                            for idx in range(len(obj.material_slots)):
                                obj.material_slots[idx].material = norm_mat
                    
                    scene.render.filepath = os.path.join(normal_dir, f"frame_{frame:03d}.png")
                    bpy.ops.render.render(write_still=True)
                    
                    # --- Pass 2: Render Diffuse Color ---
                    for obj, mats in original_mats.items():
                        if not mats:
                            obj.data.materials.clear()
                        else:
                            for idx, mat in enumerate(mats):
                                if idx < len(obj.material_slots):
                                    obj.material_slots[idx].material = mat
                                    
                    scene.render.filepath = os.path.join(diffuse_dir, f"frame_{frame:03d}.png")
                    bpy.ops.render.render(write_still=True)
                    
        print("Headless rendering complete!")
        print("=========================================")
    finally:
        # Restore armature rotation
        armature_obj.rotation_euler = original_rotation

if __name__ == "__main__":
    main()
