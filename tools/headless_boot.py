"""Bootstrap for headless runs (tools/hhc_headless.sh): repo on sys.path, GPU on, run a script, dump `result`.
argv after '--': <repo UNC root> <script path> <json output path>"""
import json
import sys
import time
import traceback

import bpy

root, script, out = sys.argv[sys.argv.index("--") + 1:][:3]
if root not in sys.path:
    sys.path.insert(0, root)
info = {}
try:
    cp = bpy.context.preferences.addons["cycles"].preferences
    cp.compute_device_type = "OPTIX"
    cp.get_devices()
    for d in cp.devices:
        d.use = d.type != "CPU"
    info["gpu"] = [d.name for d in cp.devices if d.use]
except Exception as e:                                 # no GPU: Cycles falls back to CPU
    info["gpu_error"] = repr(e)
ns = {"__name__": "__hhc__", "ROOT": root}
t = time.perf_counter()
try:
    exec(compile(open(script, encoding="utf-8").read(), script, "exec"), ns)
    res = ns.get("result")
except Exception:
    res = {"error": traceback.format_exc()}
info["seconds"] = round(time.perf_counter() - t, 1)
with open(out, "w", encoding="utf-8") as f:
    json.dump({"info": info, "result": res}, f, indent=1, default=str)
