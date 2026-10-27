# Opening, closing and finding projects

The outline now shows **only open projects**. Saved projects remain in the library even after closing them. On the first launch after updating an older workspace, only the previously selected project is opened. The open list persists across restarts, including an empty list when you close everything.

- **Open project…** in File, Home or above the outline opens a searchable list of saved projects. Search by project name or model filename, then double-click or choose Open project. **Ctrl+O** also opens this list.
- **Rename project…** in File, the outline's right-click menu, or Rename in the library changes its display name. **F2** renames the current project. Files stay in their original locations and numerical results remain valid.
- **Close project** removes a project from the outline. **Ctrl+W** closes the current project. Unapplied settings are saved first; invalid settings must be corrected before closing. This keeps models and previous runs, and does not stop background jobs.
- Right-click a project or any of its model-tree entries for Rename, File locations, Open project folder, Close project and **Close other projects**.

## Find the files

Choose **File → File locations…** or the equivalent right-click action. The dialog shows read-only paths for:

- the project folder;
- the model copy actually used by the simulator;
- the original imported file, when recorded;
- the latest run folder, including failed/stopped runs;
- the folder containing all runs;
- the local saved-project library database.

Each path has **Copy path** and **Open folder** buttons. Hover over a long path to read it in full. File paths open their containing folders; they do not launch the CAD file or database. **File → Open latest run folder** goes directly to the newest run's input files, logs and outputs.

New imports record their original source path. Older imports may show “Not available” for the original file, but their stored model copy is still listed. Generated examples do not claim the original path of a previous import. Project folder names remain stable identifiers so renaming cannot break references from existing runs.

These projects are stored in the current simulator workspace's library. Opening a project through MCP's existing `show_in_desktop` action also adds it to the outline; `list_projects` continues to return the complete saved library. No projects or result files are deleted by these controls.

## Verification

The broad check passed **217 tests**, with one optional browser test skipped and 19 numerical integration tests deselected. After the final path-display and styling adjustments, the focused desktop/workspace/navigation checks passed **32 tests**. Coverage includes legacy migration, persistent empty state, close/reopen, rename without changed revisions/files, background-job preservation, original/copy/latest-run paths, library search and saving unapplied settings before closing.

A visible Windows check verified the library in both themes, exact paths, clipboard copying, Close other projects and reopening the persisted open list. No new dependencies were added.
