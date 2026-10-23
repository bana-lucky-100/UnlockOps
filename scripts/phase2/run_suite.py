"""Exercise real HTTP → queue → worker → MCP → DB flows inside the isolated stack."""
from __future__ import annotations

from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

import httpx


class CheckFailed(Exception):
    pass


def check(condition, message):
    # Explicit checks remain active under python -O.
    if not condition:
        raise CheckFailed(message)


class Session:
    def __init__(self, login):
        self.client = httpx.Client(base_url="http://frontend", timeout=15)
        self.refresh_csrf()
        self.call("POST", "/api/auth/login", json={"loginId": login, "password": os.environ["EVAL_PASSWORD"]})
        self.refresh_csrf()

    def refresh_csrf(self):
        token = self.call("GET", "/api/auth/csrf")
        self.csrf = {token["headerName"]: token["token"]}

    def call(self, method, path, expected=200, **kwargs):
        headers = {**getattr(self, "csrf", {}), **kwargs.pop("headers", {})}
        response = self.client.request(method, path, headers=headers, **kwargs)
        # Do not include response bodies, session tokens or passwords in reports.
        check(response.status_code == expected, f"{method} {path}: expected HTTP {expected}, got {response.status_code}")
        return response.json() if response.content else None


class Suite:
    def __init__(self):
        self.sessions = {}
        self.internal = httpx.Client(base_url="http://backend:8080", timeout=15,
                                    headers={"Authorization": "Bearer " + os.environ["INTERNAL_API_TOKEN"]})

    def user(self, login):
        if login not in self.sessions:
            self.sessions[login] = Session(login)
        return self.sessions[login]

    def close(self):
        self.internal.close()
        for session in self.sessions.values():
            session.client.close()

    def settle(self, session, path):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            view = session.call("GET", path)
            if view["status"] not in {"RECEIVED", "DIAGNOSING", "EXECUTING"}:
                return view
            time.sleep(0.5)
        raise TimeoutError("Workflow did not settle within 90 seconds")

    def access(self, case, result):
        requester = self.user(case["login_prefix"] + "requester")
        key = str(uuid4())
        created = requester.call("POST", "/api/v2/problems", expected=202, json=case["input"], headers={"Idempotency-Key": key})
        pid = created["problem_id"]
        result["problem_id"] = pid
        path = "/api/v2/problems/" + pid
        replay = requester.call("POST", "/api/v2/problems", expected=202, json=case["input"], headers={"Idempotency-Key": key})
        check(replay["problem_id"] == pid, "submission replay created a different problem")
        view = self.settle(requester, path)
        reject_step = case["overrides"].get("reject_step")
        expected = "WAITING_APPROVAL" if reject_step else case["expected_status"]
        reason = "ELIGIBLE" if reject_step else case["expected_reason_code"]
        check((view["status"], view["reason_code"]) == (expected, reason),
              f"analysis expected {expected}/{reason}, got {view['status']}/{view['reason_code']}")
        result["checks"].extend(["submission_idempotency", "analysis_status_reason"])
        if view["status"] != "WAITING_APPROVAL":
            if view["status"] == "DONE":
                check(view["result_type"] == "GUIDANCE" and view["verification_ok"] is None, "guidance claimed execution")
            result["final_status"] = view["status"]
            return

        users = case["company_data"]["users"]
        roles = (["head"] if case["company"] == "A" else ["team_lead", "head"])
        roles += ["figma_operator" if case["company"] == "B" and case["platform"] == "FIGMA" else "operator"]
        if case["company"] == "B" and Decimal(case["monthly_amount"]) >= 100:
            roles += ["it_head"]
        check([s["approver_id"] for s in view["approval_steps"]] == [users[r] for r in roles], "approval route differs")
        report = requester.call("GET", path + "/report")
        check(bool(report["policy_evidence"]) and bool(report["requester_name"]), "report lacks policy/name")
        check(Decimal(report["plan"]["monthly_amount"]) == Decimal(case["monthly_amount"]), "plan cost differs")
        if case["id"] == "B-02":
            check(report["plan"]["entitlement_id"] == case["overrides"]["entitlement_id"], "Admin was not reduced to Read")
        result["checks"].extend(["approval_route", "policy_evidence", "plan_cost"])

        def decide(role, action, expected=200, plan_hash=None, plan_version=None):
            return self.user(case["login_prefix"] + role).call("POST", path + "/decisions", expected=expected, json={
                "action": action, "expected_plan_hash": plan_hash or view["plan_hash"],
                "expected_plan_version": view["plan_version"] if plan_version is None else plan_version,
                "reason": "평가 시나리오 승인 보류/반려" if action != "APPROVE" else None})

        if case["id"] == "E-01":
            requester.call("POST", "/api/v2/problems", expected=409,
                           json={**case["input"], "contents": "다른 요청 본문"}, headers={"Idempotency-Key": key})
            decide("requester", "APPROVE", 403)
            decide(roles[-1], "APPROVE", 403)
            decide(roles[0], "APPROVE", 409, "0" * 64)
            self.user(case["other_login"]).call("GET", path, expected=403)
            original_version = view["plan_version"]
            original_hash = view["plan_hash"]
            held = decide(roles[0], "HOLD")
            check(held["status"] == "ON_HOLD" and held["reason_code"] == "HELD_BY_APPROVER", "hold not persisted")
            requester.call("POST", path + "/resume", expected=202)
            view = self.settle(requester, path)
            check(view["status"] == "WAITING_APPROVAL" and view["plan_version"] > original_version, "resume did not create a new plan")
            check(all(s["status"] != "APPROVED" for s in view["approval_steps"]), "resume retained old approvals")
            check(view["plan_hash"] == original_hash, "unchanged plan content should retain its hash")
            for action in ("APPROVE", "REJECT", "HOLD"):
                decide(roles[0], action, 409, original_hash, original_version)
            check(requester.call("GET", path) == view, "stale decisions changed the current round")
            result["checks"].append("stale_plan_version_409")
            result["checks"].extend(["request_key_payload_conflict", "self_and_future_approval_denied", "stale_hash_409", "tenant_isolation", "hold_resume_new_plan"])

        for number, role in enumerate(roles, 1):
            check(view["status"] == "WAITING_APPROVAL" and view["current_step"] == number, "approval order differs")
            view = decide(role, "REJECT" if number == reject_step else "APPROVE")
            if number == reject_step:
                check((view["status"], view["reason_code"]) == (case["expected_status"], case["expected_reason_code"]), "human rejection differs")
                check(bool(view["approval_steps"][number - 1]["reason"]), "rejection reason missing")
                result.update(final_status=view["status"])
                result["checks"].append("human_rejection")
                return
        view = self.settle(requester, path)
        check(view["status"] == "DONE" and view["result_type"] == "ACCESS_VERIFIED" and view["verification_ok"] is True, "grant was not independently verified")
        context = self.internal.get("/internal/v2/problems/" + pid + "/context")
        check(context.status_code == 200, "internal verification context unavailable")
        p = context.json()["problem"]
        execute_body = {"job_event_id": p["active_job_event_id"], "plan_hash": p["approved_plan_hash"], "idempotency_key": p["idempotency_key"]}
        receipts = [self.internal.post("/internal/v2/problems/" + pid + "/execute", json=execute_body) for _ in range(2)]
        check(all(r.status_code == 200 for r in receipts), "execution replay failed")
        check(receipts[0].json() == receipts[1].json(), "execution replay changed receipt")
        check(Decimal(receipts[0].json()["charged_amount"]) == Decimal(case["monthly_amount"]), "charged amount differs")
        result.update(final_status="DONE", assignment_id=receipts[0].json()["assignment_id"])
        result["checks"].extend(["ordered_human_approval", "independent_grant_verification", "execution_receipt_replay"])
        if case["id"] == "E-01":
            anonymous = httpx.get("http://frontend" + path, timeout=15)
            check(anonymous.status_code == 401, "missing session did not return 401")
            result["checks"].append("unauthenticated_401")

    def reclaim(self, case, result):
        manager = self.user(case["login_prefix"] + "it_head")
        body, key = {"scope_id": case["scope_id"]}, str(uuid4())
        created = manager.call("POST", "/api/reclaim/runs", expected=202, json=body, headers={"Idempotency-Key": key})
        rid = created["run_id"]
        result["run_id"] = rid
        path = "/api/reclaim/runs/" + rid
        replay = manager.call("POST", "/api/reclaim/runs", expected=202, json=body, headers={"Idempotency-Key": key})
        check(replay["run_id"] == rid, "scan replay created another run")
        view = self.settle(manager, path)
        check((view["status"], view["reason_code"]) == (case["expected_status"], case["expected_reason_code"]),
              f"scan expected {case['expected_status']}/{case['expected_reason_code']}, got {view['status']}/{view['reason_code']}")
        items = manager.call("GET", path + "/items")
        check(view["scan_complete"] is True and {i["assignment_id"] for i in items} == set(case["expected_assignments"]) and len(items) == len(case["expected_assignments"]), "scan missing/duplicate assignments")
        check(all(i["action_taken"] == "NONE" for i in items), "scan claimed revocation")
        self.user(case["other_login"]).call("GET", path, expected=403)
        expected_fields = {"R-02": ("exclusion_reason_code", "ACTIVE_OTHER_TF"), "R-03": ("exclusion_reason_code", "RETENTION_APPROVED"), "R-04": ("skip_reason_code", "ALREADY_NOTIFIED"), "X-11": ("candidate_reason_code", "EMPLOYEE_LEFT")}
        if case["id"] in expected_fields:
            field, expected = expected_fields[case["id"]]
            check(all(i[field] == expected for i in items), "reclaim decision reason differs")
        if case["id"] in {"X-UNKNOWN", "X-COST"}:
            check(view["needs_review_count"] == len(items) and all(i["review_required"] and i["candidate_status"] is None for i in items), "missing facts were treated as zero/confirmed")
            if case["id"] == "X-COST":
                check(all(i["cost_impact"]["status"] == "UNKNOWN" and i["cost_impact"]["monthly_amount"] is None for i in items), "unknown cost was treated as zero")
        result["checks"].extend(["scan_idempotency", "complete_snapshot", "scan_status_reason", "no_revocation_claim", "tenant_isolation"])
        result["final_status"] = view["status"]
        if case["id"] not in {"R-01", "R-04", "X-10", "X-11"}:
            return
        recipient_roles = ["operator", "figma_operator"] if case["id"] == "X-10" else ["operator"]
        targets = {i["target_id"] for i in items}
        before = {}
        for role in recipient_roles:
            session = self.user(case["login_prefix"] + role)
            notifications = session.call("GET", "/api/reclaim/notifications")
            own = [n for n in notifications if n["target_id"] in targets]
            check(len(own) == 1, "recipient should receive exactly one notification for this scope")
            before[role] = {n["id"] for n in notifications}
            notification = own[0]
            read_path = "/api/reclaim/notifications/" + notification["id"] + "/read"
            read = session.call("PATCH", read_path)
            check(bool(read["read_at"]) and session.call("PATCH", read_path) == read, "read timestamp changed on replay")
            target = session.call("GET", "/api/reclaim/targets/" + notification["target_id"])
            check(target["read_at"] is not None, "personal read state missing")
            if case["id"] == "X-10":
                check(target["platform"] == ("FIGMA" if role == "figma_operator" else "GITHUB"), "platform notification leaked")
                session.call("GET", path, expected=403)
                other_target = next(t for t in targets if t != target["target_id"])
                session.call("GET", "/api/reclaim/targets/" + other_target, expected=403)
        again = manager.call("POST", "/api/reclaim/runs", expected=202, json=body, headers={"Idempotency-Key": str(uuid4())})
        later_path = "/api/reclaim/runs/" + again["run_id"]
        later = self.settle(manager, later_path)
        check(later["status"] == "DONE" and later["reason_code"] == "NO_NEW_CANDIDATES" and later["new_candidate_count"] == 0, "repeat scan generated new candidates")
        later_items = manager.call("GET", later_path + "/items")
        check({(i["target_id"], i["episode_id"]) for i in items} == {(i["target_id"], i["episode_id"]) for i in later_items}, "repeat scan changed episode")
        for role in recipient_roles:
            notifications = self.user(case["login_prefix"] + role).call("GET", "/api/reclaim/notifications")
            check({n["id"] for n in notifications} == before[role], "repeat scan duplicated notifications")
        result["checks"].extend(["recipient_delivery", "read_idempotency", "episode_stability", "notification_deduplication"])


def run(bundle):
    runner = Suite()
    results = []
    try:
        response = httpx.get("http://frontend/", timeout=15)
        check(response.status_code == 200 and '<div id="app"' in response.text, "frontend artifact is not served")
        for case in bundle["cases"]:
            started = time.monotonic()
            result = {"id": case["id"], "status": "NOT_RUN", "checks": []}
            try:
                (runner.reclaim if case["scope_id"] else runner.access)(case, result)
                result["status"] = "PASS"
            except CheckFailed as error:
                result.update(status="FAIL", detail=str(error))
            except (TimeoutError, httpx.TimeoutException):
                result.update(status="TIMEOUT", detail="Workflow/HTTP deadline exceeded")
            except Exception as error:
                result.update(status="ERROR", detail=type(error).__name__)
            result["duration_seconds"] = round(time.monotonic() - started, 2)
            results.append(result)
            print(f"{result['id']}: {result['status']}", file=sys.stderr, flush=True)
    finally:
        runner.close()
    return {"status": "PASS" if all(r["status"] == "PASS" for r in results) else "FAIL", "cases": results,
            "frontend_artifact": "PASS", "browser_interaction": "NOT_RUN"}


if __name__ == "__main__":
    report = run(json.loads(Path(sys.argv[1]).read_text()))
    print(json.dumps(report, ensure_ascii=False))
    sys.exit(0 if report["status"] == "PASS" else 1)
