# BUILD_STATE.md — MABC_HMM_HWPX

## 기준
- main: 5fa39ed9c1e5c9c2b1f6d3c7e9b4e6d5a2c8f0e1 (2026-09-14)
- 원격: https://github.com/wayne0525/MABC_HMM_HWPX

## 현재 상태 (2026-09-14)
- 이식(transplant) 모드 코드: `vercel/hwpx_core/core.py`에 단일 구현.
- Vercel API: `vercel/api/index.py` → `api.handler.handler` export. multipart 파싱 + `hwpx_core.run` 호출.
- root CLI: `transplant.py`는 self-contained 상태 (아직 `hwpx_core` import 안 함). 호출자가 모두 새 패키지를 가리키기 전까지 보존.
- 채우기(fill) 모드 없음. 표 칸 매핑/Solar 호출 없음.

## 실행 경로
- root: `python3 transplant.py A.hwpx B.hwpx out.hwpx` (현재 self-contained, `hwpx_core` 미사용)
- Vercel API entrypoint: `vercel/api/index.py` (handler export) → `vercel/api/handler.py` (multipart 파싱 + 검증 + `hwpx_core.run`)
- 코어: `vercel/hwpx_core/__init__.py` → `hwpx_core.core`
- 테스트: `cd vercel && python3 -m unittest tests.test_red_state -v`

## 중복 코어 현황
- `transplant.py` (root, 689 lines): self-contained, CLI 포함. 호출자가 없으므로 보존.
- `vercel/hwpx_core/core.py` (397 lines): 단일 출처. `vercel/api/handler.py`가 import.
- `vercel/api/handler.py`: multipart + handler. `hwpx_core.run` 호출.
- `vercel/api/transplant.py`: 이전 커밋(5fa39ed)에서 제거됨.
- `vercel/transplant.py`는 존재하지 않음.

## 확인된 현재 코드 오류
1. `find_closing_tag`가 로컬 이름("p")만 받아 `</p>`를 찾았으나, XML은 `</hp:p>` → 파싱 전부 실패. 패치: tag="p"일 때 `<[a-z]+:p>`, `</[a-z]+:p>` 패턴 사용.
2. `replace_t_in_paragraph`가 생성 태그를 항상 `<hp:t>`로 고정 → 매칭은 접두사 무관, 생성 시 원본 `open_tag` 사용.
3. `transplant_body_v4` 출력에 root `<hp:hp>` 요소·`</hp:hp>` closure 누락 → `ET.fromstring` 실패. 패치: root open/close 검색 추가, head+body+tail 조립.
4. `_build_extra_paras` 새 문단 id가 항상 "0" → A 최대 id+1부터 순차 부여로 패치.
5. `section_table_cells` 내부 `t_match`가 `<hp:t>` 고정 → 접두사 무관 패치 완료.
6. (의도된 RED) multipart CRLF 보존 테스트 미이행 — 05 이슈로 이관.
7. root `transplant.py`가 `hwpx_core`를 import 하지 않음 — API는 새 패키지 사용 중, root CLI 전환은 호출 측 정리 후 진행.

## 테스트 결과 (2026-09-14)
- `cd vercel && python3 -m unittest tests.test_red_state -v`:
  - `test_extract_single_value` — ok (B 첫 텍스트 A 앞 문단 진입)
  - `test_alt_ns_same_result` — ok (B가 hh: 접두사여도 추출)
  - `test_output_is_parseable` — ok (ET.fromstring 성공, namespace 복원)
  - `test_no_duplicate_extraction` — ok (표 안/밖 중복 없음)
  - `test_same_core_from_different_cwd` — ok (PYTHONPATH 없이 import)
  - `test_multipart_crlf_preserved` — FAIL (의도된 RED, 05 이슈)

## 합성 fixture
- `vercel/tests/fixtures/A_template.hwpx` — 표 1개, 문단 3개 (표 앞 문단 2개)
- `vercel/tests/fixtures/B_content.hwpx` — 문단 3개, 표 없음
- `vercel/tests/fixtures/B_content_alt_ns.hwpx` — hh: 접두사 사용 (namespace 변형 테스트)

## 미구현
- multipart CRLF 보존 테스트 (05 이슈로 이관)
- root CLI `transplant.py` → `hwpx_core` import 전환 (호출 측 정리 후)
- 실제 한글 호환 시험 (한컴 오피스에서 열기) — 합성 fixture로 ZIP/XML 유효성만 확인
- 채우기(fill) 모드: 표 입력란 탐지/값 매핑/Solar 호출 없음

## 다음 번호
05: multipart CRLF 보존 테스트 + 실제 파일 쌍(01_culture_cctv)으로 이식 검증 + Vercel 배포 재도전
