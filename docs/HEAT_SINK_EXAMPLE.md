# Sample heat sink

Choose **Examples → Heat sink** to create a separate project with a generated STEP solid, mesh and thermal settings. Wait for meshing, then choose **Run thermal study**. Select the thermal solution to view temperature or heat flux. Change total power or conductivity and solve again to compare results.

The base measures **60 × 40 × 4 mm**. Six **2 × 40 × 20 mm** fins are fused to it, making one connected solid, 24 mm tall overall. STEP coordinates are millimeters; the preset applies CAD scale **0.001**. The starting mesh uses quadratic tetrahedra and a 2.5 mm target size.

The preset uses:

- Conductivity: **200 W/(m·K)**, an illustrative input rather than an alloy specification.
- Total input: **20 W**, distributed over the underside of the base.
- Fixed temperature: **20 °C**, on all six fin tips.
- All other faces: insulated.

This is an idealized steady-conduction example. Fixed-temperature tips represent ideal cooling; the model does not include air convection and does not predict real-air heat-sink performance or heating time.

An example solve with 19,660 nodes and 9,661 quadratic tetrahedra gave **20.0000–24.4885 °C**, with a relative heat-balance residual of **2.55e-9**. Heat balance checks conservation; it does not establish mesh convergence or validate the assumed cooling conditions.

Automated checks verify one solid, volume, dimensions, selected boundary areas, separated thermal surfaces, the background build-and-solve path and conservation of the applied 20 W. Creating the sample leaves other projects' inputs unchanged.

MCP clients can use `create_test_object(project_id, kind="heat_sink")`, poll the example job, then call `run_thermal_analysis(project_id)`. Use a new project because example generation replaces its geometry and installs this thermal recipe.
