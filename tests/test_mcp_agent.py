import json, os, sys, tempfile, pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

@pytest.mark.anyio
async def test_mcp_guardrails():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db = tmp.name
    try:
        env = {**os.environ, "OPS_DB_PATH": db}
        params = StdioServerParameters(command=sys.executable, args=["-m", "server.ops_mcp_server"], env=env)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                small = json.loads((await s.call_tool("create_restock_order", {"sku": "NET-SW-08", "quantity": 4, "justification": "test"})).content[0].text)
                assert small["approval_status"] == "AUTO_APPROVED"
                large = json.loads((await s.call_tool("create_restock_order", {"sku": "NET-RTR-01", "quantity": 6, "justification": "test"})).content[0].text)
                assert large["approval_status"] == "PENDING_MANAGER_APPROVAL"
    finally:
        if os.path.exists(db):
            os.remove(db)
