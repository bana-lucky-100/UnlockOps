"""Show where each natural-language case stops: interpretation or entitlement selection.

Runs the agent's own interpret/select code (no DB, no MCP) against the real model.
Run inside the agent image so dependencies match, e.g. from the repo root:
  docker run --rm --env-file .env -e AGENT_MODE=llm -e PYTHONPATH=/app/agent \
    -v "$PWD/agent:/app/agent:ro" -v "$PWD/data:/app/data:ro" \
    -v "$PWD/scripts/phase2/diagnose_interpret.py:/tmp/diagnose.py:ro" \
    unlockops-agent python /tmp/diagnose.py N-04 N-06
No arguments = all 20 cases. Prints no secrets.
"""
import asyncio
import json
import re
import sys
from pathlib import Path

from unlockops.access.intent import interpret_v4
from unlockops.access.planner import raw_intent
from unlockops.access.selection import select_entitlement
from unlockops.common.models import ToolFailure
from unlockops.common.settings import settings

DATA = Path("/app/data/phase2")
natural = json.loads((DATA / "scenarios-natural-v1.json").read_text())["cases"]
v4 = {s["id"]: s for s in json.loads((DATA / "scenarios-current.json").read_text())["scenarios"]}
catalog = json.loads((DATA / "catalog.json").read_text())
seed = (DATA / "seed.sql").read_text()

resources = {m.group(1): {"company_id": m.group(2), "platform": m.group(3), "external_id": m.group(4), "name": m.group(5)}
             for m in re.finditer(r"INSERT INTO resources \([^)]*\) VALUES \('([^']+)','([^']+)','([^']+)','([^']+)','([^']+)'", seed)}
options = [{"id": m.group(1), "resource_id": m.group(3), "code": m.group(4), "kind": m.group(5),
            "name": resources[m.group(3)]["name"], "external_id": resources[m.group(3)]["external_id"],
            "platform": resources[m.group(3)]["platform"], "company_id": m.group(2)}
           for m in re.finditer(r"INSERT INTO entitlements \([^)]*\) VALUES \('([^']+)','([^']+)','([^']+)','([^']+)','([^']+)'", seed)
           if m.group(3) in resources]
code_of = {o["id"]: o["code"] for o in options}


async def diagnose(case):
    base = v4[case["base"]]
    company = catalog["companies"][base["company"]]["company_id"]
    item = next(x for x in catalog["catalog"] if x["company"] == base["company"] and x["platform"] == base["platform"])
    resource = None if case["base"] == "B-05" else base["overrides"].get("resource_id", item["resource_id"])
    text, platform = case["input_text"], base["platform"]
    row = {"id": case["id"], "expected": case.get("expected_entitlement"), "rule_role": raw_intent(text).requested_role}
    try:
        intent = await interpret_v4(text, platform)
    except ToolFailure as error:
        return {**row, "stopped_at": "interpret", "reason": f"{error.code}: {error}"}
    row.update(llm_request_type=intent.request_type, llm_role=intent.requested_role, llm_out_of_scope=intent.out_of_scope)
    if intent.out_of_scope:
        return {**row, "stopped_at": "interpret", "reason": "LLM marked out_of_scope"}
    if intent.request_type == "GUIDE":
        return {**row, "stopped_at": None, "reason": "guidance (no selection)"}
    context = {"problem": {"contents": text, "platform": platform, "resource_id": resource},
               "entitlements": [o for o in options if o["company_id"] == company and o["platform"] == platform]}
    try:
        chosen, least = await select_entitlement(context, intent.model_dump())
    except ToolFailure as error:
        return {**row, "stopped_at": "select", "reason": f"{error.code}: {error}"}
    return {**row, "stopped_at": None, "chosen": code_of.get(chosen), "least_privilege": least}


async def main(ids):
    print(f"mode={settings.mode}", file=sys.stderr)
    for case in natural:
        if ids and case["id"] not in ids:
            continue
        print(json.dumps(await diagnose(case), ensure_ascii=False), flush=True)


asyncio.run(main(set(sys.argv[1:])))
