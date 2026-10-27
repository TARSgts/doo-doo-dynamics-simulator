# Validation evidence

The selected-region/recovered-stress expansion passed **128 tests in 71.87 seconds** with no skips. Additional focused checks cover the final display/export updates. The custom-region axial bar validates recovered von Mises stress and SI/native-unit conversion; an equivalent modal run checks mass/length conversion invariance. Properties controls remain inside the scroll viewport at three widths in English and Cat mode. See [feature scope](SURFACE_REGIONS.md).

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

## Timoshenko bending and shear

Executed October 27, 2026. The [Timoshenko study](timoshenko/REPORT.md) uses three independent C3D10 mesh densities for each of three solid cantilevers. All have 20 × 20 mm sections, E=210 GPa and a −10 N tip-center Z force. Comparison uses area-averaged tip displacement against `FL³/(3EI)+FL/(κGA)`, with κ=5/6.

- Thin beam: L=1 m, ν=0.3; FEM −1.188822551 mm versus −1.190847619 mm, **0.1701% error**, **0.0135% last-mesh change**.
- Shear control: L=0.1 m, ν=0; FEM −0.001218646 mm versus −0.001219048 mm, **0.0329% error**. The excess over Euler–Bernoulli recovers **98.594%** of theoretical shear.
- Clamp diagnostic: L=0.1 m, ν=0.3; **1.4630% total error** is retained and documented. Poisson constraint and warping at a full 3D clamp differ from 1D beam conditions.

Every solve passes force/moment residuals below 1e−5. The thin beam's shear term is only 0.0312% of bending; its total-deflection match alone does not establish shear accuracy. The zero-Poisson control is a verification material, not assumed steel behavior. The report records separate criteria and limitations. Reproduce with `open-sim validate-timoshenko --out <new-folder>`.

After this addition, the complete suite passed **54 tests in 40.96 seconds**, including all nine Timoshenko solver cases, with no skips.

## Modal frequencies and mode shapes

The [modal cantilever benchmark](modal/REPORT.md), executed October 27, 2026, uses a 1,000 × 20 × 20 mm square solid beam with E=210 GPa, ν=0.3 and density 7,850 kg/m³. All six modes pass the 2% Euler–Bernoulli frequency criterion; the largest error is 0.4012%. Maximum last-mesh change is 0.0251%. All longitudinal edge-shape MAC values exceed 0.999997, and fixed-node normalized mode components are zero in the recorded results. Quadrupling density halves all frequencies on the same mesh within 0.000039%.

The native desktop Modal action ran a real background solve, selected mode 3 (104.6114 Hz), animated it, and retained one WebGL geometry upload. Separate browser checks verified animation and pause in WebGL and Canvas fallback with no page errors. Mode labels and exported data explicitly distinguish normalized eigenvectors from physical displacement amplitudes. Real stdio MCP checks cover the expanded catalog and modal settings. See the benchmark report for limits on pair orientation, shear/rotary inertia and the edge-based MAC measurement.

The full suite passed **74 tests in 56.36 seconds**, with no skips, after modal integration. No new dependencies were required. The worker and desktop checks were rerun after the final layout and geometry-preview adjustments.

## Uniform distributed surface load

The [distributed-load study](distributed/REPORT.md) validates total-force-based, consistently integrated vector traction. A 1,000 × 20 × 20 mm beam carries −10 N uniformly over its Z-max surface: −500 Pa in Z, equivalent to q=−10 N/m. Fine C3D10 tip mean is −0.445632043 mm against `qL⁴/(8EI)` = −0.446428571 mm, **0.1784% error**. The last mesh change is **0.0202%**. Reaction force is +10 N Z and root moment −5 N·m Y within equilibrium tolerances. Two axial uniform-stress meshes each agree with `FL/(EA)` within 0.000005%.

The full suite passed **116 tests in 63.58 seconds**, with no skips. This includes P1/P2 surface integration across six surfaces and three force directions, exact quadratic virtual work, load scaling/reversal, support-load reaction correction, real beam/axial solves and a real MCP distributed solve. The native desktop also solved the beam and displayed nine illustrative load arrows. See the report for model limits.

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
