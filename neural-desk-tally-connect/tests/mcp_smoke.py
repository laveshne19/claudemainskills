"""Starts the real MCP server over stdio against the simulated Tally and calls tools like Claude would."""
import asyncio, json, os, pathlib, sys, tempfile
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tally_connect.mocktally import MockTally
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    m = MockTally().start()
    home = tempfile.mkdtemp()
    cfg = {"host": "127.0.0.1", "port": m.port, "company_gstin": "04AAAAA0000A1Z5", "company_state": "Chandigarh"}
    pathlib.Path(home, "config.json").write_text(json.dumps(cfg))
    env = {**os.environ, "TALLY_CONNECT_HOME": home, "PYTHONPATH": str(ROOT / "src")}
    params = StdioServerParameters(command=sys.executable, args=["-m", "tally_connect.server"], env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = [t.name for t in (await s.list_tools()).tools]
            print("tools:", len(tools), tools)
            d = json.loads((await s.call_tool("tally_doctor", {})).content[0].text)
            print("doctor ->", d["gateway_reachable"], d["company_loaded"], d["companies"])
            f = json.loads((await s.call_tool("find_ledger", {"name": "bright"})).content[0].text)
            print("find_ledger ->", f["status"], f["name"])
            pv = json.loads((await s.call_tool("preview_invoice", {
                "voucher_type": "Sales", "date": "2026-09-07", "number": "9001", "party_ledger": "SHARMA TELECOM",
                "items": [{"stock_item": "Pb331", "qty": 1, "rate": 100.0, "amount": 100.0, "ledger": "SALES LOCAL@ 18%"}],
                "tax": [["CGST OUTPUT", 9.0], ["UTGST OUTPUT", 9.0]], "total": 118.0,
                "party_gstin": "04AAAAA1111A1Z5", "party_state": "Chandigarh", "place_of_supply": "Chandigarh"})).content[0].text)
            print("preview ->", pv["ok"], pv["summary"]["expected_delta"])
            cf = json.loads((await s.call_tool("confirm_import", {"preview_id": pv["preview_id"]})).content[0].text)
            print("confirm ->", cf["ok"], cf["verified"], cf["balance_delta"])
            assert d["company_loaded"] and cf["verified"]
    m.stop()
    print("MCP SMOKE OK")
asyncio.run(main())
