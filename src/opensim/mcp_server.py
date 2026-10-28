import argparse
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from opensim.workspace import CAPABILITIES, Workspace


def create_server(workspace: Workspace) -> FastMCP:
    server = FastMCP("Doo Doo Dynamics Simulator", instructions=(
        "Control the local simulator workspace. Jobs run asynchronously: poll get_job. "
        "All quantities are SI. Static structural supports X-min clamped and X/Y/Z point, legacy equal-node face, or uniform vector traction loads, using C3D4 or C3D10. Traction takes total force in N, not pressure, and load_surface selects an X/Y/Z min/max bounding-plane patch. "
        "Optional support_region/load_region dictionaries select CAD face IDs and box_m centroid filters. A selected support is fully fixed, not contact. Static results include recovered nodal von Mises stress. "
        "Undamped unprestressed modal analysis is available with positive density and default or selected fixed support. "
        "run_convergence_study checks whether results depend on mesh size. Use cancel_job to stop a job that is taking too long. Inspect get_capabilities before requesting other physics. The desktop reflects shared workspace changes."))

    @server.tool()
    def set_modal_parameters(project_id: str, density_kg_m3: float = 7850.0, mode_count: int = 6) -> dict[str, Any]:
        """Set density and 1–30 requested modes. Elasticity, mesh and fixed X-min support come from the project."""
        return workspace.set_parameters(project_id, {"density_kg_m3": density_kg_m3, "mode_count": mode_count})

    @server.tool()
    def run_modal_analysis(project_id: str) -> dict[str, Any]:
        """Start undamped, unprestressed CalculiX eigenfrequency extraction. Static force is ignored; poll get_job."""
        return workspace.start_job(project_id, "modal")

    @server.tool()
    def get_modal_results(project_id: str) -> dict[str, Any]:
        """Return natural frequencies in Hz, normalized mode viewers and raw mode data for current inputs."""
        return workspace.get_modal_results(project_id)

    @server.tool()
    def get_capabilities() -> dict[str, Any]:
        """List implemented and disabled planned features and live desktop status."""
        return {"features": CAPABILITIES, "workspace": str(workspace.root), "desktop": workspace.ui_state()}

    @server.tool()
    def set_desktop_theme(theme: str = "dark") -> dict[str, Any]:
        """Persist dark, light or midnight mode and update the running desktop viewport."""
        workspace.set_theme(theme)
        return workspace.ui_state()

    @server.tool()
    def list_projects() -> list[dict[str, Any]]:
        """List simulation projects and their current input parameters."""
        return workspace.list_projects()

    @server.tool()
    def create_project(name: str) -> dict[str, Any]:
        """Create a local simulation project without overwriting existing projects."""
        project = workspace.create_project(name)
        workspace.show_project(project["id"])
        return project

    @server.tool()
    def get_project(project_id: str) -> dict[str, Any]:
        """Read project configuration and job history."""
        return workspace.get_project(project_id) | {"jobs": workspace.list_jobs(project_id)}

    @server.tool()
    def import_cad(project_id: str, path: str) -> dict[str, Any]:
        """Copy a user-selected local solid into the project: STEP, IGES, BREP, or a closed STL, OBJ or 3MF surface mesh. Mesh files are usually millimeters (cad_scale 0.001); tip point loads need exact CAD."""
        return workspace.import_cad(project_id, path)

    @server.tool()
    def set_analysis_parameters(project_id: str, mesh_size_m: float = 0.004, cad_scale: float = 1.0,
                                young_Pa: float = 210e9, poisson: float = 0.3, load_N: float = 1000,
                                element_order: int = 1, load_axis: str = "x", load_kind: str = "face", load_surface: str = "x-max",
                                support_region: dict[str, Any] | None = None, load_region: dict[str, Any] | None = None) -> dict[str, Any]:
        """Set SI static inputs. With traction, load_axis x/y/z gives global-vector traction; normal-in/normal-out gives local inward/outward normals. Positive load_N follows that choice, negative reverses it. Normal load_N is the surface integral of traction magnitude, not net force on curved/multiple faces. face retains legacy equal-node end loading. Changed inputs invalidate prior results."""
        parameters = {"mesh_size_m": mesh_size_m, "cad_scale": cad_scale,
                                                    "young_Pa": young_Pa, "poisson": poisson, "load_N": load_N,
                                                    "element_order": element_order, "load_axis": load_axis, "load_kind": load_kind, "load_surface": load_surface}
        if support_region is not None:
            parameters["support_region"] = support_region
        if load_region is not None:
            parameters["load_region"] = load_region
        return workspace.set_parameters(project_id, parameters)

    @server.tool()
    def create_test_object(project_id: str, kind: str = "perforated_plate") -> dict[str, Any]:
        """Create perforated_plate, axial_bar or cantilever_beam; return its background job ID."""
        return workspace.start_job(project_id, "example", example=kind)

    @server.tool()
    def mesh_project(project_id: str) -> dict[str, Any]:
        """Start Gmsh tetrahedral meshing. Poll get_job for completion."""
        return workspace.start_job(project_id, "mesh")

    @server.tool()
    def solve_project(project_id: str) -> dict[str, Any]:
        """Start a real CalculiX static structural solve. Poll get_job; no other physics is available."""
        return workspace.start_job(project_id, "solve")

    @server.tool()
    def get_job(job_id: str) -> dict[str, Any]:
        """Read a background job's status, numerical summary or failure."""
        return workspace.get_job(job_id)

    @server.tool()
    def run_convergence_study(project_id: str, levels: int = 4, refinement_ratio: float = 1.4,
                              tolerance_percent: float = 2.0, target: str = "displacement") -> dict[str, Any]:
        """Start a mesh convergence study: the static solve runs at mesh_size_m, then mesh_size_m/ratio, /ratio², … for up to 3–6 meshes, stopping early once the target (displacement = max |U|, response = loaded-area mean displacement along the force, stress = max von Mises) changes less than tolerance_percent. Uses the project's current static settings. Poll get_job, then get_convergence_results."""
        workspace.set_parameters(project_id, {"convergence_levels": levels, "convergence_ratio": refinement_ratio,
                                              "convergence_tolerance_percent": tolerance_percent, "convergence_target": target})
        return workspace.start_job(project_id, "convergence")

    @server.tool()
    def get_convergence_results(project_id: str) -> dict[str, Any]:
        """Return per-mesh values, change between meshes, verdict, Richardson extrapolation/GCI and the HTML report path for the current inputs."""
        return workspace.get_convergence_results(project_id)

    @server.tool()
    def cancel_job(job_id: str) -> dict[str, Any]:
        """Stop a queued or running mesh, static or modal job. Its CalculiX process is ended and the job is marked cancelled; partial files stay in the job folder."""
        return workspace.cancel_job(job_id)

    @server.tool()
    def get_results(project_id: str) -> dict[str, Any]:
        """Return current validated displacement/reaction results and local artifact paths."""
        return workspace.get_results(project_id)

    @server.tool()
    def show_in_desktop(project_id: str, view: str = "results", mode: int = 1) -> dict[str, Any]:
        """Select geometry, mesh, static results or modal view and mode number in the running desktop app."""
        return workspace.show_project(project_id, view, mode)

    return server


def main():
    parser = argparse.ArgumentParser(description="Doo Doo Dynamics Simulator local MCP server")
    parser.add_argument("--workspace", type=Path)
    arguments = parser.parse_args()
    create_server(Workspace(arguments.workspace)).run(transport="stdio")


if __name__ == "__main__":
    main()
