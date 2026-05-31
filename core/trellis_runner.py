import os
import sys
from PIL import Image

# Set environment variables before importing torch/trellis modules
os.environ['SPCONV_ALGO'] = 'native'
os.environ['ATTN_BACKEND'] = 'sdpa'
os.environ['SPARSE_ATTN_BACKEND'] = 'sdpa'
os.environ['XFORMERS_DISABLED'] = '1'

# Add the trellis repository to python path
current_dir = os.path.dirname(os.path.abspath(__file__))
trellis_path = os.path.abspath(os.path.join(current_dir, '..', 'trellis'))
if trellis_path not in sys.path:
    sys.path.append(trellis_path)

try:
    from trellis.pipelines import TrellisImageTo3DPipeline
    from trellis.utils import postprocessing_utils
except ImportError as e:
    print(f"Error importing TRELLIS modules: {e}")
    print(f"sys.path: {sys.path}")
    raise

_pipeline = None

def get_pipeline():
    """Lazy load the pipeline to save memory and initialization time."""
    global _pipeline
    if _pipeline is None:
        print("Initializing TrellisImageTo3DPipeline...")
        _pipeline = TrellisImageTo3DPipeline.from_pretrained("microsoft/TRELLIS-image-large")
        _pipeline.cuda()
        print("TrellisImageTo3DPipeline initialized successfully.")
    return _pipeline

def generate_mesh_from_turnaround(image_path: str, output_glb_path: str) -> bool:
    """
    Ingests a front turnaround illustration and outputs a textured 3D mesh (.glb).
    """
    try:
        # Load and process the input image
        if not os.path.exists(image_path):
            print(f"Error: Source image not found at {image_path}")
            return False

        image = Image.open(image_path)
        
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(os.path.abspath(output_glb_path))
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        pipeline = get_pipeline()
        print(f"Running TRELLIS inference on {image_path}...")
        outputs = pipeline.run(image, seed=1)

        print("Generating GLB mesh from outputs...")
        glb = postprocessing_utils.to_glb(
            outputs['gaussian'][0],
            outputs['mesh'][0],
            simplify=0.95,      # Simplify mesh (ratio of triangles to remove)
            texture_size=1024   # Texture resolution
        )
        
        print(f"Exporting GLB to {output_glb_path}...")
        glb.export(output_glb_path)
        
        print(f"Successfully generated 3D mesh at: {output_glb_path}")
        return True
    except Exception as e:
        print(f"Error during 3D mesh generation: {e}")
        import traceback
        traceback.print_exc()
        return False
