# Desktop workbench and MCP automation

The native Windows desktop application provides an engineering ribbon, model outline, material/load/mesh properties, rotatable viewport, analysis toolbox and job log. It uses original interface code and common engineering-workbench conventions. It contains no Ansys interface assets, source code or branding.

Dark mode is on by default. Use the header button or View → Dark mode to switch; the preference persists in the shared workspace. The renderer supports both palettes, automatic deformation scaling, signed displacement components, a color bar, and clamp/load annotations. The properties pane scrolls vertically, input controls disable during active jobs, and top result cards summarize displacement and force balance.

The application title now shares the full-width top bar with the menus and theme control. The viewport uses batched WebGL rendering where available; drag to rotate, Shift/middle/right-drag to pan and scroll to zoom. Existing saved results automatically receive the current renderer when opened in the desktop. See [performance measurements and fallback behavior](VIEWPORT_PERFORMANCE.md).

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

1. Click **Test plate** to create a 100 × 40 × 5 mm solid with a 12 mm through hole, or create a project and import STEP/IGES/BREP.
2. Set mesh size, coordinate scale, Young's modulus, Poisson ratio and total axial load in the details panel; click **Apply settings**.
3. Click **Generate mesh** or **Solve**. Meshing and CalculiX run in a separate process while the UI remains responsive.
4. Select Geometry, Mesh or Solution in the outline. Drag the viewport to rotate; use Fit view, Edges and the deformation display selector.

Project inputs, job statuses and results persist in `workspace/workspace.sqlite3` and per-project folders. The workspace is ignored by Git. Input changes invalidate displayed results without deleting historical job files. Active jobs prevent changes to that project's inputs. Job failure messages and worker/solver logs are retained. Cancelling or recovering interrupted workers is not implemented yet; normal jobs finish independently of the GUI window.

Implemented analysis supports one solid and one isotropic linear material with an X-min clamp and X/Y/Z end forces, using either C3D4 or C3D10. Choose an end-face total nodal force or a single point at the planar tip center. The cantilever preset uses a 1 m × 20 mm × 20 mm beam with −10 N in Z and C3D10. Planned modal, thermal, transient, CFD, electromagnetic, contact, nonlinear, optimization and GPU features remain **disabled controls**. Geometry mode displays undeformed tessellation, not a CAD editor; contour results show total or signed-component displacement only.

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

| Tool | Purpose |
| --- | --- |
| `get_capabilities` | Available/planned features, workspace and desktop heartbeat |
| `set_desktop_theme` | Persist dark/light mode and update the live desktop |
| `list_projects` / `create_project` / `get_project` | Project discovery and creation |
| `import_cad` | Copy an explicitly selected local CAD file into the project |
| `set_analysis_parameters` | Set SI inputs, element order, force direction and face/point application |
| `create_test_object` | Generate a perforated plate, axial bar or cantilever beam |
| `mesh_project` / `solve_project` | Start asynchronous meshing or static structural solve |
| `get_job` | Poll status, failure or numerical summary |
| `get_results` | Current results and artifact paths; rejects stale inputs |
| `set_modal_parameters` | Set positive density and 1–30 requested modes |
| `run_modal_analysis` | Start unprestressed frequency extraction with X-min fixed |
| `get_modal_results` | Frequencies, raw data and per-mode HTML/VTK artifacts |
| `show_in_desktop` | Select project and geometry/mesh/results/modal view and mode number |

Typical sequence: create project → set parameters → create/import CAD → wait for meshing → solve → poll job → get results → show in desktop. Each returned job ID identifies a distinct output folder. The server accepts only the implemented job kinds; it does not expose arbitrary command execution or an executable-path override.

## Verified behavior

The properties panel wraps explanations and keeps controls inside the dock at narrow/wide sizes in both languages. The current suite contains 128 passing tests. Selected support/load regions and recovered stress contours are documented in [surface regions](SURFACE_REGIONS.md), including the native-unit conversion and limitations of fully fixed support approximations.

Modal analysis is now enabled in the desktop toolbox and Solution ribbon. Density, mode count, mode selection and normalized animation are available; see [modal setup](MODAL.md) and [validation](modal/REPORT.md). The MCP catalog has expanded from 13 to **16** tools with `set_modal_parameters`, `run_modal_analysis` and `get_modal_results`. `show_in_desktop` also accepts `view="modal"` and a `mode` number. Static and modal results stay separate and both reject stale revisions. Reconnect an existing MCP client to discover the new catalog.

The full suite passes 116 tests locally, including real MCP stdio modal and distributed-load solves, persistent theme and joke-language toggling, parameter validation, disabled UI controls, saved-viewer upgrades, top-header placement, C3D10 node mapping and quadratic face/load integration, point-force deck generation, cross-process jobs, stale-result rejection, malformed-CAD failure and the structural benchmarks. The [cantilever report](cantilever/REPORT.md) documents the bending comparison and mesh refinement. A separate MCP workflow configured the quadratic beam, applied its point load, solved it, selected its desktop results view and enabled dark mode.

Uniform distributed traction is available through **Force application → Uniform surface traction**, plus the bounding-plane surface selector and signed total force in N. The MCP `set_analysis_parameters` tool accepts `load_kind="traction"` and `load_surface="z-max"` (or any X/Y/Z min/max plane). See [setup](DISTRIBUTED_LOADS.md) and [validation](distributed/REPORT.md). The surface selector is ignored for legacy equal-node and point loads; modal analysis ignores loads.

The Validation ribbon also opens the [Timoshenko bending/shear report](timoshenko/REPORT.md) and [circular-hole stress report](hole/REPORT.md) in native desktop report windows. These published reference studies are explicitly separate from the selected project's settings. A new thin-beam desktop project was solved through the shared background worker and displayed with the front XZ camera and Uz contours, matching the Timoshenko study's fine-mesh result.

The native app was also launched with `pythonw.exe`; invoking its desktop Solve action completed a second real solver job, refreshed the shared job log and displayed the same numerical result. The Codex registration was added and verified on the development machine; an already-running chat must reconnect or restart to discover the new server.
