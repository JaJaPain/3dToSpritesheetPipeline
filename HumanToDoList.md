# Human Pre-Requisites & Project Setup Asset Guide

This document tracks all manual setup steps, asset acquisitions, and environment configurations you must complete before passing control to the AI automation engine. Follow these steps meticulously to prevent system execution failures.

---

## [ ] Step 1: System Dependencies & Environment Setup
Before the Python environment can touch Blender or Trellis, your operating system must have the correct low-level binaries installed and mapped to your system PATH.

- [ ] **1.1 Install Git & Git LFS:** Required to clone the Trellis repository and download large weights.
  * *Windows:* Download Git for Windows. Open terminal and run: `git lfs install`
- [ ] **1.2 Install Python 3.10 or 3.11:** **Crucial:** Do not use Python 3.12 or higher. Trellis and its underlying CUDA extensions (like `flash-attn`) will fail to compile on newer Python versions. Ensure "Add Python to PATH" is checked during installation.
- [ ] **1.3 Install Blender 4.2 LTS (or latest stable):** Download the official installer. 
  * *Crucial PATH Configuration:* You must manually add the Blender installation directory (e.g., `C:\Program Files\Blender Foundation\Blender 4.2\`) to your System Environment Variables PATH so the command `blender --version` runs successfully from a clean command prompt.
- [ ] **1.4 Install CUDA Toolkit 11.8 or 12.1:** Match this to your GPU capability to allow Trellis local inference to run at hardware speed.

---

## [ ] Step 2: Establish the Standardized UV Layout
The entire "Paper Doll" texture-swapping engine relies on every character mesh sharing identical texture coordinates.

- [ ] **2.1 Design a UV Template Grid:** Create a square 2048x2048 image canvas. Divide it into strict bounding boxes:
  * Top-Left: Skin details, hands, face textures.
  * Top-Right: Outer clothing / Shirts / Dresses.
  * Bottom-Left: Lower clothing / Pants / Skirts.
  * Bottom-Right: Footwear and loose accessory surfaces.
- [ ] **2.2 Save Layout Reference:** Export a transparent `.png` of this grid layout as `docs/uv_layout_blueprint.png`. Any 2D turnaround illustrations you feed to Trellis should loosely align their color blocks to this layout, or you must be prepared to let the script map textures to these fixed boundaries.

---

## [ ] Step 3: Create the Master Skeletons & Download Mixamo Actions
You must build your male and female base armatures manually to guarantee that joint placements behave properly during automated binding.

- [ ] **3.1 Acquire a Base Character Mesh:** Download two simple, un-rigged humanoid meshes (one male proportions, one female proportions) facing forward in an **A-Pose**. Ensure their UV wraps map perfectly to your `uv_layout_blueprint.png`.
- [ ] **3.2 Upload Base Meshes to Mixamo:** Go to the Mixamo web interface. Upload the male mesh, position the markers (chin, wrists, elbows, knees, groin), and let Mixamo auto-rig it. Repeat this exact process for the female mesh.
- [ ] **3.3 Assemble the Master Animation Library:**
  * Search Mixamo for your primary game animations: `walk`, `idle`, `wave`, `run`, `sit`.
  * Download each animation choosing the options: **FBX Binary**, **30 FPS**, **With Skin**, **No Keyframe Reduction**.
  * Rename these files to clean snake_case strings (e.g., `mixamo_walk.fbx`, `mixamo_idle.fbx`).
- [ ] **3.4 Construct the Master Blend Files:**
  * Open Blender. Import `mixamo_walk.fbx` for the male skeleton.
  * Open the *Dope Sheet > Action Editor*. Rename the imported animation action data block to `anim_male_walk`.
  * Import the rest of your downloaded male `.fbx` files into this same scene. Move their actions into the scene's data block cache and name them clearly (`anim_male_idle`, etc.).
  * Delete all imported loose meshes, leaving **only the single master armature skeleton object**. Rename this skeleton object to `Base_Armature_Male`.
  * Save this file in your project directory as `library/skeletons/template_rig_male.blend`.
  * Repeat this entire step for the female skeleton, saving the result as `library/skeletons/template_rig_female.blend`.

---

## [ ] Step 4: Build the Modular Attachment Library
Rigid elements that don't deform with skin movement must be modeled as separate static objects ready for script attachment.

- [ ] **4.1 Model/Acquire Accessories:** Build or gather loose 3D attachments (e.g., `hair_bald.obj`, `hair_braids.obj`, `hat_baker.obj`, `beard_long.obj`).
- [ ] **4.2 Align Assets to Template Origin:** Import your `template_rig_male.blend` skeleton into a workspace. Model or place your hair/hat objects so they sit perfectly on the skeleton's head. **Crucial:** Clear all transformations and set their origins to the exact world center $(0,0,0)$ before exporting each accessory back out as an individual `.obj` or `.fbx` into `library/attachments/`. This ensures that when the automated script imports them, they instantly align with the target character bone space without floating away.

---

## Verification Checkpoint
Before launching the AI coding phase, open a terminal window and verify that these items return valid outputs:
```bash
python --version     # Should return 3.10.x or 3.11.x
blender --background --version # Should return Blender 4.2+ text with no errors