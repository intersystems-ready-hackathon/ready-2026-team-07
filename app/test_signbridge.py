"""Smoke test for the SignBridge MCP endpoint.

Discovers tools at /mcp/signbridge and invokes ProcessIntake with the
red-flag preset. Prints the activity log and the final Markdown brief.

Usage:
    pip install -r app/requirements.txt
    python app/test_signbridge.py
"""

import asyncio
import base64
import json

from langchain_mcp_adapters.client import MultiServerMCPClient


URL = "http://localhost:8080/mcp/signbridge"
AUTH = "Basic " + base64.b64encode(b"SuperUser:SYS").decode()


PRESET_RED_FLAG = {
    "patient_id":      None,
    "chief_complaint": "chest pain radiating to left arm",
    "duration":        "2 hours",
    "age":             58,
    "sex":             "M",
    "sign_style":      "BSL",
    "known_conditions":["type 2 diabetes", "hypertension"],
    "current_meds":    ["metformin 1000mg BID", "lisinopril 20mg"],
    "free_text":       "Crushing pressure, sweaty, nauseated. No nitroglycerin tried.",
}


async def main() -> None:
    client = MultiServerMCPClient(
        {
            "signbridge": {
                "transport": "http",
                "url": URL,
                "headers": {"Authorization": AUTH},
            }
        }
    )
    tools = await client.get_tools()
    print(f"Discovered {len(tools)} tools at {URL}:")
    for t in sorted(tools, key=lambda x: x.name):
        print(f"  - {t.name}")

    target = next((t for t in tools if t.name.endswith("ProcessIntake")), None)
    if target is None:
        raise SystemExit("ProcessIntake tool not found.")

    print("\nInvoking ProcessIntake with the red-flag preset...\n")
    raw = await target.ainvoke({"intakeJson": json.dumps(PRESET_RED_FLAG)})
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            print(raw)
            return
    else:
        data = raw

    if not data.get("ok"):
        print("ERROR:", data.get("error"))
        return

    print(data["brief"])
    if data.get("tokens"):
        print("\nTokens:", data["tokens"])


if __name__ == "__main__":
    asyncio.run(main())
