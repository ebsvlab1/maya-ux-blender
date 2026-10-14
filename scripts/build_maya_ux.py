"""MayaUX 확장 설치용 zip 만들기 (Blender 없이).

    python scripts/build_maya_ux.py            # dist/maya_ux-<version>.zip, dist/mayaux_sample_addon-<version>.zip

Blender 가 있다면 공식 빌드 명령도 쓸 수 있다:
    blender --command extension build --source-dir maya_ux --output-dir dist
"""

import os
import re
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCLUDE_DIRS = {"__pycache__", "tests", "docs", ".pytest_cache"}


def build(src: str, out_dir: str) -> str:
    with open(os.path.join(src, "blender_manifest.toml"), encoding="utf-8") as f:
        manifest = f.read()
    ext_id = re.search(r'^id\s*=\s*"([^"]+)"', manifest, re.M).group(1)
    version = re.search(r'^version\s*=\s*"([^"]+)"', manifest, re.M).group(1)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{ext_id}-{version}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(src):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
            for name in sorted(files):
                if name.endswith((".pyc", ".zip")):
                    continue
                path = os.path.join(root, name)
                zf.write(path, os.path.relpath(path, src))
    return out


if __name__ == "__main__":
    dist = os.path.join(REPO, "dist")
    for folder in ("maya_ux", os.path.join("maya_ux_samples", "mayaux_sample_addon")):
        print(build(os.path.join(REPO, folder), dist))
