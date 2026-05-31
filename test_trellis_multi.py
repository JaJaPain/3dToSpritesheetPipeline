import os
import sys

# Ensure project root is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.trellis_runner import generate_mesh_from_turnaround

def run_test():
    print("Starting Multi-Image TRELLIS 3D Generation Unit Test...")
    
    # 3 canonical input views: Front, Back, Side
    source_imgs = [
        "TestingMaleSprites/MaleFront.png",
        "TestingMaleSprites/MaleBack.png",
        "TestingMaleSprites/MaleSideFacingRight.png"
    ]
    output_glb = "workspace/01_raw_3d/character_male_base_multi.glb"
    
    # Check source image existence
    for img in source_imgs:
        if not os.path.exists(img):
            print(f"FAILED: Source image not found at {img}")
            sys.exit(1)
        
    print(f"Source Images: {source_imgs}")
    print(f"Output GLB Path: {output_glb}")
    
    # Run multi-image inference
    success = generate_mesh_from_turnaround(source_imgs, output_glb)
    
    if success and os.path.exists(output_glb):
        glb_size = os.path.getsize(output_glb)
        print("=========================================")
        print("SUCCESS: Multi-image 3D model generated successfully!")
        print(f"Output location: {output_glb}")
        print(f"File size: {glb_size / (1024 * 1024):.2f} MB")
        print("=========================================")
    else:
        print("=========================================")
        print("FAILED: Multi-image 3D model generation failed.")
        print("=========================================")
        sys.exit(1)

if __name__ == "__main__":
    run_test()
