"""Prepare independent mock tenants; never rewrite a running demo company's facts."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
UUID_RE = re.compile(r"\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b")
LITERAL = re.compile(r"'((?:''|[^'])*)'", re.S)
BASE = datetime.fromisoformat("2026-10-22T09:00:00+09:00")
SMOKE = {"E-01", "E-02", "E-04", "B-02", "R-01", "R-04", "X-10", "X-08b-USAGE", "BUDGET-INSUFFICIENT"}
EXTRA = [
    {"id": "X-08", "company": "A", "platform": "GITHUB", "expected_status": "DONE", "expected_reason_code": "NO_NEW_CANDIDATES", "overrides": {}, "reclaim_fixture": "R-02"},
    {"id": "X-12", "company": "A", "platform": "GITHUB", "expected_status": "WAITING_APPROVAL", "expected_reason_code": "ELIGIBLE", "overrides": {}, "input_text": "GitHub Copilot 좌석과 Jira 프로젝트 권한을 한 번에 신청합니다."},
    {"id": "X-07", "company": "A", "platform": "GITHUB", "expected_status": "WAITING_APPROVAL", "expected_reason_code": "ELIGIBLE", "overrides": {}, "input_text": "GitHub Copilot 좌석 신청. 전화번호 010-1234-5678. 주소: 서울특별시 강남구 테헤란로 123"},
    {"id": "X-10", "company": "B", "platform": "GITHUB", "expected_status": "DONE", "expected_reason_code": "SCAN_COMPLETED", "overrides": {}, "reclaim_fixture": "X-10-GITHUB"},
    {"id": "X-08b-USAGE", "company": "A", "platform": "GITHUB", "expected_status": "DONE", "expected_reason_code": "SCAN_COMPLETED", "overrides": {}, "reclaim_fixture": "MISSING_USAGE"},
    {"id": "X-03", "company": "B", "platform": "SNOWFLAKE", "expected_status": "WAITING_APPROVAL", "expected_reason_code": "ELIGIBLE", "overrides": {"budget": "500.00"}},
    {"id": "X-11", "company": "A", "platform": "GITHUB", "expected_status": "DONE", "expected_reason_code": "SCAN_COMPLETED", "overrides": {}, "reclaim_fixture": "X-11"},
    {"id": "X-08b-COST", "company": "A", "platform": "GITHUB", "expected_status": "DONE", "expected_reason_code": "SCAN_COMPLETED", "overrides": {}, "reclaim_fixture": "R-01"},
    {"id": "X-06", "company": "A", "platform": "GITHUB", "expected_status": "MANUAL_REVIEW", "expected_reason_code": "APPROVER_UNAVAILABLE", "overrides": {}},
]


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def prepare(run_id: str, suite="smoke", now: datetime | None = None):
    namespace = UUID(run_id)
    now = now or datetime.now(ZoneInfo("Asia/Seoul"))
    shift = now.date() - BASE.date()
    catalog = json.loads((ROOT / "data/phase2/catalog.json").read_text())
    seed = (ROOT / "data/phase2/seed.sql").read_text()
    v4 = json.loads((ROOT / 'data/phase2/scenarios-current.json').read_text())
    for item in catalog['catalog']:
        if item['platform'] == 'FIGMA': item['monthly_amount'] = v4['figma_monthly_amount']
        if item['platform'] in {'NOTION', 'TABLEAU_CLOUD'}: item['monthly_amount'] = '0.00'
    imports = [(ROOT / 'data/phase2/policies' / name).read_text() for name in ('apply.sql', 'apply-v4.sql', 'apply-costs.sql')]
    # Budget holds belong to an actual seat purchase, not a licensed page edit.
    seat_case = next(s for s in v4['scenarios'] if s['id'] == 'E-01')
    conditions = {
        'entitlement_code': 'COPILOT_SEAT', 'entitlement_kind': 'SEAT', 'access_scope': 'SEAT',
        'monthly_amount': '19.00', 'unit_monthly_amount': '19.00', 'currency': 'USD',
        'cost_basis': 'SEAT_MONTHLY', 'remaining_budget': '10.00', 'policy_revision': 4,
        'pricing_revision': 4, 'source_kind': 'PUBLIC_LIST_PRICE', 'tf_member': False,
        'account_exists': True, 'license_active': True, 'work_scope_assigned': True,
        'already_assigned': False, 'operation': 'PURCHASE_SEAT', 'license_coverage': 'NOT_COVERED',
    }
    boundaries = []
    for case_id, budget in [('BUDGET-INSUFFICIENT', '10.00'), ('BUDGET-EQUAL', '19.00'), ('BUDGET-ABOVE', '30.00'), ('BUDGET-FREE', '10.00')]:
        free = case_id == 'BUDGET-FREE'
        hold = case_id == 'BUDGET-INSUFFICIENT'
        required = {**conditions, 'remaining_budget': budget}
        overrides = {'budget': budget}
        if free:
            required.update(monthly_amount='0.00', cost_basis='NO_ADDITIONAL_COST', license_coverage='COVERED')
            overrides['license_coverage'] = 'COVERED'
        boundaries.append({**seat_case, 'id': case_id, 'overrides': overrides, 'preconditions': required,
                           'decision_rule': 'BUDGET_EXCEEDED' if hold else 'NO_ADDITIONAL_COST' if free else 'BUDGET_SUFFICIENT',
                           'expected_evidence': [['POL-06', '제2조']],
                           'expected_status': 'ON_HOLD' if hold else 'WAITING_APPROVAL',
                           'expected_reason_code': 'BUDGET_INSUFFICIENT' if hold else 'ELIGIBLE'})
    definitions = v4['scenarios'] + EXTRA + boundaries
    if suite == "smoke":
        definitions = [s for s in definitions if s["id"] in SMOKE]
    elif suite != "full":
        raise ValueError("Unknown suite")
    bundle = {"schema_version": 1, "suite": suite, "run_id": run_id, "prepared_at": now.isoformat(), "cases": []}
    statements = ["BEGIN;", "DO $$ BEGIN IF current_database()<>'phase2_eval' THEN RAISE EXCEPTION 'evaluation database required'; END IF; END $$;"]
    for index, definition in enumerate(definitions, 1):
        tag = f"c{index:02d}"
        case_namespace = uuid5(namespace, definition["id"])

        def translate(value):
            # Historical reports/snapshots contain nested timestamps as well as SQL literals.
            if value.startswith(("{", "[")):
                try:
                    structured = json.loads(value)
                except ValueError:
                    pass
                else:
                    return json.dumps(tree(structured), ensure_ascii=False, separators=(",", ":"))
            value = UUID_RE.sub(lambda m: str(uuid5(case_namespace, m.group())), value)
            # Identifiers, names and email uniqueness; original policy body/hash is unchanged.
            for prefix in ("p2_", "p2-", "P2_", "P2-"):
                value = value.replace(prefix, prefix + tag + prefix[-1])
            value = value.replace("phase2:", "phase2:" + tag + ":").replace("@example.test", "+" + tag + "@example.test")
            if value.startswith("Phase 2 "):
                value += " " + tag
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T.*)?", value):
                stamp = datetime.fromisoformat(value) + shift
                return stamp.isoformat() if "T" in value else stamp.date().isoformat()
            return value

        def tree(value):
            if isinstance(value, dict): return {k: tree(v) for k, v in value.items()}
            if isinstance(value, list): return [tree(v) for v in value]
            return translate(value) if isinstance(value, str) else value

        mapped = tree(catalog)
        scenario = tree(definition)
        company = mapped["companies"][scenario["company"]]
        company_ids = [c["company_id"] for c in mapped["companies"].values()]
        seeded = LITERAL.sub(lambda m: quote(translate(m.group(1).replace("''", "'"))), seed)
        statements.append(seeded.replace("BEGIN;", "").replace("COMMIT;", ""))
        for imported in imports:
            statements.append(LITERAL.sub(lambda m: quote(translate(m.group(1).replace("''", "'"))), imported).replace('BEGIN;', '').replace('COMMIT;', ''))
        company_filter = ",".join(quote(x) for x in company_ids)
        # New users use the isolated stack's demo password hash; never print or export it.
        statements.append(f"UPDATE users SET password_hash=(SELECT password_hash FROM users WHERE login_id='kim_dev') WHERE company_id IN ({company_filter});")
        # Rebase only this run's copied facts so tests do not expire after the original fixture date.
        statements.append(f"UPDATE assignment_usage SET observed_at=now() WHERE company_id IN ({company_filter});")
        co, dept, requester = company["company_id"], company["department_id"], company["users"]["requester"]
        item = next(x for x in mapped["catalog"] if x["company"] == scenario["company"] and x["platform"] == scenario["platform"])
        overrides = scenario["overrides"]
        budget = overrides.get("budget", "500.00" if scenario["company"] == "A" else "100.00")
        statements.append(f"UPDATE department_budgets SET remaining_monthly_amount={quote(budget)} WHERE department_id={quote(dept)};")
        if overrides.get("job_family"):
            statements.append(f"UPDATE users SET job_family={quote(overrides['job_family'])} WHERE id={quote(requester)};")
        if overrides.get("membership") is False:
            # The generic Slack seed has GENERAL scope; the negative TF case explicitly binds its scope.
            statements.append(f"UPDATE resources SET access_scope='TF',tf_id={quote(company['active_tf_id'])} WHERE id={quote(item['resource_id'])};")
            statements.append(f"UPDATE tf_members SET active=false WHERE user_id={quote(requester)} AND tf_id={quote(company['active_tf_id'])};")
        if overrides.get("already_assigned"):
            statements.append("INSERT INTO access_assignments(id,company_id,user_id,resource_id,entitlement_id,entitlement_revision,granted_at) VALUES(" + ",".join(quote(x) for x in [str(uuid5(case_namespace, "existing")), co, requester, item["resource_id"], item["entitlement_id"]]) + ",1,now());")
        if overrides.get('license_coverage'):
            statements.append(f"UPDATE saas_license_facts SET coverage={quote(overrides['license_coverage'])},purchase_required=false WHERE company_id={quote(co)} AND user_id={quote(requester)} AND platform={quote(scenario['platform'])};")
        if scenario["id"] == "X-08b-COST":
            # Two simultaneous price families are ambiguous: UNKNOWN, never 0.00.
            columns = "revision,company_id,entitlement_id,entitlement_revision,monthly_amount,currency,cost_basis,source_kind,source_reference,effective_from,effective_until,policy_id,policy_revision"
            statements.append(f"INSERT INTO pricing_revisions(pricing_id,{columns}) SELECT {quote(uuid5(case_namespace, 'ambiguous-price'))},{columns} FROM pricing_revisions WHERE pricing_id={quote(item['pricing_id'])} AND revision=4;")
        if scenario["id"] == "X-06":
            # The only mapped operator has left: the route cannot name an approver, so no one is guessed.
            statements.append(f"UPDATE users SET employment_status='LEFT' WHERE id={quote(company['users']['operator'])};")
        if overrides.get("policy_missing"):
            content = "정책 원문을 확인할 수 없습니다."
            digest = hashlib.sha256(content.encode()).hexdigest()
            # A new, unusable source revision exercises missing evidence without deleting immutable history.
            statements.append(f"INSERT INTO policy_revisions(policy_id,revision,company_id,doc_id,article,source_path,source_hash,content,is_mock) SELECT policy_id,5,company_id,doc_id,article,source_path,{quote(digest)},{quote(content)},true FROM policy_revisions WHERE policy_id={quote(company['policy_id'])} AND revision=4;")
        body = {"schema_version": 2, "platform": scenario["platform"], "contents": scenario.get("input_text") or f"{scenario['platform']} 업무 권한을 신청합니다.", "resource_id": item["resource_id"]}
        if scenario["id"] == "B-02":
            body.update(contents=scenario["input_text"], resource_id=overrides["resource_id"])
            body.pop("entitlement_id", None)  # Agent must actually propose Read, not receive an explicit Read selection.
        if scenario["id"] == "B-05":
            body = {"schema_version": 2, "platform": scenario["platform"], "contents": overrides["request"]}
        reclaim_key = scenario.get("reclaim_fixture", scenario["id"] if scenario["id"].startswith("R-") else None)
        fixture = mapped["reclaim_fixtures"].get(reclaim_key)
        scenario.update(
            companies=mapped["companies"], company_data=company, input=body,
            login_prefix=f"p2_{tag}_{scenario['company'].lower()}_",
            other_login=f"p2_{tag}_{'b' if scenario['company']=='A' else 'a'}_it_head",
            initial_budget=budget, monthly_amount="0.00" if scenario["id"] == "B-02" else '0.00' if overrides.get('license_coverage') == 'COVERED' else item["monthly_amount"],
            fixture_entitlement_id=overrides.get('entitlement_id', item['entitlement_id']),
            scope_id=fixture["scope_id"] if fixture else None,
            expected_assignments=[f["assignment_id"] for key, f in mapped["reclaim_fixtures"].items() if fixture and f["scope_id"] == fixture["scope_id"]],
        )
        bundle["cases"].append(scenario)
    statements.append("COMMIT;")
    return bundle, "\n".join(statements) + "\n"
