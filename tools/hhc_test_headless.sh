#!/bin/bash
# Run the Blender test suite in a separate headless Blender, in a fresh HHC.blend (Windows temp folder).
# usage: tools/hhc_test_headless.sh [pattern]      (pattern as for tools/hhc_test.sh; "test_cost" for the slow checks)
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(dirname "$HERE")"
WORK="/mnt/c/Users/Tony/AppData/Local/Temp/hhc_headless/suite"
mkdir -p "$WORK" "$ROOT/tests/fixtures/v05"
for f in ngkit build_v1 build_v3; do
  [ -s "$ROOT/tests/fixtures/v05/$f.py" ] || git -C "$ROOT" show "v0.5:nodes/$f.py" > "$ROOT/tests/fixtures/v05/$f.py" || exit 1
done
[ -d "$ROOT/tests/fixtures/sets" ] || python3 "$ROOT/tests/fixtures/make_sets.py" > /dev/null
S=$(mktemp -d)
cat > "$S/mk.py" <<'PY'
import bpy, os
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(os.environ["TEMP"], "hhc_headless", "suite", "HHC.blend"))
result = {}
PY
cat > "$S/run.py" <<PY
from tests.blender import runner
result = runner.run(ROOT, "${1:-}")
PY
"$HERE/hhc_headless.sh" - "$S/mk.py" 120 > /dev/null
OUT="$("$HERE/hhc_headless.sh" "$(wslpath -w "$WORK/HHC.blend")" "$S/run.py" 3000)"
rm -rf "$S"
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
