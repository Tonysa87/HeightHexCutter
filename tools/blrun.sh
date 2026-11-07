#!/bin/bash
# Run a Python snippet in the open Blender with the project modules preloaded:
#   AT = nodes/build_v0.py   V1/V2/V3 = nodes/build_v1/2/3.py   BE = bench/bench.py
#   EB = bench/eevee_band_test.py   NC = bench/normal_check.py   PT = bench/projection_test.py
#   OUT = renders/ (Windows UNC path to this project's renders folder)
# usage: tools/blrun.sh 'gs, lost = V3.build_all(); result = {"lost": lost}'
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(dirname "$HERE")"
mkdir -p "$ROOT/renders" "$ROOT/tools/.req"
F=$(mktemp "$ROOT/tools/.req/req_XXXX.py")
UNC="//wsl.localhost/Ubuntu-24.04$ROOT"
{
echo 'import importlib.util, bpy'
echo 'def _load(n, p):'
echo '    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m'
echo "ROOT = \"$UNC\""
echo 'OUT = ROOT + "/renders"'
for pair in AT:nodes/build_v0 V1:nodes/build_v1 V2:nodes/build_v2 V3:nodes/build_v3 BE:bench/bench EB:bench/eevee_band_test NC:bench/normal_check PT:bench/projection_test; do
  echo "${pair%%:*} = _load(\"at_${pair%%:*}\", ROOT + \"/${pair#*:}.py\")"
done
echo "$1"
} > "$F"
"$HERE/bmcp.sh" "$F"
