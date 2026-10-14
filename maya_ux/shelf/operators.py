"""Shelf 실행/공용 Operator: 버튼 실행, 탭 전환, 편집기 열기, 내보내기/가져오기, 초기화, 설정 마법사."""

from __future__ import annotations

import os

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper

from .. import state
from ..integrations import addon_discovery as AD
from ..integrations import context_guard, scripts
from ..keymap import conflicts as C
from ..keymap import registry as keymap_registry
from ..shelf.model import ValidationError, default_shelf
from ..state import S
from ..storage import json_io
from . import registry


def active_tab(context):
    tab_id = context.window_manager.maya_ux_active_tab
    return S.shelf.tab(tab_id) or (S.shelf.tabs[0] if S.shelf.tabs else None)


class MAYAUX_OT_run_button(bpy.types.Operator):
    bl_idname = "maya_ux.run_button"
    bl_label = "Shelf 버튼 실행"
    bl_options = {"INTERNAL"}  # 실행되는 Operator 가 각자 Undo 단계를 만든다

    tab_id: StringProperty(options={"SKIP_SAVE"})
    button_id: StringProperty(options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context, props):
        b = S.shelf.button(props.tab_id, props.button_id)
        if b is None:
            return "버튼을 찾을 수 없습니다"
        lines = [b.tooltip or b.title, ""]
        if b.kind == "operator":
            lines.append(f"Operator: {b.target}")
            shortcut = keymap_registry.find_shortcut(b.target, b.properties)
            if shortcut:
                lines.append(f"단축키: {shortcut}")
        elif b.kind == "menu":
            lines.append(f"메뉴: {b.target}")
        elif b.kind == "preset":
            lines.append("프리셋: " + " → ".join(s.target for s in b.steps))
        elif b.kind == "script":
            lines.append(f"스크립트: {b.target}")
        if b.properties:
            lines.append("프로퍼티: " + ", ".join(f"{k}={v}" for k, v in b.properties.items()))
        if b.requires_mode:
            lines.append(f"요구 모드: {context_guard.modes_label(b.requires_mode)}")
        if b.area != "VIEW_3D":
            lines.append(f"실행 영역: {context_guard.AREA_LABELS.get(b.area, b.area)}")
        if b.addon:
            lines.append(f"제공 확장: {b.addon}")
        a = context_guard.check(context, b)
        if not a.ok:
            lines += ["", f"⚠ {a.reason}"]
        return "\n".join(lines)

    def execute(self, context):
        b = S.shelf.button(self.tab_id, self.button_id)
        if b is None:
            self.report({"ERROR"}, "버튼을 찾을 수 없습니다")
            return {"CANCELLED"}
        ok, msg = context_guard.run(context, b)
        if not ok:
            self.report({"WARNING"}, msg)
            return {"CANCELLED"}
        return {"FINISHED"}


class MAYAUX_OT_set_tab(bpy.types.Operator):
    bl_idname = "maya_ux.set_tab"
    bl_label = "Shelf 탭"
    bl_options = {"INTERNAL"}

    tab_id: StringProperty()

    @classmethod
    def description(cls, context, props):
        t = S.shelf.tab(props.tab_id)
        return f"{t.title} 탭 ({len(t.buttons)}개 버튼)" if t else ""

    def execute(self, context):
        context.window_manager.maya_ux_active_tab = self.tab_id
        return {"FINISHED"}


_EDITOR_TYPES = [
    ("FCURVES", "Graph Editor", "", "GRAPH", 0),
    ("DOPESHEET", "Dope Sheet", "", "ACTION", 1),
    ("NLA_EDITOR", "NLA", "", "NLA", 2),
    ("OUTLINER", "Outliner", "", "OUTLINER", 3),
    ("PROPERTIES", "Properties", "", "PROPERTIES", 4),
    ("ShaderNodeTree", "Shader Editor", "", "NODE_MATERIAL", 5),
    ("UV", "UV Editor", "", "UV", 6),
    ("TEXT_EDITOR", "Text Editor", "", "TEXT", 7),
]


class MAYAUX_OT_open_editor(bpy.types.Operator):
    """편집기를 별도 창으로 연다 (Maya Windows 메뉴처럼)"""

    bl_idname = "maya_ux.open_editor"
    bl_label = "편집기 창 열기"

    editor_type: EnumProperty(items=_EDITOR_TYPES, name="편집기")
    properties_context: StringProperty(name="Properties 탭", default="")

    @classmethod
    def poll(cls, context):
        return context.screen is not None and context.window is not None

    def execute(self, context):
        wm = context.window_manager
        src = context.area or context.screen.areas[0]
        region = next((r for r in src.regions if r.type == "WINDOW"), context.region)
        before = {w.as_pointer() for w in wm.windows}
        try:
            with context.temp_override(window=context.window, area=src, region=region):
                bpy.ops.screen.area_dupli("INVOKE_DEFAULT")
        except RuntimeError as e:
            self.report({"WARNING"}, f"새 창을 열 수 없습니다: {e}")
            return {"CANCELLED"}
        new = [w for w in wm.windows if w.as_pointer() not in before]
        if not new:
            self.report({"WARNING"}, "새 창을 열 수 없습니다 (창 관리자 제한)")
            return {"CANCELLED"}
        area = new[0].screen.areas[0]
        area.ui_type = self.editor_type
        if self.editor_type == "PROPERTIES" and self.properties_context:
            try:
                area.spaces.active.context = self.properties_context
            except TypeError:
                pass
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# 내보내기 / 가져오기
# ---------------------------------------------------------------------------

class MAYAUX_OT_export_config(bpy.types.Operator, ExportHelper):
    """Shelf 와 키맵 설정을 JSON 파일로 내보낸다"""

    bl_idname = "maya_ux.export_config"
    bl_label = "MayaUX 설정 내보내기"

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})
    include_shelf: BoolProperty(name="Shelf 포함", default=True)
    include_keymap: BoolProperty(name="키맵 설정 포함", default=True)

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = "maya_ux_config.json"
        return super().invoke(context, event)

    def execute(self, context):
        if not (self.include_shelf or self.include_keymap):
            self.report({"WARNING"}, "내보낼 항목을 하나 이상 고르세요")
            return {"CANCELLED"}
        data = json_io.build_export(S.shelf if self.include_shelf else None,
                                    S.keymap if self.include_keymap else None, state.meta())
        try:
            json_io.write_atomic(self.filepath, json_io.dumps(data))
        except OSError as e:
            self.report({"ERROR"}, f"저장 실패: {e}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"내보냄: {self.filepath}")
        return {"FINISHED"}


_pending: dict = {}


class MAYAUX_OT_import_config(bpy.types.Operator, ImportHelper):
    """JSON 설정을 읽어 미리보기 후 적용한다 (스크립트는 자동 실행되지 않음)"""

    bl_idname = "maya_ux.import_config"
    bl_label = "MayaUX 설정 가져오기"

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        try:
            preview = json_io.parse(json_io.read_text(self.filepath))
        except (OSError, ValidationError) as e:
            self.report({"ERROR"}, f"가져오기 실패: {e}")
            return {"CANCELLED"}
        _pending["preview"] = preview
        _pending["path"] = self.filepath
        bpy.ops.maya_ux.import_preview("INVOKE_DEFAULT")
        return {"FINISHED"}


class MAYAUX_OT_import_preview(bpy.types.Operator):
    bl_idname = "maya_ux.import_preview"
    bl_label = "가져오기 미리보기"
    bl_options = {"INTERNAL"}

    mode: EnumProperty(
        name="Shelf",
        items=[("REPLACE", "교체", "현재 Shelf 를 가져온 내용으로 바꿉니다"),
               ("MERGE", "병합", "가져온 탭/버튼을 현재 Shelf 에 추가합니다"),
               ("SKIP", "건너뜀", "Shelf 는 가져오지 않습니다")],
        default="REPLACE",
    )
    apply_keymap: BoolProperty(name="키맵 설정 적용", default=True)

    def invoke(self, context, event):
        if "preview" not in _pending:
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self, width=560)

    def draw(self, context):
        pv = _pending.get("preview")
        if pv is None:
            return
        col = self.layout.column(align=True)
        col.label(text=os.path.basename(_pending.get("path", "")), icon="FILE")
        meta = pv.meta
        if meta:
            col.label(text=f"만든 환경: Blender {meta.get('blender_version', '?')} · {meta.get('os', '?')} · "
                           f"MayaUX {meta.get('addon_version', '?')}")
        for m in pv.migrations:
            col.label(text=f"스키마 변환: {m}", icon="FILE_REFRESH")
        if pv.shelf:
            n = sum(len(t.buttons) for t in pv.shelf.tabs)
            box = self.layout.box()
            box.label(text=f"Shelf: 탭 {len(pv.shelf.tabs)}개, 버튼 {n}개", icon="TOOL_SETTINGS")
            box.row().prop(self, "mode", expand=True)
            missing = []
            for t, b in pv.shelf.all_buttons():
                if b.kind == "script":
                    continue
                a = context_guard._static_check(b)
                if a.missing:
                    missing.append(f"{t.title} / {b.title}: {b.target or b.kind}" + (f" ({b.addon})" if b.addon else ""))
            if missing:
                box.label(text=f"이 환경에 없는 명령 {len(missing)}개 (버튼은 비활성으로 표시됨):", icon="ERROR")
                for line in missing[:8]:
                    box.label(text="   " + line)
                if len(missing) > 8:
                    box.label(text=f"   … 외 {len(missing) - 8}개")
            deps = [d for d in meta.get("dependencies", []) if not AD.addon_enabled(d)]
            if deps:
                box.label(text="필요한 확장: " + ", ".join(deps), icon="PLUGIN")
            if pv.script_buttons:
                box.label(text=f"스크립트 버튼 {len(pv.script_buttons)}개 — 자동 실행되지 않으며 각각 신뢰 확인이 필요합니다",
                          icon="SCRIPT")
        if pv.keymap:
            box = self.layout.box()
            box.prop(self, "apply_keymap")
            box.label(text=f"키맵: 프로파일 {pv.keymap.profile}, 항목 {len(pv.keymap.mapping_ids)}개, "
                           f"대체 결정 {sum(1 for d in pv.keymap.decisions.values() if d == 'REPLACE')}개")
            box.label(text="적용 후 충돌은 Preferences > MayaUX 에서 다시 확인할 수 있습니다", icon="INFO")
        if pv.errors or pv.warnings:
            box = self.layout.box()
            box.label(text=f"건너뛴 항목/경고 {len(pv.errors) + len(pv.warnings)}개", icon="ERROR")
            for line in (pv.errors + pv.warnings)[:8]:
                box.label(text="   " + line[:110])

    def execute(self, context):
        pv = _pending.pop("preview", None)
        _pending.pop("path", None)
        if pv is None:
            return {"CANCELLED"}
        done = []
        if pv.shelf and self.mode != "SKIP":
            if self.mode == "REPLACE":
                S.shelf = pv.shelf
                done.append("Shelf 교체")
            else:
                added = S.shelf.merge(pv.shelf)
                done.append(f"버튼 {added}개 추가")
            state.save_shelf()
        if pv.keymap and self.apply_keymap:
            S.keymap = pv.keymap
            state.save_keymap()
            state.apply_keymap()
            done.append("키맵 적용")
        self.report({"INFO"}, "가져오기 완료: " + (", ".join(done) or "변경 없음"))
        return {"FINISHED"}

    def cancel(self, context):
        _pending.clear()


# ---------------------------------------------------------------------------
# 초기화 / 마법사
# ---------------------------------------------------------------------------

class MAYAUX_OT_reset(bpy.types.Operator):
    """MayaUX 설정을 기본값으로 되돌린다"""

    bl_idname = "maya_ux.reset"
    bl_label = "MayaUX 초기화"

    target: EnumProperty(items=[
        ("SHELF", "Shelf 기본값", "Shelf 를 기본 탭/버튼으로 되돌립니다"),
        ("KEYMAP", "Blender 키맵으로 복귀", "MayaUX 단축키를 모두 제거하고 끈 항목을 복원합니다"),
        ("CLEANUP", "제거 전 정리", "단축키 제거·복원 후 MayaUX 설정 파일을 삭제합니다 (확장 삭제 전에 실행)"),
    ])

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        if self.target == "SHELF":
            S.shelf = default_shelf()
            state.save_shelf()
            self.report({"INFO"}, "Shelf 를 기본값으로 되돌렸습니다")
        elif self.target == "KEYMAP":
            S.keymap.enabled = False
            S.keymap.decisions.clear()
            state.save_keymap()
            state.remove_keymap()
            msg = "MayaUX 단축키를 제거했습니다"
            if S.deactivated:
                msg += f" (복원하지 못한 항목 {len(S.deactivated)}개: 진단 참고)"
            self.report({"INFO"}, msg)
        else:
            state.remove_keymap()
            failed = list(S.deactivated)
            for name in ("shelf.json", "keymap.json", "local.json"):
                path = os.path.join(S.folder, name)
                if os.path.exists(path):
                    os.remove(path)
            S.keymap.enabled = False
            S.deactivated = []
            scripts.load_trust({})
            self.report({"INFO"}, "정리 완료. 이제 확장을 비활성화/삭제해도 됩니다" +
                        (f" — 복원 실패 {len(failed)}개는 Keymap 설정에서 직접 확인하세요" if failed else ""))
        return {"FINISHED"}


class MAYAUX_OT_setup_wizard(bpy.types.Operator):
    """처음 사용 설정: 기준 키맵, 프로파일, 충돌 처리 방식 선택"""

    bl_idname = "maya_ux.setup_wizard"
    bl_label = "MayaUX 설정 마법사"

    profile: EnumProperty(name="프로파일", items=[
        ("maya_basic", "Maya 기본", "IC 기준 + Maya 차이 항목 전부 (4/5/6/7 셰이딩, Z 실행취소 등)"),
        ("blender_hybrid", "Blender 절충", "IC 기준 보완 + 충돌이 적은 항목만"),
        ("custom", "사용자 정의", "Maya 기본에서 시작해 항목을 직접 켜고 끕니다"),
    ])
    activate_ic: BoolProperty(name="Industry Compatible 키맵 활성화 (권장)", default=True)
    conflicts: EnumProperty(name="충돌 처리", items=[
        ("KEEP", "기존 유지 후 하나씩 결정", "충돌하는 항목은 등록하지 않고 목록으로 보여줍니다"),
        ("REPLACE", "모두 MayaUX 로 대체", "충돌하는 기존 단축키를 끄고 MayaUX 를 적용합니다 (언제든 복원 가능)"),
    ])

    def invoke(self, context, event):
        self.activate_ic = not keymap_registry.is_industry_compatible()
        self.profile = S.keymap.profile
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, context):
        col = self.layout.column()
        name = keymap_registry.active_keyconfig_name() or "?"
        if keymap_registry.is_industry_compatible():
            col.label(text=f"현재 키맵: {name} ✓", icon="CHECKMARK")
        else:
            col.label(text=f"현재 키맵: {name}", icon="INFO")
            col.prop(self, "activate_ic")
        col.separator()
        col.label(text="1. 프로파일")
        col.prop(self, "profile", expand=True)
        col.separator()
        col.label(text="2. 단축키 충돌 처리")
        col.prop(self, "conflicts", expand=True)
        col.separator()
        col.label(text="Shelf 는 3D 뷰포트 사이드바(N) > MayaUX 탭에 있습니다.", icon="INFO")

    def execute(self, context):
        if self.activate_ic and not keymap_registry.is_industry_compatible():
            path = bpy.utils.preset_find("Industry_Compatible", "keyconfig")
            if path:
                bpy.ops.preferences.keyconfig_activate(filepath=path)
            else:
                self.report({"WARNING"}, "Industry Compatible 프리셋을 찾을 수 없습니다")
        S.keymap.set_profile(self.profile)
        S.keymap.enabled = True
        state.apply_keymap()
        if self.conflicts == "REPLACE":
            for mid, a in keymap_registry.analyses.items():
                if a.status == C.CONFLICT:
                    S.keymap.decisions[mid] = "REPLACE"
            state.apply_keymap()
        S.wizard_done = True
        state.save_keymap()
        state.save_local()
        n_conf = sum(1 for a in keymap_registry.analyses.values() if a.status == C.CONFLICT)
        self.report({"INFO"}, "MayaUX 설정 완료" + (f" — 충돌 {n_conf}개는 Preferences 에서 확인하세요" if n_conf else ""))
        return {"FINISHED"}


class MAYAUX_OT_refresh(bpy.types.Operator):
    """설치된 확장 목록·명령 검색 목록을 갱신하고 단축키 충돌을 다시 검사한다"""

    bl_idname = "maya_ux.refresh"
    bl_label = "다시 검사"

    def execute(self, context):
        registry.refresh()
        if S.keymap.enabled:
            state.apply_keymap()
        state._redraw()
        return {"FINISHED"}


classes = (
    MAYAUX_OT_run_button,
    MAYAUX_OT_set_tab,
    MAYAUX_OT_open_editor,
    MAYAUX_OT_export_config,
    MAYAUX_OT_import_config,
    MAYAUX_OT_import_preview,
    MAYAUX_OT_reset,
    MAYAUX_OT_setup_wizard,
    MAYAUX_OT_refresh,
)
