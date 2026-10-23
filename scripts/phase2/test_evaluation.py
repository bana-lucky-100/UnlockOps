"""Three offline checks for fixture isolation and the evaluator's failure boundary."""
from datetime import datetime
import hashlib
import json
import unittest
from uuid import UUID, uuid5

from fixtures import LITERAL, ROOT, prepare
from run_suite import CheckFailed, check

RUN = "43b1ac51-7fb0-4ddf-981b-00b1e83b73fb"
NOW = datetime.fromisoformat("2027-01-15T12:00:00+09:00")


class EvaluationTest(unittest.TestCase):
    def test_complete_isolated_fixtures_and_negative_overrides(self):
        bundle, sql = prepare(RUN, "full", NOW)
        catalog = json.loads((ROOT / "data/phase2/catalog.json").read_text())
        cases = {c["id"]: c for c in bundle["cases"]}
        self.assertEqual(len(cases), 25)
        self.assertTrue({s["id"] for s in catalog["scenarios"]}.issubset(cases))
        self.assertIn("current_database()<>'phase2_eval'", sql)
        tenant_ids = [co["company_id"] for c in cases.values() for co in c["companies"].values()]
        self.assertEqual(len(set(tenant_ids)), 50)
        self.assertTrue(all(co["company_id"] not in sql for co in catalog["companies"].values()))
        self.assertNotIn("entitlement_id", cases["B-02"]["input"])
        self.assertNotIn("resource_id", cases["B-05"]["input"])
        self.assertIn("SET access_scope='TF'", sql)
        self.assertIn("entitlement_revision,granted_at", sql)
        self.assertEqual(len(cases["X-10"]["expected_assignments"]), 2)
        self.assertEqual(len(prepare(RUN, "smoke", NOW)[0]["cases"]), 8)
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
        self.assertEqual(prepare(RUN, "smoke", NOW), (bundle, sql))

    def test_mismatches_fail_even_with_assertions_disabled(self):
        check(True, "valid")
        with self.assertRaisesRegex(CheckFailed, "wrong status"):
            check(False, "wrong status")
        with self.assertRaises(ValueError):
            prepare("not-a-uuid")
        with self.assertRaises(ValueError):
            prepare(RUN, "unsupported")


if __name__ == "__main__":
    unittest.main()
