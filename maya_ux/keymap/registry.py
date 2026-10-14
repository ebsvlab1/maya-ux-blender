"""MayaUX 키맵 등록/해제.

모든 KeyMapItem 은 애드온 키맵(keyconfigs.addon)에만 추가하고 직접 추적한다.
충돌 분석은 MayaUX 항목을 뺀 상태의 사용자(병합) 키맵을 기준으로 한다.
"""

from __future__ import annotations

import sys

import bpy

from ..integrations.addon_discovery import operator_exists
from . import conflicts as C
from . import restore
from .mappings import KEYMAP_SPACES, MAPPINGS, KeymapState, os_warning, platform_event

_registered: list = []  # (KeyMap, KeyMapItem, mapping_id)
analyses: dict = {}  # mapping_id -> Analysis
last_error: str = ""


def _keyconfigs():
    wm = getattr(bpy.context, "window_manager", None)
    return wm.keyconfigs if wm else None


def available() -> bool:
    kcs = _keyconfigs()
    return bool(kcs and kcs.addon and kcs.user)


def active_keyconfig_name() -> str:
    kcs = _keyconfigs()
    return kcs.active.name if kcs and kcs.active else ""


def is_industry_compatible() -> bool:
    return active_keyconfig_name().replace(" ", "_").lower() == "industry_compatible"


def registered_items() -> list:
    out = []
    for km, kmi, _mid in _registered:
        try:
            out.append(restore.kmi_to_item(km.name, kmi, "maya_ux"))
        except ReferenceError:
            pass
    return out


def unregister_items() -> None:
    for km, kmi, _mid in _registered:
        try:
            km.keymap_items.remove(kmi)
        except (ReferenceError, RuntimeError):
            pass
    _registered.clear()


def _addon_signatures(kcs) -> set:
    sigs = set()
    for km in kcs.addon.keymaps:
        for kmi in km.keymap_items:
            sigs.add(restore.kmi_signature(km.name, kmi))
    return sigs


def collect_items(kcs) -> dict:
    """사용자(병합) 키맵의 항목을 KeyItem 으로 수집. 출처(프리셋/애드온/사용자)를 표시한다."""
    names = set(KEYMAP_SPACES)
    addon_sigs = _addon_signatures(kcs)
    out = {}
    for name in names:
        km = kcs.user.keymaps.get(name) or (kcs.active.keymaps.get(name) if kcs.active else None)
        if km is None:
            continue
        items = []
        for kmi in km.keymap_items:
            if kmi.map_type not in {"KEYBOARD", "MOUSE"}:
                continue
            it = restore.kmi_to_item(name, kmi)
            if it.signature() in addon_sigs:
                it.source = "addon"
            elif getattr(kmi, "is_user_defined", False) or getattr(kmi, "is_user_modified", False):
                it.source = "user"
            items.append(it)
        out[name] = items
    return out


def _space_of(kcs, name: str):
    km = kcs.default.keymaps.get(name) if kcs.default else None
    if km is not None:
        return km.space_type, km.region_type
    return KEYMAP_SPACES.get(name, ("EMPTY", "WINDOW"))


def _set_props(kmi, props: dict) -> None:
    for key, value in props.items():
        try:
            rna = kmi.properties.bl_rna.properties[key]
            if rna.type == "ENUM" and getattr(rna, "is_enum_flag", False) and isinstance(value, list):
                value = set(value)
            setattr(kmi.properties, key, value)
        except (KeyError, AttributeError, TypeError, ValueError) as e:
            print(f"[MayaUX] {kmi.idname}.{key} 설정 실패: {e}")


def _register(kcs, mapping, event) -> None:
    space, region = _space_of(kcs, mapping.keymap)
    km = kcs.addon.keymaps.new(name=mapping.keymap, space_type=space, region_type=region)
    kmi = km.keymap_items.new(mapping.idname, event.type, event.value, ctrl=event.ctrl, shift=event.shift,
                              alt=event.alt, oskey=event.oskey)
    _set_props(kmi, mapping.properties)
    _registered.append((km, kmi, mapping.id))


def apply(state: KeymapState, deactivated: list, platform: str = sys.platform) -> list:
    """현재 상태로 키맵을 다시 구성한다. 새 비활성화 기록 목록을 반환."""
    global last_error
    last_error = ""
    analyses.clear()
    kcs = _keyconfigs()
    if not available():
        last_error = "키맵을 사용할 수 없는 환경입니다 (백그라운드 모드 등)"
        return deactivated

    unregister_items()
    left = restore.restore(kcs.user, deactivated)
    kcs.update()
    items = collect_items(kcs)

    records = list(left)
    to_register = []
    for mapping in MAPPINGS:
        enabled = state.enabled and mapping.id in state.mapping_ids
        event = platform_event(state.event_for(mapping), platform, state.mac_ctrl_as_cmd)
        if enabled and not operator_exists(mapping.idname):
            analyses[mapping.id] = C.Analysis(mapping, event, C.UNAVAILABLE, reason=f"{mapping.idname} 없음")
            continue
        a = C.analyze(mapping, event, items, platform, enabled)
        if a.status == C.CONFLICT and state.decisions.get(mapping.id) == "REPLACE":
            recs, failed = restore.deactivate(kcs.user, a.conflicts)
            records.extend(recs)
            if failed:
                a.reason = "일부 항목을 끌 수 없음: " + "; ".join(failed)
            a.status = C.REPLACED
        if a.status in (C.FREE, C.REPLACED):
            to_register.append((mapping, event))
        a.warning = os_warning(mapping, platform) or ""
        analyses[mapping.id] = a

    for mapping, event in to_register:
        try:
            _register(kcs, mapping, event)
        except (RuntimeError, TypeError) as e:
            analyses[mapping.id].status = C.UNAVAILABLE
            analyses[mapping.id].reason = str(e)
    kcs.update()
    return records


def remove_all(deactivated: list) -> list:
    """MayaUX 항목 제거 + 끈 항목 복원. 복원하지 못한 기록을 반환."""
    unregister_items()
    analyses.clear()
    kcs = _keyconfigs()
    if not kcs or not kcs.user:
        return deactivated
    left = restore.restore(kcs.user, deactivated)
    try:
        kcs.update()
    except RuntimeError:
        pass
    return left


def find_shortcut(idname: str, props: dict) -> str:
    """해당 명령에 연결된 단축키 문자열(있다면)."""
    kcs = _keyconfigs()
    if not kcs or not kcs.user:
        return ""
    preferred = ("3D View", "Object Mode", "Mesh", "Pose", "Frames", "Screen", "Window", "3D View Generic")
    found = []
    for km in kcs.user.keymaps:
        for kmi in km.keymap_items:
            if kmi.idname != idname or not kmi.active or kmi.map_type not in {"KEYBOARD", "MOUSE"}:
                continue
            if C.props_match(restore.kmi_props(kmi), props or {}):
                found.append((0 if km.name in preferred else 1, f"{kmi.to_string()} ({km.name})"))
    found.sort()
    return ", ".join(s for _, s in found[:2])
