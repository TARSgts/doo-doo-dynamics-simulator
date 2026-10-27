# Application icon

The app uses an original faceted gold D with a cyan deformation edge on a navy rounded tile. The PNG source and Windows ICO are packaged under `src/opensim/assets/` and shipped in the wheel. The ICO includes 16, 20, 24, 32, 40, 48, 64, 96, 128 and 256 pixel images with alpha transparency.

Qt applies the icon to application windows. On Windows the process and shortcuts share the explicit application ID `TARSgts.DooDooDynamicsSimulator.1` so the taskbar can associate the window with its launcher. `tools/create-shortcuts.ps1` creates or updates the app's Desktop and Start Menu shortcuts with the ICO and matching identity. The desktop installer runs this helper outside CI. Existing open windows need reopening to load the new icon.

Verification covered Qt loading at 16/32/256 pixels, ICO resolutions, icon assets in the built wheel, saved Windows shortcut icon/identity properties and a native window's icon handles.

## Design provenance

Created with the built-in image-generation tool. The original generated PNG is retained, and copies are stored in the project. Pillow was used only to export a multi-resolution Windows ICO; no new runtime dependency is needed. This is a new project-specific mark and does not use proprietary simulator logos.

Final generation prompt:

> Use case: logo-brand. Asset type: original Windows desktop application icon for Doo Doo Dynamics Simulator, an open-source engineering and FEA simulation workbench. Create ONE polished square icon, not an icon sheet or mockup. Use the app's existing deep navy, warm gold/orange and small cyan accent palette. The central mark is a bold, highly legible geometric capital D made from a small number of large faceted triangular elements, with a subtle cyan displaced/offset edge suggesting structural deformation and simulation. Strong silhouette, uncluttered and recognizable at 16 to 32 pixels, restrained dimensional shading, crisp edges, generous safe padding. Put the mark on a deep navy rounded-square tile; outside the tile is genuinely transparent. No words, captions, numbers, thin wireframe clutter, watermark, gradients outside the tile, or other brands' logos. The D itself is the only letter. Face-on view, clean centered app icon, no surrounding scene.
