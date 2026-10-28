# Steady thermal analysis

The thermal study solves **steady, isotropic heat conduction** in one solid using CalculiX. It supports the same CAD import and linear/quadratic tetrahedral meshes as structural analysis. It calculates temperature and recovered heat-flux vectors, with a heat-balance check.

## Desktop workflow

1. Open/import your model and generate a mesh. Check the CAD scale: STL/OBJ are usually millimeters, so use 0.001 to convert them to meters.
2. Expand **Thermal Analysis** in the model tree. Its settings replace the structural properties below. Enter the material's **Conductivity**, in **W/(m·K)**; this is separate from Young's modulus, density and Poisson ratio. The default conductivity is a placeholder, not a material recommendation.
3. Enter the **Fixed temperature**, in **°C**. **Pick fixed-temperature faces** selects the cyan thermal surface. If nothing is selected, it uses the X-min face.
4. Choose **Thermal source**: **Prescribed temperature** gives the orange faces a second temperature, or **Total heat input** distributes a specified total **W** over them. Positive watts add heat; negative watts extract it. **Pick thermal source faces** selects these orange faces. If blank, X-max is used. The two thermal surfaces must be separate and share no nodes. Other surfaces are insulated.
5. Save picked faces, apply settings and choose **Run thermal study**. The Home/Solution **Solve** command also follows the selected study. The right-side **Thermal analysis** button starts this solver directly.
6. View the temperature contour in **°C**, or choose heat-flux magnitude / signed global X, Y or Z in **W/m²**. Thermal geometry is undeformed; deformation controls are disabled. The top cards show min/max temperatures and the heat-balance residual.
7. **Result plots** offers temperature and heat-flux scatter plots against X/Y/Z position, plus nodal histograms. Export figures as PNG/SVG or plot data as CSV. These include all mesh nodes, not an interpolated path. **File locations** opens the job folder.

Thermal boundary selections are stored separately from structural fixed supports and force surfaces. Switching studies retains their hidden input values. Geometry, mesh settings and the project revision remain shared, so changing numerical inputs makes prior results historical. CAD re-import clears both structural and thermal face selections.

On irregular/curved shapes, a bounding extreme may not contain a usable face; pick the intended faces explicitly. The solver rejects overlapping thermal selections and empty/invalid surfaces rather than inventing a boundary.

## Scope

There is **no convection, radiation, transient heating/cooling, volumetric heat generation, temperature-dependent material law, thermal contact or thermal-expansion/stress coupling** in this stage. Heat capacity and density are not needed for this steady conduction solve. Results are not a prediction of heating time. The existing Convergence Study remains a **static structural** study; thermal meshes can be compared manually by rerunning at different sizes.

Unspecified surfaces have zero normal heat flux. Surface heat input uses consistent triangle shape-function integration: linear nodes receive area/3; straight quadratic faces distribute the integral to their midside nodes. A prescribed-temperature boundary supplies/removes whatever heat is needed to maintain its temperature. Reaction heat rates are positive **into** the solid; a cooled boundary typically has a negative rate.

## Files and units

Thermal jobs use `<project>/jobs/<job-id>/thermal/`:

- `results.html`: offline temperature/flux viewer.
- `results.vtk`: temperature in Kelvin and vector heat flux in W/m².
- `thermal.npz`: points (m), connectivity, temperature (K), heat flux (W/m²), nodal/applied heat rates (W), boundary-node indices.
- `temperatures.csv`: node ID, coordinates in m, both Kelvin/Celsius temperature and flux components in W/m².
- `model.inp`, `model.dat`, `model.frd`, `solver.log`: native solver inputs and outputs.
- `manifest.json`: input/deck/solver hashes, parameters, units and numerical summary.

The solver, CLI and MCP use **Kelvin**, **meters** and **watts**. Only the desktop controls and temperature charts convert to Celsius. The result parser checks complete finite temperatures, heat rates and flux arrays; energy balance is checked before publishing a successful result.

## CLI and MCP

```powershell
open-sim thermal bar.step --out runs/thermal-bar --mesh-size 0.01 --order 2 --conductivity 10 --fixed-temperature 293.15 --source-temperature 373.15
open-sim thermal bar.step --out runs/thermal-power --mesh-size 0.01 --order 2 --conductivity 10 --fixed-temperature 293.15 --boundary-mode power --power 0.4
```

`--regions regions.json` accepts `thermal_fixed_region` and `thermal_source_region`, each using CAD face IDs and/or `box_m` centroid limits, like structural surface selections. CLI outputs must use a new directory.

MCP adds **`set_thermal_parameters`**, **`run_thermal_analysis`** and **`get_thermal_results`**, bringing the server to 22 tools. Poll `get_job`, then retrieve the thermal result or call `show_in_desktop(project_id, view="thermal")`. `cancel_job` also stops thermal jobs. Restart an already-running MCP server after updating to discover the added tools.

## Verification

See [eight Fourier-conduction comparisons](thermal/REPORT.md): a 100 × 20 × 20 mm bar at k=10 W/(m·K), with two mesh sizes, both element orders, and both boundary modes. All nodal temperatures differ from the exact linear solution by less than **0.001 K**, recovered heat-flux vectors by less than **0.01%**, and relative heat-balance residuals are below **1e-6**. The equations, actual element counts and raw comparison values are recorded in the report.

Automated tests also cover selected faces, millimeter import scaling, zero/negative input power, invalid material/temperature data, overlapping surfaces, malformed output, background-worker completion, stale results, independent thermal/structural picks, Celsius conversion and result plotting. A native desktop check rendered the actual thermal solve, switched temperature/heat-flux display, checked zero deformation and exported all four chart types.

The linear bar benchmark verifies this workflow; accuracy on a new geometry still depends on the model, boundary assumptions and mesh resolution.
