package guardrail

import rego.v1

# Phase 3 target: reproduce policy/rules_v1.yaml's decisions exactly, with
# no knowledge of trifecta_state at all (Phase 2 never produced one).
# First-match-wins by rule order, same as the Python engine should use.
#
# Note: the role_permits boolean shown in the original build guide's §4.4
# only distinguishes allow/deny and can't reproduce the require_approval
# rule (require-approval-sensitive-write) in rules_v1.yaml. This version
# reads the decision straight off the matching rule so it's a true
# regression target.

default decision := "deny"

decision := data.rules[first_match].decision if {
	matches := [i | some i; rule_matches(data.rules[i])]
	count(matches) > 0
	first_match := min(matches)
}

rule_matches(rule) if {
	rule.role in {input.role, "any"}
	input.tool in rule.tool
	resource_ok(rule)
}

resource_ok(rule) if {
	not rule.resource
}

resource_ok(rule) if {
	rule.resource
	glob.match(rule.resource, ["."], input.resource)
}

