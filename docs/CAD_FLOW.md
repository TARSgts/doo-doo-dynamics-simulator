# Imported CAD fluid-volume flow

**Solution → CFD → CAD fluid volume · 3D creeping flow** accepts a general closed single-volume CAD shape, including bends. The implementation solves the 3D incompressible Stokes equations on its tetrahedral mesh. This extends the earlier built-in cylinder, pipe and plate studies; it is not a full finite-Reynolds-number Navier–Stokes or turbulence solver.

## Setup

1. In CAD, create the volume **occupied by fluid**. For internal flow, this is the empty passage through the pipe/duct, not the material making the pipe wall. For flow around a solid object, first subtract the object from a surrounding fluid enclosure. The app does not construct this enclosure automatically.
2. Choose **Import CAD fluid volume**. STEP, IGES and BREP are preferred; existing supported closed mesh formats use the surface-rebuild path.
3. Set **CAD scale to meters**: 0.001 for millimeter coordinates, 1 for meter coordinates. Enter **Flow mesh size** in mm. CAD flow always uses linear geometry with MINI velocity bubbles; the structural element selector does not control it.
4. Enter fluid **dynamic viscosity (Pa·s)**, **density (kg/m³)** and a positive **pressure drop (Pa)**. Use a very small pressure drop initially, such as 0.00001 Pa for the supplied water-like elbow example; the correct scale depends on geometry and fluid properties.
5. Use **Inspect mesh / choose ports**. Pick inlet faces, pick outlet faces, then **Use picked port faces**. Selected CAD IDs appear in the two fields. Blank fields use X-min inlet and X-max outlet. All other surfaces are stationary no-slip walls. The edges shared between a port and a wall are no-slip, so the port mesh needs interior nodes.
6. Choose **Run flow study**. Inspect the volume flow rate, inlet/outlet mass balance and numerical residual. The report shows interior cell-centroid velocities, including bubble contributions. Its interactive result link shows rotatable surface velocity and pressure; CSV/NPZ/VTK retain volume data.

Prescribed port pressures are **normal tractions**, with zero tangential traction, not fixed nodal pressure values. Boundary nodal pressures can differ from those tractions near ends. This produces end effects relative to a fully developed infinite-duct formula. Sharp corners can also require refinement.

The initial resource limit is **7000 nodes / 35000 tetrahedra**. Increase the mesh size if exceeded. Separate projects retain inputs and results; the structural project selected in the main window is unchanged by CFD workbench actions. Replacement CAD clears stale structural, thermal and flow selections.

## Validity

Inertia is neglected. A conservative upper bound on peak velocity, using nodal speed plus the local bubble amplitude and inlet hydraulic diameter, is used to require **Re ≤ 1**. Use Reynolds numbers well below one for the creeping-flow approximation. A run exceeding the limit fails with a request to reduce pressure drop, rather than displaying a Stokes result as a general aerodynamic solution.

No turbulence, separation/stall prediction at finite Re, compressibility, transient wake, moving walls, multiple fluid materials, conjugate heat transfer or automatic external fluid-domain construction is implemented. The existing external potential-flow benchmarks do not become viscous CAD aerodynamics merely by selecting this mode.

The stable MINI element uses linear nodal velocity enriched by one quartic tetrahedral bubble per component, and linear pressure. Bubble velocities are condensed locally and recovered for volume output. A symmetric-gradient weak form applies no-slip walls and pressure traction ports. SciPy's sparse direct solver solves the scaled coupled system. No pressure penalty or arbitrary pressure pin is used to conceal a singular setup.

## Verification

Automated checks cover:

- A 100 × 10 × 10 mm square fluid duct, μ=0.001 Pa·s, ρ=1000 kg/m³, Δp=0.0001 Pa. At mesh sizes 3, 2 and 1.2 mm, flow approaches the fully developed reference `Q≈0.0351443 a⁴Δp/(μL)`. The finest flow is about **5.97%** below this reference, within the recorded 6% starter threshold. This documents limited spatial accuracy; it does not claim mesh-independent engineering precision. Pressure-traction ends are not the exact fully developed boundary data.
- Doubling pressure drop doubles flow; all normalized linear residuals and inlet/outlet flux errors are below 1e-8.
- A fused L-shaped fluid volume with its inlet normal to X and outlet normal to Y, using independently selected surfaces. The solved sample has 637 nodes / 1998 tetrahedra, conservative peak Re about **0.00579**, and relative flux imbalance below 1e-14. This is a CAD/port/conservation test, not an independent analytical elbow solution.
- Overlapping port faces, unusable coarse ports, oversized meshes and out-of-range Reynolds numbers are rejected.

Recorded square-duct comparison (`Q_reference = 3.51443e-10 m³/s`):

| Target mesh size | Nodes | Tetrahedra | Outlet flow (m³/s) | Relative reference error |
|---|---|---|---|---|
| 3 mm | 732 | 2352 | 2.40438446e-10 | 31.59% |
| 2 mm | 1748 | 6535 | 2.93530936e-10 | 16.48% |
| 1.2 mm | 6572 | 28822 | 3.30465350e-10 | 5.97% |

The fine-mesh relative inlet/outlet flux imbalance was approximately `3.13e-16`. Small conservation residuals do not eliminate the discretization/reference error shown in the table.

The straight-duct reference is documented in [Lawrence Berkeley National Laboratory's square-duct analysis](https://escholarship.org/content/qt5qx3k9sd/qt5qx3k9sd.pdf). The MINI formulation is an original implementation of the published mixed finite-element method; see [3D MINI discretization study](https://arxiv.org/abs/2110.14462) and [SciPy's sparse solver documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.spsolve.html).

## Automation

MCP uses the existing `import_cad`, `set_cfd_parameters`, `run_cfd_analysis`, `get_job` and `get_cfd_results` tools. Set `cfd_case="cad"`, `cfd_mesh_size_m`, `cfd_cad_scale`, fluid properties, pressure drop, and independent `cfd_inlet_region` / `cfd_outlet_region` dictionaries (`faces` and/or `box_m`, in SI). The original `validate_all` suite still runs the three built-in analytical models; CAD checks are in `tests/test_cad_flow.py`.

```powershell
open-sim cfd --case cad --cad fluid-volume.step --parameters fluid-settings.json --out runs/cad-flow
```

Store settings under `cfd_*` keys. The original CAD file is copied into the project and not modified. Results contain `flow.npz`, nodal `data.csv`, `results.vtk`, `results.html`, `plot.png`, `manifest.json` and the report. VTK/NPZ preserve pressures and velocities in SI; NPZ additionally retains bubble and cell-centroid velocities.
