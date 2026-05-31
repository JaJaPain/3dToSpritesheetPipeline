import os
import sys
import argparse
import bpy
from mathutils import Vector

def clear_scene_except_templates(keep_objects=None):
    """Deletes all objects in the scene except those in keep_objects list."""
    if keep_objects is None:
        keep_objects = []
    
    # Ensure we are in object mode
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
        
    bpy.ops.object.select_all(action='DESELECT')
    for obj in bpy.data.objects:
        if obj not in keep_objects:
            obj.select_set(True)
    bpy.ops.object.delete()

def import_glb(filepath):
    """Imports raw GLB mesh and returns the newly imported mesh objects."""
    before_objs = set(bpy.data.objects)
    print(f"Importing raw mesh from GLB: {filepath}")
    bpy.ops.import_scene.gltf(filepath=filepath)
    after_objs = set(bpy.data.objects)
    
    new_objs = after_objs - before_objs
    mesh_objs = [obj for obj in new_objs if obj.type == 'MESH']
    
    if not mesh_objs:
        raise ValueError(f"No mesh objects found in imported GLB: {filepath}")
    
    # If multiple meshes are imported, join them into a single object
    if len(mesh_objs) > 1:
        print(f"Joining {len(mesh_objs)} imported mesh objects...")
        bpy.ops.object.select_all(action='DESELECT')
        for mesh in mesh_objs:
            mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh_objs[0]
        bpy.ops.object.join()
        return bpy.context.view_layer.objects.active
    else:
        return mesh_objs[0]

def decimate_mesh(obj, target_faces=50000):
    """Applies a Decimate modifier to reduce face count below target_faces."""
    # Ensure active object
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    
    current_faces = len(obj.data.polygons)
    print(f"Current face count of raw mesh: {current_faces}")
    
    if current_faces > target_faces:
        ratio = target_faces / current_faces
        print(f"Adding Decimate Modifier with ratio: {ratio:.4f}")
        mod = obj.modifiers.new(name="Decimate", type='DECIMATE')
        mod.ratio = ratio
        bpy.ops.object.modifier_apply(modifier=mod.name)
        print(f"Decimated face count: {len(obj.data.polygons)}")
    else:
        print("Mesh face count is already below target limit. Skipping decimation.")

def align_meshes(source_obj, target_obj):
    """Aligns source_obj's center and scales its Z-axis to match target_obj."""
    print("Aligning and scaling source mesh to match target template...")
    
    # Calculate bounding boxes in world space
    target_corners = [target_obj.matrix_world @ Vector(corner) for corner in target_obj.bound_box]
    source_corners = [source_obj.matrix_world @ Vector(corner) for corner in source_obj.bound_box]
    
    target_min = Vector((min(c[0] for c in target_corners), min(c[1] for c in target_corners), min(c[2] for c in target_corners)))
    target_max = Vector((max(c[0] for c in target_corners), max(c[1] for c in target_corners), max(c[2] for c in target_corners)))
    
    source_min = Vector((min(c[0] for c in source_corners), min(c[1] for c in source_corners), min(c[2] for c in source_corners)))
    source_max = Vector((max(c[0] for c in source_corners), max(c[1] for c in source_corners), max(c[2] for c in source_corners)))
    
    target_center = (target_min + target_max) / 2
    source_center = (source_min + source_max) / 2
    
    # Translate source to align centers
    translation = target_center - source_center
    source_obj.location += translation
    bpy.context.view_layer.update()
    
    # Scale source Z-axis (height) uniformly to match target Z-axis height
    target_height = target_max.z - target_min.z
    source_height = source_max.z - source_min.z
    
    if source_height > 0.001:
        scale_factor = target_height / source_height
        source_obj.scale *= scale_factor
        bpy.context.view_layer.update()
        print(f"Scaled source mesh by factor: {scale_factor:.4f}")
    
    # Apply location and scale transforms
    bpy.ops.object.select_all(action='DESELECT')
    source_obj.select_set(True)
    bpy.context.view_layer.objects.active = source_obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

def setup_bake_material(target_obj, image_name="BakedTexture", width=2048, height=2048):
    """Prepares target_obj's material node tree with an active image texture node for baking."""
    if not target_obj.data.materials:
        mat = bpy.data.materials.new(name="BakeMaterial")
        target_obj.data.materials.append(mat)
    else:
        mat = target_obj.data.materials[0]
        
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    
    # Find or create Image Texture node
    tex_node = None
    for node in nodes:
        if node.type == 'TEX_IMAGE':
            tex_node = node
            break
            
    if not tex_node:
        tex_node = nodes.new(type='ShaderNodeTexImage')
        tex_node.location = (-300, 300)
        
    # Create the target image
    if image_name in bpy.data.images:
        bpy.data.images.remove(bpy.data.images[image_name])
        
    bake_image = bpy.data.images.new(image_name, width=width, height=height, alpha=True)
    tex_node.image = bake_image
    
    # Set texture node as active and selected so Blender knows where to bake
    nodes.active = tex_node
    tex_node.select = True
    
    return bake_image

def run_cycles_bake(source_obj, target_obj, output_image_path):
    """Executes Cycles Selected-to-Active Diffuse baking."""
    print("Configuring Cycles render settings for Selected-to-Active baking...")
    
    # Configure Cycles
    bpy.context.scene.render.engine = 'CYCLES'
    
    # Setup GPU acceleration (CUDA fallback to CPU)
    cycles_preferences = bpy.context.preferences.addons['cycles'].preferences
    cycles_preferences.compute_device_type = 'CUDA'
    cycles_preferences.get_devices()
    gpu_enabled = False
    for device in cycles_preferences.devices:
        if device.type == 'CUDA':
            device.use = True
            gpu_enabled = True
            
    if gpu_enabled:
        bpy.context.scene.cycles.device = 'GPU'
        print("Cycles configured to GPU (CUDA)")
    else:
        bpy.context.scene.cycles.device = 'CPU'
        print("Cycles falling back to CPU")
        
    # Low sample count is fine for diffuse color projection
    try:
        bpy.context.scene.cycles.bake_samples = 4
    except AttributeError:
        pass
        
    # Setup selected-to-active
    bpy.context.scene.render.bake.use_selected_to_active = True
    bpy.context.scene.render.bake.margin = 8
    bpy.context.scene.render.bake.cage_extrusion = 0.08
    bpy.context.scene.render.bake.max_ray_distance = 0.5
    
    # Select source, then target, make target active
    bpy.ops.object.select_all(action='DESELECT')
    source_obj.select_set(True)
    target_obj.select_set(True)
    bpy.context.view_layer.objects.active = target_obj
    
    print("Baking diffuse color map...")
    bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'})
    
    # Save image
    bake_image = target_obj.data.materials[0].node_tree.nodes.active.image
    bake_image.filepath_raw = output_image_path
    bake_image.file_format = 'PNG'
    bake_image.save()
    print(f"Successfully saved baked texture to: {output_image_path}")

def create_dummy_template():
    """Generates a dummy cylinder target mesh with UVs if no template rig is provided."""
    print("Warning: Template file not found or not specified. Creating dummy template mesh for verification...")
    # Clear default startup items
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.object.select_by_type(type='MESH')
    bpy.ops.object.delete()
    
    bpy.ops.mesh.primitive_cylinder_add(radius=0.5, depth=2.0, location=(0, 0, 1.0))
    dummy_obj = bpy.context.view_layer.objects.active
    dummy_obj.name = "Template_Mesh_Dummy"
    
    # Add simple material
    mat = bpy.data.materials.new(name="BakeMaterial")
    dummy_obj.data.materials.append(mat)
    
    return dummy_obj, None

def main():
    if '--' in sys.argv:
        args_start = sys.argv.index('--') + 1
        script_args = sys.argv[args_start:]
    else:
        script_args = []
        
    parser = argparse.ArgumentParser(description="Headless Blender Optimization & Baking Bridge")
    parser.add_argument("--input", required=True, help="Path to raw TRELLIS .glb file")
    parser.add_argument("--template", required=False, help="Path to template .blend file")
    parser.add_argument("--output", required=True, help="Path to output optimized .fbx file")
    parser.add_argument("--decimate-faces", type=int, default=50000, help="Target face count limit")
    
    args = parser.parse_args(script_args)
    
    print("=========================================")
    print("Starting Blender Headless Optimization...")
    print(f"Input: {args.input}")
    print(f"Template: {args.template}")
    print(f"Output: {args.output}")
    print("=========================================")
    
    target_mesh = None
    armature_obj = None
    
    # Load template scene if exists
    if args.template and os.path.exists(args.template):
        if args.template.lower().endswith('.blend'):
            print(f"Opening template blend file: {args.template}")
            bpy.ops.wm.open_mainfile(filepath=args.template)
        elif args.template.lower().endswith('.fbx'):
            print(f"Importing template FBX file: {args.template}")
            clear_scene_except_templates([])
            bpy.ops.import_scene.fbx(filepath=args.template)
        elif args.template.lower().endswith('.obj'):
            print(f"Importing template OBJ file: {args.template}")
            clear_scene_except_templates([])
            try:
                bpy.ops.wm.obj_import(filepath=args.template)
            except AttributeError:
                bpy.ops.import_scene.obj(filepath=args.template)
        else:
            raise ValueError(f"Unsupported template file format: {args.template}")
        
        # Discover template mesh and armature
        template_meshes = [obj for obj in bpy.data.objects if obj.type == 'MESH']
        armatures = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']
        
        if not template_meshes:
            raise ValueError(f"No mesh objects found in template file: {args.template}")
            
        target_mesh = template_meshes[0]
        if armatures:
            armature_obj = armatures[0]
            print(f"Found template armature: {armature_obj.name}")
        print(f"Found template target mesh: {target_mesh.name}")
    else:
        target_mesh, armature_obj = create_dummy_template()
        
    # Create keeping list so we don't clear the template mesh
    keep_list = [target_mesh]
    if armature_obj:
        keep_list.append(armature_obj)
        
    # Clear any other objects from the scene (like startup cube, lights, cameras) to keep it clean
    clear_scene_except_templates(keep_list)
    
    # Import the raw TRELLIS GLB mesh
    source_mesh = import_glb(args.input)
    print(f"Imported source mesh: {source_mesh.name}")
    
    # Decimate the raw mesh if it's too dense
    decimate_mesh(source_mesh, args.decimate_faces)
    
    # Scale and translate the raw mesh to align with template coordinates
    align_meshes(source_mesh, target_mesh)
    
    # Prepare texture node
    output_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(output_dir, exist_ok=True)
    
    base_name = os.path.basename(args.output).split('.')[0]
    tex_path = os.path.join(output_dir, f"{base_name}_tex.png")
    
    setup_bake_material(target_mesh)
    
    # Execute selected-to-active bake
    run_cycles_bake(source_mesh, target_mesh, tex_path)
    
    # Delete raw source mesh
    print("Cleaning up raw source mesh...")
    bpy.ops.object.select_all(action='DESELECT')
    source_mesh.select_set(True)
    bpy.ops.object.delete()
    
    # Save out the optimized template model as FBX
    print("Exporting optimized mesh to FBX...")
    bpy.ops.object.select_all(action='DESELECT')
    target_mesh.select_set(True)
    if armature_obj:
        armature_obj.select_set(True)
        bpy.context.view_layer.objects.active = armature_obj
    else:
        bpy.context.view_layer.objects.active = target_mesh
        
    bpy.ops.export_scene.fbx(
        filepath=args.output,
        use_selection=True,
        object_types={'ARMATURE', 'MESH'},
        use_mesh_modifiers=True,
        add_leaf_bones=False,
        bake_anim=True
    )
    print(f"Export completed! Clean FBX saved to: {args.output}")
    print("=========================================")

if __name__ == "__main__":
    main()
