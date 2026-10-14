"""단축키 충돌 분석 (bpy 비의존).

Blender KeyMapItem 을 KeyItem 으로 옮긴 뒤 순수 함수로 분석한다. 그래서 가짜
데이터로 단위 테스트가 가능하다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .mappings import RELATED_KEYMAPS, KeyEvent, KeyMapping, os_reserved_reason

# 상태 코드
BASELINE = "BASELINE"  # ensure 항목이 기준 키맵에 이미 있음 → 등록 불필요
FREE = "FREE"  # 충돌 없음 → 등록
CONFLICT = "CONFLICT"  # 충돌, 사용자 결정 대기(기본: 유지 = 등록 안 함)
REPLACED = "REPLACED"  # 충돌 항목을 끄고 MayaUX 를 등록
RESERVED = "RESERVED"  # 운영체제 예약키 → 등록 안 함
DISABLED = "DISABLED"  # 사용자가 끈 항목
UNAVAILABLE = "UNAVAILABLE"  # 대상 Operator 가 이 Blender 에 없음

STATUS_LABELS = {
    BASELINE: "기준 키맵에 있음",
    FREE: "MayaUX 적용",
    CONFLICT: "충돌 - 기존 유지",
    REPLACED: "MayaUX 로 대체",
    RESERVED: "OS 예약키",
    DISABLED: "꺼짐",
    UNAVAILABLE: "명령 없음",
}


@dataclass
class KeyItem:
    keymap: str
    idname: str
    event: KeyEvent
    props: dict = field(default_factory=dict)
    active: bool = True
    any_mod: bool = False
    source: str = "preset"  # preset | addon | user
    name: str = ""

    def describe(self) -> str:
        what = self.name or self.idname
        extra = ""
        if self.idname in ("wm.call_menu", "wm.call_menu_pie", "wm.call_panel") and "name" in self.props:
            extra = f" ({self.props['name']})"
        elif self.idname == "wm.tool_set_by_id" and "name" in self.props:
            extra = f" ({self.props['name']})"
        elif "data_path" in self.props:
            extra = f" ({self.props['data_path']})"
        src = {"preset": "키맵 프리셋", "addon": "다른 애드온", "user": "사용자 설정"}.get(self.source, self.source)
        return f"[{self.keymap}] {what}{extra} · {src}"

    def signature(self) -> str:
        return signature(self.keymap, self.idname, self.event, self.props)


def signature(keymap: str, idname: str, event: KeyEvent, props: dict) -> str:
    return json.dumps([keymap, idname, event.to_dict(), _norm(props)], sort_keys=True, ensure_ascii=False)


def _norm(props: dict) -> dict:
    out = {}
    for k, v in (props or {}).items():
        if isinstance(v, (set, frozenset, tuple, list)):
            v = sorted(v) if all(isinstance(x, str) for x in v) else list(v)
        elif isinstance(v, float):
            v = round(v, 5)
        out[k] = v
    return out


_PRESS_LIKE = {"PRESS", "CLICK"}


def values_overlap(a: str, b: str) -> bool:
    if a == b:
        return True
    # PRESS 는 CLICK 보다 먼저 발생하므로 같은 키의 PRESS/CLICK 은 서로 가로챈다.
    return a in _PRESS_LIKE and b in _PRESS_LIKE


def same_trigger(item: KeyItem, event: KeyEvent) -> bool:
    if item.event.type != event.type or not values_overlap(item.event.value, event.value):
        return False
    if item.any_mod:
        return True
    a, b = item.event, event
    return (a.ctrl, a.shift, a.alt, a.oskey) == (b.ctrl, b.shift, b.alt, b.oskey)


def props_match(item_props: dict, wanted: dict) -> bool:
    ip, wp = _norm(item_props), _norm(wanted)
    return all(ip.get(k) == v for k, v in wp.items() if k != "cycle")


def same_action(item: KeyItem, mapping: KeyMapping) -> bool:
    return item.idname == mapping.idname and props_match(item.props, mapping.properties)


@dataclass
class Analysis:
    mapping: KeyMapping
    event: KeyEvent
    status: str
    conflicts: list = field(default_factory=list)  # KeyItem
    reason: str = ""
    warning: str = ""

    @property
    def label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)


def analyze(mapping: KeyMapping, event: KeyEvent, items_by_keymap: dict, platform: str = "linux",
            enabled: bool = True) -> Analysis:
    """매핑 하나의 상태와 충돌 목록을 계산한다.

    items_by_keymap: {keymap 이름: [KeyItem, ...]} — MayaUX 자신의 항목은 제외되어 있어야 한다.
    """
    if not enabled:
        return Analysis(mapping, event, DISABLED)
    reserved = os_reserved_reason(event, platform)
    if reserved:
        return Analysis(mapping, event, RESERVED, reason=reserved)

    own = items_by_keymap.get(mapping.keymap, [])
    if mapping.mode == "ensure":
        for it in own:
            if it.active and same_trigger(it, event) and mapping.accepts_idname(it.idname):
                return Analysis(mapping, event, BASELINE, reason=it.describe())

    conflicts = []
    seen = set()
    for km in RELATED_KEYMAPS.get(mapping.keymap, [mapping.keymap]):
        for it in items_by_keymap.get(km, []):
            if not it.active or not same_trigger(it, event):
                continue
            if km == mapping.keymap and same_action(it, mapping):
                # 똑같은 동작이 이미 있음 → 충돌 아님
                return Analysis(mapping, event, BASELINE, reason=it.describe())
            sig = it.signature()
            if sig not in seen:
                seen.add(sig)
                conflicts.append(it)
    if conflicts:
        return Analysis(mapping, event, CONFLICT, conflicts=conflicts)
    return Analysis(mapping, event, FREE)

