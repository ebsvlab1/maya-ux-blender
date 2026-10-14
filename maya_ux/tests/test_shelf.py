import copy
import json

import pytest

from maya_ux.keymap.mappings import KeymapState
from maya_ux.shelf.model import DEFAULT_SHELF, SCHEMA_VERSION, Button, Shelf, ValidationError, default_shelf
from maya_ux.storage import json_io
from maya_ux.storage.migration import migrate


def test_default_shelf_has_prd_tabs():
    shelf = default_shelf()
    assert [t.title for t in shelf.tabs] == ["General", "Modeling", "Animation", "Rigging", "Rendering", "Custom"]
    general = [b.title for b in shelf.tab("general").buttons]
    assert general == ["Select", "Move", "Rotate", "Scale", "Duplicate", "Delete", "Parent"]
    modeling = [b.title for b in shelf.tab("modeling").buttons]
    assert modeling == ["Cube", "Sphere", "Extrude", "Bevel", "Inset", "Loop Cut", "Boolean"]
    # Blender 명령 15개 이상 + 외부 애드온 명령 3개 이상 (Phase 2 성공 조건)
    blender_cmds = [b for _, b in shelf.all_buttons() if b.kind == "operator" and not b.addon]
    addon_cmds = [b for _, b in shelf.all_buttons() if b.addon == "mayaux_sample_addon"]
    assert len(blender_cmds) >= 15
    assert len(addon_cmds) == 3


def test_roundtrip_is_lossless():
    shelf = default_shelf()
    data = shelf.to_dict()
    again, errors = Shelf.from_dict(json.loads(json.dumps(data)))
    assert not errors
    assert again.to_dict() == data
    assert data["schema_version"] == SCHEMA_VERSION


def test_prd_sample_parses():
    sample = {
        "schema_version": 1,
        "profile": "maya_basic",
        "tabs": [{"id": "modeling", "title": "Modeling", "buttons": [{
            "id": "add_cube", "title": "Cube", "icon": "MESH_CUBE", "kind": "operator",
            "target": "mesh.primitive_cube_add", "properties": {}, "context_policy": "INVOKE_DEFAULT"}]}],
    }
    pv = json_io.parse(json.dumps(sample))
    assert pv.shelf.button("modeling", "add_cube").target == "mesh.primitive_cube_add"
    assert not pv.errors


@pytest.mark.parametrize("bad, message", [
    ({"id": "x", "kind": "operator", "target": "Not An Op"}, "Operator ID"),
    ({"id": "x", "kind": "shell", "target": "rm"}, "kind"),
    ({"id": "x y", "kind": "operator", "target": "a.b"}, "id"),
    ({"id": "x", "kind": "menu", "target": "mesh.foo"}, "메뉴 ID"),
    ({"id": "x", "kind": "operator", "target": "a.b", "properties": {"k": {"nested": 1}}}, "형식"),
    ({"id": "x", "kind": "operator", "target": "a.b", "requires_mode": ["FLY"]}, "requires_mode"),
    ({"id": "x", "kind": "operator", "target": "a.b", "context_policy": "EXEC_REGION_WIN"}, "context_policy"),
    ({"id": "x", "kind": "script", "target": "/tmp/evil.sh"}, ".py"),
    ({"id": "x", "kind": "preset", "steps": []}, "steps"),
    ({"id": "x", "kind": "preset", "steps": [{"kind": "script", "target": "a.py"}]}, "operator/menu"),
])
def test_button_validation(bad, message):
    with pytest.raises(ValidationError, match=message):
        Button.from_dict(bad)


def test_invalid_items_are_skipped_and_reported():
    data = copy.deepcopy(DEFAULT_SHELF)
    data["tabs"][0]["buttons"].append({"id": "bad", "kind": "operator", "target": "???"})
    data["tabs"][0]["buttons"].append(copy.deepcopy(data["tabs"][0]["buttons"][0]))  # 중복 id
    data["tabs"].append({"id": "general", "title": "dup"})
    shelf, errors = Shelf.from_dict(data)
    assert len(errors) == 3
    assert len(shelf.tab("general").buttons) == 7
    with pytest.raises(ValidationError):
        Shelf.from_dict(data, strict=True)


def test_editing_operations():
    shelf = default_shelf()
    assert shelf.move_button("general", "move", -1)
    assert [b.id for b in shelf.tab("general").buttons][:2] == ["move", "select"]
    assert not shelf.move_button("general", "move", -1)  # 이미 맨 앞
    assert shelf.move_tab("custom", -10)
    assert shelf.tabs[0].id == "custom"
    clone = shelf.duplicate_button("modeling", "add_cube")
    assert clone.id == "add_cube_2" and clone.target == "mesh.primitive_cube_add"
    assert shelf.move_button_to_tab("modeling", "add_cube_2", "general")
    assert shelf.button("general", "add_cube_2") is not None
    tab = shelf.add_tab("General")
    assert tab.id == "general_2"
    assert shelf.remove_tab("general_2") and shelf.tab("general_2") is None
    assert shelf.remove_button("general", "add_cube_2")


def test_merge_adds_only_new_or_changed():
    a, b = default_shelf(), default_shelf()
    assert a.merge(b) == 0
    b.tab("general").buttons[0].title = "Pick"
    b.add_tab("Team").buttons.append(Button.from_dict({"id": "t", "target": "mesh.primitive_cube_add"}))
    assert a.merge(b) == 2
    assert a.button("general", "select_2").title == "Pick"
    assert a.tab("team") is not None


def test_import_never_carries_script_trust(tmp_path):
    data = {"schema_version": 1, "format": "maya_ux_config", "tabs": [{"id": "c", "title": "C", "buttons": [
        {"id": "s", "kind": "script", "target": "/home/me/tool.py", "trusted": True, "sha256": "abc"}]}],
        "trusted_scripts": {"/home/me/tool.py": "abc"}}
    pv = json_io.parse(json.dumps(data))
    (_title, button), = pv.script_buttons
    assert button.to_dict().get("trusted") is None
    assert "trusted_scripts" not in json_io.build_export(pv.shelf, None, {})


def test_malformed_and_foreign_files():
    with pytest.raises(ValidationError, match="JSON"):
        json_io.parse("{not json")
    with pytest.raises(ValidationError, match="새로운"):
        json_io.parse(json.dumps({"schema_version": 99, "tabs": []}))
    with pytest.raises(ValidationError, match="MayaUX"):
        json_io.parse(json.dumps({"schema_version": 1, "format": "other", "tabs": []}))
    with pytest.raises(ValidationError, match="schema_version"):
        json_io.parse(json.dumps({"hello": 1}))
    with pytest.raises(ValidationError, match="가져올"):
        json_io.parse(json.dumps({"schema_version": 1}))


def test_v0_migration():
    old = {"shelves": [{"name": "Mine", "items": [{"label": "Cube", "command": "mesh.primitive_cube_add",
                                                    "args": {"size": 2}}]}]}
    data, steps = migrate(old)
    assert steps == ["v0 → v1"]
    shelf, errors = Shelf.from_dict(data)
    assert not errors
    b = shelf.tabs[0].buttons[0]
    assert (shelf.tabs[0].title, b.title, b.properties) == ("Mine", "Cube", {"size": 2})
    assert "shelves" in old  # 원본 불변


def test_export_import_roundtrip(tmp_path):
    shelf = default_shelf()
    km = KeymapState()
    km.set_profile("blender_hybrid")
    km.decisions["shade_wire"] = "REPLACE"
    data = json_io.build_export(shelf, km, {"blender_version": "4.5.3", "os": "Test"})
    assert data["meta"]["dependencies"] == ["looptools", "mayaux_sample_addon"]
    path = tmp_path / "cfg.json"
    json_io.write_atomic(str(path), json_io.dumps(data))
    pv = json_io.parse(json_io.read_text(str(path)))
    assert pv.shelf.to_dict()["tabs"] == shelf.to_dict()["tabs"]
    assert pv.keymap.to_dict() == km.to_dict()
    assert pv.meta["blender_version"] == "4.5.3"


def test_load_json_quarantines_broken_file(tmp_path):
    path = tmp_path / "shelf.json"
    path.write_text("{broken", encoding="utf-8")
    data, msg = json_io.load_json(str(path), "DEFAULT")
    assert data == "DEFAULT" and "기본값" in msg
    assert (tmp_path / "shelf.json.broken").exists() and not path.exists()
