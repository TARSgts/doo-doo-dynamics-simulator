# CFD numerical verification

All eight acceptance checks **PASS**. These compare numerical implementations with theory under the documented assumptions; no experimental validation is claimed.

| Case | Panels / cells | Error metric | Coarse | Medium | Fine |
|---|---|---|---|---|---|
| Cylinder | 24 / 48 / 96 | Maximum exterior velocity error / freestream | 2.9918% | 1.6696% | 0.87994% |
| Pipe | 12 / 24 / 48 | Relative volume-flow error | 0.69444% | 0.17361% | 0.043403% |
| Flat plate | 12 / 24 / 48 | Maximum absolute CL error vs 2π sin α | 3.33e-16 | 3.33e-16 | 9.99e-16 |

Cylinder field samples use 32 angles offset from the panels, at r/R = 1.25, 2 and 4. Cp errors at regular collocation points are below 1e-14; this symmetry result is not a substitute for the exterior-field test. The finest off-body error meets the 1% acceptance threshold and decreases with refinement.

Pipe settings: R=0.005 m, L=1 m, Δp=0.1 Pa, μ=1.81e-5 Pa·s, ρ=1.225 kg/m³. Flow-rate error decreases by a factor of four each time cells double, consistent with second-order convergence. The 48-cell result is below the 0.05% acceptance threshold.

Plate settings: c=0.1 m, U=10 m/s, ρ=1.225 kg/m³; α=−8°…8° in 1° increments. The fitted lift slope is approximately **6.2695 per radian**, **0.21814%** below 2π because this fits a sine over a finite range. Integrated lift can be exact at low panel counts for this idealized geometry; it does not verify local pressure accuracy or any separated-flow behavior. The absolute CL threshold is 1e-8, and the fitted slope tolerance is 0.5%.

All normalized linear/no-penetration residuals are below 1e-8. The full suite also checks surface Cp and decreasing cylinder errors. The reproducible runner writes its exact values and pass/fail checks into `report.json` and `data.csv`.

Run **Validation → CFD checks**, or `open-sim validate-cfd --out runs/cfd-verification`, to regenerate the plots and raw comparisons. See [models, scope, instructions and primary references](../CFD.md).

The recorded [raw comparison values](validation.csv) accompany this report.
