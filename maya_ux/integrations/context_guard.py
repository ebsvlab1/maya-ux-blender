"""버튼 실행 가능 여부 판단과 올바른 컨텍스트에서의 실행.

Sidebar(UI 영역)에서 누른 버튼이라도 많은 Operator 는 3D 뷰의 WINDOW 영역 컨텍스트를
요구한다. 여기서는 대상 영역을 찾아 temp_override 로 실행하고, 실패하면 사용자가 이해할
수 있는 이유를 돌려준다.
"""

from __future__ import annotations

from dataclasses import dataclass

import bpy

from . import addon_discovery as AD
from . import scripts

MODE_LABELS = {
    "OBJECT": "Object Mode",
    "EDIT_MESH": "Edit Mode(Mesh)",
    "EDIT_CURVE": "Edit Mode(Curve)",
    "EDIT_ARMATURE": "Edit Mode(Armature)",
    "POSE": "Pose Mode",
    "SCULPT": "Sculpt Mode",
    "PAINT_WEIGHT": "Weight Paint",
    "PAINT_VERTEX": "Vertex Paint",
    "PAINT_TEXTURE": "Texture Paint",
}
AREA_LABELS = {
    "VIEW_3D": "3D Viewport",
    "GRAPH_EDITOR": "Graph Editor",
    "DOPESHEET_EDITOR": "Dope Sheet",
    "NLA_EDITOR": "NLA Editor",
}


@dataclass
class Availability:
    ok: bool
    reason: str = ""
    missing: bool = False  # 명령 자체가 없음(애드온 누락 등)


def modes_label(modes) -> str:
    return ", ".join(MODE_LABELS.get(m, m) for m in modes)


def find_area(context, area_type: str):
    if area_type == "ANY":
        return context.area
    if context.area and context.area.type == area_type:
        return context.area
    screen = context.screen
    if screen is None:
        return None
    for area in screen.areas:
        if area.type == area_type:
            return area
    return None


def _window_region(area):
    for region in area.regions:
        if region.type == "WINDOW":
            return region
    return None


def override_kwargs(context, area_type: str):
    """(kwargs, 실패 이유)"""
    area = find_area(context, area_type)
    if area is None and area_type == "ANY":
        return {}, ""  # 영역과 무관한 명령: 현재 컨텍스트 그대로
    if area is None:
        return None, f"{AREA_LABELS.get(area_type, area_type)} 영역이 현재 화면에 없습니다"
    region = _window_region(area) or context.region
    kw = {"area": area, "region": region}
    if context.window is not None:
        kw["window"] = context.window
    return kw, ""


def _missing_reason(button, what: str) -> str:
    if button.addon:
        if AD.addon_enabled(button.addon):
            return f"{what} 이(가) 없습니다. '{button.addon}' 확장 버전이 바뀌었을 수 있습니다"
        return (f"'{button.addon}' 확장이 설치/활성화되어 있지 않습니다. "
                "Edit > Preferences > Get Extensions 에서 설치 후 활성화하세요")
    return f"{what} 이(가) 이 Blender 버전에 없습니다"


def _convert_props(op, props: dict) -> dict:
    """JSON 의 목록 값을 enum-flag 프로퍼티에 맞게 set 으로 바꾼다."""
    if not props:
        return {}
    out = dict(props)
    try:
        rna_props = op.get_rna_type().properties
    except (KeyError, AttributeError):
        return out
    for key, value in props.items():
        p = rna_props.get(key)
        if p is not None and p.type == "ENUM" and getattr(p, "is_enum_flag", False) and isinstance(value, list):
            out[key] = set(value)
    return out


def _static_check(button) -> Availability:
    if not button.enabled:
        return Availability(False, "사용자가 이 버튼을 비활성화했습니다")
    if button.kind == "operator":
        if not AD.operator_exists(button.target):
            return Availability(False, _missing_reason(button, f"명령 {button.target}"), missing=True)
    elif button.kind == "menu":
        if not AD.menu_exists(button.target):
            return Availability(False, _missing_reason(button, f"메뉴 {button.target}"), missing=True)
    elif button.kind == "preset":
        for step in button.steps:
            exists = AD.operator_exists(step.target) if step.kind == "operator" else AD.menu_exists(step.target)
            if not exists:
                return Availability(False, _missing_reason(button, f"프리셋 단계 {step.target}"), missing=True)
    elif button.kind == "script":
        status = scripts.status(button.target)
        if status != scripts.OK:
            return Availability(False, scripts.STATUS_MESSAGES[status], missing=status == scripts.MISSING)
    return Availability(True)


def check(context, button, deep: bool = True) -> Availability:
    """버튼을 지금 실행할 수 있는지. deep=True 면 Operator poll() 까지 확인."""
    a = _static_check(button)
    if not a.ok:
        return a
    if button.requires_mode and context.mode not in button.requires_mode:
        return Availability(False, f"{modes_label(button.requires_mode)} 에서 사용할 수 있습니다 "
                                   f"(현재: {MODE_LABELS.get(context.mode, context.mode)})")
    kw, why = override_kwargs(context, button.area)
    if kw is None:
        return Availability(False, why)
    if deep and button.kind == "operator":
        op = AD.get_operator(button.target)
        try:
            with context.temp_override(**kw):
                if not op.poll(button.context_policy):
                    return Availability(False, "현재 선택/모드에서는 실행할 수 없습니다 (poll 실패)")
        except Exception:  # noqa: BLE001 - 패널 그리기 중 poll 확인 실패가 UI 를 깨뜨리지 않게
            pass  # poll 확인 자체가 불가능하면 실행 시점에 판단
    return Availability(True)


def _run_operator(context, kw, target, props, policy):
    op = AD.get_operator(target)
    with context.temp_override(**kw):
        if not op.poll(policy):
            raise RuntimeError("현재 선택/모드에서는 실행할 수 없습니다 (poll 실패)")
        return op(policy, **_convert_props(op, props))


def run(context, button):
    """(성공 여부, 메시지)"""
    a = check(context, button, deep=False)
    if not a.ok:
        return False, a.reason
    kw, why = override_kwargs(context, button.area)
    if kw is None:
        return False, why
    try:
        if button.kind == "operator":
            result = _run_operator(context, kw, button.target, button.properties, button.context_policy)
            if "CANCELLED" in result:
                return False, f"{button.title}: 취소되었습니다"
        elif button.kind == "menu":
            with context.temp_override(**kw):
                bpy.ops.wm.call_menu(name=button.target)
        elif button.kind == "preset":
            for i, step in enumerate(button.steps, 1):
                if step.kind == "menu":
                    with context.temp_override(**kw):
                        bpy.ops.wm.call_menu(name=step.target)
                    continue
                result = _run_operator(context, kw, step.target, step.properties, step.context_policy)
                if "CANCELLED" in result:
                    return False, f"{button.title}: {i}단계({step.target})가 취소되어 중단했습니다"
        elif button.kind == "script":
            with context.temp_override(**kw):
                scripts.run(button.target)
            bpy.ops.ed.undo_push(message=f"MayaUX: {button.title}")
    except TypeError as e:
        return False, f"{button.title}: 프로퍼티가 맞지 않습니다 — {e}"
    except RuntimeError as e:
        msg = str(e).replace("Error: ", "").strip()
        return False, f"{button.title}: {msg}"
    except Exception as e:  # noqa: BLE001 - 사용자 스크립트 오류를 UI 로 전달
        return False, f"{button.title}: {type(e).__name__}: {e}"
    return True, ""
