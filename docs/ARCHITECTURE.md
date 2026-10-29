# Architecture and code navigation

The desktop keeps one project tree: shared Geometry and Mesh, then Static Structural, Modal, Convergence, Thermal and Fluid Dynamics. Each study shows its relevant properties below the tree. The restructuring changes code ownership and result validity; it preserves existing project files, job folders, controls and solver algorithms.

## Where to look

| Area | Location | Responsibility |
|---|---|---|
| Public project API | `src/opensim/workspace.py` | Stable facade used by desktop, MCP and scripts |
| Study definitions | `src/opensim/application/studies.py` | Ordered registry, input dependencies, result views, worker and desktop commands |
| Input policy | `src/opensim/application/parameters.py` | Compatibility defaults, validation and normalization |
| Persistence | `src/opensim/storage/` | SQLite setup, job lifecycle/history queries, result discovery |
| Background execution | `src/opensim/execution/` | Registered analysis adapters, shared meshing and example creation |
| Worker process | `src/opensim/worker.py` | Claim a job, report progress, handle cancellation and failures |
| Desktop entry point | `src/opensim/desktop.py` | Assemble the window and own its lifecycle |
| Desktop UI | `src/opensim/ui/` | Commands, layout, project navigation, study panels/tree, selection, viewing, reports, presentation and refresh state |
| Numerical adapters | Existing `solver.py`, `modal.py`, `thermal.py`, `su2_flow.py`, etc. | Solver-specific model construction, execution and numerical result parsing |
| Viewer | `viewer.html`, `viewport.js` | Render geometry/results and camera-aligned setup overlays |
| Tests | `tests/` | Input isolation, saved-project compatibility, UI behavior and numerical checks |

UI sections share their owning Qt window through focused mixins. They contain presentation and user interaction; they do not implement numerical solvers. `desktop_cfd.py` remains a compatibility import for the moved `ui/cfd.py` controls. Asset paths are resolved centrally in `ui/resources.py` so moving a panel cannot break bundled viewers or reference reports.

## Settings and result identity

Geometry, meshing and structural material/support controls retain their existing shared behavior. Thermal and CFD conditions remain separately named input groups. `Workspace.study_settings(project_id, study)` exposes the effective inputs of one named study while the existing flat `get_project()['parameters']` API remains compatible.

The global project revision is retained as a provenance counter. It no longer decides whether every result is current. Results compare their immutable saved job inputs with the inputs actually consumed by that study:

- Static force changes invalidate Static Structural and Convergence, but do not invalidate unprestressed modes.
- Density changes affect modes, not an ordinary static solve.
- Thermal conductivity changes affect Thermal; CFD speed changes affect CFD.
- Shared elastic properties affect structural studies, not conduction or flow.
- Structural mesh settings affect structural/thermal studies. CFD uses its dedicated mesh size and CAD scale.
- Replacing CAD invalidates studies that consume it. Independent analytical CFD verification does not consume CAD.
- Unused controls, such as a legacy single force when independent load entries are active, do not falsely invalidate a result.

This comparison also works for existing jobs that contain complete input snapshots; no destructive conversion or re-solving is needed. Very old/incomplete snapshots without parameters conservatively retain the global-revision rule. Managed imported CAD files are immutable copies; use Import CAD to replace geometry rather than manually editing a job's input files. Restoring previous relevant inputs can make an older matching result current again.

Geometry/mesh previews are additionally restricted to the selected study, preventing a CFD enclosure from replacing the structural mesh view. The existing shared example geometry remains accessible. Plot availability and the historical/current plot banner use the same input-dependency check as result lookup.

## Execution and history

The study registry selects a handler through `execution/dispatch.py`. Every analysis handler takes `(cad, job_directory, parameters, progress)` and returns a numerical summary. Solvers run outside the UI process. Job snapshots, cancellation checks and the one-active-job-per-project constraint remain in force.

History reads join progress in one SQL query instead of opening a connection for every job. `list_jobs` accepts optional `limit`, `offset`, `kinds` and `status` filters. The desktop fetches at most 100 recent jobs per refresh, while its compact message panel retains the existing latest-eight display. The API retains access to complete history, and result lookup can still find older matching studies. An additive project/history index supports these reads.

## Adding a capability

1. Define its numerical input dependencies and metadata in `application/studies.py`.
2. Add a thin handler in `execution/analyses.py`, delegating numerical work to a dedicated solver adapter.
3. Add properties and result navigation to the appropriate `ui/` sections. Keep controls relevant to the selected study and give inputs units/tooltips.
4. Add tests for which changes invalidate its results, compatibility with saved snapshots, job cancellation, and an independent numerical reference where applicable.
5. Run `python tools/run_tests.py -q` in the project environment. The runner preserves pytest's result and logs its return before native-library shutdown.

## CI and remaining work

GitHub Actions uses pinned official Node 24 actions, installs trusted CalculiX/SU2 dependencies, and retains XML reports and the full test log even on failure. Desktop tests keep one QApplication alive for the suite and delete remaining windows before native WebEngine shutdown. A nonzero process exit remains a failure, including a shutdown error after passing tests; the runner does not force success or suppress notifications.

This is a foundation for growth, not a distributed compute platform. Native thread limits and timeouts still use their existing defaults. Large results still use whole-file JSON/HTML viewers and NPZ/VTK exports. Resource scheduling, streaming/binary result loading, independently editable mesh/material configurations per study, remote workers and multiphysics coupling remain separate future changes.
