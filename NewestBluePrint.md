# AI Pipeline Implementation Plan & Project Code Atlas

## High-Level System Architecture Overview
This system operates as a fully automated 3D-to-2D asset pipeline designed to process batches of character turnaround concepts into production-ready, 8-directional animated 2D sprite sheets. 

The pipeline runs completely locally through a series of connected Python layers:
1. **Trellis 2 Layer:** Ingests a 2D turnaround illustration and outputs a textured 3D mesh (`.glb`).
2. **Blender Headless Core Engine:** Imports the `.glb`, executes mesh decimation, scales either the male or female master skeleton template to fit the asset dimensions, applies automatic vertex weight skins, binds modular attachments (hair/hats), and injects script-defined colors into a custom Paper Doll shader layout.
3. **Multi-Angle Camera Engine:** Headlessly rotates the armature 8 times in 45-degree increments, exporting raw frame sequences for both diffuse color passes and surface vector Normal Maps.
4. **Stitching & Manifest Layer:** Utilizes the Pillow library to compress the frame sequences into grid sprite sheets and writes out a frame-accurate coordinate `.json` atlas map for the game engine.

---

## 🗺️ Code Atlas & Explicit API Specification
*AI Model Instruction: Reference this index to understand exact function signatures, data structures, and CLI arguments without searching or guessing naming conventions across files.*

### 1. `main_pipeline.py`
The central orchestration script. Reads character configuration profiles and dispatches tasks to subprocesses.
* **Key Data Structure (`citizen_profile` schema):**
    ```json
    {
      "citizen_id": "string (e.g., 'character_male_base')",
      "gender": "string ('male' | 'female')",
      "height_scale": "float (0.80 to 1.20)",
      "width_scale": "float (0.80 to 1.20)",
      "skin_tone": "array of 4 floats [R, G, B, A]",
      "shirt_color": "array of 4 floats [R, G, B, A]",
      "pants_color": "array of 4 floats [R, G, B, A]",
      "attachment_file": "string (e.g., 'hat_baker.obj')"
    }
    ```

### 2. `core/trellis_runner.py`
Handles local Trellis 2 ML inference tasks.
* **Primary Function:** `generate_mesh_from_turnaround(image_path: str, output_glb_path: str) -> bool`

### 3. `core/blender_headless_core.py`
The internal Python script executed inside Blender's background process via CLI.
* **Invoked via CLI Commands:**
    ```bash
    blender -b -P core/blender_headless_core.py -- --input [path_to_glb] --profile [path_to_profile_json] --output-dir [path_to_frame_output]
    ```
* **Core Function Signatures:**
    * `optimize_and_bake_mesh(ai_mesh_path: str, template_mesh_path: str, output_path: str) -> None`
        * Imports the messy Trellis mesh and your clean UV template model. Decimates the AI mesh, triggers Selected-to-Active Cycles baking to project the colors onto the clean layout sheet, and exports a low-poly, clean-UV `.fbx`.
    * `inject_paper_doll_materials(material_name: str, profile_data: dict) -> None`
        * **Node Hooks:** Updates shader values via named inputs: `"Injected_Skin_RGB"`, `"Injected_Shirt_RGB"`, `"Injected_Pants_RGB"`.

---

## ⚠️ AI Model Guardrails & Execution Instructions
- **Context Preservation Rule:** Concentrate ONLY on the currently active step. Do not rewrite code blocks for steps marked completed.
- **Incremental Implementation:** Generate functional, modular code blocks that can be unit-tested immediately before adding more complexity.
- **Explicit Wait Rule:** At the end of every numbered step, you **must print a bold message** instructing the developer to verify the output and confirm whether you should proceed or halt so they can spin up a clean conversation container if context limits are reached.

---

## 🛠️ Phase-by-Phase Implementation Checklist

### [ ] Step 1: Core Environment Setup & Local Trellis 2 Verification
*Objective:* Build the pipeline stage that initializes your environmental dependencies and leverages local Trellis 2 inference to process your turnaround images into raw 3D geometry.

- [ ] **1.1 Establish Workspace Framework:** Install foundational ML modules (`torch`, `torchvision`, `xformers`) mapped to your CUDA toolkit.
- [ ] **1.2 Construct `core/trellis_runner.py`:** Build the functional wrapper for `generate_mesh_from_turnaround` to process an image source and drop a textured `.glb` inside `workspace/01_raw_3d/`.
- [ ] **1.3 Execution Unit Test:** Confirm that running the script against `workspace/00_source_images/character_male_base.png` generates a complete 3D model file without memory leakages.

> **🛑 STOP & PAUSE WORK: CRITICAL SYSTEM CHECKPOINT**
> **Do not write any more code. Ask the developer to test this stage. Instructions:**
> *"Please execute the Trellis extraction loop test. Once you confirm a valid `.glb` mesh is created, close this chat container, open a new session, paste this plan back in, and explicitly command me to begin Step 2."*

---

### [ ] Step 2: Headless Blender Optimization & UV Texture Projection Bridge
*Objective:* Write the core mesh-baking and decimation backend script. This script takes the messy AI mesh, scales it, traces its colors onto your clean UV map, shrinks the polycount, and spits out clean files for you to send to Mixamo.

- [ ] **2.1 Construct `core/blender_headless_core.py` (Baking Section):**
  * Write functions to import the raw Trellis geometry alongside a clean template mesh.
  * Apply a **Decimate Modifier** to reduce density below 50,000 polygons cleanly.
  * Implement Selected-to-Active texture projection via Cycles to transfer the colors onto your structured `UVGuide.png` grid coordinates.
  * Delete the raw Trellis mesh and save out an optimized, low-poly, clean-UV model to `workspace/02_optimized_fbx/character_male_base.fbx`.

> **🛑 STOP & PAUSE WORK: CRITICAL DELIVERABLE STOP**
> **Do not write any more code. Ask the developer to test this stage. Instructions:**
> *"The pipeline has completed the optimization phase. Please grab your two reduced-size, clean-UV files from `workspace/02_optimized_fbx/`, upload them to Mixamo to attach your animation sets, and save them into the animations folder. Once done, open a clean chat session and command me to start Step 3."*

---

### [ ] Step 3: Modular Attachment Fitting & Paper Doll Shading Engine
*Objective:* Automate loading external accessories and mutating materials programmatically.

- [ ] **3.1 Implement Static Accessory Mounting Logic:** Import external hair/hat assets and anchor them dynamically to the rig's `Head` bone space.
- [ ] **3.2 Write Material Property Injections:** Target the material node trees and feed structural color array definitions straight into your named shader parameters (`"Injected_Skin_RGB"`, etc.).

> **🛑 STOP & PAUSE WORK:** Do not write any more code. Ask the developer to test this stage. Instructions: *"Please check your shaded layout view to ensure attachments track correctly. Confirm readiness to move to Step 4."*

---

### [ ] Step 4: 8-Way Multi-Angle Rendering Loop Engine
*Objective:* Drive the background camera engine to loop through directions and render consecutive file sequences for diffuse and normal channels.

- [ ] **4.1 Configure Rendering Engine Properties Programmatically:** Enforce Eevee rendering configurations, turn on alpha transparency flags, and lock outputs to RGBA image streams.
- [ ] **4.2 Write the 45-Degree Rotation Iterator Loop:** Bind your targeted Mixamo animation actions, spin the armature through 8 incremental steps on its Z-axis, and bake matching frame sets of diffuse color and vector surface normal maps.

> **🛑 STOP & PAUSE WORK:** Do not write any more code. Ask the developer to test this stage. Instructions: *"Please confirm your raw frame assets are properly exported to your directory folders, then specify whether to continue here or start a fresh chat for Step 5."*

---

### [ ] Step 5: Pillow Packing Engine & Metadata JSON Generation
*Objective:* Collect raw frame image arrays, assemble compact sheet grids, and export structural metadata manifests.

- [ ] **5.1 Write `core/spritesheet_packer.py`:** Process loose frame image arrays via Pillow, compiling them onto an aligned transparent grid sheet. Export final color and normal sheets.
- [ ] **5.2 Write Engine Meta-JSON Exporter:** Map exact bounding coordinates for every frame cell and write a clean, machine-readable `sprite_atlas.json` map right alongside your graphics.