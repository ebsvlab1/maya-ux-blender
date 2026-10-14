# 설치 · 제거

지원: **Blender 4.5 LTS** (초기 검증 기준), 4.2 이상 설치 가능. 다른 버전은 회귀 테스트 후 사용하세요.

## 1. 패키지 만들기

```bash
python scripts/build_maya_ux.py
# dist/maya_ux-1.0.0.zip               ← MayaUX 확장
# dist/mayaux_sample_addon-1.0.0.zip   ← (선택) Shelf 호환성 확인용 샘플 애드온
```

Blender 가 설치되어 있다면 공식 명령도 됩니다: `blender --command extension build --source-dir maya_ux`

## 2. 설치

1. Blender 4.5 실행 → **Edit > Preferences > Get Extensions**
2. 오른쪽 위 `∨` 메뉴 → **Install from Disk…** → `maya_ux-1.0.0.zip` 선택
3. 설치 후 자동 활성화됩니다. (샘플 애드온도 같은 방법으로 설치하면 Custom 탭 버튼 3개가 동작합니다)

## 3. 처음 설정 (설정 마법사)

3D 뷰포트에서 `N` → **MayaUX** 탭 → **MayaUX 설정 마법사**

1. **Industry Compatible 키맵 활성화** (권장, 체크 시 Preferences > Keymap 프리셋이 바뀜)
2. **프로파일**: Maya 기본 / Blender 절충 / 사용자 정의
3. **충돌 처리**: 기존 유지 후 하나씩 결정(기본) / 모두 MayaUX 로 대체

Preferences 를 자동 저장하지 않는 설정이라면 **Save Preferences** 로 키맵 프리셋 선택을 저장하세요.
(MayaUX 자체 설정은 설정 폴더의 JSON 에 즉시 저장됩니다.)

## 4. 사용

* **Shelf**: `N` 사이드바 > MayaUX. 3D 뷰 헤더의 🔧 버튼(팝오버)으로 사이드바 없이도 열 수 있습니다.
* **편집**: Shelf 패널 제목 옆 ✏ 를 켜면 편집 모드 — 명령 검색 추가, 메뉴 추가, 직접 입력/스크립트, ▲▼ 순서, ✎ 편집, ▾ 메뉴(아이콘·복제·다른 탭으로·삭제), 탭 추가/이름/이동/삭제
* **회색 버튼**: 지금은 실행할 수 없는 상태(모드·선택·애드온 누락). 마우스를 올리면 이유가, 누르면 안내 메시지가 표시됩니다.
* **단축키 표**: Preferences > Add-ons > MayaUX > 단축키 — 항목별 켜기/끄기, 충돌 내용, `대체`/`복원`, ↵ 로 키 직접 지정

## 5. 백업 · 이전

Preferences > MayaUX > 백업·복원

* **내보내기**: Shelf + 키맵 프로파일/항목/충돌 결정을 JSON 한 파일로. Blender 버전, OS, 의존 확장 목록이 함께 기록됩니다.
* **가져오기**: 미리보기에서 누락 명령, 필요한 확장, 스크립트 버튼, 경고를 먼저 보여주고 `교체/병합/건너뜀` 을 고릅니다.
  스크립트 신뢰 정보는 파일에 담기지 않으므로 가져온 스크립트는 절대 자동 실행되지 않습니다.

설정 파일 위치: `<Blender 사용자 폴더>/extensions/.user/<repo>/maya_ux/` (`shelf.json`, `keymap.json`, `local.json`)

## 6. 되돌리기 · 제거

| 하고 싶은 것 | 방법 |
|---|---|
| Shelf 를 처음 상태로 | 백업·복원 > Shelf 기본값 |
| Blender 키맵으로 복귀 | 백업·복원 > Blender 키맵으로 복귀 (또는 단축키 탭에서 `MayaUX 단축키 켜짐` 끄기) |
| 잠시 끄기 | Preferences > Add-ons 에서 MayaUX 체크 해제 → MayaUX 단축키 제거 + 대체하느라 끈 기존 단축키 자동 복원 |
| 완전 삭제 | 백업·복원 > **제거 전 정리** → Get Extensions 에서 MayaUX **Uninstall** |
| IC 키맵도 되돌리기 | Preferences > Keymap 에서 프리셋을 `Blender` 로 |

MayaUX 는 `.blend` 파일에 아무것도 저장하지 않습니다. 확장을 지워도 프로젝트 파일은 그대로 열립니다.
