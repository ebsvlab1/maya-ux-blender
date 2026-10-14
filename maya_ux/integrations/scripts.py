"""사용자 Python 스크립트 버튼.

보안 원칙
* 사용자가 직접 고르고 '신뢰' 를 확인한 로컬 .py 파일만 실행한다.
* 신뢰 정보(경로 + SHA-256)는 이 컴퓨터의 설정 폴더에만 저장하며 내보내기 파일에
  포함하지 않는다. 그래서 가져온 Shelf 의 스크립트 버튼은 항상 '신뢰 필요' 상태다.
* 신뢰 후 파일 내용이 바뀌면 다시 확인을 요구한다.
* 샌드박스가 아니다. 스크립트는 Blender 와 같은 권한으로 실행된다.
"""

from __future__ import annotations

import hashlib
import os

OK = "OK"
DISABLED = "DISABLED"
MISSING = "MISSING"
UNTRUSTED = "UNTRUSTED"
CHANGED = "CHANGED"

STATUS_MESSAGES = {
    OK: "",
    DISABLED: "스크립트 버튼이 꺼져 있습니다 (Preferences > MayaUX > 스크립트 버튼 허용)",
    MISSING: "스크립트 파일을 찾을 수 없습니다",
    UNTRUSTED: "신뢰 확인이 필요합니다. 편집(✎)에서 내용을 확인한 뒤 '신뢰' 하세요",
    CHANGED: "신뢰한 뒤 파일 내용이 바뀌었습니다. 다시 확인하고 신뢰하세요",
}

_trusted: dict = {}  # 절대경로 -> sha256
_allowed = {"value": False}


def set_allowed(on: bool) -> None:
    _allowed["value"] = bool(on)


def allowed() -> bool:
    return _allowed["value"]


def load_trust(data) -> None:
    _trusted.clear()
    if isinstance(data, dict):
        for path, digest in data.items():
            if isinstance(path, str) and isinstance(digest, str):
                _trusted[path] = digest


def trust_data() -> dict:
    return dict(_trusted)


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(path)))


def file_hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def status(path: str) -> str:
    if not _allowed["value"]:
        return DISABLED
    p = _norm(path)
    if not os.path.isfile(p):
        return MISSING
    digest = _trusted.get(p)
    if digest is None:
        return UNTRUSTED
    try:
        return OK if file_hash(p) == digest else CHANGED
    except OSError:
        return MISSING


def trust(path: str) -> None:
    p = _norm(path)
    _trusted[p] = file_hash(p)


def untrust(path: str) -> None:
    _trusted.pop(_norm(path), None)


def preview(path: str, lines: int = 12) -> list:
    try:
        with open(_norm(path), encoding="utf-8", errors="replace") as f:
            return [ln.rstrip("\n") for _, ln in zip(range(lines), f, strict=False)]
    except OSError:
        return []


def run(path: str) -> None:
    """신뢰 상태를 다시 확인한 뒤 실행. 실패 시 예외를 그대로 올린다."""
    st = status(path)
    if st != OK:
        raise RuntimeError(STATUS_MESSAGES[st])
    p = _norm(path)
    with open(p, encoding="utf-8") as f:
        source = f.read()
    import bpy  # 스크립트 편의를 위해 네임스페이스에 제공

    namespace = {"__name__": "__maya_ux_script__", "__file__": p, "bpy": bpy}
    exec(compile(source, p, "exec"), namespace)  # noqa: S102 - 사용자가 명시적으로 신뢰한 파일만
