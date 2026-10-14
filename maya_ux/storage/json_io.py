"""설정 JSON 내보내기/가져오기 (bpy 비의존).

내보내기 파일 구조 (schema_version 1)::

    {
      "schema_version": 1,
      "format": "maya_ux_config",
      "meta": {"blender_version", "os", "addon_version", "exported_at", "dependencies": [...]},
      "profile": "maya_basic",
      "tabs": [...],                # PRD 6.2 의 Shelf 구조
      "keymap": {...}               # 선택: 키맵 프로파일/항목/충돌 결정
    }

스크립트 신뢰 정보와 '끈 키맵 항목' 기록은 기기별 정보라서 포함하지 않는다.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field

from ..keymap.mappings import KeymapState
from ..shelf.model import SCHEMA_VERSION, Shelf, ValidationError
from .migration import migrate

FORMAT = "maya_ux_config"
MAX_BYTES = 5 * 1024 * 1024


def build_export(shelf: Shelf | None, keymap: KeymapState | None, meta: dict) -> dict:
    data = {"schema_version": SCHEMA_VERSION, "format": FORMAT, "meta": dict(meta)}
    if shelf is not None:
        sd = shelf.to_dict()
        data["profile"] = sd["profile"]
        data["tabs"] = sd["tabs"]
        deps = sorted({b.addon for _, b in shelf.all_buttons() if b.addon})
        data["meta"]["dependencies"] = deps
    if keymap is not None:
        data["keymap"] = keymap.to_dict()
    return data


def dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


@dataclass
class ImportPreview:
    shelf: Shelf | None = None
    keymap: KeymapState | None = None
    meta: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)  # 건너뛴 항목
    warnings: list = field(default_factory=list)
    migrations: list = field(default_factory=list)

    @property
    def script_buttons(self) -> list:
        if not self.shelf:
            return []
        return [(t.title, b) for t, b in self.shelf.all_buttons() if b.kind == "script"]


def parse(text: str) -> ImportPreview:
    """텍스트를 검증해 미리보기를 만든다. 치명적 오류는 ValidationError."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValidationError(f"JSON 형식 오류 (줄 {e.lineno}, 칸 {e.colno}): {e.msg}") from None
    data, steps = migrate(raw)
    fmt = data.get("format", FORMAT)
    if fmt != FORMAT:
        raise ValidationError(f"MayaUX 설정 파일이 아닙니다 (format: {fmt})")
    pv = ImportPreview(meta=data.get("meta") if isinstance(data.get("meta"), dict) else {}, migrations=steps)
    if "tabs" in data:
        pv.shelf, pv.errors = Shelf.from_dict(data)
    if "keymap" in data:
        try:
            pv.keymap, kw = KeymapState.from_dict(data["keymap"])
            pv.warnings.extend(kw)
        except ValueError as e:
            pv.errors.append(f"keymap: {e}")
    if pv.shelf is None and pv.keymap is None:
        raise ValidationError("가져올 Shelf(tabs) 나 keymap 정보가 없습니다")
    return pv


def read_text(path: str) -> str:
    size = os.path.getsize(path)
    if size > MAX_BYTES:
        raise ValidationError(f"파일이 너무 큽니다 ({size // 1024} KB > {MAX_BYTES // 1024} KB)")
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


def write_atomic(path: str, text: str) -> None:
    """임시 파일에 쓴 뒤 교체해 저장 중 오류로 설정이 깨지지 않게 한다."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".maya_ux_", suffix=".json", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def load_json(path: str, default):
    """내부 설정 파일 읽기. 깨진 파일은 .bak 로 보존하고 기본값 사용."""
    if not os.path.isfile(path):
        return default, ""
    try:
        return json.loads(read_text(path)), ""
    except (OSError, ValueError, ValidationError) as e:
        backup = path + ".broken"
        try:
            os.replace(path, backup)
        except OSError:
            backup = ""
        return default, f"{os.path.basename(path)} 를 읽지 못해 기본값을 사용합니다 ({e}). 원본: {backup}"
