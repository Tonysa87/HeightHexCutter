#!/bin/bash
# Run a Python snippet in the open Blender with the project modules preloaded:
#   HHC = height_hex_cutter (the add-on package, freshly reloaded)   BE = bench/bench.py
#   OUT = renders/ (Windows UNC path to this project's renders folder)
# usage: tools/blrun.sh 'g = HHC.groups.ensure_group(); result = {"group": g.name}'
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(dirname "$HERE")"
mkdir -p "$ROOT/renders" "$ROOT/tools/.req"
F=$(mktemp "$ROOT/tools/.req/req_XXXX.py")
UNC="//wsl.localhost/Ubuntu-24.04$ROOT"
{
echo 'import sys, importlib, bpy'
echo "ROOT = \"$UNC\""
echo 'OUT = ROOT + "/renders"'
echo 'if ROOT not in sys.path: sys.path.insert(0, ROOT)'
echo 'for _m in [m for m in sys.modules if m.startswith(("height_hex_cutter", "bench"))]: del sys.modules[_m]'
echo 'import height_hex_cutter as HHC'
echo 'from height_hex_cutter import groups, collect, build, ui'
echo 'from bench import bench as BE'
echo "$1"
} > "$F"
"$HERE/bmcp.sh" "$F"
