# Roadmap

## Stage 0 — foundation (implemented)

Independent source tree, dependency pins and hashes, licensing records, explicit SI quantities, separate tool adapters and automated validation. REA identified and installed locally as a separate research tool, with no role in simulation execution.

## Stage 1 — first structural workflow (implemented, limited scope)

Single-solid STEP/IGES/BREP import, first-order tetrahedral meshing, X-face clamp and axial total force, isotropic static elasticity, external CalculiX process, solver log retention, displacement/force parsing, equilibrium checks, VTK export and local HTML visualization. Analytical axial-bar test and two-density mesh comparison.

Exit evidence: reproduce the supplied benchmark with a real solver and inspect the generated viewer. This establishes a starter workflow, not general engineering validation.

## Stage 2 — practical structural modeling

Add a versioned project schema; CAD face selection and persistent named groups; consistent pressure/traction integration; arbitrary vector loads and displacement constraints; multiple materials and load cases; automatic rigid-body checks; stress parsing, von Mises contours and reaction summaries. Add patch tests, bending benchmarks, manufactured solutions, distorted-element tests and quantitative convergence studies before expanding supported analyses.

## Stage 3 — accuracy and usability

Quadratic tetrahedra, element-quality reports, local refinement and convergence automation. Desktop workspace with geometry, mesh, boundary conditions, solve status and result selection. Job cancellation and resource limits. Portable CI on supported solver builds and validated Windows/Linux installation paths. Add schema migration tests and reproducible reference cases.

## Stage 4 — more physics

Add modal, steady/transient thermal and thermoelastic analysis through documented open-source solver interfaces. Each capability requires an analytical or independently published benchmark, a mesh/time-step study and a documented validity range. Contact, plasticity and geometric nonlinearity follow only after those validation foundations.

## Stage 5 — extensible platform

Evaluate established open-source CFD/electromagnetic solvers, multiphysics coupling and distributed job execution. Review each solver's maintenance, installation and license before adopting it. Interoperability is based on documented open formats; proprietary database compatibility is not a prerequisite.
