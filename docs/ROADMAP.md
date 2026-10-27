# Roadmap

## Stage 0 — foundation (implemented)

Independent source tree, dependency pins and hashes, licensing records, explicit SI quantities, separate tool adapters and automated validation. REA identified and installed locally as a separate research tool, with no role in simulation execution.

## Stage 1 — first structural workflow (implemented, limited scope)

Single-solid STEP/IGES/BREP import, first-order tetrahedral meshing, X-face clamp and axial total force, isotropic static elasticity, external CalculiX process, solver log retention, displacement/force parsing, equilibrium checks, VTK export and local HTML visualization. Analytical axial-bar test and two-density mesh comparison.

Exit evidence: reproduce the supplied benchmark with a real solver and inspect the generated viewer. This establishes a starter workflow, not general engineering validation.

## Stage 2 — practical structural modeling

The initial native Qt workbench, persistent project/job state and 12-tool local MCP interface are implemented. The desktop exposes the current Stage 1 solver; future physics controls are disabled. This does not complete the modeling and validation work below.

Additional implemented work: C3D10 meshing and export, planar tip-center point loads in X/Y/Z, moment equilibrium, a reproducible Euler–Bernoulli beam benchmark, persistent dark/light themes and a thirteenth MCP tool for theme selection. Quadratic elements and transverse loads are available; general face/support selection remains planned.

The dedicated circular-hole benchmark now includes CPS8R plane-stress meshing, consistent edge traction, FRD tensor parsing, recovered hoop stress and Kirsch mesh/domain verification. See [results](hole/REPORT.md). General desktop stress selection and arbitrary plate modeling remain planned.

The [Timoshenko benchmark](timoshenko/REPORT.md) adds thin-beam total-deflection verification, a shorter zero-Poisson shear control and a retained short-beam Poisson/clamp diagnostic, with three C3D10 meshes each. The desktop Validation ribbon opens these reference reports without changing the selected model.

Initial modal analysis is implemented: positive density, 1–30 modes, X-min fixed support, unprestressed CalculiX eigenfrequency extraction, normalized mode viewers/animation, CLI and MCP controls, and a [six-mode beam benchmark](modal/REPORT.md) covering mesh refinement, shape comparison and density scaling. See [scope](MODAL.md).

Add a versioned project schema; CAD face selection and persistent named groups; consistent pressure/traction integration in the general solid workflow; arbitrary vector loads and displacement constraints; multiple materials and load cases; automatic rigid-body checks; general stress parsing, von Mises contours and reaction summaries. Add patch tests, manufactured solutions and distorted-element tests before expanding supported analyses.

## Stage 3 — accuracy and usability

Quadratic tetrahedra, element-quality reports, local refinement and convergence automation. Desktop workspace with geometry, mesh, boundary conditions, solve status and result selection. Job cancellation and resource limits. Portable CI on supported solver builds and validated Windows/Linux installation paths. Add schema migration tests and reproducible reference cases.

## Stage 4 — more physics

Expand modal analysis to named supports, free-free modes and independently validated prestress before adding modal forced response. Add steady/transient thermal and thermoelastic analysis through documented open-source solver interfaces. Each capability requires an analytical or independently published benchmark, a mesh/time-step study and a documented validity range. Contact, plasticity and geometric nonlinearity follow only after those validation foundations.

## Stage 5 — extensible platform

Evaluate established open-source CFD/electromagnetic solvers, multiphysics coupling and distributed job execution. Review each solver's maintenance, installation and license before adopting it. Interoperability is based on documented open formats; proprietary database compatibility is not a prerequisite.
