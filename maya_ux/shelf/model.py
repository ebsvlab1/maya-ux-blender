"""Shelf 데이터 모델 (bpy 비의존).

Shelf → Tab → Button 구조와 검증 규칙을 정의한다. Blender 없이 단위 테스트가
가능하도록 순수 파이썬으로만 작성한다.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

SCHEMA_VERSION = 1

KINDS = ("operator", "menu", "preset", "script")
CONTEXT_POLICIES = ("INVOKE_DEFAULT", "EXEC_DEFAULT")
# 버튼 실행 시 대상 편집기. ANY 는 현재 영역을 그대로 사용한다.
AREAS = ("VIEW_3D", "GRAPH_EDITOR", "DOPESHEET_EDITOR", "NLA_EDITOR", "ANY")
# bpy.context.mode 값 중 버튼 요구 조건으로 허용하는 것.
MODES = (
    "OBJECT",
    "EDIT_MESH",
    "EDIT_CURVE",
    "EDIT_ARMATURE",
    "POSE",
    "SCULPT",
    "PAINT_WEIGHT",
    "PAINT_VERTEX",
    "PAINT_TEXTURE",
)

_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_OPERATOR_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
_MENU_RE = re.compile(r"^[A-Z0-9_]+_MT_[A-Za-z0-9_]+$")
_SCALAR = (str, int, float, bool)


class ValidationError(ValueError):
    """사용자에게 보여줄 수 있는 검증 오류."""


def _check_props(props, where: str) -> dict:
    if props is None:
        return {}
    if not isinstance(props, dict):
        raise ValidationError(f"{where}: properties 는 객체여야 합니다")
    for key, value in props.items():
        if not isinstance(key, str) or not key.isidentifier():
            raise ValidationError(f"{where}: 잘못된 프로퍼티 이름 '{key}'")
        if isinstance(value, list):
            if not all(isinstance(v, _SCALAR) for v in value):
                raise ValidationError(f"{where}: '{key}' 값은 스칼라 목록이어야 합니다")
        elif not isinstance(value, _SCALAR):
            raise ValidationError(f"{where}: '{key}' 값 형식이 지원되지 않습니다")
    return dict(props)


def validate_target(kind: str, target: str, where: str = "button") -> None:
    if kind == "operator" and not _OPERATOR_RE.match(target or ""):
        raise ValidationError(f"{where}: Operator ID 형식이 아닙니다 (예: mesh.primitive_cube_add): '{target}'")
    if kind == "menu" and not _MENU_RE.match(target or ""):
        raise ValidationError(f"{where}: 메뉴 ID 형식이 아닙니다 (예: VIEW3D_MT_object): '{target}'")
    if kind == "script" and not (target or "").lower().endswith(".py"):
        raise ValidationError(f"{where}: 스크립트는 .py 파일 경로여야 합니다")


@dataclass
class Step:
    """프리셋 명령의 한 단계. 안전성을 위해 operator / menu 만 허용한다."""

    kind: str
    target: str
    properties: dict = field(default_factory=dict)
    context_policy: str = "EXEC_DEFAULT"

    @classmethod
    def from_dict(cls, data, where="step") -> "Step":
        if not isinstance(data, dict):
            raise ValidationError(f"{where}: 객체여야 합니다")
        kind = data.get("kind", "operator")
        if kind not in ("operator", "menu"):
            raise ValidationError(f"{where}: 프리셋 단계는 operator/menu 만 가능합니다 (받은 값: {kind})")
        target = str(data.get("target", ""))
        validate_target(kind, target, where)
        policy = data.get("context_policy", "EXEC_DEFAULT")
        if policy not in CONTEXT_POLICIES:
            raise ValidationError(f"{where}: context_policy 값이 잘못되었습니다: {policy}")
        return cls(kind, target, _check_props(data.get("properties"), where), policy)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "target": self.target,
            "properties": copy.deepcopy(self.properties),
            "context_policy": self.context_policy,
        }


@dataclass
class Button:
    id: str
    title: str
    kind: str = "operator"
    target: str = ""
    icon: str = "NONE"
    properties: dict = field(default_factory=dict)
    context_policy: str = "INVOKE_DEFAULT"
    tooltip: str = ""
    enabled: bool = True
    requires_mode: list = field(default_factory=list)
    area: str = "VIEW_3D"
    addon: str = ""  # 이 명령을 제공하는 확장(있다면). 누락 시 안내용.
    steps: list = field(default_factory=list)  # kind == "preset"

    @classmethod
    def from_dict(cls, data, where="button") -> "Button":
        if not isinstance(data, dict):
            raise ValidationError(f"{where}: 객체여야 합니다")
        bid = str(data.get("id", ""))
        if not _ID_RE.match(bid):
            raise ValidationError(f"{where}: id 는 영문/숫자/_/- 1~64자여야 합니다: '{bid}'")
        where = f"{where}[{bid}]"
        kind = data.get("kind", "operator")
        if kind not in KINDS:
            raise ValidationError(f"{where}: 알 수 없는 kind '{kind}'")
        target = str(data.get("target", ""))
        steps = []
        if kind == "preset":
            raw_steps = data.get("steps")
            if not isinstance(raw_steps, list) or not raw_steps:
                raise ValidationError(f"{where}: preset 은 steps 목록이 필요합니다")
            steps = [Step.from_dict(s, f"{where}.steps[{i}]") for i, s in enumerate(raw_steps)]
        else:
            validate_target(kind, target, where)
        policy = data.get("context_policy", "INVOKE_DEFAULT")
        if policy not in CONTEXT_POLICIES:
            raise ValidationError(f"{where}: context_policy 값이 잘못되었습니다: {policy}")
        modes = data.get("requires_mode") or []
        if not isinstance(modes, list) or any(m not in MODES for m in modes):
            raise ValidationError(f"{where}: requires_mode 는 {', '.join(MODES)} 중에서 골라야 합니다")
        area = data.get("area", "VIEW_3D")
        if area not in AREAS:
            raise ValidationError(f"{where}: area 값이 잘못되었습니다: {area}")
        title = str(data.get("title") or bid)[:64]
        return cls(
            id=bid,
            title=title,
            kind=kind,
            target=target,
            icon=str(data.get("icon") or "NONE"),
            properties=_check_props(data.get("properties"), where),
            context_policy=policy,
            tooltip=str(data.get("tooltip") or ""),
            enabled=bool(data.get("enabled", True)),
            requires_mode=list(modes),
            area=area,
            addon=str(data.get("addon") or ""),
            steps=steps,
        )

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "title": self.title,
            "icon": self.icon,
            "kind": self.kind,
            "target": self.target,
            "properties": copy.deepcopy(self.properties),
            "context_policy": self.context_policy,
            "tooltip": self.tooltip,
            "enabled": self.enabled,
        }
        if self.requires_mode:
            d["requires_mode"] = list(self.requires_mode)
        if self.area != "VIEW_3D":
            d["area"] = self.area
        if self.addon:
            d["addon"] = self.addon
        if self.kind == "preset":
            d["steps"] = [s.to_dict() for s in self.steps]
        return d


@dataclass
class Tab:
    id: str
    title: str
    buttons: list = field(default_factory=list)

    def find(self, button_id: str):
        for b in self.buttons:
            if b.id == button_id:
                return b
        return None

    def unique_button_id(self, base: str) -> str:
        base = re.sub(r"[^A-Za-z0-9_\-]", "_", base)[:56] or "button"
        taken = {b.id for b in self.buttons}
        if base not in taken:
            return base
        n = 2
        while f"{base}_{n}" in taken:
            n += 1
        return f"{base}_{n}"


@dataclass
class Shelf:
    tabs: list = field(default_factory=list)
    profile: str = "maya_basic"

    # ---- 조회 -------------------------------------------------------------
    def tab(self, tab_id: str):
        for t in self.tabs:
            if t.id == tab_id:
                return t
        return None

    def button(self, tab_id: str, button_id: str):
        t = self.tab(tab_id)
        return t.find(button_id) if t else None

    def all_buttons(self):
        for t in self.tabs:
            for b in t.buttons:
                yield t, b

    # ---- 편집 -------------------------------------------------------------
    def unique_tab_id(self, base: str) -> str:
        base = re.sub(r"[^A-Za-z0-9_\-]", "_", base.lower())[:56] or "tab"
        taken = {t.id for t in self.tabs}
        if base not in taken:
            return base
        n = 2
        while f"{base}_{n}" in taken:
            n += 1
        return f"{base}_{n}"

    def add_tab(self, title: str) -> Tab:
        tab = Tab(self.unique_tab_id(title), title[:64] or "Tab")
        self.tabs.append(tab)
        return tab

    def remove_tab(self, tab_id: str) -> bool:
        t = self.tab(tab_id)
        if t is None:
            return False
        self.tabs.remove(t)
        return True

    def move_tab(self, tab_id: str, delta: int) -> bool:
        t = self.tab(tab_id)
        if t is None:
            return False
        i = self.tabs.index(t)
        j = max(0, min(len(self.tabs) - 1, i + delta))
        if i == j:
            return False
        self.tabs.insert(j, self.tabs.pop(i))
        return True

    def move_button(self, tab_id: str, button_id: str, delta: int) -> bool:
        t = self.tab(tab_id)
        b = t.find(button_id) if t else None
        if b is None:
            return False
        i = t.buttons.index(b)
        j = max(0, min(len(t.buttons) - 1, i + delta))
        if i == j:
            return False
        t.buttons.insert(j, t.buttons.pop(i))
        return True

    def move_button_to_tab(self, tab_id: str, button_id: str, dest_tab_id: str) -> bool:
        src, dst = self.tab(tab_id), self.tab(dest_tab_id)
        b = src.find(button_id) if src else None
        if b is None or dst is None or src is dst:
            return False
        src.buttons.remove(b)
        b.id = dst.unique_button_id(b.id)
        dst.buttons.append(b)
        return True

    def remove_button(self, tab_id: str, button_id: str) -> bool:
        t = self.tab(tab_id)
        b = t.find(button_id) if t else None
        if b is None:
            return False
        t.buttons.remove(b)
        return True

    def duplicate_button(self, tab_id: str, button_id: str):
        t = self.tab(tab_id)
        b = t.find(button_id) if t else None
        if b is None:
            return None
        clone = Button.from_dict(b.to_dict())
        clone.id = t.unique_button_id(b.id)
        clone.title = f"{b.title} copy"[:64]
        t.buttons.insert(t.buttons.index(b) + 1, clone)
        return clone

    def merge(self, other: "Shelf") -> int:
        """다른 Shelf 의 탭/버튼을 추가한다. 추가된 버튼 수를 반환."""
        added = 0
        for ot in other.tabs:
            mine = self.tab(ot.id)
            if mine is None:
                mine = Tab(self.unique_tab_id(ot.id), ot.title)
                self.tabs.append(mine)
            for b in ot.buttons:
                existing = mine.find(b.id)
                if existing is not None and existing.to_dict() == b.to_dict():
                    continue
                clone = Button.from_dict(b.to_dict())
                clone.id = mine.unique_button_id(b.id)
                mine.buttons.append(clone)
                added += 1
        return added

    # ---- 직렬화 -----------------------------------------------------------
    @classmethod
    def from_dict(cls, data, strict: bool = False):
        """(shelf, errors) 반환. strict=False 면 잘못된 버튼/탭은 건너뛰고 오류로 보고."""
        errors: list = []
        if not isinstance(data, dict):
            raise ValidationError("Shelf 데이터는 JSON 객체여야 합니다")
        raw_tabs = data.get("tabs")
        if not isinstance(raw_tabs, list):
            raise ValidationError("'tabs' 목록이 없습니다")
        shelf = cls(tabs=[], profile=str(data.get("profile") or "maya_basic"))
        for ti, rt in enumerate(raw_tabs):
            try:
                if not isinstance(rt, dict):
                    raise ValidationError(f"tabs[{ti}]: 객체여야 합니다")
                tid = str(rt.get("id", ""))
                if not _ID_RE.match(tid):
                    raise ValidationError(f"tabs[{ti}]: 잘못된 탭 id '{tid}'")
                if shelf.tab(tid) is not None:
                    raise ValidationError(f"tabs[{ti}]: 중복된 탭 id '{tid}'")
                tab = Tab(tid, str(rt.get("title") or tid)[:64])
            except ValidationError as e:
                if strict:
                    raise
                errors.append(str(e))
                continue
            for bi, rb in enumerate(rt.get("buttons") or []):
                try:
                    b = Button.from_dict(rb, f"{tid}.buttons[{bi}]")
                    if tab.find(b.id) is not None:
                        raise ValidationError(f"{tid}.buttons[{bi}]: 중복된 버튼 id '{b.id}'")
                    tab.buttons.append(b)
                except ValidationError as e:
                    if strict:
                        raise
                    errors.append(str(e))
            shelf.tabs.append(tab)
        return shelf, errors

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "profile": self.profile,
            "tabs": [
                {"id": t.id, "title": t.title, "buttons": [b.to_dict() for b in t.buttons]}
                for t in self.tabs
            ],
        }


# ---------------------------------------------------------------------------
# 기본 Shelf (PRD 9장). Operator ID 는 Blender 4.5 / 5.x 에서 존재를 확인했다.
# ---------------------------------------------------------------------------

def _tool(bid, title, icon, tool_id, modes=None, tooltip=""):
    return {
        "id": bid,
        "title": title,
        "icon": icon,
        "kind": "operator",
        "target": "wm.tool_set_by_id",
        "properties": {"name": tool_id},
        "context_policy": "EXEC_DEFAULT",
        "tooltip": tooltip,
        "requires_mode": modes or [],
    }


def _op(bid, title, icon, target, props=None, policy="INVOKE_DEFAULT", modes=None, tooltip="", area="VIEW_3D", addon=""):
    d = {
        "id": bid,
        "title": title,
        "icon": icon,
        "kind": "operator",
        "target": target,
        "properties": props or {},
        "context_policy": policy,
        "tooltip": tooltip,
        "requires_mode": modes or [],
        "area": area,
    }
    if addon:
        d["addon"] = addon
    return d


def _menu(bid, title, icon, menu_id, modes=None, tooltip=""):
    return {
        "id": bid,
        "title": title,
        "icon": icon,
        "kind": "menu",
        "target": menu_id,
        "tooltip": tooltip,
        "requires_mode": modes or [],
    }


_EDIT_MESH = ["EDIT_MESH"]

DEFAULT_SHELF = {
    "schema_version": SCHEMA_VERSION,
    "profile": "maya_basic",
    "tabs": [
        {
            "id": "general",
            "title": "General",
            "buttons": [
                _tool("select", "Select", "RESTRICT_SELECT_OFF", "builtin.select_box", tooltip="선택 도구 (Maya Q)"),
                _tool("move", "Move", "EMPTY_ARROWS", "builtin.move", tooltip="이동 도구 (Maya W)"),
                _tool("rotate", "Rotate", "DRIVER_ROTATIONAL_DIFFERENCE", "builtin.rotate", tooltip="회전 도구 (Maya E)"),
                _tool("scale", "Scale", "FULLSCREEN_ENTER", "builtin.scale", tooltip="크기 조절 도구 (Maya R)"),
                _op("duplicate", "Duplicate", "DUPLICATE", "object.duplicate", {"linked": False}, "EXEC_DEFAULT", ["OBJECT"],
                    "제자리에 복제 (Maya Ctrl+D)"),
                _op("delete", "Delete", "TRASH", "object.delete", {"use_global": False, "confirm": False}, "EXEC_DEFAULT", ["OBJECT"],
                    "선택 오브젝트 삭제"),
                _op("parent", "Parent", "LINKED", "object.parent_set", {"type": "OBJECT", "keep_transform": True}, "EXEC_DEFAULT",
                    ["OBJECT"], "선택 → 활성(마지막 선택) 오브젝트에 페어런트 (Maya P)"),
            ],
        },
        {
            "id": "modeling",
            "title": "Modeling",
            "buttons": [
                _op("add_cube", "Cube", "MESH_CUBE", "mesh.primitive_cube_add", policy="INVOKE_DEFAULT", tooltip="큐브 추가"),
                _op("add_sphere", "Sphere", "MESH_UVSPHERE", "mesh.primitive_uv_sphere_add", tooltip="UV 스피어 추가"),
                _tool("extrude", "Extrude", "MOD_SOLIDIFY", "builtin.extrude_region", _EDIT_MESH, "익스트루드 도구 (Maya Ctrl+E)"),
                _tool("bevel", "Bevel", "MOD_BEVEL", "builtin.bevel", _EDIT_MESH, "베벨 도구 (Maya Ctrl+B)"),
                _tool("inset", "Inset", "FULLSCREEN_EXIT", "builtin.inset_faces", _EDIT_MESH, "면 인셋 도구"),
                _tool("loop_cut", "Loop Cut", "MOD_EDGESPLIT", "builtin.loop_cut", _EDIT_MESH, "루프 컷 도구 (Maya Insert Edge Loop)"),
                _op("boolean", "Boolean", "MOD_BOOLEAN", "object.modifier_add", {"type": "BOOLEAN"}, "EXEC_DEFAULT", ["OBJECT"],
                    "활성 오브젝트에 Boolean 모디파이어 추가"),
            ],
        },
        {
            "id": "animation",
            "title": "Animation",
            "buttons": [
                _op("insert_key", "Set Key", "KEY_HLT", "anim.keyframe_insert", policy="EXEC_DEFAULT", modes=["OBJECT", "POSE"],
                    tooltip="현재 프레임에 키프레임 (Maya S)"),
                _op("play", "Play/Pause", "PLAY", "screen.animation_play", policy="EXEC_DEFAULT", tooltip="재생/정지 (Space)"),
                _op("frame_selected", "Frame Sel", "ZOOM_SELECTED", "view3d.view_selected", policy="EXEC_DEFAULT",
                    tooltip="선택 대상 프레이밍 (Maya F)"),
                _op("graph_editor", "Graph Ed.", "GRAPH", "maya_ux.open_editor", {"editor_type": "FCURVES"}, "EXEC_DEFAULT",
                    tooltip="Graph Editor 를 새 창으로 열기"),
                _op("dope_sheet", "Dope Sheet", "ACTION", "maya_ux.open_editor", {"editor_type": "DOPESHEET"}, "EXEC_DEFAULT",
                    tooltip="Dope Sheet 를 새 창으로 열기"),
            ],
        },
        {
            "id": "rigging",
            "title": "Rigging",
            "buttons": [
                _op("add_armature", "Armature", "ARMATURE_DATA", "object.armature_add", policy="EXEC_DEFAULT", modes=["OBJECT"],
                    tooltip="아마추어(조인트 체인 시작) 추가"),
                _op("rig_parent", "Parent", "LINKED", "object.parent_set", {"type": "OBJECT", "keep_transform": True}, "EXEC_DEFAULT",
                    ["OBJECT"], "선택 → 활성 오브젝트에 페어런트"),
                _op("parent_armature", "Skin Bind", "MOD_ARMATURE", "object.parent_set", {"type": "ARMATURE_AUTO"}, "EXEC_DEFAULT",
                    ["OBJECT"], "자동 웨이트로 아마추어에 바인딩 (Maya Bind Skin 대응)"),
                _menu("constraints", "Constraint", "CONSTRAINT", "VIEW3D_MT_object_constraints", ["OBJECT"],
                      "오브젝트 컨스트레인트 메뉴"),
                _menu("bone_constraints", "Bone Cnstr", "CONSTRAINT_BONE", "VIEW3D_MT_pose_constraints", ["POSE"],
                      "본 컨스트레인트 메뉴 (Pose Mode)"),
            ],
        },
        {
            "id": "rendering",
            "title": "Rendering",
            "buttons": [
                _op("render", "Render", "RENDER_STILL", "render.render", {"use_viewport": True}, "INVOKE_DEFAULT",
                    tooltip="현재 프레임 렌더 (F12)"),
                _op("rendered_view", "Rendered", "SHADING_RENDERED", "view3d.toggle_shading", {"type": "RENDERED"}, "EXEC_DEFAULT",
                    tooltip="뷰포트 Rendered 셰이딩 토글"),
                _op("render_props", "Render Set.", "PROPERTIES", "maya_ux.open_editor",
                    {"editor_type": "PROPERTIES", "properties_context": "RENDER"}, "EXEC_DEFAULT", tooltip="Render Properties 열기"),
            ],
        },
        {
            "id": "custom",
            "title": "Custom",
            "buttons": [
                {
                    "id": "smooth_cube",
                    "title": "Smooth Cube",
                    "icon": "MOD_SUBSURF",
                    "kind": "preset",
                    "target": "",
                    "tooltip": "프리셋 예시: 큐브 추가 → 스무스 셰이딩 → Subdivision 모디파이어",
                    "steps": [
                        {"kind": "operator", "target": "mesh.primitive_cube_add", "context_policy": "EXEC_DEFAULT"},
                        {"kind": "operator", "target": "object.shade_smooth", "context_policy": "EXEC_DEFAULT"},
                        {"kind": "operator", "target": "object.modifier_add", "properties": {"type": "SUBSURF"},
                         "context_policy": "EXEC_DEFAULT"},
                    ],
                },
                _op("sample_center", "Center Pivot", "PIVOT_BOUNDBOX", "mayaux_sample.center_pivot", policy="EXEC_DEFAULT",
                    modes=["OBJECT"], tooltip="샘플 애드온: 피벗을 바운딩 박스 중심으로", addon="mayaux_sample_addon"),
                _op("sample_freeze", "Freeze Xform", "FREEZE", "mayaux_sample.freeze_transforms", policy="EXEC_DEFAULT",
                    modes=["OBJECT"], tooltip="샘플 애드온: Maya Freeze Transformations", addon="mayaux_sample_addon"),
                _op("sample_random", "Random Color", "COLOR", "mayaux_sample.random_color", policy="EXEC_DEFAULT",
                    modes=["OBJECT"], tooltip="샘플 애드온: 선택 오브젝트 뷰포트 색 무작위", addon="mayaux_sample_addon"),
                _op("looptools_relax", "LT Relax", "MOD_SMOOTH", "mesh.looptools_relax", policy="INVOKE_DEFAULT",
                    modes=_EDIT_MESH, tooltip="LoopTools 확장의 Relax (확장이 설치되어 있어야 함)", addon="looptools"),
            ],
        },
    ],
}


def default_shelf() -> Shelf:
    shelf, errors = Shelf.from_dict(copy.deepcopy(DEFAULT_SHELF), strict=True)
    assert not errors
    return shelf
