from maya_ux.keymap import conflicts as C
from maya_ux.keymap.conflicts import KeyItem, analyze
from maya_ux.keymap.mappings import (MAPPINGS, MAPPINGS_BY_ID, KeyEvent, KeymapState, os_reserved_reason,
                                     platform_event, profile_mapping_ids)


def item(keymap, idname, type, value="PRESS", props=None, active=True, any_mod=False, **mods):
    return KeyItem(keymap, idname, KeyEvent(type, value, **mods), props or {}, active, any_mod)


def test_mapping_table_is_consistent():
    assert len(MAPPINGS_BY_ID) == len(MAPPINGS)
    for m in MAPPINGS:
        assert m.mode in ("ensure", "add")
        assert "." in m.idname
        assert m.priority in ("P0", "P1", "P2")
    # PRD 4.1 의 P0 항목이 모두 정의되어 있다
    for mid in ("tool_q_object", "tool_w_object", "tool_e_object", "tool_r_object", "nav_orbit", "nav_pan",
                "nav_zoom", "frame_selected", "frame_all", "duplicate_obj", "key_all_obj", "play"):
        assert MAPPINGS_BY_ID[mid].priority == "P0"


def test_profiles():
    maya = set(profile_mapping_ids("maya_basic"))
    hybrid = set(profile_mapping_ids("blender_hybrid"))
    assert hybrid < maya
    assert "undo_z" in maya and "undo_z" not in hybrid
    assert "hotbox" not in maya  # P2, 기본 비활성


def test_ensure_satisfied_by_baseline():
    m = MAPPINGS_BY_ID["tool_w_object"]
    items = {"Object Mode": [item("Object Mode", "wm.tool_set_by_id", "W", props={"name": "builtin.move"})]}
    assert analyze(m, m.event, items).status == C.BASELINE


def test_ensure_registers_when_missing():
    m = MAPPINGS_BY_ID["nav_orbit"]
    assert analyze(m, m.event, {}).status == C.FREE


def test_direct_conflict_and_shadow_conflict():
    m = MAPPINGS_BY_ID["shade_wire"]  # 3D View: 4
    items = {"Object Non-modal": [item("Object Non-modal", "object.mode_set", "FOUR", props={"mode": "OBJECT"})]}
    a = analyze(m, m.event, items)
    assert a.status == C.CONFLICT
    assert a.conflicts[0].idname == "object.mode_set"
    # 다른 편집기(Graph Editor) 키맵은 3D View 와 충돌하지 않는다
    assert analyze(m, m.event, {"Graph Editor": [item("Graph Editor", "x.y", "FOUR")]}).status == C.FREE


def test_inactive_and_identical_items_are_not_conflicts():
    m = MAPPINGS_BY_ID["undo_z"]
    assert analyze(m, m.event, {"Screen": [item("Screen", "view3d.zoom_border", "Z", active=False)]}).status == C.FREE
    assert analyze(m, m.event, {"Screen": [item("Screen", "ed.undo", "Z")]}).status == C.BASELINE


def test_modifiers_value_and_any():
    m = MAPPINGS_BY_ID["undo_z"]
    other_mod = {"Screen": [item("Screen", "ed.undo", "Z", ctrl=True)]}
    assert analyze(m, m.event, other_mod).status == C.FREE
    any_mod = {"Screen": [item("Screen", "foo.bar", "Z", any_mod=True)]}
    assert analyze(m, m.event, any_mod).status == C.CONFLICT
    click = {"Screen": [item("Screen", "foo.bar", "Z", value="CLICK")]}
    assert analyze(m, m.event, click).status == C.CONFLICT
    drag = {"Screen": [item("Screen", "foo.bar", "Z", value="CLICK_DRAG")]}
    assert analyze(m, m.event, drag).status == C.FREE


def test_os_reserved_keys():
    assert os_reserved_reason(KeyEvent("SPACE", ctrl=True), "darwin")
    assert os_reserved_reason(KeyEvent("SPACE", ctrl=True), "linux") is None
    assert os_reserved_reason(KeyEvent("F4", alt=True), "win32")
    m = MAPPINGS_BY_ID["maximize_area"]
    assert analyze(m, m.event, {}, platform="darwin").status == C.RESERVED
    assert analyze(m, m.event, {}, platform="win32").status == C.FREE


def test_mac_ctrl_as_cmd():
    ev = KeyEvent("D", ctrl=True)
    assert platform_event(ev, "darwin", True) == KeyEvent("D", oskey=True)
    assert platform_event(ev, "darwin", False) == ev
    assert platform_event(ev, "win32", True) == ev


def test_disabled_mapping():
    m = MAPPINGS_BY_ID["undo_z"]
    assert analyze(m, m.event, {}, enabled=False).status == C.DISABLED


def test_state_roundtrip_and_custom_profile():
    st = KeymapState()
    st.toggle("undo_z", False)
    assert st.profile == "custom" and "undo_z" not in st.mapping_ids
    st.overrides["pivot_edit"] = KeyEvent("D", alt=True)
    st.decisions["shade_wire"] = "REPLACE"
    again, warnings = KeymapState.from_dict(st.to_dict())
    assert not warnings
    assert again.to_dict() == st.to_dict()
    assert again.event_for(MAPPINGS_BY_ID["pivot_edit"]).label() == "Alt + D"


def test_state_from_future_or_bad_data():
    st, warnings = KeymapState.from_dict({"profile": "nope", "mappings": ["undo_z", "from_v9"],
                                          "decisions": {"undo_z": "DELETE_ALL"}, "overrides": {"undo_z": {}}})
    assert st.profile == "maya_basic"
    assert st.mapping_ids == ["undo_z"]
    assert st.decisions == {}
    assert len(warnings) == 3


def test_event_labels():
    assert KeyEvent("LEFTMOUSE", alt=True).label() == "Alt + LMB"
    assert KeyEvent("PERIOD", shift=True).label() == "Shift + ."


def test_global_mapping_is_shadowed_by_editor_keymap():
    m = MAPPINGS_BY_ID["undo_z"]  # Screen: Z
    items = {"3D View": [item("3D View", "view3d.zoom_border", "Z")]}
    a = analyze(m, m.event, items)
    assert a.status == C.CONFLICT and a.conflicts[0].keymap == "3D View"
