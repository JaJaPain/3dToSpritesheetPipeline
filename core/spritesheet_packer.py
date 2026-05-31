import os
import sys
import json
import argparse
import re
from PIL import Image

def natural_sort_key(s):
    """Key for sorting strings with embedded numbers naturally (e.g., frame_2 before frame_10)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def pack_spritesheet(citizen_dir, output_dir):
    """Scans frame directories, groups them by action, and compiles diffuse and normal spritesheets with JSON manifests."""
    if not os.path.exists(citizen_dir):
        print(f"Error: Character frames directory not found: {citizen_dir}")
        return False
        
    citizen_id = os.path.basename(citizen_dir)
    print(f"Packing spritesheets for character: {citizen_id}")
    
    # 1. Discover actions and angles
    # Directory structure: [citizen_id]/[action_name]_angle[degrees]/[diffuse|normal]/frame_###.png
    subdirs = [d for d in os.listdir(citizen_dir) if os.path.isdir(os.path.join(citizen_dir, d))]
    
    # Group directories by action
    # Directory format match: e.g., "walk_angle45" or "static_angle270"
    actions = {}
    for subdir in subdirs:
        match = re.match(r'^(.*)_angle(\d+)$', subdir)
        if match:
            action_name = match.group(1)
            angle = int(match.group(2))
            if action_name not in actions:
                actions[action_name] = []
            actions[action_name].append((angle, subdir))
            
    if not actions:
        print("No valid action/angle subdirectories found.")
        return False
        
    os.makedirs(output_dir, exist_ok=True)
    
    # 8 canonical directions in order
    directions = [0, 45, 90, 135, 180, 225, 270, 315]
    
    for action_name, angle_folders in actions.items():
        print(f"Processing action: {action_name}")
        
        # Sort folders to ensure we map rows to directions in order: 0, 45, 90, ..., 315
        # Map angle to folder
        angle_map = {angle: folder for angle, folder in angle_folders}
        
        # Verify which frames exist. Let's look at one of the folders to determine frame count
        sample_folder = angle_folders[0][1]
        sample_diffuse_dir = os.path.join(citizen_dir, sample_folder, "diffuse")
        if not os.path.exists(sample_diffuse_dir):
            print(f"Warning: Sample diffuse folder not found: {sample_diffuse_dir}. Skipping action.")
            continue
            
        frame_files = sorted([f for f in os.listdir(sample_diffuse_dir) if f.endswith('.png')], key=natural_sort_key)
        if not frame_files:
            print(f"Warning: No frames found in {sample_diffuse_dir}. Skipping action.")
            continue
            
        frame_count = len(frame_files)
        print(f"  Frame count: {frame_count} frames per direction")
        
        # Load sample dimensions
        with Image.open(os.path.join(sample_diffuse_dir, frame_files[0])) as img:
            frame_width, frame_height = img.size
            
        # Spritesheet grid layout:
        # Rows = 8 directions (0 to 315 deg)
        # Columns = N frames
        sheet_width = frame_width * frame_count
        sheet_height = frame_height * 8
        
        print(f"  Spritesheet dimensions: {sheet_width}x{sheet_height}")
        
        # Create transparent canvases
        diffuse_sheet = Image.new("RGBA", (sheet_width, sheet_height), (0, 0, 0, 0))
        normal_sheet = Image.new("RGBA", (sheet_width, sheet_height), (128, 128, 255, 0)) # Default normal color (flat normal)
        
        atlas_data = {
            "meta": {
                "image": f"{citizen_id}_{action_name}.png",
                "normal_image": f"{citizen_id}_{action_name}_normal.png",
                "size": { "w": sheet_width, "h": sheet_height },
                "scale": "1"
            },
            "frames": {}
        }
        
        # Paste frames into grid
        for row_idx, angle in enumerate(directions):
            folder_name = angle_map.get(angle)
            if not folder_name:
                print(f"  Warning: Direction {angle} missing for action {action_name}. Row will be blank.")
                continue
                
            angle_diffuse_dir = os.path.join(citizen_dir, folder_name, "diffuse")
            angle_normal_dir = os.path.join(citizen_dir, folder_name, "normal")
            
            # Sort frames
            diff_frames = sorted([f for f in os.listdir(angle_diffuse_dir) if f.endswith('.png')], key=natural_sort_key)
            norm_frames = sorted([f for f in os.listdir(angle_normal_dir) if f.endswith('.png')], key=natural_sort_key)
            
            for col_idx in range(frame_count):
                x_pos = col_idx * frame_width
                y_pos = row_idx * frame_height
                
                # 1. Paste Diffuse Color Frame
                if col_idx < len(diff_frames):
                    diff_file = os.path.join(angle_diffuse_dir, diff_frames[col_idx])
                    with Image.open(diff_file) as f_img:
                        diffuse_sheet.paste(f_img, (x_pos, y_pos))
                        
                # 2. Paste Normal Map Frame
                if col_idx < len(norm_frames):
                    norm_file = os.path.join(angle_normal_dir, norm_frames[col_idx])
                    with Image.open(norm_file) as f_img:
                        normal_sheet.paste(f_img, (x_pos, y_pos))
                        
                # 3. Add to metadata atlas
                frame_key = f"{action_name}_angle{angle}_frame{col_idx + 1:03d}"
                atlas_data["frames"][frame_key] = {
                    "frame": { "x": x_pos, "y": y_pos, "w": frame_width, "h": frame_height },
                    "rotated": False,
                    "trimmed": False,
                    "spriteSourceSize": { "x": 0, "y": 0, "w": frame_width, "h": frame_height },
                    "sourceSize": { "w": frame_width, "h": frame_height }
                }
                
        # Export files
        diffuse_path = os.path.join(output_dir, f"{citizen_id}_{action_name}.png")
        normal_path = os.path.join(output_dir, f"{citizen_id}_{action_name}_normal.png")
        json_path = os.path.join(output_dir, f"{citizen_id}_{action_name}.json")
        
        diffuse_sheet.save(diffuse_path, "PNG")
        normal_sheet.save(normal_path, "PNG")
        
        with open(json_path, 'w') as f:
            json.dump(atlas_data, f, indent=2)
            
        print(f"  Stitched spritesheet saved to: {diffuse_path}")
        print(f"  Stitched normal map saved to: {normal_path}")
        print(f"  Atlas manifest saved to: {json_path}")
        
    return True

def main():
    parser = argparse.ArgumentParser(description="Stitch loose animation frame sequences into spritesheets")
    parser.add_index = ... # Wait!
    parser.add_argument("--input-dir", required=True, help="Base folder containing character frame sequences")
    parser.add_argument("--output-dir", required=True, help="Directory to save finished spritesheet assets")
    
    args = parser.parse_args()
    
    print("=========================================")
    print("Starting Spritesheet Packer...")
    print(f"Input frame folder: {args.input_dir}")
    print(f"Output folder: {args.output_dir}")
    print("=========================================")
    
    # Iterate through all character folders in the input directory
    if not os.path.exists(args.input_dir):
        print(f"Error: Input directory {args.input_dir} does not exist.")
        sys.exit(1)
        
    char_dirs = [os.path.join(args.input_dir, d) for d in os.listdir(args.input_dir) if os.path.isdir(os.path.join(args.input_dir, d))]
    
    # Check if the input directory itself is the character directory (contains action_angle subfolders)
    if any(re.match(r'^.*_angle\d+$', d) for d in os.listdir(args.input_dir)):
        pack_spritesheet(args.input_dir, args.output_dir)
    elif char_dirs:
        for char_dir in char_dirs:
            if any(re.match(r'^.*_angle\d+$', d) for d in os.listdir(char_dir)):
                pack_spritesheet(char_dir, args.output_dir)
    else:
        print("No character frame directories found.")
        sys.exit(1)
            
    print("Packing finished successfully!")
    print("=========================================")

if __name__ == "__main__":
    main()
