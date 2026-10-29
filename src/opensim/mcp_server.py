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
        "Steady thermal conduction is available through set_thermal_parameters/run_thermal_analysis/get_thermal_results; Kelvin, W, W/m/K. No convection, radiation or thermal expansion. "
        "Static load_cases independently specify name, kind force/pressure, components_N or pressure_Pa, region, surface, enabled. Nonempty load_cases replace the legacy single load. Pressure is positive inward. material_preset selects editable generic Steel, Aluminum or solid ABS defaults. "
        "CFD is a main-window project study. With cfd_case=cad and cfd_backend=su2, the imported CAD may be a solid (cfd_domain_mode=external builds surrounding fluid) or an existing fluid passage (fluid). Configure cfd_speed_m_s, fluid density/viscosity, cfd_flow_axis x/y/z, near-model mesh size, CAD scale, and cfd_turbulence none/sa. SU2 solves steady incompressible Navier-Stokes or SA RANS. cfd_backend=stokes retains pressure-driven Re<=1 flow on existing fluid volumes. No thermal coupling or time-accurate wakes. show_in_desktop views cfd_slice, cfd and cfd_report select main-window flow results. "
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
                                support_region: dict[str, Any] | None = None, load_region: dict[str, Any] | None = None,
                                load_cases: list[dict[str, Any]] | None = None, material_preset: str | None = None) -> dict[str, Any]:
        """Set SI inputs. Nonempty load_cases replaces the legacy load: each entry has name, kind=force/pressure, components_N=[Fx,Fy,Fz] or pressure_Pa (positive inward), region (CAD face IDs/box_m), surface fallback, enabled. Entries act simultaneously. Empty list restores legacy face/point/traction settings. material_preset: Steel (generic), Aluminum (generic), ABS (solid, isotropic approximation); sets E, nu, density and conductivity together. Changed inputs invalidate prior results."""
        parameters = {"mesh_size_m": mesh_size_m, "cad_scale": cad_scale,
                                                    "young_Pa": young_Pa, "poisson": poisson, "load_N": load_N,
                                                    "element_order": element_order, "load_axis": load_axis, "load_kind": load_kind, "load_surface": load_surface}
        if support_region is not None:
            parameters["support_region"] = support_region
        if load_region is not None:
            parameters["load_region"] = load_region
        if load_cases is not None: parameters['load_cases']=load_cases
        if material_preset is not None:
            from opensim.materials import MATERIALS
            if material_preset not in MATERIALS:raise ValueError('Choose: '+', '.join(MATERIALS))
            parameters.update(MATERIALS[material_preset]);parameters['material_name']=material_preset
        return workspace.set_parameters(project_id, parameters)

    @server.tool()
    def create_test_object(project_id: str, kind: str = "perforated_plate") -> dict[str, Any]:
        """Create perforated_plate, axial_bar, cantilever_beam or heat_sink; return a background job ID. heat_sink sets a 20 W base, 20 °C fin tips and k=200 W/m/K for a steady-conduction demonstration, not convection."""
        return workspace.start_job(project_id, "example", example=kind)

    @server.tool()
    def mesh_project(project_id: str) -> dict[str, Any]:
        """Start Gmsh tetrahedral meshing. Poll get_job for completion."""
        return workspace.start_job(project_id, "mesh")

    @server.tool()
    def solve_project(project_id: str) -> dict[str, Any]:
        """Start a real CalculiX static structural solve. Poll get_job. Use run_thermal_analysis for conduction."""
        return workspace.start_job(project_id, "solve")

    @server.tool()
    def set_thermal_parameters(project_id: str, conductivity_W_mK: float = 1., fixed_temperature_K: float = 293.15,
                               source_temperature_K: float = 373.15, boundary_mode: str = "temperature", power_W: float = 10.,
                               fixed_region: dict[str, Any] | None = None, source_region: dict[str, Any] | None = None) -> dict[str, Any]:
        """Set steady isotropic thermal inputs, SI (Kelvin, W, W/m/K). Choose temperature or power on the source faces. Defaults: X-min fixed temperature, X-max source, other surfaces insulated. Thermal selections are independent of structural supports/loads. No convection/radiation/transients/expansion."""
        parameters = {"thermal_conductivity_W_mK": conductivity_W_mK, "thermal_fixed_temperature_K": fixed_temperature_K,
                      "thermal_source_temperature_K": source_temperature_K, "thermal_boundary_mode": boundary_mode, "thermal_power_W": power_W}
        if fixed_region is not None: parameters['thermal_fixed_region'] = fixed_region
        if source_region is not None: parameters['thermal_source_region'] = source_region
        return workspace.set_parameters(project_id, parameters)

    @server.tool()
    def run_thermal_analysis(project_id: str) -> dict[str, Any]:
        """Start steady conduction with CalculiX. Poll get_job, then get_thermal_results. Temperatures and heat flux, not thermal stress."""
        return workspace.start_job(project_id, 'thermal')

    @server.tool()
    def get_thermal_results(project_id: str) -> dict[str, Any]:
        """Return current temperature/heat-flow summary, energy balance, viewer, VTK, CSV and NPZ in SI (Kelvin, W, W/m²). Desktop display uses Celsius."""
        return workspace.get_thermal_results(project_id)

    @server.tool()
    def set_cfd_parameters(project_id: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Set cfd_* inputs. For real CAD use cfd_case=cad, cfd_backend=su2, cfd_domain_mode=external (solid body with automatic enclosure) or fluid (existing passage). Set cfd_mesh_size_m, cfd_cad_scale, cfd_speed_m_s, cfd_density_kg_m3, cfd_viscosity_Pa_s, cfd_flow_axis=x/y/z, cfd_turbulence=none/sa, cfd_iterations and cfd_residual_target (log10). Independent cfd_inlet_region/cfd_outlet_region accept faces or box_m; blank uses automatic ports. Legacy stokes is pressure-driven Re<=1 on fluid volumes. Other benchmark cases remain available. No thermal coupling or time-accurate CFD."""
        from opensim.cfd_parameters import CFD_DEFAULTS
        if set(parameters) - set(CFD_DEFAULTS):
            raise ValueError('Use only cfd_* parameters from the CFD defaults')
        return workspace.set_parameters(project_id, parameters)

    @server.tool()
    def run_cfd_analysis(project_id: str, validate_all: bool = False) -> dict[str, Any]:
        """Start the current project's CFD. cad uses SU2 Navier-Stokes/SA RANS on user solids or fluid volumes when cfd_backend=su2, or legacy Stokes otherwise. validate_all runs the original analytical reference checks. Poll get_job then get_cfd_results; display cfd_slice/cfd/cfd_report in the main desktop. Failed convergence is not returned as a valid solution."""
        return workspace.start_job(project_id, 'cfd_validation' if validate_all else 'cfd')

    @server.tool()
    def get_cfd_results(project_id: str) -> dict[str, Any]:
        """Return current CFD results, model assumptions, numerical/reference comparison, report, plotted CSV, full arrays and PNG chart."""
        return workspace.get_cfd_results(project_id)

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
        """Stop a queued or running mesh, static, modal, convergence or thermal job. Its CalculiX process is ended; partial files stay in the job folder."""
        return workspace.cancel_job(job_id)

    @server.tool()
    def get_results(project_id: str) -> dict[str, Any]:
        """Return current validated displacement/reaction results and local artifact paths."""
        return workspace.get_results(project_id)

    @server.tool()
    def show_in_desktop(project_id: str, view: str = "results", mode: int = 1) -> dict[str, Any]:
        """Select geometry, mesh, static results, modal or thermal view in the running desktop app. Mode selects a vibration mode only."""
        return workspace.show_project(project_id, view, mode)

    return server


def main():
    parser = argparse.ArgumentParser(description="Doo Doo Dynamics Simulator local MCP server")
    parser.add_argument("--workspace", type=Path)
    arguments = parser.parse_args()
    create_server(Workspace(arguments.workspace)).run(transport="stdio")


if __name__ == "__main__":
    main()
