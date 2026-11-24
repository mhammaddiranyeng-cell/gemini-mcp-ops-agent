import json, os, sqlite3
from datetime import datetime, timezone
from mcp.server.fastmcp import FastMCP

DB_PATH = os.getenv("OPS_DB_PATH", "ops_state.db")
mcp = FastMCP("enterprise-ops-mcp")

def get_conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c
def init_db():
    with get_conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS inventory (sku TEXT PRIMARY KEY, name TEXT, stock_qty INT, reorder_threshold INT, unit_cost_usd REAL, supplier TEXT);
            CREATE TABLE IF NOT EXISTS incidents (ticket_id TEXT PRIMARY KEY, site TEXT, severity TEXT, summary TEXT, status TEXT);
            CREATE TABLE IF NOT EXISTS restock_orders (order_id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT, quantity INT, total_cost_usd REAL, approval_status TEXT, reason TEXT, created_at TEXT);
        """)
        if c.execute("SELECT COUNT(*) FROM inventory").fetchone()[0] == 0:
            c.executemany("INSERT INTO inventory VALUES (?,?,?,?,?,?)", [
                ("NET-RTR-01", "5G Edge Router", 2, 5, 220.0, "Phoenicia Tech"),
                ("NET-SW-08", "8-Port PoE Switch", 1, 4, 180.0, "Phoenicia Tech"),
                ("PWR-UPS-2K", "2kVA Rack UPS", 6, 3, 410.0, "Cedars Power"),
            ])
            c.executemany("INSERT INTO incidents VALUES (?,?,?,?,?)", [
                ("INC-401", "Zahle-POP-01", "HIGH", "Uplink packet loss >18%; standby router needed.", "OPEN"),
                ("INC-402", "Beirut-DC-02", "LOW", "SNMP latency spike resolved.", "MONITORING"),
            ])

init_db()
@mcp.resource("ops://policy/sla")
def get_ops_policy() -> str:
    return (
        "1. Restock any SKU with stock_qty < reorder_threshold up to reorder_threshold + 3.\n"
        "2. Orders < $1000 USD are AUTO_APPROVED; >= $1000 USD are PENDING_MANAGER_APPROVAL.\n"
        "3. Escalate OPEN HIGH-severity incidents to Tier-3."
    )

@mcp.tool()
def list_low_stock_inventory() -> str:
    with get_conn() as c:
        rows = c.execute("SELECT * FROM inventory WHERE stock_qty < reorder_threshold").fetchall()
    return json.dumps([dict(r) for r in rows])

@mcp.tool()
def list_open_incidents() -> str:
    with get_conn() as c:
        rows = c.execute("SELECT * FROM incidents WHERE status != 'CLOSED'").fetchall()
    return json.dumps([dict(r) for r in rows])
@mcp.tool()
def create_restock_order(sku: str, quantity: int, justification: str) -> str:
    with get_conn() as c:
        item = c.execute("SELECT * FROM inventory WHERE sku = ?", (sku,)).fetchone()
        if not item:
            return json.dumps({"error": f"Unknown SKU: {sku}"})
        total = round(float(item["unit_cost_usd"]) * quantity, 2)
        status = "AUTO_APPROVED" if total < 1000.0 else "PENDING_MANAGER_APPROVAL"
        cur = c.execute(
            "INSERT INTO restock_orders (sku, quantity, total_cost_usd, approval_status, reason, created_at) VALUES (?,?,?,?,?,?)",
            (sku, quantity, total, status, justification, datetime.now(timezone.utc).isoformat()),
        )
        return json.dumps({"order_id": cur.lastrowid, "sku": sku, "quantity": quantity, "total_cost_usd": total, "approval_status": status})

@mcp.tool()
def escalate_incident(ticket_id: str, escalation_note: str) -> str:
    with get_conn() as c:
        row = c.execute("SELECT * FROM incidents WHERE ticket_id = ?", (ticket_id,)).fetchone()
        if not row:
            return json.dumps({"error": f"Ticket {ticket_id} not found"})
        c.execute("UPDATE incidents SET status = 'ESCALATED_TIER3' WHERE ticket_id = ?", (ticket_id,))
    return json.dumps({"ticket_id": ticket_id, "new_status": "ESCALATED_TIER3", "note": escalation_note})

if __name__ == "__main__":
    mcp.run(transport="stdio")
