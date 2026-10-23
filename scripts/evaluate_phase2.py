#!/usr/bin/env python3
"""Plan or run mock evaluation in a disposable Docker project (stdlib host CLI)."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from phase2.fixtures import ROOT, prepare, quote


class Blocked(Exception):
    pass


def save(path, report):
    if "status" in report and "cases" in report:
        report["summary"] = {status: sum(c["status"] == status for c in report["cases"])
                             for status in ("PASS", "FAIL", "ERROR", "TIMEOUT", "NOT_RUN")}
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="Prepare fixtures only (default)")
    mode.add_argument("--run", action="store_true", help="Build and run a new isolated Docker stack")
    parser.add_argument("--suite", choices=["smoke", "full"], default="smoke")
    parser.add_argument("--keep", action="store_true", help="Keep this run's isolated stack for debugging")
    args = parser.parse_args(argv)
    run_id = str(uuid4())
    project = "unlockops-p2-eval-" + run_id
    output = ROOT / "test-results/phase2" / run_id
    output.mkdir(parents=True)
    bundle, sql = prepare(run_id, args.suite)
    save(output / "bundle.json", bundle)
    (output / "fixtures.sql").write_text(sql)
    report = {"schema_version": 1, "run_id": run_id, "suite": args.suite,
              "created_at": datetime.now(timezone.utc).isoformat(), "status": "NOT_RUN",
              "project": project, "cases": [{"id": c["id"], "status": "NOT_RUN", "checks": []} for c in bundle["cases"]],
              "browser_interaction": "NOT_RUN", "legacy_upgrade": "NOT_RUN",
              "checks": {}, "cleanup": "NOT_NEEDED"}
    path = output / "report.json"
    if not args.run:
        save(path, report)
        print(f"Prepared {len(bundle['cases'])} cases; no services started.\n{path}")
        return 0

    env = {**os.environ, "PHASE2_EVAL_INPUT": str(output / "bundle.json")}
    command = ["docker", "compose", "--env-file", os.devnull, "--project-name", project,
               "-f", str(ROOT / "infra/compose.phase2-eval.yaml")]
    log_path = output / "runtime.log"
    started = False

    def execute(cmd, *, input=None, timeout=120, allow_failure=False):
        with log_path.open("a") as log:
            completed = subprocess.run(cmd, input=input, stdout=subprocess.PIPE, stderr=log,
                                       text=True, env=env, cwd=ROOT, timeout=timeout)
            log.write(completed.stdout)
            if not allow_failure and completed.returncode:
                raise Blocked(f"Command failed (exit {completed.returncode}); see runtime.log")
            return completed

    def database(sql):
        return execute(command + ["exec", "-T", "postgres", "psql", "-XAt", "-v", "ON_ERROR_STOP=1",
                                  "-U", "evaluator", "-d", "phase2_eval"], input=sql).stdout.strip()

    legacy_sql = """SELECT json_build_object(
      'problems', (SELECT md5(coalesce(string_agg(to_jsonb(p)::text,'' ORDER BY id),'')) FROM problems p WHERE contract_version=1),
      'users', (SELECT md5(coalesce(string_agg((to_jsonb(u)-'password_hash')::text,'' ORDER BY u.id),'')) FROM users u JOIN companies c ON c.id=u.company_id WHERE c.code='LEGACY'),
      'budgets', (SELECT md5(coalesce(string_agg(to_jsonb(b)::text,'' ORDER BY b.department_id),'')) FROM department_budgets b JOIN departments d ON d.id=b.department_id JOIN companies c ON c.id=d.company_id WHERE c.code='LEGACY'));
    """
    try:
        execute(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=20)
        execute(command + ["config", "--quiet"])
        # UUID project names and the database guard prevent targeting a user's demo stack.
        started = True
        print(f"Building isolated stack {project} ...", flush=True)
        execute(command + ["up", "--build", "--wait", "--wait-timeout", "240", "postgres", "rabbitmq", "backend",
                           "policy-mcp", "business-mcp", "agent", "frontend"], timeout=1800)
        report["checks"]["locked_frontend_test_build"] = "PASS"
        versions = json.loads(database("SELECT json_agg(version ORDER BY installed_rank) FROM flyway_schema_history WHERE success AND version IS NOT NULL;"))
        if not {"6", "7", "8"}.issubset(versions):
            raise Blocked("Required migrations V6/V7/V8 were not applied")
        report["checks"]["fresh_migration_v1_v8"] = "PASS"
        before = database(legacy_sql)
        database(sql)
        report["checks"]["fixture_install"] = "PASS"
        completed = execute(command + ["run", "--build", "--rm", "--no-deps", "-T", "evaluator"],
                            timeout=120 + len(bundle["cases"]) * 210, allow_failure=True)
        try:
            result = json.loads(completed.stdout)
        except ValueError as error:
            raise Blocked("Evaluator did not produce a complete JSON report; see runtime.log") from error
        if {r["id"] for r in result["cases"]} != {c["id"] for c in bundle["cases"]}:
            raise Blocked("Evaluator returned an incomplete case set")
        report.update(result)
        if completed.returncode != 0:
            report["status"] = "FAIL"
        report["checks"]["legacy_facts_unchanged"] = "PASS" if before == database(legacy_sql) else "FAIL"
        by_id = {r["id"]: r for r in report["cases"]}
        # Independently check DB side effects; matching HTTP receipts alone cannot prove one debit.
        for case in bundle["cases"]:
            outcome = by_id[case["id"]]
            if outcome["status"] != "PASS":
                continue
            dept = quote(case["company_data"]["department_id"])
            budget = Decimal(database(f"SELECT remaining_monthly_amount FROM department_budgets WHERE department_id={dept};"))
            executed = bool(outcome.get("assignment_id"))
            expected_budget = Decimal(case["initial_budget"]) - (Decimal(case["monthly_amount"]) if executed else Decimal(0))
            correct = budget == expected_budget
            if case["scope_id"]:
                ids = ",".join(quote(i) for i in case["expected_assignments"])
                active = int(database(f"SELECT count(*) FROM access_assignments WHERE id IN ({ids}) AND status='ACTIVE' AND ended_at IS NULL;"))
                revoked = outcome.get("revoked_assignment_ids", [])
                correct = correct and set(revoked).issubset(case["expected_assignments"])
                correct = correct and active == len(case["expected_assignments"]) - len(revoked)
                if revoked:
                    revoked_sql = ",".join(quote(i) for i in revoked)
                    confirmed = int(database(f"SELECT count(*) FROM access_assignments a JOIN reclaim_execution_receipts e ON e.assignment_id=a.id WHERE a.id IN ({revoked_sql}) AND a.status='INACTIVE' AND a.ended_at IS NOT NULL AND e.verification_ok AND NOT EXISTS(SELECT 1 FROM mock_entitlement_memberships m WHERE m.assignment_id=a.id) AND NOT EXISTS(SELECT 1 FROM reclaim_targets t WHERE t.assignment_id=a.id AND t.closed_at IS NULL);"))
                    correct = correct and confirmed == len(revoked)
            else:
                pid = quote(outcome["problem_id"])
                receipts = int(database(f"SELECT count(*) FROM access_execution_receipts WHERE problem_id={pid};"))
                correct = correct and receipts == int(executed)
            if correct:
                outcome["checks"].append("database_budget_and_side_effects")
            else:
                outcome.update(status="FAIL", detail="Database budget, receipt count or active assignments differ")
        if any(r["status"] != "PASS" for r in report["cases"]) or "FAIL" in report["checks"].values():
            report["status"] = "FAIL"
    except (Blocked, OSError, subprocess.TimeoutExpired) as error:
        report.update(status="BLOCKED", detail=str(error) if isinstance(error, Blocked) else type(error).__name__)
    except KeyboardInterrupt:
        report.update(status="INTERRUPTED", detail="Interrupted by operator")
    finally:
        if started:
            if args.keep:
                report["cleanup"] = "KEPT"
            else:
                try:
                    execute(command + ["down", "--volumes", "--remove-orphans"], timeout=120)
                    report["cleanup"] = "REMOVED"
                except (Blocked, OSError, subprocess.TimeoutExpired):
                    report["cleanup"] = "FAILED"
                    if report["status"] == "PASS":
                        report["status"] = "BLOCKED"
        save(path, report)
        print(f"{report['status']}: {path}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
