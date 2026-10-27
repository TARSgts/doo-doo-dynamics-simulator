# Local feature review

Reviewed the locally authored additions before publishing: STL/OBJ/3MF import, cancellation, static mesh-convergence studies, axis triad and corrected viewport orientation, desktop controls, CLI and MCP tools.

## Corrections made during review

- Removed a native-mesher import from the MCP file-import path. The real stdio test previously hung on `import_cad`; shared extension constants now live in a lightweight module. The protocol test now completes with all 19 tools, modal solve and static solve.
- 3MF readers now honor declared units, build translations and the primary model relationship. Coordinates normalize to mm before applying `cad_scale`; this avoids thousandfold errors for meter-authored files. OBJ/3MF vertex indices are validated. Disconnected closed shells are rejected before reconstruction.
- Cancellation can no longer let a late example worker replace a newly imported model. A deterministic cancellation/import race test covers the write boundary.
- Convergence requires at least three genuinely refined meshes. Repeated element counts cannot establish convergence. Richardson order uses the two measured effective refinement ratios separately; unequal-ratio tests recover a known second-order limit.
- Added an actual element-count cap before starting the solver, supplementing the previous estimate. Oversized first meshes are also rejected before solving. Meshing itself can still consume resources before its element count is known.
- Reports describe GCI as an indicative estimate, not a guaranteed error bound. Reopening a report restores it after viewing a mesh result and applies the current theme, including light mode on dark-themed systems.

## Validation

The full suite passed **228 tests**, with one optional browser test skipped because the Python Playwright package was unavailable. Separate Node/Edge browser checks covered WebGL and Canvas: all camera presets preserve handedness, nearest-face picking agrees with the corrected projection, and toggle/drag/role-switch behavior works at device-pixel ratio 2. Focused report/convergence checks were repeated after the final navigation/theme adjustments (**23 passed**). The expanded mesh-import suite was repeated after adding explicit rejection of concave/nonplanar OBJ polygons (**18 passed**).

The suite includes real CalculiX/Gmsh solves, beam convergence against theory, imported-mesh comparisons with STEP, worker cancellation, and real MCP stdio communication. No new runtime dependencies or proprietary assets were added.

## Supported scope

Mesh import supports one connected closed triangle shell, not assemblies, 3MF component hierarchies or separate enclosed cavity shells. STL/OBJ geometry remains dependent on export faceting and source-coordinate units; the desktop's mm default is an assumption for those formats. 3MF units and transforms follow the [3MF Consortium core specification](https://github.com/3MFConsortium/spec_core/blob/master/3MF%20Core%20Specification.md).

Convergence uses element-count-derived effective mesh sizes and a power-law error assumption. Passing its change tolerance is a mesh-stability check; it does not validate material data, restraints, load realism or singular peak stress.
