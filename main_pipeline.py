import os
import sys
import json
import argparse
import subprocess

# Paths to executables
PYTHON_EXE = sys.executable
BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"

def run_command(cmd, desc="Running command"):
    print(f"\n--- {desc} ---")
    print(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True)
    
    stdout = result.stdout.decode('utf-8', errors='replace') if result.stdout else ""
    stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ""
    
    # Ensure stdout and stderr can be printed to the current console encoding without crashing
    console_encoding = sys.stdout.encoding or 'utf-8'
    safe_stdout = stdout.encode(console_encoding, errors='replace').decode(console_encoding)
    safe_stderr = stderr.encode(console_encoding, errors='replace').decode(console_encoding)
    
    if result.returncode != 0:
        print(f"Error: {desc} failed!")
        print("STDOUT:", safe_stdout)
        print("STDERR:", safe_stderr)
        return False
    print("SUCCESS")
    if safe_stdout.strip():
        print(safe_stdout)
    return True

def main():
    parser = argparse.ArgumentParser(description="3D to Animated Spritesheet Pipeline Orchestrator")
    parser.add_argument("--profile", required=True, help="Path to character profile JSON")
    parser.add_argument("--front-img", required=True, help="Path to front-facing turnaround drawing")
    parser.add_argument("--back-img", help="Path to back-facing turnaround drawing (optional)")
    parser.add_argument("--side-img", help="Path to side-facing turnaround drawing (optional)")
    parser.add_argument("--skip-trellis", action="store_true", help="Skip TRELLIS 3D model generation")
    parser.add_argument("--skip-bake", action="store_true", help="Skip Blender texture baking")
    parser.add_argument("--skip-render", action="store_true", help="Skip camera loop rendering")
    parser.add_argument("--skip-pack", action="store_true", help="Skip spritesheet packing")
    
    args = parser.parse_args()
    
    # Load profile data
    if not os.path.exists(args.profile):
        print(f"Error: Profile JSON not found at {args.profile}")
        sys.exit(1)
        
    with open(args.profile, 'r') as f:
        profile = json.load(f)
        
    citizen_id = profile.get("citizen_id", "character")
    gender = profile.get("gender", "male")
    
    print("=================================================================")
    print(f"Starting pipeline orchestration for: {citizen_id} ({gender})")
    print("=================================================================")
    
    # Define file paths
    raw_3d_dir = "workspace/01_raw_3d"
    opt_fbx_dir = "workspace/02_optimized_fbx"
    frames_dir = "workspace/03_frames"
    spritesheet_dir = "workspace/04_spritesheets"
    
    glb_output = os.path.join(raw_3d_dir, f"{citizen_id}.glb")
    fbx_output = os.path.join(opt_fbx_dir, f"{citizen_id}.fbx")
    unrigged_template = os.path.join("library", "skeletons", f"template_unrigged_{gender}.fbx")
    rigged_template = os.path.join("library", "skeletons", f"template_rig_{gender}.blend")
    
    # Ensure Blender exists
    if not os.path.exists(BLENDER_EXE):
        print(f"Error: Blender executable not found at: {BLENDER_EXE}")
        print("Please configure the path in main_pipeline.py.")
        sys.exit(1)
        
    # STAGE 1: TRELLIS Multi-image Inference
    if not args.skip_trellis:
        image_inputs = [args.front_img]
        if args.back_img:
            image_inputs.append(args.back_img)
        if args.side_img:
            image_inputs.append(args.side_img)
            
        print("\n--- Stage 1: Running TRELLIS 3D Generation ---")
        # Run trellis runner via imported module to keep CUDA loaded cleanly
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from core.trellis_runner import generate_mesh_from_turnaround
        success = generate_mesh_from_turnaround(image_inputs if len(image_inputs) > 1 else image_inputs[0], glb_output)
        if not success:
            print("Error: TRELLIS 3D generation failed.")
            sys.exit(1)
    else:
        print("\n--- Stage 1: Skipping TRELLIS 3D Generation ---")
        
    # STAGE 2: Blender Decimation & UV Projection Bake
    if not args.skip_bake:
        # Run decimate, UV segmentation, and bake texture script
        # No template needed — the TRELLIS mesh itself is preserved and UV-remapped
        cmd_bake = [
            BLENDER_EXE, "-b", "-P", "core/blender_headless_core.py", "--",
            "--input", glb_output,
            "--output", fbx_output,
            "--decimate-faces", "50000"
        ]
        if not run_command(cmd_bake, "Executing decimation, UV segmentation, and Cycles baking"):
            sys.exit(1)
            
        print("\n=================================================================")
        print("=== ACTION REQUIRED: MIXAMO RIGGING STEP ===")
        print("=================================================================")
        print(f"The unrigged character mesh was successfully created at:")
        print(f"  {fbx_output}")
        print("Please:")
        print("  1. Upload this FBX to Mixamo (https://www.mixamo.com).")
        print("  2. Run the Auto-Rigger, map joints, and attach your game animation clips.")
        print("  3. Download the animation clips as FBX files.")
        print(f"  4. Open Blender, import them, and save as the master template file at:")
        print(f"  {rigged_template}")
        print("Once the rigged template blend is saved, re-run this script with:")
        print("  --skip-trellis --skip-bake")
        print("=================================================================\n")
    else:
        print("\n--- Stage 2: Skipping Blender Decimation & Baking ---")
        
    # STAGE 3: Camera Rendering Loop
    if not args.skip_render:
        input_model = rigged_template
        if not os.path.exists(input_model):
            # Fall back to unrigged FBX if rigged blend doesn't exist yet
            if os.path.exists(fbx_output):
                input_model = fbx_output
                print(f"Rigged template not found. Falling back to unrigged FBX: {input_model}")
            else:
                print(f"Error: No template model found at {rigged_template} or {fbx_output}")
                sys.exit(1)
                
        cmd_render = [
            BLENDER_EXE, "-b", "-P", "core/blender_renderer.py", "--",
            "--input", input_model,
            "--profile", args.profile,
            "--output-dir", frames_dir
        ]
        if not run_command(cmd_render, "Executing 8-directional rendering loop"):
            sys.exit(1)
    else:
        print("\n--- Stage 3: Skipping Camera Rendering Loop ---")
        
    # STAGE 4: Spritesheet Packing
    if not args.skip_pack:
        char_frames_dir = os.path.join(frames_dir, citizen_id)
        cmd_pack = [
            PYTHON_EXE, "core/spritesheet_packer.py",
            "--input-dir", char_frames_dir,
            "--output-dir", spritesheet_dir
        ]
        if not run_command(cmd_pack, "Compiling final spritesheet assets"):
            sys.exit(1)
    else:
        print("\n--- Stage 4: Skipping Spritesheet Packing ---")
        
    print("\n=================================================================")
    print("Pipeline Orchestration finished successfully!")
    print(f"Diffuse Spritesheet: {spritesheet_dir}/{citizen_id}_static.png")
    print(f"Normal Spritesheet:  {spritesheet_dir}/{citizen_id}_static_normal.png")
    print(f"Atlas Manifest:       {spritesheet_dir}/{citizen_id}_static.json")
    print("=================================================================")

if __name__ == "__main__":
    main()
