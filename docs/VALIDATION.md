# Validation evidence

Executed October 26, 2026, on Windows x64 with Python 3.12.14, Gmsh 4.15.2, NumPy 2.3.4 and CalculiX 2.23 (`ccx_static.exe`, SPOOLES).

See the [long cantilever validation](cantilever/REPORT.md) for the C3D10 tip-point-load benchmark, three quadratic meshes, C3D4 failure baseline, curve comparison and force/moment checks. Dark/light rendering and persistent theme toggles were also exercised in a native desktop session.

The original axial-bar suite had 15 passing tests, including the real solver integration test, with no solver skips. Later benchmark evidence is recorded below.

## Circular-hole stress concentration

Executed October 27, 2026. The [repeatable Kirsch benchmark](hole/REPORT.md) uses a 400 × 400 × 0.1 mm plate, a centered 10 mm hole and 1 MPa remote X tension. A quarter-symmetry CPS8R model applies consistent quadratic-edge traction; it does not clamp the plate. Peak recovered nodal hoop stress is measured at the hole boundary.

The full suite passed **45 tests in 29.77 seconds**, with no skips, including real axial, bending and hole-stress solver studies. `pip check` reported no broken requirements. No new dependencies were needed for this benchmark.

| Case | Quadratic elements | Gross Kt |
| --- | ---: | ---: |
| Coarse | 768 | 2.954750 |
| Medium | 3,072 | 2.991440 |
| Fine | 12,288 | 3.002000 |
| Doubled plate size | 14,720 | 2.998090 |

Kirsch's infinite-plate reference is 3. The fine model differs by 0.0667%, the last mesh change is 0.3518%, and the domain change is 0.1304%. The peak is at 90°/270° from the load axis. Force and moment balance pass for all cases. Gross remote stress and net-section nominal stress are explicitly distinguished in the report. This validates the dedicated elastic plane-stress benchmark, not arbitrary 3D peak-stress predictions.

Reproduce with `open-sim validate-hole --out <new-folder>` after installing the validation extra. Tests include signed fixed-width FRD parsing, malformed stress rejection, tensor transformation, exact traction resultants and the real four-case solver study.

## Axial bar

Independent rectangular solid: length 1 m, width and height 0.1 m, Young's modulus 210 GPa, Poisson ratio 0, applied axial total force 1000 N. The X-minimum face is clamped. Equal nodal loads are used at X maximum, so end traction is not exactly uniform and a small difference from the ideal bar is expected.

Analytical mean displacement: `F L / (E A) = 4.7619047619e-7 m`.

| Mesh size | Nodes | Tetrahedra | Mean loaded-face X displacement | Relative force imbalance |
| --- | ---: | ---: | ---: | ---: |
| 0.05 m | 190 | 434 | 4.7854725e-7 m | 4.000006e-8 |
| 0.035 m | 541 | 1537 | 4.7851248e-7 m | 1.000000e-8 |

Both mean displacements are within 0.5% of the ideal analytical solution. This is a two-density stability check, not proof of mesh convergence for arbitrary geometries. Regression acceptance is 2% against the analytical result and 3% between the two meshes. Reaction-result acceptance in the integration test is tighter than the runtime equilibrium threshold.

The generated files include the imported mesh, CalculiX input, DAT/FRD results, logs, displacement VTK, HTML viewer and run manifest. Large native outputs and manifests with local machine paths are kept in ignored `runs/`, not published.

## Other checks

- STEP, IGES and BREP box round trips; IGES surface sewing into a closed solid.
- Millimeter-coordinate scaling, nonpositive mesh parameters and multiple-solid rejection.
- Surface extraction excludes shared interior faces; VTK connectivity is zero based.
- Invalid material/load input, incomplete/nonfinite/duplicate result records and solver failure/timeout log retention.
- HTML viewer loaded in headless Microsoft Edge through Playwright; no page errors, and scale/reset controls passed. The screenshot in this directory is generated from the independent example.
- REA `6.8.0` version and doctor commands execute; native-analysis providers and assistant registration are absent. The patched locked install reports zero known npm audit vulnerabilities. Registry verification reports 176 verified package signatures and 38 attestations.

The first automated GitHub Actions run is separate evidence and must be inspected after publishing; local success does not establish hosted-CI success.
