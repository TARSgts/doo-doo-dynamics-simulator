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
                assert len(catalog.tools) == 16
                themed = await session.call_tool("set_desktop_theme", {"theme": "dark"})
                assert themed.structuredContent["theme"] == "dark"
                capabilities = await session.call_tool("get_capabilities", {})
                assert not capabilities.isError
                data = capabilities.structuredContent
                assert not next(feature for feature in data["features"] if feature["name"] == "Thermal analysis")["enabled"]
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
                selected = await session.call_tool("show_in_desktop", {"project_id": project_id, "view": "mesh"})
                assert selected.structuredContent["project_id"] == project_id
                rejected = await session.call_tool("set_analysis_parameters", {"project_id": project_id, "poisson": 0.5})
                assert rejected.isError
    asyncio.run(asyncio.wait_for(check(), timeout=30))
