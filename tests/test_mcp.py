import asyncio
import json
import sys

import pytest

mcp = pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_actual_stdio_protocol_and_workspace_mutation(tmp_path):
    async def check():
        parameters = StdioServerParameters(command=sys.executable,
                                            args=["-m", "opensim.mcp_server", "--workspace", str(tmp_path)])
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                catalog = await session.list_tools()
                assert len(catalog.tools) == 13
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
                selected = await session.call_tool("show_in_desktop", {"project_id": project_id, "view": "mesh"})
                assert selected.structuredContent["project_id"] == project_id
                rejected = await session.call_tool("set_analysis_parameters", {"project_id": project_id, "poisson": 0.5})
                assert rejected.isError
    asyncio.run(check())
