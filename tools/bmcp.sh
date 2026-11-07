#!/bin/bash
# Run a Python file inside the open Blender (Windows) through the Blender Lab MCP add-on socket.
# usage: tools/bmcp.sh <python-file>     (the code must set `result = {...}`)
# Needed because the add-on listens on Windows 127.0.0.1:9876, not reachable from WSL (NAT).
HERE="$(cd "$(dirname "$0")" && pwd)"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$HERE/bmcp.ps1")" "$(wslpath -w "$1")"
