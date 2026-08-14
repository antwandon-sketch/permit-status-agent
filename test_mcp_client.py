"""
Throwaway script: proves server.py works as a real MCP server, not just
as a Python function call. Launches server.py as a real subprocess and
talks real MCP protocol to it over stdio, using the mcp v2 SDK's own
client (mcp==2.0.0 — this project's venv was rebuilt on Python 3.12 for
that reason; the mcp package requires 3.10+).
"""
import asyncio
import json
import sys

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=["server.py"])

    async with Client(stdio_client(params)) as client:
        print("=== list_tools() ===")
        tools = await client.list_tools()
        for t in tools.tools:
            print(f"- {t.name}: {t.description.strip().splitlines()[0]}")
        print()

        print("=== call_tool: check_permit_status(identifier='ELEC-24-00375') ===")
        result = await client.call_tool(
            "check_permit_status", {"identifier": "ELEC-24-00375"}
        )
        for block in result.content:
            if hasattr(block, "text"):
                print(json.dumps(json.loads(block.text), indent=2))
        print()

        print("=== call_tool: get_inspection_history(permit_number='2016-8666') ===")
        result = await client.call_tool(
            "get_inspection_history", {"permit_number": "2016-8666"}
        )
        for block in result.content:
            if hasattr(block, "text"):
                print(json.dumps(json.loads(block.text), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
