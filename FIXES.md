# Fixes applied to the original build guide, and how they were verified

## 1. `data.rules` was never loaded into OPA

`guardrail.rego`'s `role_permits`/`rule_matches` reads `data.rules`, but the
compose file only mounts `./policy/rego` into the OPA container, and
`rules_v1.yaml` lives one level up in `./policy`. OPA had no way to see it.

**Fix:** `scripts/generate_opa_data.py` converts `policy/rules_v1.yaml` into
`policy/rego/rules_data.json`. That file lives inside the mounted directory,
and because OPA's ad-hoc `opa run <dir>` mode (no `--bundle` flag) merges a
loaded JSON file's top-level keys straight into the root `data` document, a
file containing `{"rules": [...]}` becomes `data.rules` automatically.

`rules_v1.yaml` stays the single source of truth for both the Phase 2 Python
engine and the Phase 3+ Rego engine. Re-run the script any time the rule
table changes:

    python3 scripts/generate_opa_data.py

**Verified:** loaded `rules_data.json` + `guardrail_phase4.rego` together
with `opa eval` (not just the hand-fed test fixture) and confirmed
`data.rules` resolves and produces the correct decision end to end.

## 2. Phase 3's own regression check was unsatisfiable as originally specified

The original guide's §4.4 Rego already included the full `trifecta_state`
branching, but Phase 3's success criterion is "same decisions as Phase 2" —
and Phase 2's rule table has no concept of `trifecta_state` at all. Feeding
Phase 2-style input (no `trifecta_state` key) into that Rego means every
`input.trifecta_state == "..."` comparison is undefined, nothing matches,
and it falls through to `default decision := "deny"` for every call,
including ones Phase 2 correctly allowed.

Separately, the original §4.4 Rego's `role_permits` was a plain boolean
(allow vs. not-allow), which can't reproduce `rules_v1.yaml`'s
`require_approval` rule (`require-approval-sensitive-write`) at all — a
second, independent gap in the same code.

**Fix:** two Rego files.
- `guardrail_phase3.rego` — matches rules by role/tool/resource (with glob
  support for the `customers.*` pattern) and returns the *matched rule's
  own decision* (allow/deny/require_approval), first-match-wins by rule
  order. No `trifecta_state` anywhere. This is what Phase 3 should regress
  against Phase 2 with.
- `guardrail_phase4.rego` — adds the `trifecta_state` branches on top of
  the exact same role-based matching logic, so `"none"` still correctly
  falls through to allow/deny/require_approval instead of collapsing to a
  boolean.

**Verified:** `opa test` — 5/5 passing on Phase 3 (one case per rule, plus
default-deny), 5/5 passing on Phase 4 (tripped-overrides-allow,
partial-forces-approval, none-falls-through to both allow and
require_approval, and missing-trifecta_state fail-closed to deny).

## 3. `docker-compose.yml`'s Splunk service was missing required env vars

The current `splunk/splunk:latest` image needs `SPLUNK_PASSWORD` to
provision the admin user, and (since it now resolves to Splunk 10.x)
`SPLUNK_GENERAL_TERMS=--accept-sgt-current-at-splunk-com`. Neither was in
the original compose file — the Splunk container likely would not have
started cleanly.

**Fix:** both added, `SPLUNK_PASSWORD` pulled from `.env` (see
`.env.example`). No changes needed for the OPA volume mount — `rules_data.json`
lives inside `./policy/rego`, which was already mounted.

