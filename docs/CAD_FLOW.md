# CFD on your own model

Fluid Dynamics is a study in the main model tree alongside Static Structural, Modal and Thermal. Properties, meshing, results and the convergence report stay in the main window. Original CAD and other studies are preserved.

## First external-flow study

1. Open a project and **Import CAD**. A closed STEP, IGES or BREP solid is preferred. Supported closed surface meshes use the existing repair/rebuild path.
2. Choose **Solution → CFD**, or **Fluid dynamics** in the toolbox. The same project gains a Fluid Dynamics branch; no separate CFD window opens.
3. Set **CAD scale to m**: `0.001` for millimeter coordinates, `1` for meters. Choose **Solid object · create surrounding fluid** and **Navier–Stokes · SU2**.
4. Enter speed, density and dynamic viscosity. Illustrative air inputs are `10 m/s`, `1.225 kg/m³`, `0.0000181 Pa·s`; use properties appropriate to your conditions. Choose positive global X, Y or Z flow. Reorient the source model for another angle.
5. Choose Laminar or Turbulent · Spalart–Allmaras. Turbulence is a modeling assumption, not an automatic accuracy upgrade. Set near-model mesh size in mm and enclosure padding. The downstream extent is longer than upstream.
6. **Build fluid mesh / preview setup** subtracts your solid from a surrounding fluid enclosure without changing the source file. Geometry displays the body; Fluid mesh displays the enclosure. External inlet/outlet faces are automatic, so ordinary external studies need no manual port picking.
7. **Run CFD study**. It runs in the background with progress and cancellation. Use the Fluid Dynamics tree to view velocity on the center slice, pressure on the body surface, and the convergence/export report. These are solved fields with deformation disabled.
8. Repeat with finer near-body mesh and larger enclosure. Compare quantities of interest before using results for engineering decisions.

The displayed center slice is cropped near the body for readability; the solver uses the complete enclosure. CSV, NPZ and VTK retain full-volume fields in SI. Pressure is gauge pressure relative to the outlet reference.

### Preview the flow direction

CFD previews show cyan **inlet** arrows, orange **outlet** arrows and a camera-aligned **Flow +X/Y/Z** indicator. Open **Fluid mesh** to see the actual enclosure boundaries; the direction indicator stays visible on body-only views. Arrows show boundary setup, not solved streamlines or a prediction of the wake. Their lengths are illustrative. Outlet arrows indicate outward pressure-boundary orientation, not a prescribed outlet speed.

Changing flow direction or speed updates the preview immediately. Face-picking drafts update arrows before saving. An inlet that points sideways or out of the selected surface turns red and displays a warning: change the flow direction or restore automatic inlet/outlet regions. Rebuild the fluid mesh after changing geometry settings. New meshes include exact boundary geometry; older saved external previews reconstruct planar enclosure arrows from their surface catalogue. Rebuild older meshes for detailed region-box previews.

## Internal passages

Import the closed volume **occupied by fluid**, rather than pipe-wall material. Choose **Existing fluid volume / passage**. Pick inlet/outlet faces on the fluid mesh using **Pick flow inlet/outlet**, then save. Blank selections use the minimum/maximum planes along the chosen axis. Other surfaces are stationary no-slip walls.

SU2 imposes a velocity inlet in the selected positive global direction and zero-gauge-pressure outlet. This starter setup does not offer arbitrary inlet vectors, moving walls or separate conditions on every boundary. Refine near ports: a coarse inlet can converge algebraically while failing the independent boundary-flux check. Changing fluid geometry settings clears stale port selections.

The older **Creeping flow · Re≤1** solver remains for pressure-driven fluid passages. It solves incompressible Stokes equations with MINI tetrahedra and independent pressure-traction ports. It requires fluid-volume mode and rejects a conservative peak Reynolds estimate above one. It does not construct an enclosure. Its 7000-node / 35000-tetrahedron cap is separate from the SU2 mesh cap of 500000 tetrahedra.

## Installation and scope

Install the pinned official Windows x64 SU2 release once from the repository root:

```powershell
.venv\Scripts\python.exe tools/install_su2.py
```

The installer verifies the release archive SHA-256 before extracting under `.tools`. No administrator access is required. Other installations can set `SU2_CFD_EXECUTABLE`. See [dependency source, version and license](DEPENDENCIES.md).

The native adapter solves steady incompressible Navier–Stokes, optionally with Spalart–Allmaras RANS, and requires Mach ≤ 0.3. It normalizes length, speed and density internally, then restores fields to SI. Finite inertia is supported beyond the old Stokes Re≤1 limit.

A successful process exit alone is insufficient: the app checks final normalized flow/turbulence residuals and independently integrates boundary flux. Runs above the residual target (allowing 0.05 log10 rounding) or above 5% boundary-flux imbalance fail and retain native partial files/logs. Passing does not establish mesh independence or drag accuracy. Automated prism layers/y+ assessment, experimental validation, transient wakes, compressibility, fluid/thermal coupling and integrated engineering lift/drag studies remain future work. Separated flows may have no stable steady solution.

## Checks and automation

`tests/test_main_cfd.py` checks that imported solids remain voids in fluid meshes, millimeter scaling works, source bytes remain unchanged, a real native finite-inertia sphere solve meets residual/flux checks, and the main-window workflow uses the current project without a CFD popout. The sphere run is an integration check, not independent aerodynamic validation. Original cylinder/pipe/plate analytical verification remains in [CFD](CFD.md).

Legacy Stokes tests retain square-duct mesh refinement. At 1.2 mm mesh size the flow is approximately 5.97% below the fully developed reference; pressure-traction ends differ from ideal fully developed boundary data. Small conservation residuals do not remove spatial/end-condition errors. See the [LBNL square-duct reference](https://escholarship.org/content/qt5qx3k9sd/qt5qx3k9sd.pdf) and [published MINI formulation study](https://arxiv.org/abs/2110.14462).

MCP supports `import_cad`, `set_cfd_parameters`, `run_cfd_analysis`, `get_job` and `get_cfd_results`. For your solid set `cfd_case="cad"`, `cfd_backend="su2"`, `cfd_domain_mode="external"`, scale, mesh, speed, density and viscosity. Optional fields include `cfd_flow_axis`, `cfd_turbulence` (`none`/`sa`), `cfd_padding`, `cfd_iterations`, `cfd_residual_target`, and independent port regions. Main views: `cfd_slice`, `cfd`, `cfd_report`.

```powershell
open-sim cfd --case cad --cad my-part.step --parameters fluid-settings.json --out runs/my-flow
```

Specify backend/domain in JSON: old API configurations retain Stokes defaults for compatibility. Native jobs save mesh, configuration, solver log/history, SI nodal CSV, NPZ, VTK, interactive views and convergence reports in their job folder.
