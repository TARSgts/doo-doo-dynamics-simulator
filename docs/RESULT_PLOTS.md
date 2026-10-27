# Result plots

Run a study, then click **Result plots…** below its settings heading, **Solution → Result plots**, or **Result plots** inside its tree branch. The dialog offers plots for that study's completed result at the current input revision. Unsolved/changed inputs must be solved first; plotting does not start a solver job.

## Available charts

| Study | Charts |
| --- | --- |
| Static Structural | Displacement, axial/normal stress, shear stress and von Mises stress against X/Y/Z position, plus histograms of each quantity |
| Modal Analysis | Natural frequency by mode number, selected normalized mode shape against X/Y/Z position |
| Convergence Study | Maximum displacement, loaded-area response, or maximum stress against actual element count |

Displacement plots support total magnitude and signed X/Y/Z components. Coordinates and static displacement use **mm**, stress uses **MPa**, frequencies use **Hz**, and normalized mode amplitudes are **dimensionless**. Coordinates are undeformed; the viewport's deformation exaggeration is not applied to the data.

For **axial / normal stress**, select **Sxx**, **Syy** or **Szz**. Positive means tension; negative means compression. For **shear stress**, select **Sxy**, **Syz** or **Szx**; these retain their tensor sign. All six components refer to the model's **global axes**, not an automatically detected beam axis or the surface normal. Choose the normal component along the member's length to examine axial stress in an axis-aligned member. Von Mises is a nonnegative equivalent stress combining all six components. Changing the horizontal position axis does not change the stress component.

These are recovered nodal stresses; peaks near idealized fixed edges or point loads can be singular and depend on mesh refinement. Older runs without a saved stress tensor still offer their saved von Mises plots; solve again to obtain the component plots. Tensor component selections are included in chart labels, CSV metadata and default export filenames.

Position plots show a scatter of **all mesh nodes across the whole model**. They are not line probes or centerline interpolation. Several nodes may share one X/Y/Z position. Histogram counts are mesh-node counts, not volume-weighted material distributions. Adjust the bin count as needed. Modal amplitudes are arbitrary normalized eigenvectors, and modal frequencies are undamped/unprestressed eigenfrequencies. Convergence plots join the actual completed mesh results against element count on a logarithmic horizontal scale; they do not invent additional simulation points.

## Viewing and saving

- Use the chart toolbar to pan, zoom, reset, or go back/forward through chart views.
- Change the plot, coordinate, component, mode or histogram bins using the controls above it.
- Toggle **Dark plot** for a dark chart or a white-background figure. Figure export follows the chart theme.
- **Save figure…** writes **PNG or SVG**, including the displayed zoom and labels. Project name, run ID and input revision appear on the figure; metadata also records the source.
- **Export CSV…** writes the entire plotted dataset, including values outside the current zoom, plus a `.metadata.json` file recording the project, run, revision, units and interpretation note.
- **Open plot folder** opens the most recent export location.

Scatter CSVs contain node IDs, all three undeformed coordinates and the selected value. Histogram CSVs contain bin edges and counts; choose a scatter plot when you want individual nodal values. Frequency CSVs contain mode numbers and Hz. Convergence CSVs contain mesh level, element count, requested mesh size and the selected response.

By default exports go under the source run's `solve/plots`, `modal/plots` or `convergence/plots` folder. You can select another location in the save dialog. Filenames distinguish coordinate/component/mode/bin choices. **File locations** in the main app can also open the run folder.

An open plot remains a snapshot of its source run. If numerical inputs change, its banner changes to **Historical result**. It can still be exported with its original run/revision metadata. Reopen Result plots after solving to see the new run. Closing a plot releases its window and data rather than keeping every old run's plot open in memory.

## Implementation and verification

Plots read `fields.npz`, `modes.npz`, or completed convergence summaries with pickle loading disabled. Shapes, finite values and modal frequencies are checked before plotting. Missing arrays and stale result revisions produce an explanation. Matplotlib 3.10.8 is already present in the hashed desktop requirements and is now also explicitly listed in the desktop package extra; no additional package download was needed.

Checks cover unit conversion, signed components, histogram totals/bin edges, mode normalization units, actual convergence counts, CSV metadata, PNG/SVG export for every chart, navigation callbacks after redraw, historical banners, study-specific availability and correct project selection from the tree. A visible Windows check generated real static, modal and convergence solves, rendered all chart types, and exported PNG/SVG/CSV for each study. The broad non-integration suite passed 233 tests, with one optional browser test skipped and 19 numerical integration tests deselected. After final export/lifecycle refinements and the cross-project selection regression check, all 12 plotting tests passed. Dependency checks also passed.
