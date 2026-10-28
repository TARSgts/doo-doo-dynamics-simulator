# Roadmap

Current CFD milestone: [numerical flow workbench](CFD.md) implements source-panel cylinder flow, fully developed laminar pipe flow and a discrete-vortex flat-plate CL/α sweep, with three-resolution reference comparisons. General CAD Navier–Stokes simulation, turbulence, separated-flow drag/stall and conjugate heat transfer remain future work.

Current thermal milestone: steady isotropic conduction is implemented, with conductivity, independent prescribed-temperature/heat-input faces, energy balance, temperature/flux contours and plots, SI exports and three MCP tools. See [scope](THERMAL.md) and [eight analytical comparisons](thermal/REPORT.md). Transient thermal, convection, radiation and thermoelastic coupling remain future stages.

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

Uniform vector traction is implemented on selected axis-aligned bounding-plane patches with consistent P1/P2 surface integration, total-force input, correct applied/support moments and RF correction for loads sharing constrained nodes. Desktop/CLI/MCP controls and [axial/UDL beam verification](distributed/REPORT.md) are available. [Perpendicular inward/outward loading](NORMAL_LOADS.md) also supports constant-magnitude traction along local initial-mesh normals. Varying traction remains future work; additional region selection is described below.

CAD face-ID regions with optional centroid-box filtering are now available for fully fixed support patches and global vector traction, including modal fixed supports. The desktop also supports clicking visible CAD faces, draft highlighting and save/cancel for supports and distributed force regions. General solid solves recover nodal stress and display von Mises contours. This does not implement contact. See [scope and tests](SURFACE_REGIONS.md).

Add a versioned project schema; persistent named face groups; pressure-in-Pa input and spatially varying traction; arbitrary vector loads and displacement constraints; multiple materials and load cases; automatic rigid-body checks. Add manufactured solutions and distorted-element tests before expanding supported analyses.

## Stage 3 — accuracy and usability

Quadratic tetrahedra and convergence automation are implemented (global-refinement convergence study with Richardson extrapolation/GCI); element-quality reports and local refinement remain. Desktop workspace with geometry, mesh, boundary conditions, solve status and result selection. Job cancellation is implemented (desktop Stop computing and MCP `cancel_job`); resource limits remain. Portable CI on supported solver builds and validated Windows/Linux installation paths. Add schema migration tests and reproducible reference cases.

## Stage 4 — more physics

Expand modal analysis to named supports, free-free modes and independently validated prestress before adding modal forced response. Steady thermal conduction is implemented; add convection, radiation, transient thermal and thermoelastic analysis through documented open-source solver interfaces next. Each capability requires an analytical or independently published benchmark, a mesh/time-step study and a documented validity range. Contact, plasticity and geometric nonlinearity follow only after those validation foundations.

## Stage 5 — extensible platform

Evaluate established open-source CFD/electromagnetic solvers, multiphysics coupling and distributed job execution. Review each solver's maintenance, installation and license before adopting it. Interoperability is based on documented open formats; proprietary database compatibility is not a prerequisite.
