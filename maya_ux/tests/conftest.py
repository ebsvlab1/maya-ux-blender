"""테스트 공용 설정.

순수 모듈(model, mappings, conflicts, json_io, migration)은 bpy 없이 테스트한다.
패키지 루트 __init__.py 는 bpy 를 import 하므로, bpy 가 없을 때는 루트 실행 없이
하위 모듈만 불러오도록 빈 패키지 객체를 미리 등록한다.
"""

import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)
HAS_BPY = importlib.util.find_spec("bpy") is not None

if REPO not in sys.path:
    sys.path.insert(0, REPO)

if not HAS_BPY and "maya_ux" not in sys.modules:
    pkg = types.ModuleType("maya_ux")
    pkg.__path__ = [ROOT]
    sys.modules["maya_ux"] = pkg
