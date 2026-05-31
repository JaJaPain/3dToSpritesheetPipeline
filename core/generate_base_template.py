import os
import sys
import bpy
from math import radians

def map_uvs(obj, min_u, max_u, min_v, max_v):
    """Maps the object's default UV coordinates to a specific UV quadrant [min_u, max_u] x [min_v, max_v]."""
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='OBJECT')
    
    mesh = obj.data
    if not mesh.uv_layers:
        mesh.uv_layers.new(name="UVMap")
    uv_layer = mesh.uv_layers.active.data
    
    # Get all loops
    uvs = [loop.uv for loop in uv_layer]
    if not uvs:
        return
        
    min_x = min(uv.x for uv in uvs)
    max_x = max(uv.x for uv in uvs)
    min_y = min(uv.y for uv in uvs)
    max_y = max(uv.y for uv in uvs)
    
    range_x = max_x - min_x
    range_y = max_y - min_y
    
    target_range_u = max_u - min_u
    target_range_v = max_v - min_v
    
    for loop in uv_layer:
        # Normalize to [0, 1]
        norm_x = (loop.uv.x - min_x) / range_x if range_x > 0 else 0.5
        norm_y = (loop.uv.y - min_y) / range_y if range_y > 0 else 0.5
        # Map to target quadrant
        loop.uv.x = min_u + norm_x * target_range_u
        loop.uv.y = min_v + norm_y * target_range_v

def create_stylized_humanoid(output_path):
    """Creates a stylized low-poly humanoid base model with clean UV mapping."""
    print("Generating stylized humanoid base mesh...")
    
    # Clear existing mesh objects
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.object.select_by_type(type='MESH')
    bpy.ops.object.delete()
    
    parts = []
    
    # 1. Head (UV Sphere) - Quadrant: Top-Left (Skin)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.22, location=(0, 0, 1.55))
    head = bpy.context.view_layer.objects.active
    head.name = "Head"
    map_uvs(head, 0.0, 0.5, 0.5, 1.0)
    parts.append(head)
    
    # 2. Torso (Cylinder) - Quadrant: Top-Right (Shirt)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.18, depth=0.6, location=(0, 0, 1.05))
    torso = bpy.context.view_layer.objects.active
    torso.name = "Torso"
    map_uvs(torso, 0.5, 1.0, 0.5, 1.0)
    parts.append(torso)
    
    # 3. Left Arm (Cylinder) - Quadrant: Top-Right (Shirt)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.06, depth=0.5, location=(-0.27, 0, 1.1))
    l_arm = bpy.context.view_layer.objects.active
    l_arm.name = "Left_Arm"
    l_arm.rotation_euler[1] = radians(15)  # Slight A-pose angle
    map_uvs(l_arm, 0.5, 1.0, 0.5, 1.0)
    parts.append(l_arm)
    
    # 4. Right Arm (Cylinder) - Quadrant: Top-Right (Shirt)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.06, depth=0.5, location=(0.27, 0, 1.1))
    r_arm = bpy.context.view_layer.objects.active
    r_arm.name = "Right_Arm"
    r_arm.rotation_euler[1] = radians(-15) # Slight A-pose angle
    map_uvs(r_arm, 0.5, 1.0, 0.5, 1.0)
    parts.append(r_arm)
    
    # 5. Left Leg (Cylinder) - Quadrant: Bottom-Left (Pants)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.07, depth=0.65, location=(-0.09, 0, 0.45))
    l_leg = bpy.context.view_layer.objects.active
    l_leg.name = "Left_Leg"
    map_uvs(l_leg, 0.0, 0.5, 0.0, 0.5)
    parts.append(l_leg)
    
    # 6. Right Leg (Cylinder) - Quadrant: Bottom-Left (Pants)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.07, depth=0.65, location=(0.09, 0, 0.45))
    r_leg = bpy.context.view_layer.objects.active
    r_leg.name = "Right_Leg"
    map_uvs(r_leg, 0.0, 0.5, 0.0, 0.5)
    parts.append(r_leg)
    
    # 7. Left Foot (Cylinder rotated) - Quadrant: Bottom-Right (Shoes)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.065, depth=0.15, location=(-0.09, -0.05, 0.085))
    l_foot = bpy.context.view_layer.objects.active
    l_foot.name = "Left_Foot"
    l_foot.rotation_euler[0] = radians(90) # Orient forward
    map_uvs(l_foot, 0.5, 1.0, 0.0, 0.5)
    parts.append(l_foot)
    
    # 8. Right Foot (Cylinder rotated) - Quadrant: Bottom-Right (Shoes)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.065, depth=0.15, location=(0.09, -0.05, 0.085))
    r_foot = bpy.context.view_layer.objects.active
    r_foot.name = "Right_Foot"
    r_foot.rotation_euler[0] = radians(90) # Orient forward
    map_uvs(r_foot, 0.5, 1.0, 0.0, 0.5)
    parts.append(r_foot)
    
    # Join all parts together
    print("Joining parts into a single base mesh...")
    bpy.ops.object.select_all(action='DESELECT')
    for part in parts:
        part.select_set(True)
    bpy.context.view_layer.objects.active = torso
    bpy.ops.object.join()
    
    base_mesh = bpy.context.view_layer.objects.active
    base_mesh.name = "Stylized_Base_Humanoid"
    
    # Apply all transforms
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    
    # Export as FBX
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    bpy.ops.export_scene.fbx(
        filepath=output_path,
        use_selection=True,
        object_types={'MESH'},
        use_mesh_modifiers=True,
        add_leaf_bones=False
    )
    print(f"Humanoid base model successfully exported to: {output_path}")

def main():
    if '--' in sys.argv:
        args_start = sys.argv.index('--') + 1
        script_args = sys.argv[args_start:]
    else:
        script_args = []
        
    if not script_args:
        print("Error: Output path argument required.")
        sys.exit(1)
        
    output_path = script_args[0]
    create_stylized_humanoid(output_path)

if __name__ == "__main__":
    main()
