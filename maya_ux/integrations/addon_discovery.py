"""설치된 Operator / 메뉴 탐색과 소유 확장 판별."""

from __future__ import annotations

import bpy

_BLENDER_MODULE_PREFIXES = ("bl_operators.", "bl_ui.", "bpy.", "bl_keymap_utils.", "_bpy")
_cache: dict = {}


def split_idname(idname: str):
    mod, _, name = idname.partition(".")
    return mod, name


def operator_exists(idname: str) -> bool:
    mod, name = split_idname(idname)
    if not mod or not name:
        return False
    try:
        getattr(getattr(bpy.ops, mod), name).get_rna_type()
        return True
    except (KeyError, AttributeError):
        return False


def get_operator(idname: str):
    mod, name = split_idname(idname)
    return getattr(getattr(bpy.ops, mod), name)


def operator_label(idname: str) -> str:
    try:
        return get_operator(idname).get_rna_type().name or idname
    except (KeyError, AttributeError):
        return idname


def operator_class_name(idname: str) -> str:
    mod, name = split_idname(idname)
    return f"{mod.upper()}_OT_{name}"


def _addon_for_module(module: str) -> str:
    for addon in bpy.context.preferences.addons.keys():
        if module == addon or module.startswith(addon + "."):
            return addon
    return ""


def operator_owner(idname: str) -> str:
    """Operator 를 등록한 확장 이름. Blender 내장이면 "" 반환."""
    cls = bpy.types.Operator.bl_rna_get_subclass_py(operator_class_name(idname))
    if cls is None:
        return ""  # C 로 구현된 내장 Operator
    module = getattr(cls, "__module__", "") or ""
    addon = _addon_for_module(module)
    if addon:
        return addon
    if module.startswith(_BLENDER_MODULE_PREFIXES) or module in ("bl_operators", "bl_ui", "bpy"):
        return ""
    return module.split(".")[0]


def addon_short_name(addon: str) -> str:
    """bl_ext.user_default.looptools → looptools"""
    return addon.rsplit(".", 1)[-1] if addon.startswith("bl_ext.") else addon


def addon_enabled(name: str) -> bool:
    if not name:
        return True
    for key in bpy.context.preferences.addons.keys():
        if key == name or addon_short_name(key) == name:
            return True
    return False


def list_operators(refresh: bool = False) -> list:
    """[(idname, label, description, owner)] — 검색 UI 용. 결과를 캐시한다."""
    if "ops" in _cache and not refresh:
        return _cache["ops"]
    out = []
    for mod in dir(bpy.ops):
        if mod.startswith("_"):
            continue
        sub = getattr(bpy.ops, mod)
        for name in dir(sub):
            if name.startswith("_"):
                continue
            idname = f"{mod}.{name}"
            try:
                rna = getattr(sub, name).get_rna_type()
            except (KeyError, AttributeError):
                continue
            owner = ""
            try:
                owner = operator_owner(idname)
            except Exception:  # noqa: BLE001 - 서드파티 클래스의 비정상 상태 방어
                pass
            out.append((idname, rna.name or name, (rna.description or "").split("\n")[0], owner))
    out.sort()
    _cache["ops"] = out
    return out


def menu_exists(menu_id: str) -> bool:
    cls = getattr(bpy.types, menu_id, None)
    return isinstance(cls, type) and issubclass(cls, bpy.types.Menu)


def list_menus(refresh: bool = False) -> list:
    """[(bl_idname, label)]"""
    if "menus" in _cache and not refresh:
        return _cache["menus"]
    out, stack, seen = [], list(bpy.types.Menu.__subclasses__()), set()
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.add(cls)
        stack.extend(cls.__subclasses__())
        idname = getattr(cls, "bl_idname", "") or cls.__name__
        if "_MT_" in idname:
            out.append((idname, getattr(cls, "bl_label", idname)))
    out.sort()
    _cache["menus"] = out
    return out


def enabled_addons() -> list:
    return sorted(addon_short_name(k) for k in bpy.context.preferences.addons.keys())


def clear_cache() -> None:
    _cache.clear()
