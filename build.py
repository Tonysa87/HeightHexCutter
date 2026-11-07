"""Build the installable extension zip:  python3 build.py  ->  dist/height_hex_cutter-<version>.zip

Equivalent to `blender --command extension build` run inside height_hex_cutter/.
"""
import os
import re
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "height_hex_cutter")


def main():
    manifest = open(os.path.join(SRC, "blender_manifest.toml"), encoding="utf-8").read()
    version = re.search(r'^version\s*=\s*"([^"]+)"', manifest, re.M).group(1)
    os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
    out = os.path.join(HERE, "dist", f"height_hex_cutter-{version}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(SRC):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for f in sorted(files):
                if f.endswith((".py", ".toml")):
                    p = os.path.join(root, f)
                    z.write(p, os.path.relpath(p, SRC))
    print(out)


if __name__ == "__main__":
    main()
