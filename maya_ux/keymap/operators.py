"""키맵 설정 Operator: 프로파일, 항목 켜기/끄기, 충돌 결정, 사용자 지정 키 입력."""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from .. import state
from ..state import S
from . import conflicts as C
from . import registry
from .mappings import MAPPINGS_BY_ID, PROFILES, KeyEvent


def _apply_and_save():
    state.save_keymap()
    if S.keymap.enabled:
        state.apply_keymap()
    else:
        state.remove_keymap()
    state._redraw()


class MAYAUX_OT_km_profile(bpy.types.Operator):
    """키맵 프로파일 선택"""

    bl_idname = "maya_ux.km_profile"
    bl_label = "프로파일"
    bl_options = {"INTERNAL"}

    profile: EnumProperty(items=[(k, k, v) for k, v in PROFILES.items()])

    @classmethod
    def description(cls, context, props):
        return PROFILES.get(props.profile, "")

    def execute(self, context):
        S.keymap.set_profile(self.profile)
        _apply_and_save()
        return {"FINISHED"}


class MAYAUX_OT_km_enable(bpy.types.Operator):
    """MayaUX 단축키 전체 켜기/끄기 (끄면 Blender 키맵 그대로 복귀)"""

    bl_idname = "maya_ux.km_enable"
    bl_label = "MayaUX 단축키"
    bl_options = {"INTERNAL"}

    enable: BoolProperty()

    def execute(self, context):
        S.keymap.enabled = self.enable
        _apply_and_save()
        return {"FINISHED"}


class MAYAUX_OT_km_toggle(bpy.types.Operator):
    """이 단축키 항목 켜기/끄기 (프로파일이 '사용자 정의'로 바뀜)"""

    bl_idname = "maya_ux.km_toggle"
    bl_label = "항목 켜기/끄기"
    bl_options = {"INTERNAL"}

    mapping_id: StringProperty()
    on: BoolProperty()

    def execute(self, context):
        S.keymap.toggle(self.mapping_id, self.on)
        _apply_and_save()
        return {"FINISHED"}


class MAYAUX_OT_km_decide(bpy.types.Operator):
    """충돌 처리: 기존 유지 또는 MayaUX 로 대체"""

    bl_idname = "maya_ux.km_decide"
    bl_label = "충돌 처리"
    bl_options = {"INTERNAL"}

    mapping_id: StringProperty()
    decision: EnumProperty(items=[
        ("KEEP", "기존 유지", "기존 단축키를 유지하고 이 MayaUX 항목은 등록하지 않습니다"),
        ("REPLACE", "MayaUX 로 대체", "충돌하는 기존 단축키를 끄고 MayaUX 항목을 등록합니다. 언제든 되돌릴 수 있습니다"),
    ])

    def execute(self, context):
        if self.decision == "KEEP":
            S.keymap.decisions.pop(self.mapping_id, None)
        else:
            S.keymap.decisions[self.mapping_id] = "REPLACE"
        _apply_and_save()
        return {"FINISHED"}


class MAYAUX_OT_km_replace_all(bpy.types.Operator):
    """현재 충돌 항목을 모두 MayaUX 로 대체"""

    bl_idname = "maya_ux.km_replace_all"
    bl_label = "모든 충돌을 MayaUX 로 대체"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        for mid, a in registry.analyses.items():
            if a.status == C.CONFLICT:
                S.keymap.decisions[mid] = "REPLACE"
        _apply_and_save()
        return {"FINISHED"}


class MAYAUX_OT_km_keep_all(bpy.types.Operator):
    """모든 대체 결정을 취소하고 기존 단축키를 복원"""

    bl_idname = "maya_ux.km_keep_all"
    bl_label = "모든 충돌에서 기존 유지"

    def execute(self, context):
        S.keymap.decisions.clear()
        _apply_and_save()
        return {"FINISHED"}


_MODIFIER_KEYS = {"LEFT_CTRL", "RIGHT_CTRL", "LEFT_SHIFT", "RIGHT_SHIFT", "LEFT_ALT", "RIGHT_ALT", "OSKEY",
                  "MOUSEMOVE", "INBETWEEN_MOUSEMOVE", "TIMER", "TIMER_REPORT", "WINDOW_DEACTIVATE",
                  "LEFTMOUSE", "MIDDLEMOUSE", "RIGHTMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "NONE"}


class MAYAUX_OT_km_capture(bpy.types.Operator):
    """다음에 누르는 키 조합을 이 항목의 단축키로 지정 (Esc: 취소)"""

    bl_idname = "maya_ux.km_capture"
    bl_label = "키 지정"
    bl_options = {"INTERNAL"}

    mapping_id: StringProperty()
    waiting = {"id": ""}

    def invoke(self, context, event):
        if self.mapping_id not in MAPPINGS_BY_ID:
            return {"CANCELLED"}
        MAYAUX_OT_km_capture.waiting["id"] = self.mapping_id
        context.window_manager.modal_handler_add(self)
        self.report({"INFO"}, "지정할 키 조합을 누르세요 (Esc: 취소)")
        state._redraw()
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.value != "PRESS" or event.type in _MODIFIER_KEYS:
            return {"RUNNING_MODAL"}
        MAYAUX_OT_km_capture.waiting["id"] = ""
        if event.type == "ESC":
            state._redraw()
            return {"CANCELLED"}
        S.keymap.overrides[self.mapping_id] = KeyEvent(event.type, "PRESS", event.ctrl, event.shift, event.alt,
                                                       event.oskey)
        S.keymap.decisions.pop(self.mapping_id, None)
        _apply_and_save()
        a = registry.analyses.get(self.mapping_id)
        if a and a.status == C.CONFLICT:
            self.report({"WARNING"}, f"{a.event.label()} 도 다른 단축키와 충돌합니다")
        return {"FINISHED"}


class MAYAUX_OT_km_clear_override(bpy.types.Operator):
    """사용자 지정 키를 지우고 기본 키로 되돌림"""

    bl_idname = "maya_ux.km_clear_override"
    bl_label = "기본 키로"
    bl_options = {"INTERNAL"}

    mapping_id: StringProperty()

    def execute(self, context):
        S.keymap.overrides.pop(self.mapping_id, None)
        _apply_and_save()
        return {"FINISHED"}


class MAYAUX_OT_km_mac_cmd(bpy.types.Operator):
    """macOS: Ctrl 조합 단축키를 Cmd 로 등록"""

    bl_idname = "maya_ux.km_mac_cmd"
    bl_label = "Ctrl → Cmd"
    bl_options = {"INTERNAL"}

    on: BoolProperty()

    def execute(self, context):
        S.keymap.mac_ctrl_as_cmd = self.on
        _apply_and_save()
        return {"FINISHED"}


classes = (
    MAYAUX_OT_km_profile,
    MAYAUX_OT_km_enable,
    MAYAUX_OT_km_toggle,
    MAYAUX_OT_km_decide,
    MAYAUX_OT_km_replace_all,
    MAYAUX_OT_km_keep_all,
    MAYAUX_OT_km_capture,
    MAYAUX_OT_km_clear_override,
    MAYAUX_OT_km_mac_cmd,
)
