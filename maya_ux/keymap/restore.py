"""충돌 항목 비활성화/복원.

'MayaUX 로 대체' 를 고른 충돌 항목은 사용자 키맵(keyconfigs.user)에서 active=False 로
끈다. 무엇을 껐는지는 서명(signature) 목록으로 기록해 확장 비활성화·초기화·재시작 시
정확히 되돌린다. 키맵 프리셋 파일이나 다른 애드온의 키맵은 직접 수정하지 않는다.
"""

from __future__ import annotations

from .conflicts import KeyItem, signature
from .mappings import KeyEvent


def kmi_props(kmi) -> dict:
    out = {}
    props = kmi.properties
    if props is None:
        return out
    try:
        rna_props = props.bl_rna.properties
    except AttributeError:
        return out
    for p in rna_props:
        key = p.identifier
        if key == "rna_type" or not props.is_property_set(key):
            continue
        try:
            value = getattr(props, key)
        except AttributeError:
            continue
        if isinstance(value, (str, int, float, bool)):
            out[key] = value
        elif isinstance(value, (set, frozenset)):
            out[key] = sorted(value)
        elif hasattr(value, "__len__") and not hasattr(value, "bl_rna"):
            try:
                out[key] = list(value)
            except TypeError:
                pass
    return out


def _flag(v) -> tuple:
    """KeyMapItem 수정 키 값 → (눌림, any). 4.x 에서는 int(-1=any, 0, 1)."""
    try:
        iv = int(v)
    except (TypeError, ValueError):
        return bool(v), False
    return iv == 1, iv == -1


def kmi_to_item(km_name: str, kmi, source: str = "preset") -> KeyItem:
    ctrl, a1 = _flag(kmi.ctrl)
    shift, a2 = _flag(kmi.shift)
    alt, a3 = _flag(kmi.alt)
    oskey, a4 = _flag(kmi.oskey)
    ev = KeyEvent(kmi.type, kmi.value, ctrl, shift, alt, oskey)
    return KeyItem(km_name, kmi.idname, ev, kmi_props(kmi), bool(kmi.active),
                   bool(getattr(kmi, "any", False)) or a1 or a2 or a3 or a4, source, getattr(kmi, "name", ""))


def kmi_signature(km_name: str, kmi) -> str:
    it = kmi_to_item(km_name, kmi)
    return signature(km_name, it.idname, it.event, it.props)


def _find(kc_user, sig_keymap: str, sig: str, want_active: bool):
    km = kc_user.keymaps.get(sig_keymap) if kc_user else None
    if km is None:
        return None
    for kmi in km.keymap_items:
        if bool(kmi.active) == want_active and kmi_signature(sig_keymap, kmi) == sig:
            return kmi
    return None


def deactivate(kc_user, items: list) -> tuple:
    """KeyItem 목록을 사용자 키맵에서 끈다. (기록 목록, 실패 설명 목록) 반환."""
    records, failed = [], []
    for it in items:
        sig = it.signature()
        kmi = _find(kc_user, it.keymap, sig, want_active=True)
        if kmi is None:
            failed.append(it.describe())
            continue
        kmi.active = False
        records.append({"keymap": it.keymap, "signature": sig, "label": it.describe()})
    return records, failed


def restore(kc_user, records: list) -> list:
    """기록된 항목을 다시 켠다. 복원하지 못한 기록 목록을 반환(키맵이 사라진 경우 등)."""
    left = []
    for rec in records:
        kmi = _find(kc_user, rec.get("keymap", ""), rec.get("signature", ""), want_active=False)
        if kmi is None:
            # 이미 켜져 있거나 사용자가 직접 지운 경우: 더 할 일 없음
            if _find(kc_user, rec.get("keymap", ""), rec.get("signature", ""), want_active=True) is None:
                left.append(rec)
            continue
        kmi.active = True
    return left
