# Modal analysis

The native desktop, command line and MCP server now run CalculiX frequency extraction for a single isotropic elastic solid with its X-min face fully fixed. This solves `K φ = ω² M φ` and reports `f=ω/(2π)` in Hz. Positive mass density is required. No force, static prestress, damping or forced response is included.

## Desktop

1. Import one closed solid or create the Cantilever preset.
2. Set Young's modulus, Poisson ratio and **Density (kg/m³)**. The initial density is 7,850 kg/m³; choose the value appropriate for your material.
3. Set **Requested modes** (1–30), mesh size and element order. Prefer C3D10 quadratic elements for bending; C3D4 may be too stiff on coarse meshes.
4. Click **Modal analysis** in the toolbox or **Solution → Modal**. The job runs in the background and locks analysis inputs until completion.
5. Choose a frequency in the **Mode** selector, then click **Animate mode**. Pan, rotate, zoom, theme and component selection work as in the static viewer.

The displayed vector magnitude is normalized to a maximum of 1 for each mode; units are dimensionless. Its sign and scale are arbitrary. Animation plays at 1 Hz for inspection, regardless of the physical natural frequency. Contours show the normalized eigenvector, rather than instantaneous forced-response displacement. The auto deformation amplitude is a display choice. Static force settings remain stored but are ignored by modal solves.

Static and modal results are kept as separate job kinds. Editing inputs makes previous results stale; old files remain in job history. Selecting another mode does not rerun the solver. A persisted mode number outside a newly completed result's range resets to mode 1 in the desktop.

## Command line

```powershell
.\.venv\Scripts\open-sim.exe modal beam.step --mesh-size 0.0067 --order 2 --young 210000000000 --poisson 0.3 --density 7850 --modes 6 --out runs\modal-beam
.\.venv\Scripts\open-sim.exe validate-modal --out runs\modal-reference
```

Use a new output directory each time. Outputs include frequencies and eigenvalues in `summary.json`, one `mode-N.html` and `mode-N.vtk` per eigenmode, `modes.npz` with raw solver and normalized vectors, the input deck, DAT/FRD, logs and provenance manifest. Normalized VTK vectors are named `mode_shape_normalized`.

## MCP

The server exposes 16 tools. Configure the shared mesh and elastic properties with `set_analysis_parameters`, then call `set_modal_parameters(project_id, density_kg_m3, mode_count)`, `run_modal_analysis(project_id)`, poll `get_job`, read `get_modal_results`, and select `show_in_desktop(project_id, view="modal", mode=3)`. Results include frequencies and per-mode viewer/VTK paths. Clients already connected to the old 13-tool server must reconnect to load the expanded catalog.

Parameter validation stays independent of native meshing libraries in the MCP process. Gmsh and CalculiX run in the background worker, avoiding a native-library import hang during settings calls.

## Verification and limits

The [repeatable beam study](modal/REPORT.md) checks all six lowest bending modes against Euler–Bernoulli theory on three meshes and checks a second density on the identical medium mesh. It also checks fixed-node values and longitudinal edge-shape correlation. Square-section bending modes come in near-degenerate pairs: their order, orientation and sign can change without changing the physical eigenspace.

The solver output parser rejects missing/duplicate modes or nodes, nonfinite vectors, nonpositive or complex frequencies, inconsistent angular/cyclic units, zero mode shapes and violations of the fixed support. It does not compute a full stiffness/mass eigenpair residual; the recorded shape MAC is a longitudinal edge comparison, not a full mass-weighted 3D MAC.

Arbitrary supports, free-free rigid-body modes, preload/stress stiffening, damping, modal superposition, response spectra, harmonic/transient response, contact and nonlinear modal analysis remain unavailable. This first modal feature does not make those greyed-out analyses executable. Check mesh convergence for each new geometry.
