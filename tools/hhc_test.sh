#!/bin/bash
# Run the Blender test suite (tests/blender/test_*.py) inside the open Blender, through bmcp.sh.
# usage: tools/hhc_test.sh [pattern]     pattern matches module or test function names (default: all)
# The runner refuses to run unless the open file is HHC.blend.
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(dirname "$HERE")"
mkdir -p "$ROOT/tools/.req" "$ROOT/tests/fixtures/v05"
# the cost test compares against the v0.5 node: extract its builders from the git tag (git-ignored copy)
for f in ngkit build_v1 build_v3; do
  [ -f "$ROOT/tests/fixtures/v05/$f.py" ] || git -C "$ROOT" show "v0.5:nodes/$f.py" > "$ROOT/tests/fixtures/v05/$f.py"
done
[ -d "$ROOT/tests/fixtures/sets" ] || python3 "$ROOT/tests/fixtures/make_sets.py" > /dev/null
F=$(mktemp "$ROOT/tools/.req/test_XXXX.py")
UNC="//wsl.localhost/Ubuntu-24.04$ROOT"
cat > "$F" <<PY
import sys
ROOT = "$UNC"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
for _m in [m for m in sys.modules if m == "height_hex_cutter" or m.startswith("height_hex_cutter.")
           or m == "tests" or m.startswith("tests.")]:
    del sys.modules[_m]
from tests.blender import runner
result = runner.run(ROOT, "${1:-}")
PY
OUT="$("$HERE/bmcp.sh" "$F")"
rm -f "$F"
# print a summary + failures; exit 1 unless everything passed
printf '%s' "$OUT" | python3 -c '
import json, sys
d = json.load(sys.stdin)
r = d.get("result", d)
if not isinstance(r, dict) or "summary" not in r:
    print(json.dumps(d, indent=1)[:4000]); sys.exit(1)
for k, v in r.get("info", {}).items():
    print("INFO", k, json.dumps(v))
for name, tb in r["failed"]:
    print("FAIL", name); print(tb)
print(r["summary"]); sys.exit(1 if r["failed"] else 0)
'

