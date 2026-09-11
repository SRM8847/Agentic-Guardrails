#!/usr/bin/env python3
"""
Fix for the 'data.rules is never loaded into OPA' gap.

policy/rules_v1.yaml is the single source of truth for the rule table
(used directly by the Phase 2 Python engine). OPA can't read YAML in
ad-hoc `opa run <dir>` mode, and the compose file only mounts
./policy/rego into the opa container -- so without this step, OPA's
`data.rules` is simply undefined and `role_permits` never matches.

This script writes policy/rego/rules_data.json, which DOES live inside
the mounted directory. In ad-hoc load mode (no --bundle flag), OPA merges
a loaded JSON file's top-level keys directly into the root `data`
document, so a file containing {"rules": [...]} becomes `data.rules`.

Run this any time rules_v1.yaml changes, before `docker compose up`
(or wire it into a Makefile / pre-start hook so it never goes stale):

    python3 scripts/generate_opa_data.py
"""
import json
import pathlib
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml --break-system-packages")

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "policy" / "rules_v1.yaml"
DST = ROOT / "policy" / "rego" / "rules_data.json"

def main():
    with open(SRC) as f:
        rules_doc = yaml.safe_load(f)

    if "rules" not in rules_doc:
        sys.exit(f"{SRC} has no top-level 'rules' key")

    DST.parent.mkdir(parents=True, exist_ok=True)
    with open(DST, "w") as f:
        json.dump(rules_doc, f, indent=2)

    print(f"Wrote {DST} ({len(rules_doc['rules'])} rules) from {SRC}")

if __name__ == "__main__":
    main()

