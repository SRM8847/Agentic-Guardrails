"""
Phase 2 policy engine. Matches (role, tool, resource) against
policy/rules_v1.yaml and returns "allow", "deny", or "require_approval".

First-match-wins by rule order, falls through to "deny" if nothing
matches. This exact semantics is what policy/rego/guardrail_phase3.rego
was built to reproduce -- Phase 3 regresses against this module's
behavior, not the other way around.
"""
import fnmatch
import pathlib
import yaml

RULES_PATH = pathlib.Path(__file__).resolve().parent.parent / "policy" / "rules_v1.yaml"


def load_rules():
    with open(RULES_PATH) as f:
        return yaml.safe_load(f)["rules"]


_RULES = load_rules()


def _resource_matches(pattern, resource):
    """Segment-based glob match on '.', mirroring OPA's
    glob.match(pattern, ["."], resource) semantics rather than Python's
    fnmatch (whose '*' would otherwise cross '.' boundaries and match
    more than the Rego side does)."""
    pattern_segs = pattern.split(".")
    resource_segs = resource.split(".")
    if len(pattern_segs) != len(resource_segs):
        return False
    return all(fnmatch.fnmatch(r, p) for p, r in zip(pattern_segs, resource_segs))


def decide(role, tool, resource=""):
    for rule in _RULES:
        if rule["role"] not in (role, "any"):
            continue
        if tool not in rule["tool"]:
            continue
        if "resource" in rule and not _resource_matches(rule["resource"], resource):
            continue
        return rule["decision"]
    return "deny"
