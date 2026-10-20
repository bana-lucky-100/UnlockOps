"""실제 직원·권한을 DB에서 조회하고, 사람 승인과 원문 근거를 재확인한 뒤 권한을 변경한다."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID
import json
import re
import os

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from unlockops.models import Plan
from unlockops.rules import ROLES, approver_is_eligible, evaluate, role_satisfies
from unlockops.settings import settings


def public(value):
    """UUID와 Decimal을 JSON으로 전달할 수 있는 문자열로 바꾼다."""
    if isinstance(value, dict): return {k: public(v) for k, v in value.items()}
    if isinstance(value, list): return [public(v) for v in value]
    if isinstance(value, UUID): return str(value)
    if isinstance(value, Decimal): return str(value)
    return value


class Repository:
    def connect(self):
        if settings.database_url:
            return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=10)
        return psycopg.connect(host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            dbname=os.getenv("DB_NAME", os.getenv("POSTGRES_DB", "unlockops")),
            user=os.getenv("DB_USER", os.getenv("POSTGRES_USER", "unlockops")),
            password=os.getenv("DB_PASSWORD", os.getenv("POSTGRES_PASSWORD", "unlockops-local-only")),
            row_factory=dict_row, connect_timeout=10)

    def profile(self, employee_id, conn=None):
        if conn is None:
            with self.connect() as c: return self.profile(employee_id, c)
        row = conn.execute("""SELECT u.id,u.employee_no,u.name,u.department_id,u.job_grade,u.job_family,
            d.name department_name,d.head_id FROM users u JOIN departments d ON d.id=u.department_id
            WHERE u.id=%s""", (employee_id,)).fetchone()
        if not row: raise ValueError("Unknown employee")
        return public(row)

    def resource(self, resource_id, conn=None):
        if conn is None:
            with self.connect() as c: return self.resource(resource_id, c)
        row = conn.execute("SELECT * FROM resources WHERE id=%s", (resource_id,)).fetchone()
        if not row: raise ValueError("Unknown resource")
        return public(row)

    def resolve(self, platform, hint):
        with self.connect() as conn:
            rows = public(conn.execute("SELECT * FROM resources WHERE platform=%s ORDER BY external_id", (platform,)).fetchall())
        hint = hint.strip().casefold()
        if not hint: return {"matches": [], "ambiguous": True}
        exact, contained = [], []
        for row in rows:
            names = [row["external_id"], row["name"], *row["aliases"]]
            def mentioned(name):
                name = name.casefold()
                if re.fullmatch(r"[a-z0-9_-]+", name):
                    return bool(re.search(r"(?<![a-z0-9_-])" + re.escape(name) + r"(?![a-z0-9_-])", hint))
                return name in hint
            if any(hint == name.casefold() for name in names): exact.append(row)
            elif any(len(name) >= 3 and mentioned(name) for name in names): contained.append(row)
        matches = exact or contained
        return {"matches": matches, "ambiguous": len(matches) != 1}

    def membership(self, employee_id, resource_id, conn=None):
        if conn is None:
            with self.connect() as c: return self.membership(employee_id, resource_id, c)
        row = conn.execute("""SELECT r.tf_id,t.leader_id,
            COALESCE(m.active,FALSE) AND t.starts_on<=CURRENT_DATE
              AND (t.ends_on IS NULL OR t.ends_on>=CURRENT_DATE) AS member
            FROM resources r LEFT JOIN tfs t ON t.id=r.tf_id
            LEFT JOIN tf_members m ON m.tf_id=t.id AND m.user_id=%s WHERE r.id=%s""",
            (employee_id, resource_id)).fetchone()
        if not row: raise ValueError("Unknown resource")
        return public(row)

    def current(self, employee_id, resource_id, conn=None):
        if conn is None:
            with self.connect() as c: return self.current(employee_id, resource_id, c)
        resource = self.resource(resource_id, conn)
        if resource["platform"] == "GITHUB" and resource["access_scope"] != "SEAT":
            rows = conn.execute("""SELECT t.id,t.saas_role FROM github_team_members m
                JOIN github_teams t ON t.id=m.team_id WHERE m.user_id=%s AND t.resource_id=%s""",
                (employee_id, resource_id)).fetchall()
            role = max((r["saas_role"] for r in rows), key=lambda r: ROLES.get(r, 0), default=None)
            return {"role": role, "teams": [r["id"] for r in rows], "source": "github-team-membership"}
        row = conn.execute("SELECT saas_role FROM permissions WHERE user_id=%s AND resource_id=%s", (employee_id, resource_id)).fetchone()
        if resource["platform"] == "JIRA":
            role = row["saas_role"] if row else None
            scheme = conn.execute("SELECT can_browse FROM jira_role_permissions WHERE resource_id=%s AND saas_role=%s",
                                   (resource_id,role)).fetchone() if role else None
            return {"role": role, "can_browse": bool(scheme and scheme["can_browse"]), "source": "jira-role-and-scheme"}
        return {"role": row["saas_role"] if row else None, "source": "mock-saas-permissions"}

    def budget(self, employee_id, conn=None, lock=False):
        if conn is None:
            with self.connect() as c: return self.budget(employee_id, c, lock)
        row = conn.execute("""SELECT b.* FROM department_budgets b JOIN users u ON u.department_id=b.department_id
            WHERE u.id=%s""" + (" FOR UPDATE OF b" if lock else ""), (employee_id,)).fetchone()
        return public(row) if row else None

    def grant(self, problem_id, idempotency_key):
        """승인된 계획을 다시 검사하고 권한·예산·실행 영수증을 한 트랜잭션으로 저장한다."""
        with self.connect() as conn:
            # 1. 같은 요청을 동시에 처리하지 못하도록 잠그고 승인 시 발급한 실행 키를 비교한다.
            problem = conn.execute("SELECT * FROM problems WHERE id=%s FOR UPDATE", (problem_id,)).fetchone()
            if not problem: raise ValueError("Unknown problem")
            if problem["idempotency_key"] != idempotency_key:
                return {"ok": False, "error_code": "INVALID_EXECUTION_KEY", "retryable": False}
            receipt = conn.execute("SELECT result FROM grant_receipts WHERE idempotency_key=%s AND problem_id=%s", (idempotency_key, problem_id)).fetchone()
            # 이미 처리한 실행 키면 이전 영수증을 반환한다. 권한·예산을 다시 변경하지 않는다.
            if receipt: return receipt["result"]
            if (problem["status"] != "EXECUTING" or problem["decision_source"] != "HUMAN"
                    or not problem["decided_at"] or not problem["approved_plan_hash"]):
                return {"ok": False, "error_code": "APPROVAL_REQUIRED", "retryable": False}
            # 2. 실행할 대상·역할은 호출 인자가 아니라 DB에 저장된 사람 승인 계획에서만 가져온다.
            plan = Plan.model_validate(problem["plan"])
            if plan.digest() != problem["approved_plan_hash"] or plan.digest() != problem["plan_hash"]:
                return {"ok": False, "error_code": "PLAN_CHANGED", "retryable": False}
            if str(problem["requester_id"]) != plan.requester_id or str(problem_id) != plan.problem_id:
                return {"ok": False, "error_code": "PLAN_IDENTITY_MISMATCH", "retryable": False}
            if (problem["platform"] != plan.platform or str(problem["resource_id"]) != plan.resource_id
                    or problem["requested_role"] != plan.requested_role):
                return {"ok": False, "error_code": "PLAN_CHANGED", "retryable": False}
            # 서로 다른 요청이어도 같은 직원·자원에 동시에 권한을 부여하지 못하도록 잠근다.
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                         (plan.requester_id + ":" + plan.resource_id,))
            profile, resource = self.profile(plan.requester_id, conn), self.resource(plan.resource_id, conn)
            membership = self.membership(plan.requester_id, plan.resource_id, conn)
            # 3. 분석 시점의 정보 대신 현재 소속과 승인자 정보를 다시 읽는다.
            # 지정 승인자가 바뀌었거나 역할·직급이 부적합해졌으면 기존 승인으로 실행할 수 없다.
            actual_approver = conn.execute("SELECT id,role,job_grade FROM users WHERE id=%s", (problem["decided_by"],)).fetchone()
            if not approver_is_eligible(profile, resource, membership, public(actual_approver)):
                return {"ok": False, "error_code": "APPROVER_CHANGED", "retryable": False}
            if resource["platform"] != plan.platform or resource["external_id"] != plan.resource_key:
                return {"ok": False, "error_code": "RESOURCE_CHANGED", "retryable": False}
            if plan.platform == "JIRA":
                scheme = conn.execute("SELECT can_browse FROM jira_role_permissions WHERE resource_id=%s AND saas_role=%s",
                                      (plan.resource_id,plan.requested_role)).fetchone()
                if not scheme or not scheme["can_browse"]:
                    return {"ok": False, "error_code": "PRECONDITION_CHANGED", "retryable": False,
                            "reason": "JIRA_SCHEME_MISMATCH"}
            current = self.current(plan.requester_id, plan.resource_id, conn)
            budget = self.budget(plan.requester_id, conn, lock=resource["access_scope"] == "SEAT")
            # 4. 승인 때 저장한 RAG 근거가 현재 원문과 맞는지, 제안 역할이 실제 자격·상한에 맞는지 확인한다.
            # LLM이 제안했거나 사람이 승인했어도 현재 조건이 달라졌으면 여기서 차단한다.
            verdict = evaluate(profile, resource, membership, current, budget, plan.requested_role,
                               evidence=problem.get("evidence") or [])
            if verdict.status == "DONE":
                result = {"ok": True, "changed": False, "role": plan.requested_role}
            elif verdict.status != "WAITING_APPROVAL":
                return {"ok": False, "error_code": "PRECONDITION_CHANGED", "retryable": False,
                        "reason": verdict.code}
            elif problem["simulate_jira_failure"] and plan.platform == "JIRA":
                return {"ok": False, "error_code": "MOCK_JIRA_UNAVAILABLE", "retryable": True}
            else:
                # 5. 모든 검사가 끝난 뒤에만 모의 SaaS 권한을 변경한다.
                if resource["access_scope"] == "SEAT":
                    # 예산 행 잠금·권한 변경·영수증을 함께 커밋해 중복 차감을 방지한다.
                    conn.execute("""UPDATE department_budgets SET remaining_monthly_amount=
                        remaining_monthly_amount-unit_monthly_price,updated_at=NOW() WHERE department_id=%s""",
                        (profile["department_id"],))
                if plan.platform == "GITHUB" and resource["access_scope"] != "SEAT":
                    team = conn.execute("SELECT id FROM github_teams WHERE resource_id=%s AND saas_role=%s", (plan.resource_id, plan.requested_role)).fetchone()
                    if not team: raise ValueError("No dedicated GitHub team for approved resource")
                    conn.execute("INSERT INTO github_team_members(team_id,user_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (team["id"],plan.requester_id))
                conn.execute("""INSERT INTO permissions(user_id,resource_id,saas_role) VALUES (%s,%s,%s)
                    ON CONFLICT(user_id,resource_id) DO UPDATE SET saas_role=excluded.saas_role,granted_at=NOW()""",
                    (plan.requester_id,plan.resource_id,plan.requested_role))
                result = {"ok": True, "changed": True, "role": plan.requested_role}
            # 영수증까지 같은 트랜잭션에 기록하므로 재전달된 작업도 이전 결과를 찾을 수 있다.
            conn.execute("INSERT INTO grant_receipts(idempotency_key,problem_id,result) VALUES (%s,%s,%s)",
                         (idempotency_key,problem_id,Jsonb(result)))
            return result

    def verify(self, employee_id, resource_id, requested_role):
        """부여 응답과 별개로 현재 권한을 다시 읽어 요청한 역할이 실제로 반영됐는지 확인한다."""
        with self.connect() as conn:
            resource = self.resource(resource_id, conn)
            current = self.current(employee_id, resource_id, conn)
        # 서로 다른 플랫폼의 역할 순위를 비교하지 않고 해당 자원 역할군 안에서만 확인한다.
        verified = role_satisfies(resource, current.get("role"), requested_role)
        if "can_browse" in current: verified = verified and current["can_browse"]
        return {"ok": True, "verified": verified,
                "current": current}
