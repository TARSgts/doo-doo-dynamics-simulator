import argparse
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from opensim.workspace import CAPABILITIES, Workspace


def create_server(workspace: Workspace) -> FastMCP:
    server = FastMCP("Doo Doo Dynamics Simulator", instructions=(
        "Control the local simulator workspace. Jobs run asynchronously: poll get_job. "
        "All quantities are SI. Static structural supports X-min clamped and X/Y/Z end-face or tip-center point loads, using C3D4 or C3D10. "
        "Inspect get_capabilities before requesting other physics. The desktop reflects shared workspace changes."))

    @server.tool()
    def get_capabilities() -> dict[str, Any]:
        """List implemented and disabled planned features and live desktop status."""
        return {"features": CAPABILITIES, "workspace": str(workspace.root), "desktop": workspace.ui_state()}

    @server.tool()
    def set_desktop_theme(theme: str = "dark") -> dict[str, Any]:
        """Persist dark or light mode and update the running desktop viewport."""
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
        """Copy a user-selected local STEP, IGES or BREP solid into the project."""
        return workspace.import_cad(project_id, path)

    @server.tool()
    def set_analysis_parameters(project_id: str, mesh_size_m: float = 0.004, cad_scale: float = 1.0,
                                young_Pa: float = 210e9, poisson: float = 0.3, load_N: float = 1000,
                                element_order: int = 1, load_axis: str = "x", load_kind: str = "face") -> dict[str, Any]:
        """Set all static-analysis inputs in SI units. Existing results become stale when inputs change."""
        return workspace.set_parameters(project_id, {"mesh_size_m": mesh_size_m, "cad_scale": cad_scale,
                                                    "young_Pa": young_Pa, "poisson": poisson, "load_N": load_N,
                                                    "element_order": element_order, "load_axis": load_axis, "load_kind": load_kind})

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
    def get_results(project_id: str) -> dict[str, Any]:
        """Return current validated displacement/reaction results and local artifact paths."""
        return workspace.get_results(project_id)

    @server.tool()
    def show_in_desktop(project_id: str, view: str = "results") -> dict[str, Any]:
        """Select the project and geometry, mesh or results view in the running desktop app."""
        return workspace.show_project(project_id, view)

    return server


def main():
    parser = argparse.ArgumentParser(description="Doo Doo Dynamics Simulator local MCP server")
    parser.add_argument("--workspace", type=Path)
    arguments = parser.parse_args()
    create_server(Workspace(arguments.workspace)).run(transport="stdio")


if __name__ == "__main__":
    main()
