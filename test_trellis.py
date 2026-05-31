import os
import sys

# Ensure project root is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.trellis_runner import generate_mesh_from_turnaround

def run_test():
    print("Starting TRELLIS 3D Generation Unit Test...")
    
    source_img = "workspace/00_source_images/character_male_base.png"
    output_glb = "workspace/01_raw_3d/character_male_base.glb"
    
    # Check source image existence
    if not os.path.exists(source_img):
        print(f"FAILED: Source image not found at {source_img}")
        sys.exit(1)
        
    print(f"Source Image: {source_img}")
    print(f"Output GLB Path: {output_glb}")
    
    # Run inference
    success = generate_mesh_from_turnaround(source_img, output_glb)
    
    if success and os.path.exists(output_glb):
        glb_size = os.path.getsize(output_glb)
        print("=========================================")
        print("SUCCESS: 3D model generated successfully!")
        print(f"Output location: {output_glb}")
        print(f"File size: {glb_size / (1024 * 1024):.2f} MB")
        print("=========================================")
    else:
        print("=========================================")
        print("FAILED: 3D model generation failed.")
        print("=========================================")
        sys.exit(1)

if __name__ == "__main__":
    run_test()
