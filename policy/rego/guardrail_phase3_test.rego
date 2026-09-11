package guardrail

import rego.v1

test_read_only_allowed if {
	decision == "allow" with input as {"role": "research_agent", "tool": "fs_read", "resource": "anything"}
		with data.rules as rules_fixture
}

test_send_email_denied_for_research_agent if {
	decision == "deny" with input as {"role": "research_agent", "tool": "send_email", "resource": ""}
		with data.rules as rules_fixture
}

test_fs_write_customers_requires_approval if {
	decision == "require_approval" with input as {"role": "any_role", "tool": "fs_write", "resource": "customers.123"}
		with data.rules as rules_fixture
}

test_fs_write_non_customers_falls_through_to_default_deny if {
	decision == "deny" with input as {"role": "any_role", "tool": "fs_write", "resource": "logs.txt"}
		with data.rules as rules_fixture
}

test_unknown_tool_defaults_deny if {
	decision == "deny" with input as {"role": "research_agent", "tool": "totally_unknown_tool", "resource": ""}
		with data.rules as rules_fixture
}

rules_fixture := [
	{"id": "allow-read-only-default", "role": "any", "tool": ["fs_read", "db_query_nonpii", "fetch_url"], "decision": "allow"},
	{"id": "deny-external-reach-default", "role": "research_agent", "tool": ["send_email", "s3_put_object"], "decision": "deny"},
	{"id": "require-approval-sensitive-write", "role": "any", "tool": ["fs_write"], "resource": "customers.*", "decision": "require_approval"},
]

