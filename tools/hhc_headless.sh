#!/bin/bash
# Run a Python script in a separate, headless Blender (factory settings, GPU on); prints its JSON result.
# usage: tools/hhc_headless.sh <blend file (Windows path) or -> <script.py> [timeout seconds]
# The script runs with the repo on sys.path and must set `result`. The user's open Blender is not touched.
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(dirname "$HERE")"
BLENDER="/mnt/c/Program Files/Blender Foundation/Blender 5.2/blender.exe"
UNC="$(wslpath -w "$ROOT")"
WORK="/mnt/c/Users/Tony/AppData/Local/Temp/hhc_headless"
mkdir -p "$WORK"
OUT="$WORK/result_$$.json"
SCRIPT_W="$(wslpath -w "$(realpath "$2")")"
ARGS=(-b --factory-startup)
[ "$1" != "-" ] && ARGS=(-b "$1" --factory-startup)
timeout "${3:-1800}" "$BLENDER" "${ARGS[@]}" --python "$(wslpath -w "$HERE/headless_boot.py")" -- "$UNC" "$SCRIPT_W" "$(wslpath -w "$OUT")" > "$WORK/log_$$.txt" 2>&1
code=$?
if [ -f "$OUT" ]; then cat "$OUT"; rm -f "$OUT"; else echo "{\"error\": \"no result (exit $code)\", \"log\": \"$(wslpath -w "$WORK/log_$$.txt")\"}"; tail -20 "$WORK/log_$$.txt"; fi
