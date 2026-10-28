# Desktop workbench and MCP automation

The native Windows desktop application provides an engineering ribbon, model outline, material/load/mesh properties, rotatable viewport, analysis toolbox and job log. It uses original interface code and common engineering-workbench conventions. It contains no Ansys interface assets, source code or branding.

Dark mode is on by default. Use **Settings → Appearance → Light / Dark / Midnight** to choose a palette; the preference persists in the shared workspace. Midnight uses near-black panels and a deeper viewport background, with readable dark-theme overlays and GIF export backgrounds. **Settings** also contains **Cat mode (joke translation)** and **Discord Rich Presence…**. Header theme/language buttons and the separate View/Integrations menus are removed. Appearance changes preserve numerical settings, project revisions and unsaved form edits. The renderer supports automatic deformation scaling, signed displacement components, a color bar, and clamp/load annotations. The properties pane scrolls vertically, input controls disable during active jobs, and top result cards summarize displacement and force balance.

The application title now shares the full-width top bar with the File, Settings and Help menus. The viewport uses batched WebGL rendering where available; drag to rotate, Shift/middle/right-drag to pan and scroll to zoom. Existing saved results automatically receive the current renderer when opened in the desktop. See [performance measurements and fallback behavior](VIEWPORT_PERFORMANCE.md).

![Native desktop workbench](desktop-preview.png)

## Install and launch

Use Python 3.12 x64 and run from this checkout:

```powershell
.\tools\install-desktop.ps1 -Python 'C:\path\to\python.exe'
```

Double-click **Launch Simulator.cmd**, or run:

```powershell
.\.venv\Scripts\doo-doo-dynamics.exe
```

This is a locally installed Python/Qt desktop application. It is not yet a self-contained executable installer. The launcher depends on the project's environment and checkout remaining in place.

The desktop/MCP extension uses the official `PySide6==6.10.2` and `mcp==1.26.0` PyPI packages. The Windows/Python 3.12 extension lock includes exact hashes for their transitive wheel dependencies and includes the core lock. Qt/PySide and Chromium retain their upstream license notices; the MCP SDK is MIT. Installed binaries are not committed or redistributed in this source repository.

## Use the desktop

Discord Rich Presence starts automatically on fresh installs using the simulator's shared public Application ID. **Settings → Discord Rich Presence…** shows connection status and lets users turn sharing off; saved off choices survive updates. No developer setup is needed. Only generic activity and session time are shared. See [setup, privacy, troubleshooting and checks](DISCORD_PRESENCE.md).

1. Click **Test plate** to create a 100 × 40 × 5 mm solid with a 12 mm through hole, or create a project and import STEP/IGES/BREP.
2. Set mesh size, coordinate scale, Young's modulus, Poisson ratio and total axial load in the details panel; click **Apply settings**.
3. Click **Generate mesh** or **Solve**. Meshing and CalculiX run in a separate process while the UI remains responsive.
4. Select Geometry, Mesh or Solution in the outline. Drag the viewport to rotate; use Fit view, Edges and the deformation display selector.

Project inputs, job statuses and results persist in `workspace/workspace.sqlite3` and per-project folders. The workspace is ignored by Git. Input changes invalidate displayed results without deleting historical job files. Active jobs prevent changes to that project's inputs. Job failure messages and worker/solver logs are retained. Cancelling or recovering interrupted workers is not implemented yet; normal jobs finish independently of the GUI window.

Structural analysis supports one solid and one isotropic linear material, with selectable fixed supports and point or surface loads, using C3D4 or C3D10. Modal analysis, steady thermal conduction and the separate CFD benchmark workbench are also enabled. Transient dynamics, electromagnetic, contact, nonlinear, optimization and GPU features remain **disabled controls**. Geometry mode displays undeformed tessellation, not a CAD editor. Structural results include displacement and recovered stress; each other study has its own supported quantities and limitations.

## MCP connection

The app exposes a local stdio MCP server. The assistant and desktop use the same workspace database; the desktop refreshes shared changes automatically. No public listener or network credentials are required.

Start manually:

```powershell
.\.venv\Scripts\python.exe -m opensim.mcp_server
```

Both executables accept `--workspace <absolute-folder>` to use another workspace. Configure both sides with the same folder. Use `python.exe`, not `pythonw.exe`, for the stdio server.

For Codex, register the installed server with absolute paths:

```powershell
codex mcp add doo_doo_dynamics -- 'C:\path\to\project\.venv\Scripts\python.exe' -m opensim.mcp_server --workspace 'C:\path\to\project\workspace'
codex mcp get doo_doo_dynamics --json
```

Restart the client or reconnect its MCP servers to discover the new tools. Registration does not inject tools into a conversation already running. This follows the [official MCP configuration documentation](https://developers.openai.com/codex/mcp/).

Other MCP clients can launch the same command using a standard stdio configuration:

```json
{
  "mcpServers": {
    "doo_doo_dynamics": {
      "command": "C:/path/to/project/.venv/Scripts/python.exe",
      "args": ["-m", "opensim.mcp_server", "--workspace", "C:/path/to/project/workspace"]
    }
  }
}
```

### Tools

The server now exposes 25 tools, including steady thermal conduction and bounded CFD benchmark studies. Restart an existing server after updating so clients can discover the added tools. See [CFD models, controls and verification](CFD.md).

| Tool | Purpose |
| --- | --- |
| `get_capabilities` | Available/planned features, workspace and desktop heartbeat |
| `set_desktop_theme` | Persist light/dark/midnight mode and update the live desktop |
| `list_projects` / `create_project` / `get_project` | Project discovery and creation |
| `import_cad` | Copy an explicitly selected local CAD file into the project |
| `set_analysis_parameters` | Set SI inputs, element order, force direction and face/point application |
| `create_test_object` | Generate a perforated plate, axial bar, cantilever beam or configured thermal heat sink |
| `mesh_project` / `solve_project` | Start asynchronous meshing or static structural solve |
| `get_job` | Poll status, failure or numerical summary |
| `cancel_job` | Stop a queued or running mesh, static or modal job |
| `get_results` | Current results and artifact paths; rejects stale inputs |
| `set_modal_parameters` | Set positive density and 1–30 requested modes |
| `run_modal_analysis` | Start unprestressed frequency extraction with X-min fixed |
| `get_modal_results` | Frequencies, raw data and per-mode HTML/VTK artifacts |
| `set_thermal_parameters` | Conductivity, temperatures in K, source power in W, separate thermal face regions |
| `run_thermal_analysis` | Start steady isotropic conduction; other surfaces insulated |
| `get_thermal_results` | Temperature/heat-flux results, energy balance, HTML/VTK/NPZ/CSV artifacts |
| `set_cfd_parameters` | CFD case and cfd_* inputs; SI except angles in degrees |
| `run_cfd_analysis` | Run cylinder, pipe or flat-plate benchmark; validate_all runs all three theory checks |
| `get_cfd_results` | Current CFD summary and report, PNG, CSV, NPZ and manifest paths |
| `show_in_desktop` | Select project and geometry/mesh/results/modal view and mode number |

Typical sequence: create project → set parameters → create/import CAD → wait for meshing → solve → poll job → get results → show in desktop. Each returned job ID identifies a distinct output folder. The server accepts only the implemented job kinds; it does not expose arbitrary command execution or an executable-path override.

## Verified behavior

**Thermal analysis.** Thermal Analysis has its own tree branch, settings panel and thermal face picks. The desktop shows temperature in °C and flux in W/m², with min/max temperature cards and an energy residual. Prescribed temperatures or fixed temperature plus total surface power are supported; convection/radiation/transients/expansion are not. Home Solve/Results follow the selected study. See [thermal setup and units](THERMAL.md) and [Fourier verification](thermal/REPORT.md).

**Result plots.** Each study has a Result plots entry, plus a settings-panel button and Solution ribbon command. Static plots show nodal displacement/stress versus position and histograms; modal plots show frequencies and normalized shapes; convergence plots show saved values against element count. Charts support pan/zoom, dark/light backgrounds, PNG/SVG export and full-data CSV with run/unit metadata. See [plot usage, interpretation and checks](RESULT_PLOTS.md).

**Study-specific settings.** Open projects contain Static Structural, Modal Analysis and Convergence Study branches. Clicking a study changes the lower settings panel and its Run button. Modal shows density/modes and support-only selection; static shows force controls; convergence adds refinement controls. Hidden values persist. Shared geometry/material/support scope and tests are documented in [study panels](STUDY_PANELS.md).

**Project navigation.** The outline contains only open projects. **Open project…** (Ctrl+O) searches the saved library; closing a project (Ctrl+W) retains all files and jobs. File and right-click menus provide Rename (F2), Close other projects, File locations, and folder shortcuts. The file-locations dialog shows the model copy, recorded import source, run folders and library database, with copy/open buttons. Open projects persist, including an empty session. See [project navigation and checks](PROJECT_NAVIGATION.md).

**Mode shape GIF export.** With a modal result open, **Export GIF** (next to Animate mode) saves the selected mode as a looping animated GIF. It is rendered from the live viewport, so it keeps your camera angle, zoom, theme, labels, color bar and XYZ triad. Choose a width (640, 960 or 1280 px, or the viewport size; never larger than the viewport) and smoothness (24, 36 or 48 frames per cycle). Each GIF holds exactly one vibration cycle and loops seamlessly. Playback is slowed to about one cycle per second, and the label says so, because real frequencies are far too fast to see. Mode shapes are normalized, so the motion size is illustrative. A 960 × 600 export with 36 frames is about 1 MB and takes a few seconds. Progress shows in the status bar. The standalone `mode-N.html` viewer has the same **Export GIF** button and downloads the file directly. Frames use a shared 256-color median-cut palette with standard GIF89a LZW coding, with no extra dependencies. Tests decode the output with Pillow and check the frame count, looping, timing and the symmetry of the motion over the cycle.

**Mesh convergence study.** **Solution → Convergence** (or **Convergence study** in the Analysis Toolbox) re-runs the current static setup on progressively finer meshes. The first mesh uses your mesh size and each later one divides it by the refinement ratio (default 1.4, about 3× the elements per step). It runs up to the chosen number of meshes (3–6, default 4). It stops early once the target changes less than the tolerance (default 2%) between the last two meshes, with at least three meshes solved. Targets are maximum displacement, loaded-area mean displacement along the force, or maximum von Mises stress. All three are always reported. For each quantity the report shows:

- the value and percent change per mesh, with a chart against element count;
- a verdict: converged, converging, not yet converged, or not converging (changes growing, typical of stress singularities);
- when three genuinely refined meshes support a power-law estimate, a Richardson-extrapolated value, observed order and indicative grid convergence index (GCI), using the two measured refinement ratios separately.

The report opens automatically when a study finishes. **Convergence report** returns to the report even after opening a mesh result from its table, and follows the app's current theme. The next mesh is skipped if its estimated count exceeds 300,000; an actual-count check also stops oversized meshes before the solver starts. At least three meshes with increasing element counts are required for a convergence verdict. Each study level's CalculiX solve may run up to 30 minutes, versus 120 s for a normal solve. **Stop computing** ends a study at any point. CLI: `open-sim convergence part.step --out runs/study --mesh-size 0.01 --order 2 --levels 4 --target response …`. MCP: `run_convergence_study` and `get_convergence_results`; the catalog has 19 tools. The real C3D10 beam test checks early stopping against Euler–Bernoulli theory. Mesh stability does not establish physical accuracy, and the GCI estimate is not a guaranteed error bound.

**Axis triad and orientation fix.** The bottom-left corner of the viewport shows an X/Y/Z triad (red, green, blue) that turns with the camera. Use it to read force and support directions. An axis drawn dimmer points away from you. An axis pointing straight at you shows as a dot, and one pointing straight away shows as a ring. The triad is computed from the model's own projection, so it always matches the picture. This work also fixed a projection bug: earlier viewers drew a mirror image seen from the far side of the part. For example, Top XY actually looked up from underneath. Views are now true rotations. Iso looks down from the +X/−Y/+Z side, Front XZ looks along +Y, and Top XY looks down −Z. Drag-to-rotate now moves the near surface with the mouse. Saved results pick up the corrected renderer automatically. A browser test checks that every camera preset is right-handed and fails on the old mirrored projection.

**Mesh file import.** **Import CAD** also accepts **STL, OBJ and 3MF** surface meshes. The importer automatically merges coincident vertices, removes duplicate/degenerate triangles and repairs flipped triangles or inside-out shells. It rejects holes, non-manifold edges and disconnected surface shells. Assemblies and separate enclosed cavity shells are unsupported. Gmsh initially splits the surface into face patches at a 40° threshold; failed patch construction retries at 25° and 10°. These patches become clickable faces and are remeshed at the requested size. The job log and `mesh.repair.json` record preparation and retry details; originals remain untouched. See [automatic repair and limits](MESH_REPAIR.md). STL/OBJ use file-coordinate units. 3MF uses its declared units and build transform, normalized internally to millimeters; the primary model relationship is respected. The desktop defaults mesh imports to CAD scale 0.001 when the current scale is 1. Change it for STL/OBJ exports in other units. A tip-center point load needs exact CAD; for mesh parts, use surface traction. Curved surfaces remain faceted. Checks compare the perforated plate's STL/OBJ/3MF volume and area to STEP within 0.5%, and STL beam displacement to STEP within 1%.

**Stop computing** appears next to the bottom progress bar and in the Analysis Toolbox for queued/running mesh, static, modal and convergence jobs. After confirmation, the job is marked *Stopped by user*, its worker ends CalculiX and exits, and project inputs unlock. Logs and partial files remain. Meshing runs inside Gmsh's native code, so the worker process is ended. Stopping also clears abandoned running jobs after a crash/reboot. MCP provides `cancel_job(job_id)` within the 19-tool catalog. Late completion reports cannot replace cancellation, and a cancelled example cannot overwrite newly imported CAD.

**Force direction** now includes **Perpendicular · inward/outward**, which automatically selects distributed surface loading. The force input remains in N; positive follows the selected inward/outward direction and negative reverses it. On curved/multiple surfaces its magnitude is the sum of local force magnitudes, which can differ from the net vector. Tooltips and an explanatory note describe this. Results show local load arrows, mean movement along the force normals and vector reactions. See [implementation, limits and tests](NORMAL_LOADS.md).

Use **Pick fixed support** / **Pick force faces** in the left panel or Environment tab to select CAD faces directly in the model. Cyan marks fixed supports, orange marks force surfaces. Switch roles freely, then use **Save picked faces**, **Clear current faces** or **Cancel picking** above the model. A new mesh is needed once for older saved viewers. Face selection saves through the existing workspace/MCP region settings; forces retain their total magnitude and direction. See [face selection and verification](SURFACE_REGIONS.md).

The model tree and properties panel have an 8-pixel vertical resize handle with a hover highlight, resize cursor and drag hint. Both panels retain useful minimum heights and cannot collapse accidentally. The desktop layout check drags the handle and verifies that the two panels resize in opposite directions and can return to their original sizes.

The compact ribbon uses single-line buttons with hover explanations. Sample model creation is confined to the Examples tab; Home and Geometry contain project actions, while Validation contains reference reports. Reduced ribbon, card and toolbar spacing moves the viewport higher. The ribbon measures 80 logical pixels tall with Segoe UI 10 on Windows, down from 116, and scrolls horizontally when commands exceed the available width. Native layout checks covered every tab at 1100 and 1520 window widths in both themes and both languages without clipped command labels. The seven desktop tests also pass.

Hover over a button, numeric field or dropdown for a short plain-language explanation. Property labels carry the same help as their inputs. Help covers material and load units, mesh tradeoffs, static versus modal behavior, display-only deformation scaling, and support/load region entry. It stays readable in both themes and remains in English in Cat mode for clarity. Seven focused desktop tests pass, including control coverage, refresh/theme/language persistence and unchanged project settings.

Number fields in the left properties panel ignore mouse-wheel input even when focused. The wheel can scroll the containing panel without altering analysis values. Typing, keyboard arrows and the field's stepper buttons remain available. Desktop checks cover both integer and decimal fields, both wheel directions, focused/unfocused states and unchanged project inputs. A synthetic wheel event delivered to a visible native field also verified panel scrolling.

The bottom status bar now shows live job progress for static, modal, mesh and example jobs: waiting, geometry creation, meshing, input preparation, CalculiX solve, result reading and saving, with elapsed time. Running stages use an indeterminate activity bar because the solver does not expose a reliable percentage. The bar becomes complete only after the job and exports finish; failures stop it and point to the job log. Switching projects or changing inputs resets it to the matching job state. `get_job` exposes the same `progress_stage` through MCP. A separate progress table preserves legacy job records and the existing jobs-column layout. The expanded suite passed 135 tests in 73.68 seconds. A native solve was observed through the stages and reached the completed bar; focused UI checks also cover failures, stale inputs and Cat mode.

The properties panel wraps explanations and keeps controls inside the dock at narrow/wide sizes in both languages. The current suite contains 128 passing tests. Selected support/load regions and recovered stress contours are documented in [surface regions](SURFACE_REGIONS.md), including the native-unit conversion and limitations of fully fixed support approximations.

Modal analysis is now enabled in the desktop toolbox and Solution ribbon. Density, mode count, mode selection and normalized animation are available; see [modal setup](MODAL.md) and [validation](modal/REPORT.md). The MCP catalog has expanded from 13 to **16** tools with `set_modal_parameters`, `run_modal_analysis` and `get_modal_results`. `show_in_desktop` also accepts `view="modal"` and a `mode` number. Static and modal results stay separate and both reject stale revisions. Reconnect an existing MCP client to discover the new catalog.

The full suite passes 116 tests locally, including real MCP stdio modal and distributed-load solves, persistent theme and joke-language toggling, parameter validation, disabled UI controls, saved-viewer upgrades, top-header placement, C3D10 node mapping and quadratic face/load integration, point-force deck generation, cross-process jobs, stale-result rejection, malformed-CAD failure and the structural benchmarks. The [cantilever report](cantilever/REPORT.md) documents the bending comparison and mesh refinement. A separate MCP workflow configured the quadratic beam, applied its point load, solved it, selected its desktop results view and enabled dark mode.

Uniform distributed traction is available through **Force application → Uniform surface traction**, plus the bounding-plane surface selector and signed total force in N. The MCP `set_analysis_parameters` tool accepts `load_kind="traction"` and `load_surface="z-max"` (or any X/Y/Z min/max plane). See [setup](DISTRIBUTED_LOADS.md) and [validation](distributed/REPORT.md). The surface selector is ignored for legacy equal-node and point loads; modal analysis ignores loads.

The Validation ribbon also opens the [Timoshenko bending/shear report](timoshenko/REPORT.md) and [circular-hole stress report](hole/REPORT.md) in native desktop report windows. These published reference studies are explicitly separate from the selected project's settings. A new thin-beam desktop project was solved through the shared background worker and displayed with the front XZ camera and Uz contours, matching the Timoshenko study's fine-mesh result.

The native app was also launched with `pythonw.exe`; invoking its desktop Solve action completed a second real solver job, refreshed the shared job log and displayed the same numerical result. The Codex registration was added and verified on the development machine; an already-running chat must reconnect or restart to discover the new server.
