"""Offline checks for fixture isolation, preconditions and failure boundaries."""
import copy
from contextlib import redirect_stdout
from datetime import datetime
import hashlib
import json
import io
import subprocess
import tempfile
import unittest
import sys
from pathlib import Path
from uuid import UUID, uuid5
from unittest.mock import patch

from fixtures import LITERAL, ROOT, prepare
from run_suite import CheckFailed, check
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phase2.preconditions import observation_sql, verify
import evaluate_phase2

RUN = "43b1ac51-7fb0-4ddf-981b-00b1e83b73fb"
NOW = datetime.fromisoformat("2027-01-15T12:00:00+09:00")


class EvaluationTest(unittest.TestCase):
    def test_complete_isolated_fixtures_and_negative_overrides(self):
        bundle, sql = prepare(RUN, "full", NOW)
        catalog = json.loads((ROOT / "data/phase2/catalog.json").read_text())
        cases = {c["id"]: c for c in bundle["cases"]}
        self.assertEqual(len(cases), 33)
        self.assertTrue({s["id"] for s in catalog["scenarios"]}.issubset(cases))
        self.assertIn("current_database()<>'phase2_eval'", sql)
        tenant_ids = [co["company_id"] for c in cases.values() for co in c["companies"].values()]
        self.assertEqual(len(set(tenant_ids)), 66)
        self.assertTrue(all(co["company_id"] not in sql for co in catalog["companies"].values()))
        self.assertNotIn("entitlement_id", cases["B-02"]["input"])
        self.assertNotIn("entitlement_id", cases["P-06"]["input"])
        self.assertEqual(cases['P-06']['monthly_amount'], '16.00')
        self.assertEqual(cases['X-08b-USAGE']['expected_reason_code'], 'SCAN_COMPLETED')
        self.assertNotIn("resource_id", cases["B-05"]["input"])
        self.assertIn("SET access_scope='TF'", sql)
        self.assertIn("entitlement_revision,granted_at", sql)
        self.assertEqual(len(cases["X-10"]["expected_assignments"]), 2)
        self.assertEqual(len(prepare(RUN, "smoke", NOW)[0]["cases"]), 9)
        other, _ = prepare("53b1ac51-7fb0-4ddf-981b-00b1e83b73fb", "full", NOW)
        self.assertTrue(set(tenant_ids).isdisjoint(c["company_data"]["company_id"] for c in other["cases"]))

    def test_rebased_facts_keep_policy_hashes_and_deterministic_ids(self):
        bundle, sql = prepare(RUN, "smoke", NOW)
        original = json.loads((ROOT / "data/phase2/catalog.json").read_text())
        first = bundle["cases"][0]
        expected = str(uuid5(uuid5(UUID(RUN), first["id"]), original["companies"]["A"]["company_id"]))
        self.assertEqual(first["company_data"]["company_id"], expected)
        self.assertIn("'2027-01-15T09:00:00+09:00'", sql)
        self.assertNotIn("'2026-10-22T09:00:00+09:00'", sql)
        literals = [m.group(1).replace("''", "'") for m in LITERAL.finditer(sql)]
        for company in ("a", "b"):
            policy = (ROOT / f"data/phase2/company-{company}-policy.md").read_text()
            self.assertIn(policy, literals)
            self.assertIn(hashlib.sha256(policy.encode()).hexdigest(), literals)
        snapshots = [json.loads(value) for value in literals if value.startswith('{"facts":')]
        self.assertTrue(snapshots)
        for snapshot in snapshots:
            self.assertEqual(snapshot["facts"]["observed_at"], "2027-01-14T09:00:00+09:00")
            self.assertEqual(snapshot["candidate"]["fact_evidence"][0]["observed_at"], snapshot["facts"]["observed_at"])
        self.assertEqual(prepare(RUN, "smoke", NOW), (bundle, sql))

    def test_mismatches_fail_even_with_assertions_disabled(self):
        check(True, "valid")
        with self.assertRaisesRegex(CheckFailed, "wrong status"):
            check(False, "wrong status")
        with self.assertRaises(ValueError):
            prepare("not-a-uuid")
        with self.assertRaises(ValueError):
            prepare(RUN, "unsupported")

    def budget_observation(self, case):
        expected = case['preconditions']
        company = case['company_data']
        price_fields = {'currency', 'cost_basis', 'pricing_revision', 'source_kind'}
        observed = {k: v for k, v in expected.items() if k not in price_fields | {'monthly_amount', 'unit_monthly_amount'}}
        observed.update(company_id=company['company_id'], department_id=company['department_id'],
                        requester_id=company['users']['requester'], resource_id=case['input']['resource_id'],
                        entitlement_id=case['fixture_entitlement_id'], budget_currency='USD',
                        license_observation_valid=True, license_observed_at=NOW.isoformat(), license_valid_until=None,
                        prices=[{**{k: expected[k] for k in price_fields},
                                 'monthly_amount': expected['unit_monthly_amount'], 'cost_basis': 'SEAT_MONTHLY',
                                 'pricing_id': 'fixture-price', 'policy_revision': 4}])
        return observed

    def test_budget_preconditions_detect_seed_and_permission_drift(self):
        bundle, _ = prepare(RUN, 'smoke', NOW)
        case = next(c for c in bundle['cases'] if c['id'] == 'E-02')
        good = self.budget_observation(case)
        self.assertEqual(verify(case, good)['status'], 'PASS')
        numeric=copy.deepcopy(good)
        numeric['prices'][0]['monthly_amount']=20.0  # PostgreSQL JSON numeric, not a money string.
        numeric['remaining_budget']=10
        self.assertEqual(verify(case,numeric)['status'],'PASS')
        for field, value in [('remaining_budget', '500.00'), ('entitlement_id', str(UUID(int=1))),
                             ('access_scope', 'DEPARTMENT'), ('tf_member', False),
                             ('budget_currency', 'KRW'), ('account_exists', None), ('policy_revision', 5)]:
            with self.subTest(field=field):
                observed = copy.deepcopy(good)
                observed[field] = value
                result = verify(case, observed)
                self.assertEqual(result['status'], 'PRECONDITION_FAILED')
                self.assertIn(field, result['mismatches'])
        zero = copy.deepcopy(good)
        zero['prices'][0].update(monthly_amount=0, cost_basis='NO_ADDITIONAL_COST')
        self.assertIn('unit_monthly_amount', verify(case, zero)['mismatches'])
        for prices in [[], [*good['prices'], {**good['prices'][0], 'pricing_id': 'other-price'}]]:
            self.assertIn('effective_price_missing_or_ambiguous', verify(case, {**good, 'prices': prices})['mismatches'])
        self.assertEqual(verify(case, None)['status'], 'PRECONDITION_FAILED')
        # Check SQL scope and effective-date semantics without needing a live DB.
        sql = observation_sql(case)
        self.assertIn(case['company_data']['company_id'], sql)
        self.assertNotIn('UPDATE ', sql)
        self.assertIn('entitlement_revision=er.revision', sql)
        self.assertIn("AT TIME ZONE 'Asia/Seoul'", sql)
        self.assertIn('lf.purchase_required',sql)
        self.assertIn('lf.valid_until>CURRENT_TIMESTAMP',sql)

        seat=next(c for c in prepare(RUN,'full',NOW)[0]['cases'] if c['id']=='BUDGET-INSUFFICIENT')
        for flag in (False,None):
            observed=self.budget_observation(seat)
            observed['purchase_required']=flag
            self.assertIn('purchase_required',verify(seat,observed)['mismatches'])
        for observed_at,valid_until in [(None,None),('2020-01-01T00:00:00+00:00','2020-02-01T00:00:00+00:00'),
                                      ('2099-01-01T00:00:00+00:00',None)]:
            observed={**good,'license_observation_valid':False,'license_observed_at':observed_at,'license_valid_until':valid_until}
            result=verify(case,observed)
            self.assertEqual(result['status'],'PRECONDITION_FAILED')
            self.assertIn('license_observation_valid',result['mismatches'])

    def test_budget_boundaries_and_declared_rule_cannot_silently_change(self):
        bundle, sql = prepare(RUN, 'full', NOW)
        cases = {c['id']: c for c in bundle['cases']}
        for name, amount, budget, status in [('E-02', '0.00', '10.00', 'WAITING_APPROVAL'),
                ('BUDGET-INSUFFICIENT', '19.00', '10.00', 'ON_HOLD'),
                ('BUDGET-EQUAL', '19.00', '19.00', 'WAITING_APPROVAL'),
                ('BUDGET-ABOVE', '19.00', '30.00', 'WAITING_APPROVAL'),
                ('BUDGET-FREE', '0.00', '10.00', 'WAITING_APPROVAL')]:
            case = cases[name]
            self.assertEqual((case['monthly_amount'], case['initial_budget'], case['expected_status']), (amount, budget, status))
            self.assertEqual(verify(case, self.budget_observation(case))['status'], 'PASS')
        self.assertIn('UPDATE saas_license_facts SET coverage=', sql)
        invalid = copy.deepcopy(cases['BUDGET-INSUFFICIENT'])
        invalid['expected_status'] = 'WAITING_APPROVAL'
        self.assertIn('decision_rule', verify(invalid, self.budget_observation(invalid))['mismatches'])

    def test_precondition_failure_blocks_requests_and_is_saved_separately(self):
        bundle, sql = prepare(RUN, 'smoke', NOW)
        case = next(c for c in bundle['cases'] if c['id'] == 'E-02')
        observed = self.budget_observation(case)
        observed['remaining_budget'] = '500.00'
        commands = []

        def execute(command, **kwargs):
            commands.append(command)
            statement = kwargs.get('input') or ''
            if 'flyway_schema_history' in statement:
                output = '["6","7","8","10"]'
            elif "'entitlement_code'" in statement:
                target = next(c for c in bundle['cases'] if c.get('preconditions') and c['fixture_entitlement_id'] in statement)
                output = json.dumps(observed if target['id'] == 'E-02' else self.budget_observation(target))
            elif "'problems'" in statement:
                output = '{}'
            else:
                output = ''
            return subprocess.CompletedProcess(command, 0, stdout=output)

        with tempfile.TemporaryDirectory() as folder:
            with patch.object(evaluate_phase2, 'ROOT', Path(folder)), \
                    patch.object(evaluate_phase2, 'prepare', return_value=(bundle, sql)), \
                    patch.object(evaluate_phase2, 'uuid4', return_value=UUID(RUN)), \
                    patch.object(evaluate_phase2.subprocess, 'run', side_effect=execute), redirect_stdout(io.StringIO()):
                self.assertEqual(evaluate_phase2.main(['--run']), 1)
            report = json.loads((Path(folder) / 'test-results/phase2' / RUN / 'report.json').read_text())
        self.assertEqual(report['status'], 'BLOCKED')
        self.assertEqual(report['summary']['PRECONDITION_FAILED'], 1)
        self.assertEqual(report['summary']['NOT_RUN'], 8)
        failed = next(c for c in report['cases'] if c['id'] == 'E-02')
        self.assertEqual(failed['precondition_check']['observed']['remaining_budget'], '500.00')
        self.assertEqual(report['cleanup'], 'REMOVED')
        self.assertFalse(any('run' in command and command[-1] == 'evaluator' for command in commands))


if __name__ == "__main__":
    unittest.main()
