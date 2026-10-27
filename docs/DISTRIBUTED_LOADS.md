# Distributed surface loads

Uniform vector traction is available in the desktop, CLI and the existing MCP analysis-parameter tool. The input is a signed **total force in N**. The selected patch area A comes from the boundary mesh, and constant traction is `F/A` in the chosen global X, Y or Z direction. Positive and negative forces are supported. This is a surface load, not a single point force or equal shares at every node.

## Desktop

1. Import a closed solid or create the Cantilever preset. The X-min face remains fully fixed.
2. Select **Uniform surface traction** under **Force application**.
3. Select **Traction surface**: X-min, X-max, Y-min, Y-max, Z-min or Z-max. It must contain planar boundary triangles at that bounding coordinate. All qualifying triangles form the selected patch, including disconnected pieces if present.
4. Choose **Force direction** X/Y/Z and enter **Total force (N)**. Direction is independent of the selected surface; tangential traction is valid.
5. Choose C3D10 for bending, set mesh size and Solve. The viewer shows illustrative arrows over the loaded patch, labeled with the total force. Arrows are not the equivalent nodal forces.

For the verification beam, use Z-max, Z direction, −10 N total. On its 1 × 0.02 m top surface, that is −500 Pa in Z and an equivalent line load of −10 N/m. The force input does not take Pa or N/m. The surface selector is active only for uniform traction; modal analysis ignores all loads. In Cat mode, the option is “Spread da boops.”

The **End face · equal nodes** option is preserved for existing projects. It applies equal nodal shares and is not uniform surface traction. **Tip center · point** is also unchanged.

## CLI and MCP

```powershell
.\.venv\Scripts\open-sim.exe solve beam.step --order 2 --mesh-size 0.0067 --poisson 0.3 --load -10 --load-axis z --load-kind traction --load-surface z-max --out runs\distributed-beam
.\.venv\Scripts\open-sim.exe validate-distributed --out runs\distributed-verification
```

MCP uses `set_analysis_parameters` with `load_kind="traction"`, `load_surface="z-max"`, `load_axis="z"` and `load_N=-10`, plus mesh and material inputs. Start `solve_project`, poll `get_job`, then use `get_results` and `show_in_desktop`. The catalog remains 16 tools; reconnect an existing client to pick up the extended parameter schema. Inputs persist, edits invalidate stale results and active jobs lock input changes.

## Integration and equilibrium

For a linear triangular surface element, each corner gets one third of the triangle's force. For an affine six-node quadratic triangle under constant traction, corner shape-function integrals are zero and each midside receives one third. Contributions at shared nodes are accumulated. Equal forces at all six nodes would be incorrect. The current tetrahedral mesher uses straight second-order edges; a non-affine quadratic load face is rejected rather than integrated with the wrong rule.

Applied moments are summed from every equivalent nodal force at its actual position. Loads can share nodes with the fixed boundary. CalculiX's printed RF includes applied CLOAD there, so physical support reaction is recovered as RF minus the applied nodal load before checking force and moment equilibrium. The run summary records the selected patch, loaded area, traction, total force and this support-load correction. `fields.npz` retains all applied nodal forces.

## Tests and limits

The [verification report](distributed/REPORT.md) includes three meshes of a uniformly loaded cantilever and two meshes of an axial uniform-stress bar. It records tip deflection, a longitudinal edge curve, force/moment balance and the fixed-edge load correction. Unit checks cover all six surfaces in all three directions for both element orders, force reversal/scaling, surface area/centroid, quadratic virtual work, malformed geometry and saved input validation. A real MCP session configured and solved a distributed-load case. The native desktop set these controls, solved the full beam and displayed nine load markers with WebGL.

The default implementation covers one constant vector traction on an axis-aligned bounding-plane patch. The newer [region selector](SURFACE_REGIONS.md) also accepts CAD face IDs and a triangle-centroid box, plus selected fully fixed supports. Interactive face picking, varying distributions, normal pressure input, follower loads and more general support/contact behavior remain future work. Mesh convergence is still required for new geometry, and local stresses at ideal fixed edges are not validated by this global-displacement benchmark.
