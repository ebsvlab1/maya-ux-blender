"""Shelf UI: 3D 뷰포트 Sidebar 패널, 헤더 팝오버, Hotbox 메뉴, 진단 패널."""

from __future__ import annotations

import bpy

from ..integrations import context_guard
from ..keymap import conflicts as C
from ..keymap import registry as keymap_registry
from ..state import S
from . import registry
from .operators import active_tab


def _prefs(context):
    from ..preferences import get_prefs

    return get_prefs(context)


def draw_tabs(layout, context, tab):
    row = layout.row(align=True)
    flow = row.grid_flow(row_major=True, columns=0, even_columns=False, align=True)
    for t in S.shelf.tabs:
        op = flow.operator("maya_ux.set_tab", text=t.title, depress=(tab is not None and t.id == tab.id))
        op.tab_id = t.id


def draw_buttons(layout, context, tab, columns=None, show_text=None, edit=False):
    prefs = _prefs(context)
    columns = columns if columns is not None else (prefs.columns if prefs else 2)
    show_text = show_text if show_text is not None else (prefs.show_text if prefs else True)
    if tab is None:
        layout.label(text="탭이 없습니다")
        return
    if not tab.buttons and not edit:
        layout.label(text="버튼이 없습니다 — 편집 모드에서 추가하세요", icon="INFO")
    if edit:
        _draw_edit_list(layout, tab)
        return
    grid = layout.grid_flow(row_major=True, columns=columns, even_columns=True, even_rows=True, align=True)
    grid.scale_y = prefs.button_scale if prefs else 1.2
    for b in tab.buttons:
        a = context_guard.check(context, b)
        cell = grid.row(align=True)
        cell.active = a.ok  # 회색이지만 클릭 가능 → 실행 시 이유를 알려줌
        icon = "ERROR" if a.missing else registry.icon_or_default(b.icon)
        op = cell.operator("maya_ux.run_button", text=b.title if show_text else "", icon=icon)
        op.tab_id, op.button_id = tab.id, b.id


def _draw_edit_list(layout, tab):
    col = layout.column(align=True)
    for i, b in enumerate(tab.buttons):
        row = col.row(align=True)
        row.context_string_set("maya_ux_tab_id", tab.id)
        row.context_string_set("maya_ux_button_id", b.id)
        row.label(text=b.title, icon=registry.icon_or_default(b.icon))
        sub = row.row(align=True)
        sub.enabled = i > 0
        op = sub.operator("maya_ux.button_move", text="", icon="TRIA_UP")
        op.tab_id, op.button_id, op.delta = tab.id, b.id, -1
        sub = row.row(align=True)
        sub.enabled = i < len(tab.buttons) - 1
        op = sub.operator("maya_ux.button_move", text="", icon="TRIA_DOWN")
        op.tab_id, op.button_id, op.delta = tab.id, b.id, 1
        op = row.operator("maya_ux.button_edit", text="", icon="GREASEPENCIL")
        op.tab_id, op.button_id = tab.id, b.id
        row.menu("MAYAUX_MT_button_actions", text="", icon="DOWNARROW_HLT")
    col.separator()
    row = col.row(align=True)
    op = row.operator("maya_ux.pick_operator", text="명령 추가", icon="ADD")
    op.tab_id = tab.id
    op = row.operator("maya_ux.pick_menu", text="메뉴 추가", icon="MENU_PANEL")
    op.tab_id = tab.id
    op = col.operator("maya_ux.button_edit", text="직접 입력 / 스크립트", icon="SCRIPT")
    op.tab_id, op.button_id = tab.id, ""

    col.separator()
    box = col.box()
    box.label(text=f"탭: {tab.title}")
    row = box.row(align=True)
    op = row.operator("maya_ux.tab_move", text="", icon="TRIA_LEFT")
    op.tab_id, op.delta = tab.id, -1
    op = row.operator("maya_ux.tab_move", text="", icon="TRIA_RIGHT")
    op.tab_id, op.delta = tab.id, 1
    op = row.operator("maya_ux.tab_rename", text="이름", icon="SORTALPHA")
    op.tab_id = tab.id
    op = row.operator("maya_ux.tab_remove", text="", icon="TRASH")
    op.tab_id = tab.id
    box.operator("maya_ux.tab_add", text="탭 추가", icon="ADD")


def draw_shelf(layout, context, compact=False):
    wm = context.window_manager
    tab = active_tab(context)
    draw_tabs(layout, context, tab)
    edit = wm.maya_ux_edit and not compact
    draw_buttons(layout, context, tab, edit=edit)


class VIEW3D_PT_maya_ux_shelf(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MayaUX"
    bl_label = "Shelf"

    def draw_header_preset(self, context):
        self.layout.prop(context.window_manager, "maya_ux_edit", text="", icon="GREASEPENCIL", emboss=False)

    def draw(self, context):
        layout = self.layout
        if not S.wizard_done:
            box = layout.box()
            box.label(text="처음이신가요?", icon="INFO")
            box.operator("maya_ux.setup_wizard", icon="SETTINGS")
        draw_shelf(layout, context)


class VIEW3D_PT_maya_ux_diagnostics(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MayaUX"
    bl_label = "진단"
    bl_parent_id = "VIEW3D_PT_maya_ux_shelf"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        name = keymap_registry.active_keyconfig_name()
        col.label(text=f"키맵: {name or '-'}", icon="CHECKMARK" if keymap_registry.is_industry_compatible() else "INFO")
        if keymap_registry.last_error:
            col.label(text=keymap_registry.last_error, icon="ERROR")
        counts = {}
        for a in keymap_registry.analyses.values():
            counts[a.status] = counts.get(a.status, 0) + 1
        if counts:
            for status in (C.FREE, C.REPLACED, C.BASELINE, C.CONFLICT, C.RESERVED, C.UNAVAILABLE):
                if counts.get(status):
                    col.label(text=f"{C.STATUS_LABELS[status]}: {counts[status]}",
                              icon="ERROR" if status in (C.CONFLICT, C.UNAVAILABLE) else "DOT")
        elif not S.keymap.enabled:
            col.label(text="MayaUX 단축키 꺼짐")

        unavailable = [(t, b, a) for t, b in S.shelf.all_buttons()
                       for a in [context_guard._static_check(b)] if not a.ok]
        if unavailable:
            col.separator()
            col.label(text=f"사용할 수 없는 버튼 {len(unavailable)}개", icon="ERROR")
            for t, b, a in unavailable[:6]:
                col.label(text=f"  {t.title}/{b.title}: {a.reason[:60]}")
        for msg in S.messages[:4]:
            col.label(text=msg[:80], icon="ERROR")
        if S.deactivated:
            col.label(text=f"MayaUX 가 끈 기존 단축키: {len(S.deactivated)}개", icon="INFO")
        row = layout.row(align=True)
        row.operator("maya_ux.refresh", icon="FILE_REFRESH")
        row.operator("preferences.addon_show", text="설정", icon="PREFERENCES").module = __package__.rsplit(".", 1)[0]


class VIEW3D_PT_maya_ux_popover(bpy.types.Panel):
    """헤더 팝오버/단축키(wm.call_panel)로 어디서나 여는 Shelf"""

    bl_space_type = "VIEW_3D"
    bl_region_type = "HEADER"
    bl_label = "MayaUX Shelf"
    bl_ui_units_x = 14

    def draw(self, context):
        draw_shelf(self.layout, context, compact=True)


class MAYAUX_MT_hotbox(bpy.types.Menu):
    """Maya Hotbox 대응: 모든 탭의 버튼을 열 단위로 보여준다"""

    bl_idname = "MAYAUX_MT_hotbox"
    bl_label = "MayaUX Hotbox"

    def draw(self, context):
        row = self.layout.row()
        for tab in S.shelf.tabs:
            col = row.column()
            col.label(text=tab.title)
            col.separator()
            for b in tab.buttons:
                a = context_guard.check(context, b, deep=False)
                sub = col.row()
                sub.active = a.ok
                op = sub.operator("maya_ux.run_button", text=b.title,
                                  icon="ERROR" if a.missing else registry.icon_or_default(b.icon))
                op.tab_id, op.button_id = tab.id, b.id


def draw_header_button(self, context):
    prefs = _prefs(context)
    if prefs is None or prefs.header_button:
        self.layout.popover("VIEW3D_PT_maya_ux_popover", text="", icon="TOOL_SETTINGS")


classes = (
    VIEW3D_PT_maya_ux_shelf,
    VIEW3D_PT_maya_ux_diagnostics,
    VIEW3D_PT_maya_ux_popover,
    MAYAUX_MT_hotbox,
)
