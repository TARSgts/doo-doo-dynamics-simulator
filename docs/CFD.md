# CFD studies and analytical benchmarks

For your own model, use the [main-window CAD workflow](CAD_FLOW.md). It supports automatic fluid enclosures around imported solids, existing internal fluid volumes, native SU2 Navier–Stokes and optional Spalart–Allmaras RANS. The legacy pressure-driven Stokes solver remains limited to Re≤1.

The original analytical benchmark models below remain available through **Validation → CFD checks**. Their reports display in the main viewport. They are distinct simplified equations, not validation of the general SU2 CAD adapter. These benchmark models use NumPy and Matplotlib without an external solver.

| Case | Numerical method | What you get | Supported physics |
|---|---|---|---|
| Cylinder in a flow | Constant-strength source boundary panels; solve impermeability equations | Surface Cp, exterior velocity/streamline plot, numerical/reference comparison | 2D incompressible inviscid flow, slip surface, zero circulation |
| Laminar round pipe | Finite volumes over radial annuli; solve the viscous momentum balance | Axial velocity profile, volume flow rate, Reynolds number, wall shear and Darcy friction factor | Steady fully developed incompressible viscous flow, no-slip wall, Re < 2000 |
| Flat-plate airfoil | Cosine-spaced discrete vortices at quarter-panel points; no-penetration at three-quarter points | CL versus α sweep, lift per unit span, circulation and pressure-jump arrays | Infinitely thin 2D plate, incompressible inviscid attached-flow approximation, α within ±10° |

External-flow models require Mach ≤ 0.3 using the entered speed of sound. Their Reynolds number is contextual only: viscosity is not part of their equations. Cylinder pressure drag near zero is the ideal potential-flow result, not a prediction of real cylinder drag. The plate does not model stall, separation, viscous drag, finite-wing induced drag or a wake instability. The pipe assumes an already developed profile and does not compute its entrance region. There is no fluid/thermal coupling or heat-sink convection yet.

## Flat-plate angle sweep

Use `open-sim cfd --case flat_plate --parameters plate.json --out runs/plate` for a custom sweep. Example JSON:

```json
{
  "cfd_chord_m": 0.1,
  "cfd_speed_m_s": 10,
  "cfd_density_kg_m3": 1.225,
  "cfd_alpha_min_deg": -8,
  "cfd_alpha_max_deg": 8,
  "cfd_alpha_step_deg": 2
}
```

The report plots solved CL against `2π sin(α)` and small-angle `2πα` (radians). CSV retains CL, both references and lift per unit span. NPZ retains circulation and approximate pressure-jump arrays. Integrated CL agreement does not establish local accuracy near the singular leading edge. The main-window validation action runs the standard reference sweep; its CFD properties are for imported CAD, not editing these analytical models.

Resolution is 12–256 panels or radial cells. More pipe cells reduce the error; increasing panels cannot add missing viscous or separated-flow physics. Reports retain their actual input values. Editing controls marks the result as outdated until rerun; previously completed reports remain in job history.

## Verification

**Validation → CFD checks** runs all three cases at three resolutions, with a report containing every acceptance check. This is numerical verification against analytical solutions, not experimental validation. See [recorded results](cfd/REPORT.md).

- Cylinder: `Cp = 1 − 4 sin²θ`; compare exterior velocities at radii 1.25R, 2R and 4R to the analytical potential field. The finest 96-panel field must be within 1% of freestream, with decreasing error on refinement. Surface Cp alone is insufficient: regular polygon symmetry can reproduce it at collocation points to roundoff.
- Pipe: `u(r) = Δp(R² − r²)/(4μL)`, `Q = πR⁴Δp/(8μL)` and Darcy `f = 64/Re`. The 48-cell flow-rate error must be below 0.05%, with approximately fourfold error reduction per doubling of cells.
- Plate: compare numerical circulation-derived `CL = 2ΣΓ/(Uc)` against `2π sin α`; check maximum absolute CL error below 1e-8 and a fitted small-angle slope within 0.5% of 2π per radian.
- All normalized equation residuals must be below 1e-8.

The cylinder's exterior solution converges more slowly than its symmetric collocation pressure. The current validation reports this actual error instead of claiming the near-roundoff Cp result establishes field accuracy.

## Files and automation

CFD jobs save `report.html`, `plot.png`, `data.csv`, `flow.npz` and `manifest.json` in `<project>/jobs/<job-id>/cfd/`. Cylinder jobs also save `field.png`. Validation jobs use `cfd_validation/`, with a combined report/CSV/JSON and three individual case folders. Existing outputs are never overwritten by the numerical runner.

```powershell
open-sim cfd --case cylinder --resolution 96 --out runs/cylinder
open-sim cfd --case pipe --resolution 48 --out runs/pipe
open-sim cfd --case flat_plate --out runs/plate
open-sim validate-cfd --out runs/cfd-verification
```

`--parameters settings.json` accepts `cfd_*` fields. Stored quantities are SI (m, m/s, Pa, Pa·s, kg/m³) except angles in degrees. Desktop lengths display in mm. Parameters in that JSON override command defaults. MCP exposes **set_cfd_parameters**, **run_cfd_analysis** and **get_cfd_results**, bringing the server to 25 tools. Create a separate project, set its CFD parameters and start a CFD job; no CAD import is needed. Poll `get_job`, then fetch the report/artifacts. `run_cfd_analysis(validate_all=True)` runs the full verification suite. Restart an existing MCP connection to discover new tools. `cancel_job` stops either worker and retains partial files.

## Primary references

- [MIT Unified Engineering: potential cylinder velocity field](https://web.mit.edu/16.unified/www/archives2006-2007/FALL/problemsets_Fall_2006/PSet08/HW8.pdf).
- [Oregon State University: potential flows and flat-plate lift](https://open.oregonstate.education/intermediate-fluid-mechanics/chapter/potential-flows/).
- [Oregon State University: discrete vortex panels, quarter/three-quarter placement](https://open.oregonstate.education/intermediate-fluid-mechanics/chapter/the-panel-method-an-introduction/).
- [OpenStax: viscosity, laminar flow and Poiseuille's law](https://openstax.org/books/college-physics-ap-courses/pages/12-4-viscosity-and-laminar-flow-poiseuilles-law).

Future stages: independent aerodynamic validation of the SU2 adapter, near-wall prism layers, integrated force studies, transient wakes and conjugate heat transfer. Each needs additional verification and an explicit validity range.
