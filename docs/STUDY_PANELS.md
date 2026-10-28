# Study tree and context-sensitive settings

Each open project now contains shared Geometry/Mesh entries and four study branches:

- **Static Structural**: fixed support, force, displacement/stress solution.
- **Modal Analysis**: fixed support, density/mode settings, natural-frequency solution.
- **Convergence Study**: fixed support, static force, refinement settings, convergence report.
- **Thermal Analysis**: independent thermal face selections, conductivity, prescribed temperatures or heat input, temperature/heat-flux solution.

Click a study name to edit its settings. This does not start a job or invalidate numerical results. Expand its branch to inspect supports, loads and solution entries. The selected study is remembered per project, including across closing/reopening and application restarts.

The lower properties panel changes with the selected study. Its heading and primary Run button also change:

| Study | Visible study-specific inputs |
| --- | --- |
| Static Structural | Total force, direction, application, traction surface when relevant |
| Modal Analysis | Density and requested mode count; static forces and convergence inputs are hidden |
| Convergence Study | Static load inputs, mesh levels, refinement ratio, tolerance and target |
| Thermal Analysis | Conductivity, fixed temperature, second-temperature/power mode and the relevant value; structural elasticity, density and force inputs are hidden |

Mesh size, CAD scale and element order remain common. Young's modulus and Poisson ratio apply to structural/modal studies. Modal support selection hides force picking and opens a support-only region dialog. Thermal face picks are stored independently of structural regions; Celsius fields are converted to Kelvin in storage. Static load regions remain saved for the static/convergence studies. Switching study types retains hidden input values and cancels unsaved face-picking drafts rather than applying them to another study. The settings scroll position resets to the top on a study change.

**Run static study**, **Run modal study**, **Run convergence study** or **Run thermal study** saves settings and starts the corresponding solver. Generic Home/Solution Solve and Home Results follow the selected study. Explicit physics actions select their corresponding context. A running job still locks numerical inputs. Selecting a solution switches to its matching study context; selecting shared geometry/mesh retains the chosen study.

## Shared-model scope

These branches organize the application's analysis types; they are not duplicate models or multiple named load cases. Geometry and mesh are shared. Static, modal and structural convergence share elasticity and fixed supports; static and convergence use the same forces. Modal analysis uses density and ignores static forces and prestress. Thermal analysis has separate conductivity and thermal boundary regions, and ignores mechanical supports and loads. Editing numerical inputs invalidates older results through the existing revision system. Merely selecting a branch does not change the revision or erase jobs.

## Verification

The broad non-integration check passed **221 tests**, with one optional browser test skipped and 19 integration tests deselected. After the final UI adjustments, **20 focused tests passed**, covering desktop/workspace behavior and actual MCP stdio communication, including static/modal jobs. New tests verify persistent selection, legacy modal migration, property/label visibility combinations, hidden input retention, the matching Run action, support-only modal regions and cancellation of face-picking drafts when switching studies.

A visible Windows check exercised all three panels in light/dark themes at narrow/wide dock widths, verified bounds for every displayed input, and confirmed that selecting studies launched no jobs and changed no numerical inputs. No solver equations or runtime dependencies changed.
