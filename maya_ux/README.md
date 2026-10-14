# MayaUX for Blender

Maya에 익숙한 사람이 **Blender 기능은 그대로** 쓰면서 **Maya식 단축키와 Shelf** 로 작업할 수 있게 하는 Blender 확장(Extension)입니다.
Blender 소스·데이터 구조·`.blend` 파일은 건드리지 않고, 확장을 끄면 원래 환경으로 돌아갑니다.

* 대상: **Blender 4.5 LTS** (4.2+ 설치 가능)
* 설치: [docs/install.md](docs/install.md) · 단축키 표: [docs/shortcut_reference.md](docs/shortcut_reference.md) · 문제 해결: [docs/troubleshooting.md](docs/troubleshooting.md)

## 기능 (PRD 대응)

| PRD | 구현 |
|---|---|
| F01 Maya형 키맵 (P0) | Industry Compatible 기준선 + 차이 항목만 추가. 프로파일 3종(Maya 기본 / Blender 절충 / 사용자 정의), 영역별(Object/Edit/Pose/Graph/Dope Sheet/전역) 64개 항목, 항목별 켜기·끄기·키 직접 지정 |
| 4.2 충돌 해결 | 등록 전 같은 키맵 + 함께 동작하는 키맵까지 검사(키·값·수정키·any). 항목별 **유지/대체/사용자 지정**, 대체 시 기존 단축키는 삭제하지 않고 끄기만 하며 기록 → 해제·초기화 시 정확히 복원. macOS/Windows OS 예약키 자동 제외, macOS Ctrl→Cmd 옵션 |
| F02 Shelf (P0) | 3D 뷰 사이드바(N) MayaUX 탭 + 헤더 팝오버 + Hotbox 메뉴. 탭 6개(General/Modeling/Animation/Rigging/Rendering/Custom), 아이콘·이름·툴팁(Operator ID, 단축키, 요구 모드, 실행 불가 사유) |
| F03 명령 등록 (P0) | Operator · 애드온 Operator · 메뉴 · 프리셋(여러 단계, operator/menu 만) · 스크립트. 3D 뷰 WINDOW 영역으로 컨텍스트 보정, `poll()` 확인, 모드 요구조건, 실패 사유 안내 |
| F04 Shelf 편집기 (P1) | 버튼 추가(전체 Operator/메뉴 검색, 소유 확장 표시)·삭제·이름·아이콘 검색·프로퍼티(JSON)·순서·탭 이동·복제, 탭 추가/이름/순서/삭제 |
| F05 스크립트 버튼 (P1) | 기본 꺼짐. 사용자가 고른 로컬 .py 만, 경고 + 코드 미리보기 + 신뢰 확인(SHA-256). 내용 바뀌면 재확인. 신뢰 정보는 내보내지 않음 → 가져온 스크립트 자동 실행 불가 |
| F06 백업·이전 (P0) | JSON 내보내기/가져오기(schema_version, Blender 버전, OS, 의존 확장), 가져오기 미리보기(누락 명령·필요 확장·스크립트·경고), 교체/병합, 스키마 마이그레이션, Shelf 초기화 / Blender 키맵 복귀 / 제거 전 정리 |
| F07 애드온 호환 (P0) | 설치된 확장의 공개 Operator 를 bl_idname 으로 호출, 소유 확장 자동 기록. 확장이 꺼지거나 지워지면 버튼 비활성 + 설치 안내. 다른 애드온과의 단축키 충돌 표시 |

## 구조

```
maya_ux/
  blender_manifest.toml    __init__.py    preferences.py    state.py
  keymap/      mappings.py(매핑·프로파일·OS 예약키) conflicts.py(충돌 분석) registry.py(등록/해제) restore.py(끈 항목 복원) operators.py
  shelf/       model.py(데이터·검증·기본 Shelf) panel.py operators.py editor.py registry.py
  integrations/ addon_discovery.py context_guard.py scripts.py
  storage/     json_io.py migration.py
  tests/       test_shelf.py test_keymap.py (bpy 불필요)  test_addon_compat.py (bpy 통합)  report_keymap.py
  docs/
maya_ux_samples/mayaux_sample_addon/   # 외부 애드온 호환성 검증용 샘플 (Operator 3개)
scripts/build_maya_ux.py               # 설치 zip 생성
```

## 검증 현황

* 단위 테스트 35개 (Python 3.11 / 3.13, bpy 없이)
* Blender 통합 테스트 10개 — **bpy 5.2 LTS 모듈**로 실행: 기본 Shelf 의 모든 Operator/메뉴 ID 존재, 실제 IC 키맵 대비 충돌 분석, 대체 → 복원, 애드온 활성/비활성 시 버튼 상태, 프리셋·스크립트 실행, 설정 파일 저장
* 확장 zip 을 `bl_ext.user_default` 로 설치·활성·비활성화 확인, Blender 확장 매니페스트 검증 통과

> 이 개발 환경에서는 Blender 4.5용 bpy(Python 3.11)를 받을 수 없어 5.2 로 검증했습니다. PRD 기준인 **4.5 LTS 에서 `pip install bpy==4.5.*` 로 같은 테스트를 다시 돌리고**,
> UI(패널 그리기, 팝업, 키 입력 지정, 새 창 열기)와 Windows/macOS 입력은 실제 Blender 에서 수동 확인이 필요합니다 (PRD Phase 4).
