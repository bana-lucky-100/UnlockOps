"""Cross-service golden vectors: invariants matter more than generated line counts."""
import json
import hashlib
import subprocess
import sys
from pathlib import Path
import pytest
from pydantic import ValidationError
from unlockops.common import phase2
from unlockops.common.models import Plan

ROOT=Path(__file__).resolve().parents[2]
VECTORS=json.loads((ROOT/'contracts/phase2/examples/vectors.json').read_text())

@pytest.mark.parametrize('case',VECTORS['valid'],ids=lambda c:c['name'])
def test_valid_wire_examples(case):
    getattr(phase2,case['model']).model_validate(case['payload'])

@pytest.mark.parametrize('case',VECTORS['invalid'],ids=lambda c:c['name'])
def test_invalid_wire_examples(case):
    with pytest.raises(ValidationError):
        getattr(phase2,case['model']).model_validate(case['payload'])


def test_cross_language_hash_vector_and_revision_changes():
    p=phase2.GrantPlanV2.model_validate(VECTORS['valid'][0]['payload'])
    assert p.canonical_json()==VECTORS['plan_canonical_json']
    assert p.digest()==VECTORS['plan_sha256']
    for field in ['entitlement_revision','pricing_revision','policy_revision','route_revision']:
        assert p.model_copy(update={field:2}).digest()!=p.digest()
    assert p.model_copy(update={'approver_ids':list(reversed(p.approver_ids))}).digest()!=p.digest()


def test_v1_plan_stays_six_fields():
    assert len(Plan.model_fields)==6
    assert 'schema_version' not in Plan.model_fields


def test_exports_are_in_sync():
    subprocess.run([sys.executable,str(ROOT/'scripts/export_phase2_contracts.py'),'--check'],check=True,cwd=ROOT)


def test_mock_catalog_has_ten_platforms_and_twenty_scenarios():
    data=json.loads((ROOT/'data/phase2/catalog.json').read_text())
    assert {x['platform'] for x in data['catalog']}==set(phase2.Platform)
    assert len(data['scenarios'])==20
    assert len({s['id'] for s in data['scenarios']})==20
    assert all(x['execution_ready'] and x['validation_status']=='NOT_RUN' for x in data['scenarios'])
    assert all(x['source_kind']=='SYNTHETIC_CONTRACT' for x in data['catalog'])
    assert len({x['assignment_id'] for x in data['reclaim_fixtures'].values()})==8


def test_seed_policy_hashes_match_document_bytes():
    seed=(ROOT/'data/phase2/seed.sql').read_text()
    for path in (ROOT/'data/phase2').glob('*-policy.md'):
        assert hashlib.sha256(path.read_bytes()).hexdigest() in seed
