"""Read-only fixture checks, separate from workflow outcome checks."""
from decimal import Decimal, InvalidOperation

from .fixtures import quote


def observation_sql(case):
    """Observe the same effective price candidates used by the server planner."""
    company = case['company_data']
    co, dept, user = quote(company['company_id']), quote(company['department_id']), quote(company['users']['requester'])
    entitlement = quote(case['fixture_entitlement_id'])
    return f"""SELECT json_build_object(
      'company_id',u.company_id,'department_id',u.department_id,'requester_id',u.id,
      'resource_id',r.id,'entitlement_id',e.id,'entitlement_code',e.code,'entitlement_kind',e.kind,
      'access_scope',r.access_scope,'remaining_budget',b.remaining_monthly_amount,'budget_currency',b.currency,
      'operation',cr.operation,'license_coverage',lf.coverage,'purchase_required',lf.purchase_required,
      'license_observed_at',lf.observed_at,'license_valid_until',lf.valid_until,
      'license_observation_valid',(lf.observed_at<=CURRENT_TIMESTAMP
        AND (lf.valid_until IS NULL OR lf.valid_until>CURRENT_TIMESTAMP)
        AND nullif(btrim(lf.source_reference),'') IS NOT NULL),
      'policy_revision',(SELECT max(revision) FROM policy_revisions WHERE company_id={co}),
      'prices',(SELECT coalesce(json_agg(to_jsonb(p) ORDER BY p.pricing_revision DESC),'[]'::json) FROM
        (SELECT pricing_id,revision AS pricing_revision,policy_revision,monthly_amount,currency,cost_basis,source_kind
         FROM pricing_revisions WHERE company_id={co} AND entitlement_id=e.id AND entitlement_revision=er.revision
           AND effective_from<=(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')::date
           AND (effective_until IS NULL OR effective_until>=(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')::date)) p),
      'tf_member',EXISTS(SELECT 1 FROM tf_members m JOIN tfs t ON t.id=m.tf_id WHERE m.user_id=u.id
        AND m.tf_id=r.tf_id AND m.active AND t.starts_on<=(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')::date
        AND (t.ends_on IS NULL OR t.ends_on>=(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')::date)),
      'account_exists',f.account_exists,'license_active',f.license_active,'work_scope_assigned',f.work_scope_assigned,
      'already_assigned',EXISTS(SELECT 1 FROM access_assignments WHERE user_id=u.id AND entitlement_id=e.id AND status='ACTIVE'))
    FROM users u JOIN entitlements e ON e.company_id=u.company_id AND e.id={entitlement}
    JOIN resources r ON r.id=e.resource_id AND r.company_id=u.company_id
    JOIN LATERAL (SELECT revision FROM entitlement_revisions WHERE entitlement_id=e.id ORDER BY revision DESC LIMIT 1) er ON true
    LEFT JOIN department_budgets b ON b.department_id=u.department_id
    LEFT JOIN saas_context_facts f ON f.company_id=u.company_id AND f.user_id=u.id AND f.platform=r.platform
    LEFT JOIN access_cost_rules cr ON cr.company_id=u.company_id AND cr.entitlement_id=e.id AND cr.entitlement_revision=er.revision
      AND cr.policy_id={quote(company['policy_id'])} AND cr.policy_revision=(SELECT max(revision) FROM policy_revisions WHERE company_id=u.company_id)
    LEFT JOIN saas_license_facts lf ON lf.company_id=u.company_id AND lf.user_id=u.id AND lf.platform=r.platform
      AND lf.billing_scope=cr.billing_scope AND lf.license_code=cr.required_license
    WHERE u.id={user} AND u.company_id={co} AND u.department_id={dept};"""


def verify(case, observed):
    """Return reviewable expected/observed facts; never label drift an agent failure."""
    expected = dict(case['preconditions'])
    company = case['company_data']
    expected.update(company_id=company['company_id'], department_id=company['department_id'],
                    requester_id=company['users']['requester'], resource_id=case['input']['resource_id'],
                    entitlement_id=case['fixture_entitlement_id'])
    actual = dict(observed or {})
    prices = actual.pop('prices', [])
    mismatches = []
    if 'license_coverage' in expected and actual.get('license_observation_valid') is not True:
        mismatches.append('license_observation_valid')
    if (actual.get('operation') == 'PURCHASE_SEAT' and actual.get('license_coverage') == 'NOT_COVERED'
            and actual.get('purchase_required') is not True):
        mismatches.append('purchase_required')
    if not prices or len({p['pricing_id'] for p in prices}) != 1:
        mismatches.append('effective_price_missing_or_ambiguous')
    else:
        price = prices[0]
        if price['policy_revision'] != actual.get('policy_revision'):
            mismatches.append('price_policy_revision_mismatch')
        actual.update({k: v for k, v in price.items() if k != 'policy_revision'})
        actual['unit_monthly_amount'] = actual['monthly_amount']
        if actual.get('license_coverage') == 'COVERED' and actual.get('operation') in {'PERMISSION_ONLY', 'PURCHASE_SEAT'}:
            actual.update(monthly_amount='0.00', cost_basis='NO_ADDITIONAL_COST')
    for field, value in expected.items():
        current = actual.get(field)
        if field in {'remaining_budget', 'monthly_amount', 'unit_monthly_amount'}:
            try:
                matches = Decimal(str(current)) == Decimal(str(value))
            except InvalidOperation:
                matches = False
        else:
            matches = type(current) is type(value) and current == value
        if not matches:
            mismatches.append(field)
    if actual.get('budget_currency') != expected['currency']:
        mismatches.append('budget_currency')
    # Validate the declared scenario rule too; do not run arbitrary expressions.
    amount, budget = Decimal(expected['monthly_amount']), Decimal(expected['remaining_budget'])
    rules = {
        'BUDGET_EXCEEDED': (amount > budget, 'ON_HOLD', 'BUDGET_INSUFFICIENT'),
        'BUDGET_SUFFICIENT': (amount <= budget, 'WAITING_APPROVAL', 'ELIGIBLE'),
        'NO_ADDITIONAL_COST': (amount == 0 and budget >= 0 and expected['cost_basis'] == 'NO_ADDITIONAL_COST', 'WAITING_APPROVAL', 'ELIGIBLE'),
    }
    decision_rule = case.get('decision_rule')
    rule = rules.get(decision_rule)
    if not rule or not rule[0] or rule[1:] != (case['expected_status'], case['expected_reason_code']):
        mismatches.append('decision_rule')
    mismatches = list(dict.fromkeys(mismatches))
    return {'status': 'PRECONDITION_FAILED' if mismatches else 'PASS', 'expected': expected,
            'observed': actual, 'mismatches': mismatches, 'decision_rule': decision_rule}
