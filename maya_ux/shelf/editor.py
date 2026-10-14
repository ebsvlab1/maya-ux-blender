"""Shelf 편집 Operator: 탭/버튼 추가·삭제·이름변경·순서·아이콘·프로퍼티, 명령 검색, 스크립트 신뢰."""

from __future__ import annotations

import json
import os

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty

from .. import state
from ..integrations import addon_discovery as AD
from ..integrations import scripts
from ..state import S
from .model import AREAS, MODES, Button, ValidationError
from . import registry


def _tab_or_report(op, tab_id):
    t = S.shelf.tab(tab_id)
    if t is None:
        op.report({"WARNING"}, "탭을 찾을 수 없습니다")
    return t


# ---------------------------------------------------------------------------
# 탭
# ---------------------------------------------------------------------------

class MAYAUX_OT_tab_add(bpy.types.Operator):
    """새 Shelf 탭 추가"""

    bl_idname = "maya_ux.tab_add"
    bl_label = "탭 추가"

    title: StringProperty(name="이름", default="New Tab")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        tab = S.shelf.add_tab(self.title.strip() or "Tab")
        context.window_manager.maya_ux_active_tab = tab.id
        state.save_shelf()
        return {"FINISHED"}


class MAYAUX_OT_tab_rename(bpy.types.Operator):
    """탭 이름 변경"""

    bl_idname = "maya_ux.tab_rename"
    bl_label = "탭 이름 변경"
    bl_options = {"INTERNAL"}

    tab_id: StringProperty()
    title: StringProperty(name="이름")

    def invoke(self, context, event):
        t = S.shelf.tab(self.tab_id)
        if t is None:
            return {"CANCELLED"}
        self.title = t.title
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        t = _tab_or_report(self, self.tab_id)
        if t is None or not self.title.strip():
            return {"CANCELLED"}
        t.title = self.title.strip()[:64]
        state.save_shelf()
        return {"FINISHED"}


class MAYAUX_OT_tab_remove(bpy.types.Operator):
    """탭과 그 안의 버튼을 삭제"""

    bl_idname = "maya_ux.tab_remove"
    bl_label = "탭 삭제"
    bl_options = {"INTERNAL"}

    tab_id: StringProperty()

    def invoke(self, context, event):
        t = S.shelf.tab(self.tab_id)
        if t is None:
            return {"CANCELLED"}
        if not t.buttons:
            return self.execute(context)
        return context.window_manager.invoke_confirm(
            self, event, title="탭 삭제", message=f"'{t.title}' 탭과 버튼 {len(t.buttons)}개를 삭제할까요?")

    def execute(self, context):
        if not S.shelf.remove_tab(self.tab_id):
            return {"CANCELLED"}
        state.save_shelf()
        return {"FINISHED"}


class MAYAUX_OT_tab_move(bpy.types.Operator):
    """탭 순서 이동"""

    bl_idname = "maya_ux.tab_move"
    bl_label = "탭 이동"
    bl_options = {"INTERNAL"}

    tab_id: StringProperty()
    delta: IntProperty()

    def execute(self, context):
        if S.shelf.move_tab(self.tab_id, self.delta):
            state.save_shelf()
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# 버튼 편집 대화상자
# ---------------------------------------------------------------------------

_KIND_ITEMS = [
    ("operator", "Operator", "Blender 또는 애드온 명령 (bl_idname)", "TOOL_SETTINGS", 0),
    ("menu", "메뉴", "bpy.types.Menu 메뉴 열기", "MENU_PANEL", 1),
    ("script", "Python 스크립트", "신뢰 확인한 로컬 .py 파일 실행", "SCRIPT", 2),
]
_MODE_ITEMS = [(m, m.replace("_", " ").title(), "", 1 << i) for i, m in enumerate(MODES)]
_AREA_ITEMS = [(a, a.replace("_", " ").title(), "") for a in AREAS]


class MAYAUX_OT_button_edit(bpy.types.Operator):
    """Shelf 버튼 추가/편집"""

    bl_idname = "maya_ux.button_edit"
    bl_label = "Shelf 버튼"
    bl_options = {"INTERNAL"}

    tab_id: StringProperty()
    button_id: StringProperty(description="비어 있으면 새 버튼")
    title: StringProperty(name="이름", default="")
    icon: StringProperty(name="아이콘", default="TOOL_SETTINGS", description="Blender 아이콘 이름 (예: MESH_CUBE)")
    kind: EnumProperty(name="종류", items=_KIND_ITEMS)
    target: StringProperty(name="명령 ID", description="operator: mesh.primitive_cube_add / menu: VIEW3D_MT_object")
    script_path: StringProperty(name="스크립트", subtype="FILE_PATH")
    properties_json: StringProperty(name="프로퍼티(JSON)", default="{}",
                                    description='예: {"size": 2.0, "align": "CURSOR"}')
    context_policy: EnumProperty(name="실행 방식", items=[
        ("INVOKE_DEFAULT", "대화형 (INVOKE)", "마우스/대화상자 등 UI 상호작용 포함"),
        ("EXEC_DEFAULT", "즉시 실행 (EXEC)", "프로퍼티 값으로 바로 실행"),
    ])
    tooltip: StringProperty(name="툴팁")
    requires_mode: EnumProperty(name="요구 모드", items=_MODE_ITEMS, options={"ENUM_FLAG"})
    area: EnumProperty(name="실행 영역", items=_AREA_ITEMS, default="VIEW_3D")
    enabled: BoolProperty(name="사용", default=True)
    trust_script: BoolProperty(name="이 스크립트를 신뢰합니다", default=False,
                               description="스크립트는 Blender 와 같은 권한으로 임의 코드를 실행할 수 있습니다")
    is_new: BoolProperty(options={"HIDDEN", "SKIP_SAVE"})

    def invoke(self, context, event):
        b = S.shelf.button(self.tab_id, self.button_id) if self.button_id else None
        self.is_new = b is None
        if b is not None:
            if b.kind == "preset":
                self.report({"INFO"}, "프리셋 버튼은 JSON 내보내기/가져오기로 편집하세요")
                return {"CANCELLED"}
            self.title, self.icon, self.kind = b.title, b.icon, b.kind
            self.target = b.target if b.kind != "script" else ""
            self.script_path = b.target if b.kind == "script" else ""
            self.properties_json = json.dumps(b.properties, ensure_ascii=False)
            self.context_policy, self.tooltip = b.context_policy, b.tooltip
            self.requires_mode = set(b.requires_mode)
            self.area, self.enabled = b.area, b.enabled
            self.trust_script = b.kind == "script" and scripts.status(b.target) == scripts.OK
        elif self.kind == "operator" and self.target and not self.title:
            self.title = AD.operator_label(self.target)[:24]
        return context.window_manager.invoke_props_dialog(self, width=520)

    def _props(self):
        try:
            data = json.loads(self.properties_json or "{}")
        except json.JSONDecodeError as e:
            raise ValidationError(f"프로퍼티 JSON 오류: {e.msg}") from None
        return data

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "kind", expand=True)
        row = col.row(align=True)
        row.prop(self, "title")
        row = col.row(align=True)
        row.prop(self, "icon")
        row.label(text="", icon=registry.icon_or_default(self.icon))
        if self.kind == "script":
            col.prop(self, "script_path")
            box = col.box()
            box.alert = True
            box.label(text="스크립트는 임의 코드를 실행할 수 있습니다. 샌드박스가 아닙니다.", icon="ERROR")
            box.label(text="직접 작성했거나 내용을 확인한 파일만 신뢰하세요.")
            if not scripts.allowed():
                box.label(text="현재 스크립트 버튼이 꺼져 있습니다 (Preferences > MayaUX)", icon="INFO")
            lines = scripts.preview(bpy.path.abspath(self.script_path)) if self.script_path else []
            if lines:
                pv = col.box().column(align=True)
                pv.scale_y = 0.7
                for ln in lines:
                    pv.label(text=ln[:100] or " ")
            col.prop(self, "trust_script")
        else:
            row = col.row(align=True)
            row.prop(self, "target")
            if self.kind == "operator" and self.target:
                exists = AD.operator_exists(self.target)
                row.label(text="", icon="CHECKMARK" if exists else "ERROR")
                if exists:
                    col.label(text=AD.operator_label(self.target), icon="INFO")
            elif self.kind == "menu" and self.target:
                row.label(text="", icon="CHECKMARK" if AD.menu_exists(self.target) else "ERROR")
            if self.kind == "operator":
                col.prop(self, "properties_json")
                col.prop(self, "context_policy")
        col.prop(self, "tooltip")
        col.label(text="요구 모드 (비우면 모든 모드):")
        grid = col.grid_flow(columns=3, align=True)
        grid.prop(self, "requires_mode")
        col.prop(self, "area")
        col.prop(self, "enabled")

    def execute(self, context):
        t = _tab_or_report(self, self.tab_id)
        if t is None:
            return {"CANCELLED"}
        old = None if self.is_new else t.find(self.button_id)
        target = bpy.path.abspath(self.script_path) if self.kind == "script" else self.target.strip()
        try:
            props = self._props() if self.kind == "operator" else {}
            data = {
                "id": old.id if old else t.unique_button_id((self.title or target or "button").lower().replace(" ", "_")),
                "title": self.title.strip() or target,
                "icon": self.icon.strip() or "NONE",
                "kind": self.kind,
                "target": target,
                "properties": props,
                "context_policy": self.context_policy,
                "tooltip": self.tooltip,
                "enabled": self.enabled,
                "requires_mode": [m for m in MODES if m in self.requires_mode],
                "area": self.area,
            }
            if self.kind == "operator" and AD.operator_exists(target):
                data["addon"] = AD.addon_short_name(AD.operator_owner(target))
            elif old and old.target == target:
                data["addon"] = old.addon
            button = Button.from_dict(data)
        except ValidationError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        if button.icon != "NONE" and not registry.valid_icon(button.icon):
            self.report({"WARNING"}, f"아이콘 '{button.icon}' 이(가) 없어 기본 아이콘으로 표시됩니다")
        if self.kind == "script":
            if self.trust_script and os.path.isfile(target):
                scripts.trust(target)
            elif not self.trust_script:
                scripts.untrust(target)
            state.save_local()
        if old:
            t.buttons[t.buttons.index(old)] = button
        else:
            t.buttons.append(button)
        state.save_shelf()
        return {"FINISHED"}


class MAYAUX_OT_pick_operator(bpy.types.Operator):
    """설치된 모든 Operator(Blender 내장 + 활성 확장)에서 검색해 버튼 추가"""

    bl_idname = "maya_ux.pick_operator"
    bl_label = "명령 검색"
    bl_options = {"INTERNAL"}
    bl_property = "operator"

    tab_id: StringProperty()
    operator: EnumProperty(items=registry.operator_enum_items)

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        bpy.ops.maya_ux.button_edit("INVOKE_DEFAULT", tab_id=self.tab_id, kind="operator", target=self.operator,
                                    title=AD.operator_label(self.operator)[:24], icon="TOOL_SETTINGS")
        return {"FINISHED"}


class MAYAUX_OT_pick_menu(bpy.types.Operator):
    """등록된 메뉴에서 검색해 버튼 추가"""

    bl_idname = "maya_ux.pick_menu"
    bl_label = "메뉴 검색"
    bl_options = {"INTERNAL"}
    bl_property = "menu"

    tab_id: StringProperty()
    menu: EnumProperty(items=registry.menu_enum_items)

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        label = next((lbl for mid, lbl in AD.list_menus() if mid == self.menu), self.menu)
        bpy.ops.maya_ux.button_edit("INVOKE_DEFAULT", tab_id=self.tab_id, kind="menu", target=self.menu,
                                    title=label[:24], icon="MENU_PANEL")
        return {"FINISHED"}


class MAYAUX_OT_pick_icon(bpy.types.Operator):
    """버튼 아이콘 검색"""

    bl_idname = "maya_ux.pick_icon"
    bl_label = "아이콘 선택"
    bl_options = {"INTERNAL"}
    bl_property = "icon"

    tab_id: StringProperty()
    button_id: StringProperty()
    icon: EnumProperty(items=registry.icon_enum_items)

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        b = S.shelf.button(self.tab_id, self.button_id)
        if b is None:
            return {"CANCELLED"}
        b.icon = self.icon
        state.save_shelf()
        return {"FINISHED"}


class MAYAUX_OT_button_move(bpy.types.Operator):
    """버튼 순서 이동"""

    bl_idname = "maya_ux.button_move"
    bl_label = "버튼 이동"
    bl_options = {"INTERNAL"}

    tab_id: StringProperty()
    button_id: StringProperty()
    delta: IntProperty()

    def execute(self, context):
        if S.shelf.move_button(self.tab_id, self.button_id, self.delta):
            state.save_shelf()
        return {"FINISHED"}


class MAYAUX_OT_button_to_tab(bpy.types.Operator):
    """버튼을 다른 탭으로 옮김"""

    bl_idname = "maya_ux.button_to_tab"
    bl_label = "다른 탭으로"
    bl_options = {"INTERNAL"}

    tab_id: StringProperty()
    button_id: StringProperty()
    dest: EnumProperty(name="대상 탭", items=registry.tab_enum_items)

    def execute(self, context):
        if S.shelf.move_button_to_tab(self.tab_id, self.button_id, self.dest):
            state.save_shelf()
        return {"FINISHED"}


class MAYAUX_OT_button_remove(bpy.types.Operator):
    """버튼 삭제"""

    bl_idname = "maya_ux.button_remove"
    bl_label = "버튼 삭제"
    bl_options = {"INTERNAL"}

    tab_id: StringProperty()
    button_id: StringProperty()

    def execute(self, context):
        if S.shelf.remove_button(self.tab_id, self.button_id):
            state.save_shelf()
        return {"FINISHED"}


class MAYAUX_OT_button_duplicate(bpy.types.Operator):
    """버튼 복제 (명령 프리셋 복제)"""

    bl_idname = "maya_ux.button_duplicate"
    bl_label = "버튼 복제"
    bl_options = {"INTERNAL"}

    tab_id: StringProperty()
    button_id: StringProperty()

    def execute(self, context):
        if S.shelf.duplicate_button(self.tab_id, self.button_id):
            state.save_shelf()
        return {"FINISHED"}


class MAYAUX_MT_button_actions(bpy.types.Menu):
    bl_idname = "MAYAUX_MT_button_actions"
    bl_label = "버튼"

    def draw(self, context):
        layout = self.layout
        tab_id = getattr(context, "maya_ux_tab_id", "")
        button_id = getattr(context, "maya_ux_button_id", "")
        if not button_id:
            layout.label(text="버튼 정보를 찾을 수 없습니다")
            return
        for op_id, text, icon in (("maya_ux.button_edit", "편집…", "GREASEPENCIL"),
                                  ("maya_ux.pick_icon", "아이콘…", "IMAGE_DATA"),
                                  ("maya_ux.button_duplicate", "복제", "DUPLICATE")):
            op = layout.operator(op_id, text=text, icon=icon)
            op.tab_id, op.button_id = tab_id, button_id
        layout.separator()
        for t in S.shelf.tabs:
            if t.id == tab_id:
                continue
            op = layout.operator("maya_ux.button_to_tab", text=f"→ {t.title}", icon="FORWARD")
            op.tab_id, op.button_id, op.dest = tab_id, button_id, t.id
        layout.separator()
        op = layout.operator("maya_ux.button_remove", text="삭제", icon="TRASH")
        op.tab_id, op.button_id = tab_id, button_id


classes = (
    MAYAUX_OT_tab_add,
    MAYAUX_OT_tab_rename,
    MAYAUX_OT_tab_remove,
    MAYAUX_OT_tab_move,
    MAYAUX_OT_button_edit,
    MAYAUX_OT_pick_operator,
    MAYAUX_OT_pick_menu,
    MAYAUX_OT_pick_icon,
    MAYAUX_OT_button_move,
    MAYAUX_OT_button_to_tab,
    MAYAUX_OT_button_remove,
    MAYAUX_OT_button_duplicate,
    MAYAUX_MT_button_actions,
)
