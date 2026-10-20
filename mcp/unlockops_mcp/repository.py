"""DB에서 정확한 사실을 조회하고, 승인된 모의 SaaS 변경을 트랜잭션으로 실행한다."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID
import re
import os

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from unlockops.models import Plan
from unlockops.rules import evaluate, ROLES
from unlockops.settings import settings


def public(value):
    """DB의 UUID·금액을 MCP 응답에서 사용할 문자열로 바꾼다."""
    if isinstance(value, dict):
        return {k: public(v) for k, v in value.items()}
    if isinstance(value, list):
        return [public(v) for v in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


class Repository:
    """MCP 도구가 사용하는 저장소. Agent 노드는 DB 연결을 직접 만들지 않는다."""

    def connect(self):
        if settings.database_url:
            return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=10)
        return psycopg.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            dbname=os.getenv("DB_NAME", os.getenv("POSTGRES_DB", "unlockops")),
            user=os.getenv("DB_USER", os.getenv("POSTGRES_USER", "unlockops")),
            password=os.getenv(
                "DB_PASSWORD", os.getenv("POSTGRES_PASSWORD", "unlockops-local-only")
            ),
            row_factory=dict_row,
            connect_timeout=10,
        )

    def profile(self, employee_id, conn=None):
        """문장 속 주장 대신 직원 ID로 소속·직급·직무를 조회한다."""
        if conn is None:
            with self.connect() as c:
                return self.profile(employee_id, c)
        row = conn.execute(
            """SELECT u.id,u.employee_no,u.name,u.department_id,u.job_grade,u.job_family,
            d.name department_name,d.head_id FROM users u JOIN departments d ON d.id=u.department_id
            WHERE u.id=%s""",
            (employee_id,),
        ).fetchone()
        if not row:
            raise ValueError("Unknown employee")
        return public(row)

    def resource(self, resource_id, conn=None):
        if conn is None:
            with self.connect() as c:
                return self.resource(resource_id, c)
        row = conn.execute("SELECT * FROM resources WHERE id=%s", (resource_id,)).fetchone()
        if not row:
            raise ValueError("Unknown resource")
        return public(row)

    def resolve(self, platform, hint):
        """같은 플랫폼 안에서 명시적으로 언급한 자원 후보만 반환한다."""
        with self.connect() as conn:
            rows = public(
                conn.execute(
                    "SELECT * FROM resources WHERE platform=%s ORDER BY external_id", (platform,)
                ).fetchall()
            )
        hint = hint.strip().casefold()
        if not hint:
            return {"matches": [], "ambiguous": True}
        exact, contained = [], []
        for row in rows:
            names = [row["external_id"], row["name"], *row["aliases"]]

            def mentioned(name):
                name = name.casefold()
                if re.fullmatch(r"[a-z0-9_-]+", name):
                    return bool(
                        re.search(r"(?<![a-z0-9_-])" + re.escape(name) + r"(?![a-z0-9_-])", hint)
                    )
                return name in hint

            if any(hint == name.casefold() for name in names):
                exact.append(row)
            elif any(len(name) >= 3 and mentioned(name) for name in names):
                contained.append(row)
        matches = exact or contained
        return {"matches": matches, "ambiguous": len(matches) != 1}

    def membership(self, employee_id, resource_id, conn=None):
        if conn is None:
            with self.connect() as c:
                return self.membership(employee_id, resource_id, c)
        row = conn.execute(
            """SELECT r.tf_id,t.leader_id,
            COALESCE(m.active,FALSE) AND t.starts_on<=CURRENT_DATE
              AND (t.ends_on IS NULL OR t.ends_on>=CURRENT_DATE) AS member
            FROM resources r LEFT JOIN tfs t ON t.id=r.tf_id
            LEFT JOIN tf_members m ON m.tf_id=t.id AND m.user_id=%s WHERE r.id=%s""",
            (employee_id, resource_id),
        ).fetchone()
        if not row:
            raise ValueError("Unknown resource")
        return public(row)

    def current(self, employee_id, resource_id, conn=None):
        """GitHub는 팀 멤버십, Jira는 역할과 조회 스킴에서 실제 권한을 확인한다."""
        if conn is None:
            with self.connect() as c:
                return self.current(employee_id, resource_id, c)
        resource = self.resource(resource_id, conn)
        if resource["platform"] == "GITHUB" and resource["access_scope"] != "SEAT":
            rows = conn.execute(
                """SELECT t.id,t.saas_role FROM github_team_members m
                JOIN github_teams t ON t.id=m.team_id WHERE m.user_id=%s AND t.resource_id=%s""",
                (employee_id, resource_id),
            ).fetchall()
            role = max((r["saas_role"] for r in rows), key=lambda r: ROLES.get(r, 0), default=None)
            return {
                "role": role,
                "teams": [r["id"] for r in rows],
                "source": "github-team-membership",
            }
        row = conn.execute(
            "SELECT saas_role FROM permissions WHERE user_id=%s AND resource_id=%s",
            (employee_id, resource_id),
        ).fetchone()
        if resource["platform"] == "JIRA":
            role = row["saas_role"] if row else None
            scheme = (
                conn.execute(
                    "SELECT can_browse FROM jira_role_permissions WHERE resource_id=%s AND saas_role=%s",
                    (resource_id, role),
                ).fetchone()
                if role
                else None
            )
            return {
                "role": role,
                "can_browse": bool(scheme and scheme["can_browse"]),
                "source": "jira-role-and-scheme",
            }
        return {"role": row["saas_role"] if row else None, "source": "mock-saas-permissions"}

    def budget(self, employee_id, conn=None, lock=False):
        if conn is None:
            with self.connect() as c:
                return self.budget(employee_id, c, lock)
        row = conn.execute(
            """SELECT b.* FROM department_budgets b JOIN users u ON u.department_id=b.department_id
            WHERE u.id=%s"""
            + (" FOR UPDATE OF b" if lock else ""),
            (employee_id,),
        ).fetchone()
        return public(row) if row else None

    def grant(self, problem_id, idempotency_key):
        """DB의 승인 계획을 재검증하고 권한·예산·실행 영수증을 함께 커밋한다."""
        with self.connect() as conn:
            problem = conn.execute(
                "SELECT * FROM problems WHERE id=%s FOR UPDATE", (problem_id,)
            ).fetchone()
            if not problem:
                raise ValueError("Unknown problem")
            if problem["idempotency_key"] != idempotency_key:
                return {"ok": False, "error_code": "INVALID_EXECUTION_KEY", "retryable": False}
            receipt = conn.execute(
                "SELECT result FROM grant_receipts WHERE idempotency_key=%s AND problem_id=%s",
                (idempotency_key, problem_id),
            ).fetchone()
            # 같은 실행 키의 작업이 다시 오면 이전 결과를 반환해 중복 변경을 막는다.
            if receipt:
                return receipt["result"]
            if (
                problem["status"] != "EXECUTING"
                or problem["decision_source"] != "HUMAN"
                or not problem["decided_at"]
                or not problem["approved_plan_hash"]
            ):
                return {"ok": False, "error_code": "APPROVAL_REQUIRED", "retryable": False}
            plan = Plan.model_validate(problem["plan"])
            if (
                plan.digest() != problem["approved_plan_hash"]
                or plan.digest() != problem["plan_hash"]
            ):
                return {"ok": False, "error_code": "PLAN_CHANGED", "retryable": False}
            if (
                str(problem["requester_id"]) != plan.requester_id
                or str(problem_id) != plan.problem_id
            ):
                return {"ok": False, "error_code": "PLAN_IDENTITY_MISMATCH", "retryable": False}
            if (
                problem["platform"] != plan.platform
                or str(problem["resource_id"]) != plan.resource_id
                or problem["requested_role"] != plan.requested_role
            ):
                return {"ok": False, "error_code": "PLAN_CHANGED", "retryable": False}
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (plan.requester_id + ":" + plan.resource_id,),
            )
            profile, resource = (
                self.profile(plan.requester_id, conn),
                self.resource(plan.resource_id, conn),
            )
            membership = self.membership(plan.requester_id, plan.resource_id, conn)
            approver = (
                membership["leader_id"] if resource["access_scope"] == "TF" else profile["head_id"]
            )
            actual_approver = conn.execute(
                "SELECT role,job_grade FROM users WHERE id=%s", (problem["decided_by"],)
            ).fetchone()
            from unlockops.rules import GRADES

            if (
                not actual_approver
                or actual_approver["role"] != "APPROVER"
                or GRADES.get(actual_approver["job_grade"], 0) < 3
                or str(approver) != str(problem["decided_by"])
                or str(problem["decided_by"]) == plan.requester_id
            ):
                return {"ok": False, "error_code": "APPROVER_CHANGED", "retryable": False}
            if (
                resource["platform"] != plan.platform
                or resource["external_id"] != plan.resource_key
            ):
                return {"ok": False, "error_code": "RESOURCE_CHANGED", "retryable": False}
            if plan.platform == "JIRA":
                scheme = conn.execute(
                    "SELECT can_browse FROM jira_role_permissions WHERE resource_id=%s AND saas_role=%s",
                    (plan.resource_id, plan.requested_role),
                ).fetchone()
                if not scheme or not scheme["can_browse"]:
                    return {
                        "ok": False,
                        "error_code": "PRECONDITION_CHANGED",
                        "retryable": False,
                        "reason": "JIRA_SCHEME_MISMATCH",
                    }
            current = self.current(plan.requester_id, plan.resource_id, conn)
            budget = self.budget(plan.requester_id, conn, lock=resource["access_scope"] == "SEAT")
            verdict = evaluate(profile, resource, membership, current, budget, plan.requested_role)
            if verdict.status == "DONE":
                result = {"ok": True, "changed": False, "role": plan.requested_role}
            elif verdict.status != "WAITING_APPROVAL":
                return {
                    "ok": False,
                    "error_code": "PRECONDITION_CHANGED",
                    "retryable": False,
                    "reason": verdict.code,
                }
            elif problem["simulate_jira_failure"] and plan.platform == "JIRA":
                return {"ok": False, "error_code": "MOCK_JIRA_UNAVAILABLE", "retryable": True}
            else:
                if resource["access_scope"] == "SEAT":
                    # Budget row lock + permission + receipt commit together.
                    conn.execute(
                        """UPDATE department_budgets SET remaining_monthly_amount=
                        remaining_monthly_amount-unit_monthly_price,updated_at=NOW() WHERE department_id=%s""",
                        (profile["department_id"],),
                    )
                if plan.platform == "GITHUB" and resource["access_scope"] != "SEAT":
                    team = conn.execute(
                        "SELECT id FROM github_teams WHERE resource_id=%s AND saas_role=%s",
                        (plan.resource_id, plan.requested_role),
                    ).fetchone()
                    if not team:
                        raise ValueError("No dedicated GitHub team for approved resource")
                    conn.execute(
                        "INSERT INTO github_team_members(team_id,user_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                        (team["id"], plan.requester_id),
                    )
                conn.execute(
                    """INSERT INTO permissions(user_id,resource_id,saas_role) VALUES (%s,%s,%s)
                    ON CONFLICT(user_id,resource_id) DO UPDATE SET saas_role=excluded.saas_role,granted_at=NOW()""",
                    (plan.requester_id, plan.resource_id, plan.requested_role),
                )
                result = {"ok": True, "changed": True, "role": plan.requested_role}
            conn.execute(
                "INSERT INTO grant_receipts(idempotency_key,problem_id,result) VALUES (%s,%s,%s)",
                (idempotency_key, problem_id, Jsonb(result)),
            )
            return result

    def verify(self, employee_id, resource_id, requested_role):
        """부여 응답을 신뢰하는 대신 현재 권한을 다시 읽어 검증한다."""
        current = self.current(employee_id, resource_id)
        verified = ROLES.get(current.get("role"), 0) >= ROLES.get(requested_role, 999)
        if "can_browse" in current:
            verified = verified and current["can_browse"]
        return {"ok": True, "verified": verified, "current": current}
