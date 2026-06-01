"""
Diagnostic: Import an FBX and dump UV layers, material nodes, and texture info.
This reveals exactly what Blender sees after the FBX round-trip.
"""
import bpy
import sys
import os

def main():
    if '--' in sys.argv:
        args = sys.argv[sys.argv.index('--') + 1:]
    else:
        args = []

    if not args:
        print("Usage: blender -b -P fbx_diagnostic.py -- <path_to_fbx>")
        return

    fbx_path = args[0]
    print(f"\n{'='*60}")
    print(f"FBX IMPORT DIAGNOSTIC: {fbx_path}")
    print(f"{'='*60}")

    # Clear scene
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

    # Import the FBX
    bpy.ops.import_scene.fbx(filepath=fbx_path)

    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        mesh = obj.data
        print(f"\nMESH: {obj.name}")
        print(f"  Faces: {len(mesh.polygons)}")
        print(f"  Verts: {len(mesh.vertices)}")

        # UV Layers
        print(f"  UV Layers ({len(mesh.uv_layers)}):")
        for i, uv in enumerate(mesh.uv_layers):
            active_str = " [ACTIVE]" if uv.active else ""
            render_str = " [RENDER]" if uv.active_render else ""
            print(f"    [{i}] '{uv.name}'{active_str}{render_str}")

            # Sample some UV coords
            loops = uv.data
            if len(loops) > 0:
                sample = loops[0]
                print(f"         First loop UV: ({sample.uv[0]:.4f}, {sample.uv[1]:.4f})")

        # Materials
        print(f"  Materials ({len(mesh.materials)}):")
        for i, mat in enumerate(mesh.materials):
            if mat is None:
                print(f"    [{i}] None")
                continue
            print(f"    [{i}] '{mat.name}' (use_nodes={mat.use_nodes})")
            if mat.use_nodes and mat.node_tree:
                for node in mat.node_tree.nodes:
                    print(f"      Node: {node.type} ({node.name})")
                    if node.type == 'TEX_IMAGE':
                        img = node.image
                        if img:
                            print(f"        Image: '{img.name}' ({img.size[0]}x{img.size[1]})")
                            print(f"        Filepath: {img.filepath}")
                            print(f"        Packed: {img.packed_file is not None}")
                        else:
                            print(f"        Image: None")
                    if node.type == 'UVMAP':
                        print(f"        uv_map: '{node.uv_map}'")

                # Show links
                for link in mat.node_tree.links:
                    print(f"      Link: {link.from_node.name}.{link.from_socket.name} -> "
                          f"{link.to_node.name}.{link.to_socket.name}")

    # Also list all images in the blend
    print(f"\nALL IMAGES IN BLEND ({len(bpy.data.images)}):")
    for img in bpy.data.images:
        print(f"  '{img.name}' {img.size[0]}x{img.size[1]} "
              f"path='{img.filepath}' packed={img.packed_file is not None}")

    print(f"\n{'='*60}")
    print("DIAGNOSTIC COMPLETE")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
