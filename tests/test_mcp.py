import asyncio
import json
import sys

import pytest

mcp = pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_actual_stdio_protocol_and_workspace_mutation(tmp_path):
    from opensim.geometry import make_box
    cad = tmp_path / "beam.step"
    make_box(cad, (0.1, 0.02, 0.02))
    async def check():
        parameters = StdioServerParameters(command=sys.executable,
                                            args=["-m", "opensim.mcp_server", "--workspace", str(tmp_path)])
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                catalog = await session.list_tools()
                assert len(catalog.tools) == 22
                assert {"cancel_job", "run_convergence_study", "get_convergence_results"} <= {tool.name for tool in catalog.tools}
                themed = await session.call_tool("set_desktop_theme", {"theme": "dark"})
                assert themed.structuredContent["theme"] == "dark"
                themed = await session.call_tool("set_desktop_theme", {"theme": "midnight"})
                assert themed.structuredContent["theme"] == "midnight"
                capabilities = await session.call_tool("get_capabilities", {})
                assert not capabilities.isError
                data = capabilities.structuredContent
                assert next(feature for feature in data["features"] if feature["name"] == "Thermal analysis")["enabled"]
                assert {'set_thermal_parameters','run_thermal_analysis','get_thermal_results'} <= {tool.name for tool in catalog.tools}
                created = await session.call_tool("create_project", {"name": "MCP project"})
                project_id = created.structuredContent["id"]
                configured = await session.call_tool("set_analysis_parameters", {"project_id": project_id, "load_N": 1500})
                assert configured.structuredContent["parameters"]["load_N"] == 1500
                modal = await session.call_tool("set_modal_parameters", {"project_id": project_id, "density_kg_m3": 2700, "mode_count": 8})
                assert modal.structuredContent["parameters"]["density_kg_m3"] == 2700
                assert modal.structuredContent["parameters"]["mode_count"] == 8
                missing = await session.call_tool("get_modal_results", {"project_id": project_id})
                assert missing.isError
                rejected_modal = await session.call_tool("set_modal_parameters", {"project_id": project_id, "density_kg_m3": -1})
                assert rejected_modal.isError
                from opensim.solver import find_solver
                try:
                    find_solver()
                except FileNotFoundError:
                    solver_available = False
                else:
                    solver_available = True
                if solver_available:
                    await session.call_tool("import_cad", {"project_id": project_id, "path": str(cad)})
                    await session.call_tool("set_analysis_parameters", {"project_id": project_id, "mesh_size_m": 0.01, "element_order": 2})
                    await session.call_tool("set_modal_parameters", {"project_id": project_id, "mode_count": 3})
                    job = await session.call_tool("run_modal_analysis", {"project_id": project_id})
                    assert not job.isError
                    job_id = job.structuredContent["id"]
                    while True:
                        status = await session.call_tool("get_job", {"job_id": job_id})
                        if status.structuredContent["status"] not in {"queued", "running"}:
                            break
                        await asyncio.sleep(0.05)
                    assert status.structuredContent["status"] == "completed"
                    results = await session.call_tool("get_modal_results", {"project_id": project_id})
                    assert len(results.structuredContent["modes"]) == 3
                    shown = await session.call_tool("show_in_desktop", {"project_id": project_id, "view": "modal", "mode": 2})
                    assert shown.structuredContent["modal_mode"] == 2
                    thermal = await session.call_tool('set_thermal_parameters', {'project_id':project_id,'conductivity_W_mK':10})
                    assert not thermal.isError
                    assert thermal.structuredContent['parameters']['thermal_fixed_temperature_K']==293.15
                    thermal_job = await session.call_tool('run_thermal_analysis', {'project_id':project_id})
                    assert not thermal_job.isError
                    while True:
                        thermal_status = await session.call_tool('get_job', {'job_id':thermal_job.structuredContent['id']})
                        if thermal_status.structuredContent['status'] not in {'queued','running'}:break
                        await asyncio.sleep(.05)
                    assert thermal_status.structuredContent['status']=='completed',thermal_status.structuredContent
                    thermal_result = await session.call_tool('get_thermal_results', {'project_id':project_id})
                    assert not thermal_result.isError
                    assert thermal_result.structuredContent['summary']['maximum_temperature_K']==373.15
                    thermal_shown = await session.call_tool('show_in_desktop', {'project_id':project_id,'view':'thermal'})
                    assert thermal_shown.structuredContent['study']=='thermal'
                    configured_load = await session.call_tool("set_analysis_parameters", {"project_id": project_id, "mesh_size_m": 0.01, "element_order": 2,
                        "poisson": 0, "load_N": -10, "load_axis": "z", "load_kind": "traction", "load_surface": "z-max",
                        "support_region": {"box_m": [-0.000001,-0.001,-0.001,0.000001,0.021,0.021]},
                        "load_region": {"box_m": [-0.001,-0.001,0.019999,0.101,0.021,0.020001]}})
                    assert configured_load.structuredContent["parameters"]["load_surface"] == "z-max"
                    load_job = await session.call_tool("solve_project", {"project_id": project_id})
                    while True:
                        load_status = await session.call_tool("get_job", {"job_id": load_job.structuredContent["id"]})
                        if load_status.structuredContent["status"] not in {"queued", "running"}:
                            break
                        await asyncio.sleep(0.05)
                    assert load_status.structuredContent["status"] == "completed"
                    load_result = await session.call_tool("get_results", {"project_id": project_id})
                    assert load_result.structuredContent["summary"]["reaction_N"][2] == pytest.approx(10, rel=1e-5)
                    assert load_result.structuredContent["summary"]["reaction_moment_Nm"][1] == pytest.approx(-0.5, rel=1e-5)
                selected = await session.call_tool("show_in_desktop", {"project_id": project_id, "view": "mesh"})
                assert selected.structuredContent["project_id"] == project_id
                rejected = await session.call_tool("set_analysis_parameters", {"project_id": project_id, "poisson": 0.5})
                assert rejected.isError
    asyncio.run(asyncio.wait_for(check(), timeout=30))
