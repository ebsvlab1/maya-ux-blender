"""Shelf 런타임 레지스트리: 아이콘/검색 목록 캐시.

Blender 동적 EnumProperty 의 items 콜백은 반환한 문자열을 파이썬이 계속 참조하고
있어야 안전하다. 그래서 목록을 모듈 수준에 보관한다.
"""

from __future__ import annotations

import bpy

from ..integrations import addon_discovery as AD

_keep: dict = {}


def icon_names() -> list:
    if "icons" not in _keep:
        enum = bpy.types.UILayout.bl_rna.functions["prop"].parameters["icon"].enum_items
        _keep["icons"] = [i.identifier for i in enum]
    return _keep["icons"]


def valid_icon(name: str) -> bool:
    return name in icon_names()


def icon_or_default(name: str) -> str:
    return name if name and valid_icon(name) else "QUESTION"


def operator_enum_items(_self=None, _context=None):
    if "op_items" not in _keep:
        items = []
        for i, (idname, label, desc, owner) in enumerate(AD.list_operators()):
            src = f" · {AD.addon_short_name(owner)}" if owner else ""
            items.append((idname, f"{label} ({idname}){src}", desc or idname, i))
        _keep["op_items"] = items
    return _keep["op_items"]


def menu_enum_items(_self=None, _context=None):
    if "menu_items" not in _keep:
        _keep["menu_items"] = [(mid, f"{label} ({mid})", mid, i) for i, (mid, label) in enumerate(AD.list_menus())]
    return _keep["menu_items"]


def icon_enum_items(_self=None, _context=None):
    if "icon_items" not in _keep:
        _keep["icon_items"] = [(name, name, "", name, i) for i, name in enumerate(icon_names()) if name != "NONE"]
    return _keep["icon_items"]


def tab_enum_items(_self, _context):
    from ..state import S

    _keep["tab_items"] = [(t.id, t.title, "") for t in S.shelf.tabs] or [("", "(탭 없음)", "")]
    return _keep["tab_items"]


def refresh() -> None:
    """확장을 켜고 끈 뒤 검색 목록 갱신."""
    for key in ("op_items", "menu_items"):
        _keep.pop(key, None)
    AD.clear_cache()
