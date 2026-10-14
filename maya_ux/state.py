"""런타임 상태와 저장 위치.

설정은 .blend 가 아닌 사용자 설정 폴더의 JSON 에 저장한다 (프로젝트 파일 비수정 원칙).

* shelf.json   — Shelf 탭/버튼
* keymap.json  — 키맵 프로파일/항목/충돌 결정
* local.json   — 이 기기 전용: 스크립트 신뢰 목록, 끈 키맵 항목 기록, 마법사 완료 여부
"""

from __future__ import annotations

import os
import platform
import sys
from datetime import datetime, timezone

import bpy

from .integrations import scripts
from .keymap import registry as keymap_registry
from .keymap.mappings import KeymapState
from .shelf.model import Shelf, ValidationError, default_shelf
from .storage import json_io

ADDON_VERSION = "1.0.0"


class _State:
    def __init__(self):
        self.shelf: Shelf = default_shelf()
        self.keymap: KeymapState = KeymapState()
        self.deactivated: list = []
        self.wizard_done: bool = False
        self.messages: list = []  # 진단 패널에 보여줄 로드 경고
        self.folder: str = ""


S = _State()


def package_name() -> str:
    return __package__ or "maya_ux"


def config_folder() -> str:
    pkg = package_name()
    if pkg.startswith("bl_ext."):
        try:
            return bpy.utils.extension_path_user(pkg, path="", create=True)
        except (ValueError, AttributeError):
            pass
    return bpy.utils.user_resource("CONFIG", path="maya_ux", create=True)


def _path(name: str) -> str:
    return os.path.join(S.folder, name)


def load() -> None:
    S.folder = config_folder()
    S.messages.clear()

    raw, msg = json_io.load_json(_path("shelf.json"), None)
    if msg:
        S.messages.append(msg)
    S.shelf = default_shelf()
    if raw is not None:
        try:
            from .storage.migration import migrate

            data, _ = migrate(raw)
            S.shelf, errors = Shelf.from_dict(data)
            S.messages.extend(errors)
        except ValidationError as e:
            S.messages.append(f"shelf.json: {e} — 기본 Shelf 사용")

    raw, msg = json_io.load_json(_path("keymap.json"), None)
    if msg:
        S.messages.append(msg)
    S.keymap = KeymapState()
    if raw is not None:
        try:
            S.keymap, warnings = KeymapState.from_dict(raw)
            S.messages.extend(warnings)
        except ValueError as e:
            S.messages.append(f"keymap.json: {e}")

    raw, msg = json_io.load_json(_path("local.json"), {})
    if msg:
        S.messages.append(msg)
    raw = raw if isinstance(raw, dict) else {}
    scripts.load_trust(raw.get("trusted_scripts"))
    S.deactivated = [r for r in raw.get("deactivated", []) if isinstance(r, dict)]
    S.wizard_done = bool(raw.get("wizard_done", False))


def save_shelf() -> None:
    json_io.write_atomic(_path("shelf.json"), json_io.dumps(S.shelf.to_dict()))
    _redraw()


def save_keymap() -> None:
    json_io.write_atomic(_path("keymap.json"), json_io.dumps(S.keymap.to_dict()))


def save_local() -> None:
    data = {"trusted_scripts": scripts.trust_data(), "deactivated": S.deactivated, "wizard_done": S.wizard_done}
    json_io.write_atomic(_path("local.json"), json_io.dumps(data))


def apply_keymap() -> None:
    S.deactivated = keymap_registry.apply(S.keymap, S.deactivated)
    save_local()
    _redraw()


def remove_keymap() -> None:
    S.deactivated = keymap_registry.remove_all(S.deactivated)
    if S.folder:
        save_local()


def meta() -> dict:
    from .integrations.addon_discovery import enabled_addons

    return {
        "blender_version": bpy.app.version_string,
        "os": f"{platform.system()} {platform.release()}",
        "platform": sys.platform,
        "addon_version": ADDON_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "enabled_addons": enabled_addons(),
    }


def _redraw() -> None:
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None:
        return
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type in {"VIEW_3D", "PREFERENCES"}:
                area.tag_redraw()
