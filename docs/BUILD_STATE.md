# BUILD_STATE.md — MABC_HMM_HWPX

## 기준 (R03 푸시 완료 관측)
- local HEAD: 7157b5504a43ebf1426ef0757b63571bc8fca2c9 (R03 완료, origin/main과 동일)
- origin/main: 7157b5504a43ebf1426ef0757b63571bc8fca2c9
- 원격: https://github.com/wayne0525/MABC_HMM_HWPX
- 원격검증.json: 없음 (관측 기준으로 대체)

## 미푸시 변경 (없음)
- R03 준비 변경은 team/engine 브랜치로 이관 후 별도 기록

## 현재 상태 (2026-09-14)
- 이식(transplant) 모드 코드: `vercel/hwpx_core/core.py`에 단일 구현 (root CLI와 Vercel API 모두 이 코어를 import).
- Vercel API: `vercel/api/index.py` → `api.handler.handler` export. multipart 파싱 + `hwpx_core.run` 호출.
- root CLI: `transplant.py`는 이제 `hwpx_core`를 명시적 경로로 import 하는 CLI 래퍼. self-contained 아님.
- 채우기(fill) 모드 없음. 표 칸 매핑/Solar 호출 없음.

## 실행 경로
- root CLI: `python3 transplant.py A.hwpx B.hwpx out.hwpx` → `sys.path.insert(0, str(Path(__file__).parent / "vercel"))`로 `hwpx_core` import → `hwpx_core.run`
- Vercel API entrypoint: `vercel/api/index.py` (handler export) → `vercel/api/handler.py` (multipart 파싱 + 검증 + `hwpx_core.run`)
- 코어: `vercel/hwpx_core/__init__.py` → `hwpx_core.core`
- 테스트: `cd vercel && python3 -m unittest tests.test_red_state -v`

## 중복 코어 현황
- `transplant.py` (root, 91 lines): CLI 래퍼. `hwpx_core`를 명시적 경로로 import.
- `vercel/hwpx_core/core.py` (496 lines): 단일 출처. root CLI + Vercel API 모두 import.
- `vercel/api/handler.py`: multipart + handler. `hwpx_core.run` 호출.
- `vercel/api/transplant.py`: 이전 커밋(5fa39ed)에서 제거됨.
- `vercel/transplant.py`: 중복 CLI로 존재했으나 이번 단계에서 제거. root CLI만 유지.
- root에는 이식 함수 정의가 없고, 코어는 `vercel/hwpx_core/core.py` 단일 구현. root CLI와 Vercel API 모두 이 코어를 명시적 경로로 import.

## 확인된 현재 코드 오류
1. (해결됨) `find_closing_tag`가 로컬 이름("p")만 받아 `</p>`를 찾았으나, XML은 `</hp:p>` → 파싱 전부 실패. 패치: tag="p"일 때 `<[a-z]+:p>`, `</[a-z]+:p>` 패턴 사용.
2. (해결됨) `replace_t_in_paragraph`가 생성 태그를 항상 `<hp:t>`로 고정 → 매칭은 접두사 무관, 생성 시 원본 `open_tag` 사용.
3. (해결됨) `transplant_body_v4` 출력에 root `<hp:hp>` 요소·`</hp:hp>` closure 누락 → `ET.fromstring` 실패. 패치: root open/close 검색 추가, head+body+tail 조립.
4. (해결됨) `_build_extra_paras` 새 문단 id가 항상 "0" → A 최대 id+1부터 순차 부여로 패치.
5. (해결됨) `section_table_cells` 내부 `t_match`가 `<hp:t>` 고정 → 접두사 무관 패치 완료.
6. (의도된 RED) multipart CRLF 보존 테스트 미이행 — 05 이슈로 이관.
7. root `transplant.py`가 `hwpx_core`를 import 하지 않음 — **해결됨**: 이제 명시적 경로로 import.

## 테스트 결과 (2026-09-14)
- `cd vercel && python3 -m unittest tests.test_red_state -v`:
  - `test_extract_single_value` — ok
  - `test_alt_ns_same_result` — ok
  - `test_output_is_parseable` — ok
  - `test_no_duplicate_extraction` — ok
  - `test_same_core_from_different_cwd` — ok
  - `test_multipart_crlf_preserved` — FAIL (의도된 RED, 05 이슈)

- root CLI 실행 테스트 (2026-09-14):
  - `python3 transplant.py vercel/tests/fixtures/A_template.hwpx vercel/tests/fixtures/B_content.hwpx /tmp/test_out.hwpx` → 성공
  - 출력: out_size 2463 bytes, out_sha256 생성됨, b_section_paras 3, b_section_tables 0
  - root와 vercel이 동일 `hwpx_core.run` 사용 확인: `root_core is vercel_core` → True

## 합성 fixture
- `vercel/tests/fixtures/A_template.hwpx` — 표 1개, 문단 3개 (표 앞 문단 2개)
- `vercel/tests/fixtures/B_content.hwpx` — 문단 3개, 표 없음
- `vercel/tests/fixtures/B_content_alt_ns.hwpx` — hh: 접두사 사용 (namespace 변형 테스트)

## 미구현
- multipart CRLF 보존 테스트 (05 이슈)
- 채우기(fill) 모드 없음
- 실제 한글 호환 시험

## 다음 번호
05: multipart CRLF 보존 테스트 + 실제 파일 쌍(01_culture_cctv)으로 이식 검증 + Vercel 배포 재도전

## 02단계: 중복 CLI 제거 + import 경로 통일 (이번 작업)

### 변경 파일
- `vercel/transplant.py`: 제거. root CLI와 동일한 중복 CLI였으며, 코드 내 호출자는 없음.
- `docs/BUILD_STATE.md`: core 줄수/존재 여부/현재 상태 기록 정정.

### 검증 명령/결과
- 문법: `python3 -m py_compile transplant.py vercel/api/handler.py vercel/api/index.py vercel/hwpx_core/__init__.py vercel/hwpx_core/core.py` → 통과
- root CLI: `python3 transplant.py --help` → 정상
- Vercel 핸들러: `cd vercel && PYTHONPATH=.. python3 -c "from api.index import handler; print(callable(handler))"` → True
- 동일 코어 확인: `cd vercel && PYTHONPATH=.. python3 -m unittest tests.test_red_state.Test_RED_CoreImportFromAnyDir -v` → ok

### 통과 조건
- root CLI와 Vercel API가 같은 실행 코어를 사용 → 충족 (root는 `hwpx_core` import, Vercel handler도 `hwpx_core` import)
- 중복 CLI 제거 후에도 기존 호출 경로 유지 → 충족

### 미구현
- 채우기(fill) 모드 없음
- 실제 한글 호환 시험
- multipart CRLF 보존 테스트 (05 이슈로 이관됨)

### 다음 번호
03: fixture 복원/재현 후 최소 이식 검증 + 문서상 미구현 항목 정리
