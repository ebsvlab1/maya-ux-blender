"""MayaUX for Blender — Maya형 키맵 프로파일 + Shelf 확장.

Blender 데이터 구조·렌더러·편집기는 그대로 두고, Maya 에 익숙한 조작(단축키)과
Shelf(빠른 명령 버튼)만 추가한다. 모든 변경은 확장을 끄면 원래대로 돌아간다.
"""

import bpy
from bpy.props import BoolProperty, StringProperty

from . import preferences, state
from .integrations import scripts
from .keymap import operators as keymap_operators
from .shelf import editor, operators, panel

_classes = (
    *preferences.classes,
    *operators.classes,
    *editor.classes,
    *keymap_operators.classes,
    *panel.classes,
)


def _deferred_apply():
    # 시작 직후에는 사용자 키맵이 아직 준비되지 않았을 수 있어 한 박자 늦게 적용한다.
    try:
        if state.S.keymap.enabled:
            state.apply_keymap()
    except Exception as e:  # noqa: BLE001 - 시작 시 키맵 오류로 Blender 사용을 막지 않음
        print(f"[MayaUX] 키맵 적용 실패: {e}")
    return None


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.maya_ux_active_tab = StringProperty(default="general")
    bpy.types.WindowManager.maya_ux_edit = BoolProperty(name="Shelf 편집", description="Shelf 편집 모드", default=False)
    state.load()
    prefs = preferences.get_prefs()
    scripts.set_allowed(bool(prefs and prefs.allow_scripts))
    bpy.types.VIEW3D_HT_header.append(panel.draw_header_button)
    bpy.app.timers.register(_deferred_apply, first_interval=0.5)


def unregister():
    if bpy.app.timers.is_registered(_deferred_apply):
        bpy.app.timers.unregister(_deferred_apply)
    # 확장을 끄면 MayaUX 단축키를 제거하고, 대체하느라 껐던 기존 단축키를 되살린다.
    state.remove_keymap()
    bpy.types.VIEW3D_HT_header.remove(panel.draw_header_button)
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.WindowManager.maya_ux_active_tab
    del bpy.types.WindowManager.maya_ux_edit
