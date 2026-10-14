"""설정 JSON 스키마 마이그레이션 (bpy 비의존).

각 단계는 dict 를 받아 다음 버전 dict 를 돌려준다. 새 스키마가 생기면
_MIGRATIONS 에 (from_version -> 함수) 를 추가한다.
"""

from __future__ import annotations

import copy

from ..shelf.model import SCHEMA_VERSION, ValidationError


def _v0_to_v1(data: dict) -> dict:
    """v0 (사전 공개 포맷): {"shelves": [{"name", "items": [{"label", "command", "args"}]}]}"""
    tabs = []
    for i, shelf in enumerate(data.get("shelves") or []):
        name = str(shelf.get("name") or f"Tab{i + 1}")
        buttons = []
        for j, item in enumerate(shelf.get("items") or []):
            command = str(item.get("command") or "")
            buttons.append({
                "id": str(item.get("id") or f"item_{j + 1}"),
                "title": str(item.get("label") or command),
                "icon": str(item.get("icon") or "NONE"),
                "kind": "operator",
                "target": command,
                "properties": item.get("args") or {},
                "context_policy": "INVOKE_DEFAULT",
            })
        tabs.append({"id": f"tab_{i + 1}", "title": name, "buttons": buttons})
    out = {k: v for k, v in data.items() if k != "shelves"}
    out["schema_version"] = 1
    out["tabs"] = tabs
    return out


_MIGRATIONS = {0: _v0_to_v1}


def detect_version(data: dict) -> int:
    if "schema_version" in data:
        v = data["schema_version"]
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise ValidationError(f"schema_version 값이 잘못되었습니다: {v!r}")
        return v
    if "shelves" in data:
        return 0
    raise ValidationError("schema_version 이 없습니다. MayaUX 설정 파일이 아닌 것 같습니다")


def migrate(data: dict):
    """(migrated_data, applied_steps) 반환. 원본은 변경하지 않는다."""
    if not isinstance(data, dict):
        raise ValidationError("설정 파일 최상위는 JSON 객체여야 합니다")
    data = copy.deepcopy(data)
    version = detect_version(data)
    if version > SCHEMA_VERSION:
        raise ValidationError(
            f"이 파일은 더 새로운 MayaUX(schema {version})에서 만들어졌습니다. 확장을 업데이트하세요 (지원: {SCHEMA_VERSION})")
    applied = []
    while version < SCHEMA_VERSION:
        step = _MIGRATIONS.get(version)
        if step is None:
            raise ValidationError(f"schema {version} 에서 마이그레이션할 수 없습니다")
        data = step(data)
        applied.append(f"v{version} → v{version + 1}")
        version += 1
    return data, applied
