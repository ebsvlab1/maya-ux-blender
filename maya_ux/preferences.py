"""MayaUX 환경설정: 설정 마법사, 키맵 프로파일·충돌 표, Shelf 표시, 백업/복원."""

from __future__ import annotations

import sys

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty

from .integrations import scripts
from .keymap import conflicts as C
from .keymap import registry as keymap_registry
from .keymap.mappings import CONTEXT_LABELS, MAPPINGS, PROFILES
from .keymap.operators import MAYAUX_OT_km_capture
from .state import S

_STATUS_ICONS = {
    C.BASELINE: "CHECKMARK",
    C.FREE: "KEYINGSET",
    C.REPLACED: "FILE_REFRESH",
    C.CONFLICT: "ERROR",
    C.RESERVED: "LOCKED",
    C.DISABLED: "CHECKBOX_DEHLT",
    C.UNAVAILABLE: "CANCEL",
}

_KM_FILTER_ITEMS = [("ALL", "전체", "")] + [
    (km, label, "") for km, label in dict.fromkeys(
        (m.keymap, CONTEXT_LABELS.get(m.keymap, m.keymap)) for m in MAPPINGS)
]


def get_prefs(context=None):
    context = context or bpy.context
    addon = context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


def _redraw(self, context):
    from . import state

    state._redraw()


def _allow_scripts_update(self, context):
    scripts.set_allowed(self.allow_scripts)
    _redraw(self, context)


class MayaUXPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    section: EnumProperty(items=[
        ("KEYMAP", "단축키", "", "KEYINGSET", 0),
        ("SHELF", "Shelf", "", "TOOL_SETTINGS", 1),
        ("DATA", "백업·복원", "", "FILE_BACKUP", 2),
    ])
    columns: IntProperty(name="열 수", default=2, min=1, max=8, update=_redraw)
    show_text: BoolProperty(name="버튼 이름 표시", default=True, update=_redraw)
    button_scale: FloatProperty(name="버튼 높이", default=1.2, min=0.8, max=3.0, update=_redraw)
    header_button: BoolProperty(name="3D 뷰 헤더에 Shelf 팝오버 버튼", default=True, update=_redraw)
    allow_scripts: BoolProperty(name="스크립트 버튼 허용", default=False, update=_allow_scripts_update,
                                description="신뢰 확인한 로컬 .py 파일을 Shelf 에서 실행할 수 있게 합니다")
    km_filter: EnumProperty(name="영역", items=_KM_FILTER_ITEMS)
    km_only_issues: BoolProperty(name="충돌·문제만", default=False)

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.operator("maya_ux.setup_wizard", icon="SETTINGS")
        row.operator("maya_ux.refresh", icon="FILE_REFRESH")
        layout.row().prop(self, "section", expand=True)
        if self.section == "KEYMAP":
            self.draw_keymap(layout)
        elif self.section == "SHELF":
            self.draw_shelf(layout)
        else:
            self.draw_data(layout)

    # ------------------------------------------------------------------
    def draw_keymap(self, layout):
        box = layout.box()
        name = keymap_registry.active_keyconfig_name() or "-"
        if keymap_registry.is_industry_compatible():
            box.label(text=f"기준 키맵: {name}", icon="CHECKMARK")
        else:
            box.label(text=f"기준 키맵: {name} — Industry Compatible 사용을 권장합니다 (설정 마법사)", icon="INFO")
        row = box.row(align=True)
        op = row.operator("maya_ux.km_enable", text="MayaUX 단축키 켜짐" if S.keymap.enabled else "MayaUX 단축키 꺼짐",
                          icon="CHECKBOX_HLT" if S.keymap.enabled else "CHECKBOX_DEHLT", depress=S.keymap.enabled)
        op.enable = not S.keymap.enabled
        row = box.row(align=True)
        row.label(text="프로파일:")
        for key, desc in PROFILES.items():
            op = row.operator("maya_ux.km_profile", text=desc.split(" — ")[0], depress=S.keymap.profile == key)
            op.profile = key
        if sys.platform == "darwin":
            op = box.operator("maya_ux.km_mac_cmd", text="Ctrl 단축키를 Cmd 로 등록",
                              icon="CHECKBOX_HLT" if S.keymap.mac_ctrl_as_cmd else "CHECKBOX_DEHLT")
            op.on = not S.keymap.mac_ctrl_as_cmd
        if keymap_registry.last_error:
            box.label(text=keymap_registry.last_error, icon="ERROR")

        n_conflict = sum(1 for a in keymap_registry.analyses.values() if a.status == C.CONFLICT)
        row = layout.row(align=True)
        row.prop(self, "km_filter", text="")
        row.prop(self, "km_only_issues", toggle=True)
        sub = row.row(align=True)
        sub.enabled = n_conflict > 0
        sub.operator("maya_ux.km_replace_all", text=f"충돌 {n_conflict}개 모두 대체")
        row.operator("maya_ux.km_keep_all", text="모두 기존 유지")

        enabled_ids = set(S.keymap.mapping_ids)
        col = layout.column(align=True)
        waiting = MAYAUX_OT_km_capture.waiting["id"]
        for m in MAPPINGS:
            if self.km_filter != "ALL" and m.keymap != self.km_filter:
                continue
            a = keymap_registry.analyses.get(m.id)
            status = a.status if a else (C.DISABLED if m.id not in enabled_ids else "")
            if self.km_only_issues and status not in (C.CONFLICT, C.RESERVED, C.UNAVAILABLE, C.REPLACED):
                continue
            on = m.id in enabled_ids
            event = S.keymap.event_for(m)
            row = col.box().row(align=False)
            op = row.operator("maya_ux.km_toggle", text="", icon="CHECKBOX_HLT" if on else "CHECKBOX_DEHLT", emboss=False)
            op.mapping_id, op.on = m.id, not on
            split = row.split(factor=0.34)
            split.label(text=f"{m.label}  [{m.priority}]")
            split = split.split(factor=0.28)
            split.label(text=m.context)
            split = split.split(factor=0.42)
            key_row = split.row(align=True)
            if waiting == m.id:
                key_row.alert = True
                key_row.label(text="키 입력 대기…")
            else:
                key_row.label(text=event.label() + (" *" if m.id in S.keymap.overrides else ""))
            if not m.event.type.endswith("MOUSE"):
                cap = key_row.operator("maya_ux.km_capture", text="", icon="EVENT_RETURN", emboss=False)
                cap.mapping_id = m.id
            if m.id in S.keymap.overrides:
                clr = key_row.operator("maya_ux.km_clear_override", text="", icon="LOOP_BACK", emboss=False)
                clr.mapping_id = m.id
            status_row = split.row(align=True)
            if status:
                status_row.alert = status in (C.CONFLICT, C.UNAVAILABLE)
                status_row.label(text=C.STATUS_LABELS.get(status, status), icon=_STATUS_ICONS.get(status, "DOT"))
            if status == C.CONFLICT:
                op = status_row.operator("maya_ux.km_decide", text="대체")
                op.mapping_id, op.decision = m.id, "REPLACE"
            elif status == C.REPLACED:
                op = status_row.operator("maya_ux.km_decide", text="복원")
                op.mapping_id, op.decision = m.id, "KEEP"
            if a and (a.conflicts or a.reason or a.warning or m.note):
                sub = col.column(align=True)
                sub.scale_y = 0.75
                for it in a.conflicts[:3]:
                    sub.label(text=f"        ↳ 충돌: {it.describe()}")
                if a.reason and status != C.BASELINE:
                    sub.label(text=f"        ↳ {a.reason}")
                if a.warning:
                    sub.label(text=f"        ↳ {a.warning}", icon="INFO")
                if m.note and status in (C.CONFLICT, C.FREE, C.REPLACED):
                    sub.label(text=f"        ↳ {m.note}")
        layout.label(text="Maya 쪽 키는 각 항목의 설명 및 docs/shortcut_reference.md 참고. * = 사용자 지정 키", icon="INFO")

    def draw_shelf(self, layout):
        col = layout.column()
        col.prop(self, "columns")
        col.prop(self, "button_scale")
        col.prop(self, "show_text")
        col.prop(self, "header_button")
        box = layout.box()
        box.prop(self, "allow_scripts")
        box.label(text="스크립트는 임의 코드를 실행합니다. 가져온 설정의 스크립트는 자동 실행되지 않으며 "
                       "버튼마다 신뢰 확인이 필요합니다.", icon="ERROR")
        layout.label(text=f"Shelf: 탭 {len(S.shelf.tabs)}개 · 버튼 {sum(len(t.buttons) for t in S.shelf.tabs)}개 · "
                          f"저장 위치: {S.folder}", icon="FILE_FOLDER")

    def draw_data(self, layout):
        col = layout.column()
        row = col.row()
        row.operator("maya_ux.export_config", icon="EXPORT")
        row.operator("maya_ux.import_config", icon="IMPORT")
        col.separator()
        col.label(text="되돌리기")
        row = col.row()
        row.operator("maya_ux.reset", text="Shelf 기본값", icon="LOOP_BACK").target = "SHELF"
        row.operator("maya_ux.reset", text="Blender 키맵으로 복귀", icon="KEYINGSET").target = "KEYMAP"
        col.operator("maya_ux.reset", text="제거 전 정리 (단축키 복원 + 설정 파일 삭제)", icon="TRASH").target = "CLEANUP"
        if S.deactivated:
            col.label(text=f"MayaUX 가 끈 기존 단축키 {len(S.deactivated)}개 — 확장을 끄면 자동 복원됩니다", icon="INFO")
        col.separator()
        col.label(text=f"설정 폴더: {S.folder}", icon="FILE_FOLDER")
        col.label(text="Blender 전체 키맵 백업은 Preferences > Keymap > Export 를 사용하세요.", icon="INFO")


classes = (MayaUXPreferences,)
