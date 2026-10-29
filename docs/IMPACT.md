# Elastic plate drop test — first impact stage

**Impact / drop test** is a bounded, low-height elastic demonstrator. It uses a parametric rectangular plate and centered blunt drop weight. It is independent of imported CAD. This is a reduced modal plate-bending model, not a general 3D impact/contact solver.

## Run it

1. Open a project, or click **Impact / drop test** in the toolbox to create one when no project is open.
2. Choose **Impact / drop test** in the model tree. Its settings replace the structural/thermal/CFD properties below the tree.
3. Set plate dimensions and elastic properties, drop-weight mass, drop height and square patch width. The supplied example uses a 200 × 150 × 3 mm plate and a 0.25 kg blunt weight dropped 10 mm. All four edges are simply supported: transverse movement is restrained while rotation is permitted.
4. Choose **Run elastic drop test**. No CAD import or Gmsh mesh is needed. Existing CAD and other studies are preserved.
5. Use **Play** or the **time slider** in the main viewport. Inspect force, deflection and energy histories below the animation. The plate display scale changes only visualization; plots and exports retain actual values.
6. Choose **Export drop-test history…** for CSV. **File → File locations** provides the job folder, including `impact.npz`, `manifest.json`, `plot.png` and `report.html`.
7. Repeat with more modes and smaller time steps. An energy check alone does not establish accuracy.

Time zero is first touch. Drop height determines initial speed; the preceding free fall is not animated. Gravity acts on the weight. Plate self-weight is omitted. The block is a display symbol for the translating weight, rather than a meshed rigid body. To keep magnified bending readable, the symbol follows the displayed plate center using the computed relative weight/patch displacement. Use the displacement plot for the actual weight trajectory.

## What is solved

The plate uses symmetric Navier sine modes of a simply supported Kirchhoff–Love plate. A finite centered square patch couples the plate modes to one translating drop-weight mass. A unilateral linear contact spring transmits compression and opens without transmitting tension. Modal viscous damping is optional. An implicit-midpoint active-set integration advances the coupled system; it is not the external CalculiX or SU2 solver.

Reported histories include downward weight displacement, patch-average plate deflection, contact force, total kinetic energy, plate/contact elastic energy, dissipated energy, gravity potential and normalized energy balance. Peak force and patch displacement are tracked on every internal step; plots/animation are sampled. Plate surface colors show sampled displacement magnitude. No stress, yield, damage or failure result is calculated.

Contact stiffness and damping are illustrative inputs requiring independent justification. Energy stored elastically can return during rebound; it is different from dissipated energy. A small-deflection check does not establish that a real material remains elastic.

## Scope and numerical guards

- Low drop heights: 0.1–50 mm; weight masses: 0.05–2 kg.
- Uniform isotropic linear-elastic thin plates, centered loading and four ideal simple supports. No arbitrary CAD, off-center impact, friction, large-deformation mechanics, plasticity, fracture, penetration, material failure or through-thickness stress-wave prediction.
- Thickness / shorter side ≤ 0.05; patch width ≤ one third of the shorter side.
- Conservative plate-deflection bound and contact compression must each remain within 25% of thickness. These are starter scope guards, not material failure criteria or accuracy guarantees.
- At most 5 symmetric modes per direction (25 modes). The internal step is the smaller of the requested maximum and a frequency-based bound. At most 300000 internal steps.
- Maximum normalized energy error must remain below 1%. Unsupported inputs/responses fail with an explanation; they are not marked as valid results.

## Verification record

`tests/test_impact.py` checks the exact nondimensional first frequency of a simply supported square plate (`2π² = 19.739208802178716`), finite-patch modal coupling against independent quadrature, oscillator energy conservation/second-order phase convergence, unilateral spring rebound against its closed-form solution, and coupled response against an independent adaptive SciPy DOP853 integration. Plate-vibration background: [Leissa, NASA SP-160](https://ntrs.nasa.gov/citations/19700009156).

For the supplied 20 ms example:

| Symmetric modes per direction | Total plate modes | Actual step (µs) | Peak contact force (N) | Peak patch deflection (mm) | Maximum relative energy error |
|---|---:|---:|---:|---:|---:|
| 1 | 1 | 2.0000 | 152.6551 | 0.142617 | 1.50e-6 |
| 3 | 9 | 1.2387 | 149.4157 | 0.145484 | 1.15e-7 |
| 5 | 25 | 0.3834 | 149.2258 | 0.145732 | 6.10e-8 |

The 9-to-25-mode changes are about 0.13% in peak force and 0.17% in patch deflection. These runs refine both modal count and the automatically limited time step. Separate fixed-mode time refinement is covered by the adaptive-integrator comparison. This is numerical verification of the stated model, not experimental validation of a physical drop test.

## CLI and MCP

```powershell
open-sim impact --out runs/elastic-drop
open-sim impact --parameters drop-settings.json --out runs/another-drop
```

The JSON accepts only `impact_*` settings in SI. MCP exposes `set_impact_parameters`, `run_impact_analysis` and `get_impact_results`, bringing the catalog to 28 tools. Poll `get_job`; `show_in_desktop(project_id, view="impact")` opens time playback and plots in the main desktop. Restart an existing MCP connection to discover the additions.
