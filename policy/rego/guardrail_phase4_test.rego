package guardrail

import rego.v1

# Scenario 1 shape: read-only call would normally be allowed by role,
# but a tripped trifecta must override that to deny.
test_tripped_overrides_would_be_allow if {
	decision == "deny" with input as {"role": "research_agent", "tool": "fs_read", "resource": "", "trifecta_state": "tripped"}
		with data.rules as rules_fixture
}

# Scenario 3 shape: partial trifecta forces human approval even though
# role-based policy alone would have allowed it.
test_partial_forces_approval_even_when_role_would_allow if {
	decision == "require_approval" with input as {"role": "research_agent", "tool": "fs_read", "resource": "", "trifecta_state": "partial"}
		with data.rules as rules_fixture
}

# Scenario 4 shape: no trifecta signal tripped -> falls through to
# ordinary role-based policy, unchanged from Phase 3.
test_none_falls_through_to_role_based_allow if {
	decision == "allow" with input as {"role": "research_agent", "tool": "fs_read", "resource": "", "trifecta_state": "none"}
		with data.rules as rules_fixture
}

test_none_falls_through_to_role_based_require_approval if {
	decision == "require_approval" with input as {"role": "any_role", "tool": "fs_write", "resource": "customers.42", "trifecta_state": "none"}
		with data.rules as rules_fixture
}

test_missing_trifecta_state_defaults_deny_fail_closed if {
	decision == "deny" with input as {"role": "research_agent", "tool": "fs_read", "resource": ""}
		with data.rules as rules_fixture
}

rules_fixture := [
	{"id": "allow-read-only-default", "role": "any", "tool": ["fs_read", "db_query_nonpii", "fetch_url"], "decision": "allow"},
	{"id": "deny-external-reach-default", "role": "research_agent", "tool": ["send_email", "s3_put_object"], "decision": "deny"},
	{"id": "require-approval-sensitive-write", "role": "any", "tool": ["fs_write"], "resource": "customers.*", "decision": "require_approval"},
]

