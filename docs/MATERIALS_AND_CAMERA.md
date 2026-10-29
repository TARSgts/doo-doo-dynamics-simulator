# Materials, camera and modal display

## Material properties

The left panel's **Material properties…** opens one editor for Young's modulus, Poisson ratio, density and thermal conductivity. Choose a preset, inspect/edit its values, then apply it. Changes invalidate prior results while retaining historical files. The current stage assigns one homogeneous isotropic material to the whole solid; it does not support separate materials on different bodies.

| Illustrative preset | E (GPa) | ν | Density (kg/m³) | Conductivity (W/m·K) |
|---|---|---|---|---|
| Steel (generic) | 210 | 0.30 | 7850 | 45 |
| Aluminum (generic) | 69 | 0.33 | 2700 | 167 |
| ABS (solid, isotropic approximation) | 2.3 | 0.35 | 1040 | 0.18 |

These are approximate room-temperature starting values, not certified alloy, temper or filament specifications. Check the actual material datasheet and adjust them. They do not establish yield strength, allowable load, fatigue life or printed-part anisotropy. The aluminum preset is generic; do not infer a particular alloy/temper from it. For reference, published [NASA 6061 sheet data](https://ntrs.nasa.gov/api/citations/20120014854/downloads/20120014854.pdf) and [NIST 6061 thermal data](https://www.nist.gov/mml/acmd/aluminum-6061-t6-uns-aa96061) show why product and temperature matter.

The solver uses E and ν for structural stiffness, density for modal inertia, and conductivity for steady thermal analysis. CFD has its own fluid density and dynamic viscosity. Editing a displayed property directly updates the material identification to **Custom** unless all four values match a preset. MCP accepts the exact preset name through `set_analysis_parameters(material_preset=...)`.

## Camera triad and Home

Click **X**, **Y** or **Z** on the viewport triad to view the model from that positive axis, showing the perpendicular plane. The smaller **−X**, **−Y**, **−Z** targets give opposite views. This rotates the camera only; geometry, force vectors and solver coordinates remain unchanged.

Click **H** below the triad, or choose **Home** in the camera menu, to restore the home orientation and fit the model. Right-click **H** to save the current orientation as home. Home defaults to the isometric orientation and is remembered locally by the viewer when browser storage is available. New viewers and newly selected projects start at Home. **Fit view** preserves the current orientation while recentering/resizing.

## Modal recheck

The modal solver was rerun against its three-mesh, six-mode cantilever verification. All checks passed: frequency errors below 2%, last-mesh changes below 0.5%, density-scaling error below 0.01%, shape MAC above 0.995 and fixed-support components below 1e-8.

The display previously exaggerated mode shape amplitude to 10% of model size by default. The new default is **2%**, with a **1% / 2% / 5% / 10%** visual amplitude selector. Mode colors remain normalized and dimensionless. Animation is intentionally slowed to 1 Hz; neither animation speed nor displayed displacement is a forced-response prediction. A square-section beam has paired bending modes whose sign and transverse orientation are arbitrary, so two valid eigenvectors may look rotated relative to each other. Loads remain ignored in the undamped, unprestressed eigenproblem.
