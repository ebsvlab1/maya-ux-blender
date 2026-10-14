"""실제 Blender(bpy 모듈)로 실행하는 통합 테스트. bpy 가 없으면 건너뛴다.

    pip install bpy pytest   # bpy 버전은 테스트할 Blender 버전과 맞춘다 (4.5 → Python 3.11)
    python -m pytest maya_ux/tests
"""

import os
import sys

import pytest

bpy = pytest.importorskip("bpy")

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAMPLES = os.path.join(REPO, "maya_ux_samples")
for p in (REPO, SAMPLES):
    if p not in sys.path:
        sys.path.insert(0, p)

import maya_ux  # noqa: E402
from maya_ux import state  # noqa: E402
from maya_ux.integrations import addon_discovery as AD  # noqa: E402
from maya_ux.integrations import context_guard, scripts  # noqa: E402
from maya_ux.keymap import conflicts as C  # noqa: E402
from maya_ux.keymap import registry  # noqa: E402
from maya_ux.keymap.mappings import MAPPINGS, KeymapState  # noqa: E402
from maya_ux.shelf.model import Button, default_shelf  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def addon(tmp_path_factory):
    folder = str(tmp_path_factory.mktemp("cfg"))
    orig = state.config_folder
    state.config_folder = lambda: folder
    maya_ux.register()
    yield folder
    maya_ux.unregister()
    state.config_folder = orig


@pytest.fixture
def sample_addon():
    import mayaux_sample_addon

    mayaux_sample_addon.register()
    yield
    mayaux_sample_addon.unregister()


@pytest.fixture(scope="module")
def industry_compatible():
    bpy.ops.preferences.keyconfig_activate(filepath=bpy.utils.preset_find("Industry_Compatible", "keyconfig"))
    assert registry.is_industry_compatible()


def test_default_shelf_targets_exist_in_this_blender():
    missing = []
    for _tab, b in default_shelf().all_buttons():
        if b.addon:
            continue
        if b.kind == "operator" and not AD.operator_exists(b.target):
            missing.append(b.target)
        if b.kind == "menu" and not AD.menu_exists(b.target):
            missing.append(b.target)
        for s in b.steps:
            if not AD.operator_exists(s.target):
                missing.append(s.target)
        if b.target == "wm.tool_set_by_id":
            assert b.properties["name"].startswith("builtin.")
    assert not missing, missing


def test_keymap_targets_exist():
    assert [m.idname for m in MAPPINGS if not AD.operator_exists(m.idname)] == []


def test_addon_operator_availability(sample_addon):
    b = default_shelf().button("custom", "sample_freeze")
    assert context_guard._static_check(b).ok
    assert AD.operator_owner("mayaux_sample.freeze_transforms") == "mayaux_sample_addon"
    assert AD.operator_owner("mesh.primitive_cube_add") == ""
    assert any(op[0] == "mayaux_sample.random_color" for op in AD.list_operators(refresh=True))


def test_missing_addon_button_is_disabled_with_guidance():
    b = default_shelf().button("custom", "sample_freeze")
    a = context_guard._static_check(b)
    assert not a.ok and a.missing
    assert "mayaux_sample_addon" in a.reason and "설치" in a.reason
    b = Button.from_dict({"id": "x", "target": "nope.not_here"})
    assert "없습니다" in context_guard._static_check(b).reason


def test_run_operator_preset_and_mode_guard():
    ctx = bpy.context
    n = len(bpy.data.objects)
    preset = default_shelf().button("custom", "smooth_cube")
    preset.area = "ANY"
    ok, msg = context_guard.run(ctx, preset)
    assert ok, msg
    assert len(bpy.data.objects) == n + 1
    assert ctx.active_object.modifiers[-1].type == "SUBSURF"

    edit_only = default_shelf().button("modeling", "extrude")
    edit_only.area = "ANY"
    ok, msg = context_guard.run(ctx, edit_only)
    assert not ok and "Edit Mode" in msg

    wrong_props = Button.from_dict({"id": "w", "target": "mesh.primitive_cube_add", "properties": {"nope": 1},
                                    "context_policy": "EXEC_DEFAULT", "area": "ANY"})
    ok, msg = context_guard.run(ctx, wrong_props)
    assert not ok and "프로퍼티" in msg


def test_script_trust_flow(tmp_path):
    path = tmp_path / "tool.py"
    path.write_text("bpy.context.scene['maya_ux_test'] = 1\n", encoding="utf-8")
    b = Button.from_dict({"id": "s", "kind": "script", "target": str(path), "area": "ANY"})
    scripts.set_allowed(False)
    assert scripts.status(str(path)) == scripts.DISABLED
    scripts.set_allowed(True)
    try:
        assert scripts.status(str(path)) == scripts.UNTRUSTED
        ok, msg = context_guard.run(bpy.context, b)
        assert not ok and "신뢰" in msg
        scripts.trust(str(path))
        ok, msg = context_guard.run(bpy.context, b)
        assert ok, msg
        assert bpy.context.scene["maya_ux_test"] == 1
        path.write_text("raise SystemExit\n", encoding="utf-8")
        assert scripts.status(str(path)) == scripts.CHANGED
    finally:
        scripts.set_allowed(False)
        scripts.load_trust({})


def test_keymap_on_industry_compatible(industry_compatible):
    state.S.keymap = KeymapState()
    state.S.deactivated = []
    state.apply_keymap()
    st = {mid: a.status for mid, a in registry.analyses.items()}
    for mid in ("tool_q_object", "tool_w_mesh", "nav_orbit", "nav_pan", "nav_zoom", "frame_selected",
                "frame_all", "duplicate_obj", "key_all_obj", "play", "graph_frame_sel", "repeat_last"):
        assert st[mid] == C.BASELINE, (mid, st[mid])
    assert st["shade_wire"] == C.CONFLICT
    assert st["undo_z"] == C.CONFLICT
    assert st["pivot_edit"] == C.FREE
    assert st["hotbox"] == C.DISABLED
    ours = registry.registered_items()
    assert any(i.idname == "wm.context_toggle" and i.event.type == "INSERT" for i in ours)
    assert not any(i.event.type == "FOUR" for i in ours)  # 충돌 → 기본은 '유지'


def _user_item(keymap, idname, type_):
    km = bpy.context.window_manager.keyconfigs.user.keymaps[keymap]
    return [k for k in km.keymap_items if k.idname == idname and k.type == type_]


def test_replace_and_restore(industry_compatible):
    state.S.keymap = KeymapState()
    state.S.keymap.decisions["shade_wire"] = "REPLACE"
    state.S.deactivated = []
    state.apply_keymap()
    assert registry.analyses["shade_wire"].status == C.REPLACED
    assert all(not k.active for k in _user_item("Object Non-modal", "object.mode_set", "FOUR"))
    assert len(state.S.deactivated) == 1
    assert any(i.event.type == "FOUR" for i in registry.registered_items())

    # 다시 적용해도 기록이 중복되지 않는다 (재시작 시나리오)
    state.apply_keymap()
    assert len(state.S.deactivated) == 1

    state.remove_keymap()
    assert state.S.deactivated == []
    assert all(k.active for k in _user_item("Object Non-modal", "object.mode_set", "FOUR"))
    assert registry.registered_items() == []


def test_shortcut_lookup(industry_compatible):
    assert "F" in registry.find_shortcut("view3d.view_selected", {})


def test_state_files_written(addon):
    state.save_shelf()
    state.save_keymap()
    state.save_local()
    assert sorted(f for f in os.listdir(addon) if f.endswith(".json")) == ["keymap.json", "local.json", "shelf.json"]
    state.load()
    assert state.S.shelf.to_dict() == default_shelf().to_dict()
