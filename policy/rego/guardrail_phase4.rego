package guardrail

import rego.v1

# Phase 4: trifecta_state overrides role-based policy.
# tripped -> hard deny, regardless of what role-based policy would say.
# partial -> require_approval, regardless of what role-based policy would say.
# none    -> fall through to the exact same role-based matching as Phase 3.
#
# The three trifecta_state branches plus the "none" branch are mutually
# exclusive by construction (trifecta_state can only hold one value at a
# time), so this can't hit OPA's "complete rules must not produce multiple
# outputs" conflict.

default decision := "deny"

decision := "deny" if input.trifecta_state == "tripped"

decision := "require_approval" if input.trifecta_state == "partial"

decision := role_based_decision if input.trifecta_state == "none"

role_based_decision := data.rules[first_match].decision if {
	matches := [i | some i; rule_matches(data.rules[i])]
	count(matches) > 0
	first_match := min(matches)
}

role_based_decision := "deny" if {
	matches := [i | some i; rule_matches(data.rules[i])]
	count(matches) == 0
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

