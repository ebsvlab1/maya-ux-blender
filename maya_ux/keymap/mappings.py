"""Maya형 키맵 매핑 정의 (bpy 비의존).

기준선은 Blender Industry Compatible(IC) 키맵이다. 각 매핑은 두 종류다.

* ``ensure``: IC 에 이미 있는 Maya 동작. 활성 키맵에 같은 키 → 같은 명령이 있으면
  아무것도 등록하지 않고(기준선 충족), 없을 때만 보완 등록한다. 그래서 Blender 기본
  키맵 사용자도 Maya 조작을 얻을 수 있다.
* ``add``: IC 와 Maya 가 다른 부분. 충돌이 있으면 사용자 결정(유지/대체/사용자 지정)을 따른다.

키맵 이름/공간은 Blender 4.5 · 5.x IC 데이터에서 확인했다.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

KEYMAP_STATE_VERSION = 1

# 키맵 이름 → (space_type, region_type). 런타임에는 default keyconfig 값을 우선한다.
KEYMAP_SPACES = {
    "Window": ("EMPTY", "WINDOW"),
    "Screen": ("EMPTY", "WINDOW"),
    "Frames": ("EMPTY", "WINDOW"),
    "3D View Generic": ("VIEW_3D", "WINDOW"),
    "3D View": ("VIEW_3D", "WINDOW"),
    "Object Mode": ("EMPTY", "WINDOW"),
    "Object Non-modal": ("EMPTY", "WINDOW"),
    "Mesh": ("EMPTY", "WINDOW"),
    "Pose": ("EMPTY", "WINDOW"),
    "Armature": ("EMPTY", "WINDOW"),
    "Graph Editor": ("GRAPH_EDITOR", "WINDOW"),
    "Dopesheet": ("DOPESHEET_EDITOR", "WINDOW"),
}

# 해당 키맵이 활성일 때 함께 이벤트를 받는 키맵들. 같은 키가 여기 있으면 '가림(shadow)' 충돌.
_VIEW3D_STACK = ["3D View", "3D View Generic", "Object Non-modal", "Frames", "Screen", "Window"]
RELATED_KEYMAPS = {
    "Object Mode": ["Object Mode", *_VIEW3D_STACK],
    "Mesh": ["Mesh", *_VIEW3D_STACK],
    "Pose": ["Pose", *_VIEW3D_STACK],
    "Armature": ["Armature", *_VIEW3D_STACK],
    "3D View": ["3D View", "3D View Generic", "Object Mode", "Mesh", "Pose", "Armature", "Object Non-modal",
                "Frames", "Screen", "Window"],
    "3D View Generic": ["3D View Generic", "3D View", "Object Mode", "Mesh", "Pose", "Object Non-modal",
                        "Frames", "Screen", "Window"],
    "Object Non-modal": ["Object Non-modal", "Object Mode", "Mesh", "Pose", "Armature", "3D View",
                         "3D View Generic", "Frames", "Screen", "Window"],
    "Graph Editor": ["Graph Editor", "Frames", "Screen", "Window"],
    "Dopesheet": ["Dopesheet", "Frames", "Screen", "Window"],
}
# 전역 키맵(Frames/Screen/Window)은 모든 편집기 키맵보다 나중에 처리되므로 어디서든 가려질 수 있다.
for _global in ("Frames", "Screen", "Window"):
    RELATED_KEYMAPS[_global] = [_global, *[k for k in KEYMAP_SPACES if k != _global]]

CONTEXT_LABELS = {
    "Object Mode": "Object",
    "Object Non-modal": "Object/Edit 공통",
    "Mesh": "Edit(Mesh)",
    "Pose": "Pose",
    "Armature": "Edit(Armature)",
    "3D View": "3D Viewport",
    "3D View Generic": "3D Viewport",
    "Graph Editor": "Graph Editor",
    "Dopesheet": "Dope Sheet",
    "Frames": "전역(프레임)",
    "Screen": "전역",
    "Window": "전역",
}

PROFILES = {
    "maya_basic": "Maya 기본 — IC 기준 + Maya 차이 항목 전부",
    "blender_hybrid": "Blender 절충 — IC 기준 보완 + 충돌이 적은 항목만",
    "custom": "사용자 정의 — 항목을 직접 켜고 끔",
}


@dataclass(frozen=True)
class KeyEvent:
    type: str
    value: str = "PRESS"
    ctrl: bool = False
    shift: bool = False
    alt: bool = False
    oskey: bool = False

    def label(self) -> str:
        parts = [n for n, on in (("Ctrl", self.ctrl), ("Shift", self.shift), ("Alt", self.alt), ("Cmd", self.oskey)) if on]
        key = _KEY_NAMES.get(self.type, self.type.title())
        suffix = {"CLICK_DRAG": " 드래그", "DOUBLE_CLICK": " 더블클릭"}.get(self.value, "")
        return " + ".join([*parts, key]) + suffix

    def to_dict(self) -> dict:
        return {"type": self.type, "value": self.value, "ctrl": self.ctrl, "shift": self.shift,
                "alt": self.alt, "oskey": self.oskey}

    @classmethod
    def from_dict(cls, d) -> "KeyEvent":
        if not isinstance(d, dict) or not isinstance(d.get("type"), str) or not d["type"]:
            raise ValueError("키 이벤트에는 type 이 필요합니다")
        value = d.get("value", "PRESS")
        if value not in ("PRESS", "RELEASE", "CLICK", "DOUBLE_CLICK", "CLICK_DRAG"):
            raise ValueError(f"지원하지 않는 value: {value}")
        return cls(d["type"].upper(), value, bool(d.get("ctrl")), bool(d.get("shift")),
                   bool(d.get("alt")), bool(d.get("oskey")))


_KEY_NAMES = {
    "LEFTMOUSE": "LMB", "MIDDLEMOUSE": "MMB", "RIGHTMOUSE": "RMB", "SPACE": "Space",
    "ONE": "1", "TWO": "2", "THREE": "3", "FOUR": "4", "FIVE": "5", "SIX": "6", "SEVEN": "7",
    "PERIOD": ".", "COMMA": ",", "EQUAL": "=", "MINUS": "-", "INSERT": "Insert", "DEL": "Delete",
    "BACK_SPACE": "Backspace",
}


@dataclass(frozen=True)
class KeyMapping:
    id: str
    label: str
    keymap: str
    idname: str
    event: KeyEvent
    properties: dict = field(default_factory=dict, hash=False, compare=False)
    mode: str = "add"  # "ensure" | "add"
    profiles: tuple = ("maya_basic", "blender_hybrid")
    maya: str = ""  # Maya 쪽 동작 설명
    note: str = ""
    equivalents: tuple = ()  # ensure 판단 시 같은 동작으로 간주할 다른 idname
    default_enabled: bool = True
    priority: str = "P0"

    @property
    def context(self) -> str:
        return CONTEXT_LABELS.get(self.keymap, self.keymap)

    def accepts_idname(self, idname: str) -> bool:
        return idname == self.idname or idname in self.equivalents


def _m(id, label, keymap, idname, type, value="PRESS", ctrl=False, shift=False, alt=False, props=None,
       mode="add", profiles=("maya_basic", "blender_hybrid"), maya="", note="", equivalents=(), enabled=True, priority="P0"):
    return KeyMapping(id, label, keymap, idname, KeyEvent(type, value, ctrl, shift, alt), props or {}, mode,
                      tuple(profiles), maya, note, tuple(equivalents), enabled, priority)


_BOTH = ("maya_basic", "blender_hybrid")
_MAYA = ("maya_basic",)
_TOOL_EQ = ("wm.tool_set_by_id", "wm.tool_set_by_index")
_KEY_EQ = ("anim.keyframe_insert", "anim.keyframe_insert_by_name", "anim.keyframe_insert_menu")

MAPPINGS: tuple = (
    # --- P0 기준(IC 에 존재: ensure) --------------------------------------
    *[
        _m(f"tool_{key.lower()}_{km.split()[0].lower()}", f"{label} 도구", km, "wm.tool_set_by_id", key,
           props={"name": tool, "cycle": True}, mode="ensure", profiles=_BOTH, maya=f"{key}: {label}",
           equivalents=_TOOL_EQ)
        for km in ("Object Mode", "Mesh", "Pose")
        for key, label, tool in (("Q", "선택", "builtin.select_box"), ("W", "이동", "builtin.move"),
                                 ("E", "회전", "builtin.rotate"), ("R", "크기", "builtin.scale"))
    ],
    _m("nav_orbit", "궤도 회전", "3D View", "view3d.rotate", "LEFTMOUSE", alt=True, mode="ensure", maya="Alt+LMB 드래그"),
    _m("nav_pan", "패닝", "3D View", "view3d.move", "MIDDLEMOUSE", alt=True, mode="ensure", maya="Alt+MMB 드래그"),
    _m("nav_zoom", "줌", "3D View", "view3d.zoom", "RIGHTMOUSE", alt=True, mode="ensure", maya="Alt+RMB 드래그",
       note="Linux 일부 창 관리자는 Alt+드래그를 창 이동에 사용합니다"),
    _m("frame_selected", "선택 대상 프레이밍", "3D View", "view3d.view_selected", "F", mode="ensure", maya="F"),
    _m("frame_all", "전체 프레이밍", "3D View", "view3d.view_all", "A", props={"center": False}, mode="ensure", maya="A"),
    _m("duplicate_obj", "복제", "Object Mode", "object.duplicate_move", "D", ctrl=True, mode="ensure", maya="Ctrl+D",
       equivalents=("object.duplicate",), note="IC 는 복제 후 이동 모드로 들어갑니다. 우클릭/Esc 로 제자리 복제"),
    _m("duplicate_mesh", "복제(컴포넌트)", "Mesh", "mesh.duplicate_move", "D", ctrl=True, mode="ensure", maya="Ctrl+D"),
    _m("key_all_obj", "위치·회전·스케일 키", "Object Mode", "anim.keyframe_insert_by_name", "S", props={"type": "LocRotScale"},
       mode="ensure", maya="S", equivalents=_KEY_EQ),
    _m("key_all_pose", "위치·회전·스케일 키", "Pose", "anim.keyframe_insert_by_name", "S", props={"type": "LocRotScale"},
       mode="ensure", maya="S", equivalents=_KEY_EQ),
    *[
        _m(f"key_{ch.lower()}_{km.split()[0].lower()}", f"{label} 키", km, "anim.keyframe_insert_by_name", ch, shift=True,
           props={"type": kt}, mode="ensure", maya=f"Shift+{ch}", equivalents=_KEY_EQ, priority="P1")
        for km in ("Object Mode", "Pose")
        for ch, label, kt in (("W", "이동", "Location"), ("E", "회전", "Rotation"), ("R", "크기", "Scaling"))
    ],
    _m("play", "재생/정지", "Frames", "screen.animation_play", "SPACE", mode="ensure", maya="Alt+V (Maya) / Space"),
    _m("graph_frame_sel", "선택 키 프레이밍", "Graph Editor", "graph.view_selected", "F", mode="ensure", maya="F"),
    _m("graph_frame_all", "전체 키 프레이밍", "Graph Editor", "graph.view_all", "A", mode="ensure", maya="A"),
    _m("graph_key", "키 삽입", "Graph Editor", "graph.keyframe_insert", "S", mode="ensure", maya="S"),
    _m("dope_frame_sel", "선택 키 프레이밍", "Dopesheet", "action.view_selected", "F", mode="ensure", maya="F"),
    _m("dope_frame_all", "전체 키 프레이밍", "Dopesheet", "action.view_all", "A", mode="ensure", maya="A"),
    _m("repeat_last", "마지막 명령 반복", "Screen", "screen.repeat_last", "G", mode="ensure", maya="G", priority="P1"),
    _m("parent", "페어런트", "Object Mode", "object.parent_set", "P", mode="ensure", maya="P", priority="P1"),
    _m("unparent", "페어런트 해제", "Object Mode", "object.parent_clear", "P", shift=True, mode="ensure", maya="Shift+P",
       priority="P1"),
    _m("soft_select", "소프트 선택(비례 편집)", "Mesh", "wm.context_toggle", "B",
       props={"data_path": "tool_settings.use_proportional_edit"}, mode="ensure", maya="B", priority="P1"),
    _m("sel_mode_vert", "버텍스 선택 모드", "Mesh", "mesh.select_mode", "ONE", props={"type": "VERT"}, mode="ensure",
       maya="F9 / 우클릭 메뉴", priority="P1"),
    _m("sel_mode_edge", "엣지 선택 모드", "Mesh", "mesh.select_mode", "TWO", props={"type": "EDGE"}, mode="ensure",
       maya="F10", priority="P1"),
    _m("sel_mode_face", "면 선택 모드", "Mesh", "mesh.select_mode", "THREE", props={"type": "FACE"}, mode="ensure",
       maya="F11", priority="P1"),

    # --- Maya 차이 항목(add) ----------------------------------------------
    _m("shade_wire", "와이어프레임", "3D View", "wm.context_set_enum", "FOUR",
       props={"data_path": "space_data.shading.type", "value": "WIREFRAME"}, profiles=_MAYA, priority="P1", maya="4",
       note="IC 의 4(Object 모드 전환)와 충돌"),
    _m("shade_solid", "셰이디드", "3D View", "wm.context_set_enum", "FIVE",
       props={"data_path": "space_data.shading.type", "value": "SOLID"}, profiles=_MAYA, priority="P1", maya="5",
       note="IC 의 5(모드 파이 메뉴)와 충돌"),
    _m("shade_material", "텍스처(머티리얼 미리보기)", "3D View", "wm.context_set_enum", "SIX",
       props={"data_path": "space_data.shading.type", "value": "MATERIAL"}, profiles=_MAYA, priority="P1", maya="6"),
    _m("shade_rendered", "라이팅(렌더 미리보기)", "3D View", "wm.context_set_enum", "SEVEN",
       props={"data_path": "space_data.shading.type", "value": "RENDERED"}, profiles=_MAYA, priority="P1", maya="7"),
    _m("gizmo_bigger", "매니퓰레이터 크게", "3D View Generic", "wm.context_scale_int", "EQUAL",
       props={"data_path": "preferences.view.gizmo_size", "value": 1.2}, profiles=_BOTH, maya="=", priority="P1"),
    _m("gizmo_smaller", "매니퓰레이터 작게", "3D View Generic", "wm.context_scale_int", "MINUS",
       props={"data_path": "preferences.view.gizmo_size", "value": 0.8}, profiles=_BOTH, maya="-", priority="P1"),
    _m("pivot_edit", "피벗(원점) 편집 토글", "Object Mode", "wm.context_toggle", "INSERT",
       props={"data_path": "tool_settings.use_transform_data_origin"}, profiles=_BOTH, maya="Insert / D 홀드",
       note="Blender 'Affect Only Origins' 토글. D 홀드는 지원하지 않음", priority="P1"),
    _m("component_toggle", "오브젝트/컴포넌트 전환", "Object Non-modal", "object.editmode_toggle", "F8", profiles=_BOTH,
       maya="F8", priority="P1"),
    _m("f9_vert_obj", "버텍스 편집으로", "Object Mode", "object.mode_set_with_submode", "F9",
       props={"mode": "EDIT", "mesh_select_mode": ["VERT"]}, profiles=_MAYA, maya="F9", priority="P1"),
    _m("f10_edge_obj", "엣지 편집으로", "Object Mode", "object.mode_set_with_submode", "F10",
       props={"mode": "EDIT", "mesh_select_mode": ["EDGE"]}, profiles=_MAYA, maya="F10", priority="P1"),
    _m("f11_face_obj", "면 편집으로", "Object Mode", "object.mode_set_with_submode", "F11",
       props={"mode": "EDIT", "mesh_select_mode": ["FACE"]}, profiles=_MAYA, maya="F11", priority="P1",
       note="Blender 기본 키맵의 F11(렌더 창 보기)과 충돌할 수 있음"),
    _m("f9_vert_mesh", "버텍스 선택 모드", "Mesh", "mesh.select_mode", "F9", props={"type": "VERT"}, profiles=_MAYA,
       maya="F9", priority="P1"),
    _m("f10_edge_mesh", "엣지 선택 모드", "Mesh", "mesh.select_mode", "F10", props={"type": "EDGE"}, profiles=_MAYA,
       maya="F10", priority="P1"),
    _m("f11_face_mesh", "면 선택 모드", "Mesh", "mesh.select_mode", "F11", props={"type": "FACE"}, profiles=_MAYA,
       maya="F11", priority="P1"),
    _m("grow_sel", "선택 확장", "Mesh", "mesh.select_more", "PERIOD", shift=True, profiles=_BOTH, maya="Shift + . (>)",
       priority="P1"),
    _m("shrink_sel", "선택 축소", "Mesh", "mesh.select_less", "COMMA", shift=True, profiles=_BOTH, maya="Shift + , (<)",
       priority="P1"),
    _m("undo_z", "실행 취소", "Screen", "ed.undo", "Z", profiles=_MAYA, maya="Z",
       note="IC 의 Z(영역 확대)와 충돌. Ctrl+Z 는 그대로 동작", priority="P1"),
    _m("redo_shift_z", "다시 실행", "Screen", "ed.redo", "Z", shift=True, profiles=_MAYA, maya="Shift+Z", priority="P1"),
    _m("next_key", "다음 키프레임", "Frames", "screen.keyframe_jump", "PERIOD", props={"next": True}, profiles=_MAYA,
       maya=".", note="IC 3D View 의 . (피벗 파이)와 충돌", priority="P1"),
    _m("prev_key", "이전 키프레임", "Frames", "screen.keyframe_jump", "COMMA", props={"next": False}, profiles=_MAYA,
       maya=",", note="IC 3D View 의 , (좌표계 파이)와 충돌", priority="P1"),
    _m("next_frame", "다음 프레임", "Frames", "screen.frame_offset", "PERIOD", alt=True, props={"delta": 1}, profiles=_BOTH,
       maya="Alt + .", priority="P1"),
    _m("prev_frame", "이전 프레임", "Frames", "screen.frame_offset", "COMMA", alt=True, props={"delta": -1}, profiles=_BOTH,
       maya="Alt + ,", priority="P1"),
    _m("maximize_area", "패널 최대화", "Screen", "screen.screen_full_area", "SPACE", ctrl=True, profiles=_BOTH,
       maya="Ctrl+Space", note="macOS 에서는 입력 소스 전환 예약키", priority="P1"),
    _m("hotbox", "Hotbox 메뉴", "3D View", "wm.call_menu", "SPACE", ctrl=True, shift=True,
       props={"name": "MAYAUX_MT_hotbox"}, profiles=(), enabled=False, maya="Space 홀드",
       note="Space 재생과의 충돌 때문에 기본 비활성. Space 홀드 대신 별도 키 사용", priority="P2"),
)

MAPPINGS_BY_ID = {m.id: m for m in MAPPINGS}
assert len(MAPPINGS_BY_ID) == len(MAPPINGS), "duplicate mapping id"


def profile_mapping_ids(profile: str) -> list:
    if profile == "custom":
        profile = "maya_basic"
    return [m.id for m in MAPPINGS if profile in m.profiles and m.default_enabled]


# ---------------------------------------------------------------------------
# 운영체제 예약키
# ---------------------------------------------------------------------------

def os_reserved_reason(event: KeyEvent, platform: str):
    """운영체제가 가로채는 조합이면 사유 문자열을, 아니면 None 을 반환."""
    if platform == "darwin":
        if event.oskey and event.type in {"SPACE", "TAB", "Q", "H", "M", "W"}:
            return "macOS 예약키 (Cmd 조합)"
        if event.ctrl and not event.shift and not event.alt and event.type == "SPACE":
            return "macOS 입력 소스 전환 예약키 (Ctrl+Space)"
        if event.ctrl and event.type in {"LEFT_ARROW", "RIGHT_ARROW", "UP_ARROW", "DOWN_ARROW"}:
            return "macOS Mission Control 예약키"
    elif platform == "win32":
        if event.alt and event.type in {"F4", "TAB", "SPACE"} and not event.ctrl:
            return "Windows 예약키 (Alt 조합)"
        if event.oskey:
            return "Windows 키 조합은 운영체제가 사용"
    return None


def os_warning(mapping: KeyMapping, platform: str):
    if platform.startswith("linux") and mapping.event.alt and mapping.event.type.endswith("MOUSE"):
        return "Linux: 창 관리자가 Alt+드래그를 가로채면 설정에서 수정 키를 Super 로 바꾸세요"
    return None


def platform_event(event: KeyEvent, platform: str, mac_ctrl_as_cmd: bool) -> KeyEvent:
    if platform == "darwin" and mac_ctrl_as_cmd and event.ctrl:
        return KeyEvent(event.type, event.value, False, event.shift, event.alt, True)
    return event


# ---------------------------------------------------------------------------
# 키맵 상태(내보내기/가져오기 대상)
# ---------------------------------------------------------------------------

DECISIONS = ("KEEP", "REPLACE")


@dataclass
class KeymapState:
    profile: str = "maya_basic"
    enabled: bool = True
    mapping_ids: list = field(default_factory=lambda: profile_mapping_ids("maya_basic"))
    overrides: dict = field(default_factory=dict)  # mapping_id -> KeyEvent (사용자 지정 키)
    decisions: dict = field(default_factory=dict)  # mapping_id -> "KEEP" | "REPLACE"
    mac_ctrl_as_cmd: bool = False

    def set_profile(self, profile: str) -> None:
        if profile not in PROFILES:
            raise ValueError(f"알 수 없는 프로파일: {profile}")
        self.profile = profile
        if profile != "custom":
            self.mapping_ids = profile_mapping_ids(profile)

    def toggle(self, mapping_id: str, on: bool) -> None:
        if mapping_id not in MAPPINGS_BY_ID:
            return
        ids = [i for i in self.mapping_ids if i != mapping_id]
        if on:
            ids.append(mapping_id)
        self.mapping_ids = [m.id for m in MAPPINGS if m.id in ids]
        self.profile = "custom"

    def event_for(self, mapping: KeyMapping) -> KeyEvent:
        return self.overrides.get(mapping.id) or mapping.event

    def active_mappings(self) -> list:
        ids = set(self.mapping_ids)
        return [m for m in MAPPINGS if m.id in ids]

    def to_dict(self) -> dict:
        return {
            "state_version": KEYMAP_STATE_VERSION,
            "profile": self.profile,
            "enabled": self.enabled,
            "mappings": list(self.mapping_ids),
            "overrides": {k: v.to_dict() for k, v in self.overrides.items()},
            "decisions": dict(self.decisions),
            "mac_ctrl_as_cmd": self.mac_ctrl_as_cmd,
        }

    @classmethod
    def from_dict(cls, d):
        """(state, warnings) 반환. 알 수 없는 매핑 ID 는 경고 후 무시."""
        warnings = []
        if not isinstance(d, dict):
            raise ValueError("keymap 섹션은 객체여야 합니다")
        st = cls()
        profile = d.get("profile", "maya_basic")
        if profile not in PROFILES:
            warnings.append(f"알 수 없는 프로파일 '{profile}' → maya_basic 사용")
            profile = "maya_basic"
        st.profile = profile
        st.enabled = bool(d.get("enabled", True))
        ids = d.get("mappings")
        if ids is None:
            st.mapping_ids = profile_mapping_ids(profile)
        else:
            unknown = [i for i in ids if i not in MAPPINGS_BY_ID]
            if unknown:
                warnings.append("이 버전에 없는 단축키 항목 무시: " + ", ".join(map(str, unknown)))
            keep = set(ids)
            st.mapping_ids = [m.id for m in MAPPINGS if m.id in keep]
        for mid, ev in (d.get("overrides") or {}).items():
            if mid not in MAPPINGS_BY_ID:
                continue
            try:
                st.overrides[mid] = KeyEvent.from_dict(ev)
            except ValueError as e:
                warnings.append(f"{mid}: {e}")
        for mid, dec in (d.get("decisions") or {}).items():
            if mid in MAPPINGS_BY_ID and dec in DECISIONS:
                st.decisions[mid] = dec
        st.mac_ctrl_as_cmd = bool(d.get("mac_ctrl_as_cmd", False))
        return st, warnings

    def copy(self) -> "KeymapState":
        st, _ = KeymapState.from_dict(copy.deepcopy(self.to_dict()))
        return st
