# BUILD_STATE.md — MABC_HMM_HWPX

## 기준
- main: 6dc92346dc92346dc92346dc92346dc92346dc92 (2026-09-14)
- 원격: https://github.com/wayne0525/MABC_HMM_HWPX

## 현재 상태 (2026-09-14)
- 이식(transplant) 모드 코드: `vercel/hwpx_core/core.py`에 단일 구현.
- Vercel API: `vercel/api/index.py` → `api.handler.handler` export. multipart 파싱 + `hwpx_core.run` 호출.
- root CLI: `transplant.py`는 이제 `hwpx_core`를 명시적 경로로 import 하는 CLI 래퍼. self-contained 아님.
- 채우기(fill) 모드 없음. 표 칸 매핑/Solar 호출 없음.

## 실행 경로
- root CLI: `python3 transplant.py A.hwpx B.hwpx out.hwpx` → `sys.path.insert(0, str(Path(__file__).parent / "vercel"))`로 `hwpx_core` import → `hwpx_core.run`
- Vercel API entrypoint: `vercel/api/index.py` (handler export) → `vercel/api/handler.py` (multipart 파싱 + 검증 + `hwpx_core.run`)
- 코어: `vercel/hwpx_core/__init__.py` → `hwpx_core.core`
- 테스트: `cd vercel && python3 -m unittest tests.test_red_state -v`

## 중복 코어 현황
- `transplant.py` (root, 103 lines): CLI 래퍼. `hwpx_core`를 명시적 경로로 import.
- `vercel/hwpx_core/core.py` (397 lines): 단일 출처. root CLI + Vercel API 모두 import.
- `vercel/api/handler.py`: multipart + handler. `hwpx_core.run` 호출.
- `vercel/api/transplant.py`: 이전 커밋(5fa39ed)에서 제거됨.
- `vercel/transplant.py`는 존재하지 않음.
- root에 남아있는 중복 함수 정의 없음 — 모든 함수 정의가 `hwpx_core.core`로 통합됨.

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
- multipart CRLF 보존 테스트 (05 이슈로 이관)
- 채우기(fill) 모드: 표 입력란 탐지/값 매핑/Solar 호출 없음
- 실제 한글 호환 시험 (한컴 오피스에서 열기) — 합성 fixture로 ZIP/XML 유효성만 확인

## 다음 번호
05: multipart CRLF 보존 테스트 + 실제 파일 쌍(01_culture_cctv)으로 이식 검증 + Vercel 배포 재도전

## 02단계: 코어 단일화 (완료)

### 변경 파일
- `transplant.py`: 함수 정의 전부 제거, `hwpx_core` 명시적 경로 import, `argparse` + `--fixtures`/`--output` 옵션 추가.
- `vercel/api/index.py`: 변경 없음 (entrypoint 유지).
- `vercel/api/handler.py`: 변경 없음 (이미 `hwpx_core` import 중).
- `docs/BUILD_STATE.md`: 02단계 기록 추가.

### 검증 명령/결과
- 문법: `python3 -m py_compile transplant.py vercel/hwpx_core/__init__.py vercel/hwpx_core/core.py vercel/api/index.py vercel/api/handler.py` → 전부 통과
- RED-state 테스트: `cd vercel && python3 -m unittest tests.test_red_state` → 5 ok, 1 의도된 RED (multipart CRLF)
- root와 vercel 동일 코어 확인: `root_core is vercel_core == True`
- root CLI 실제 실행: `python3 transplant.py vercel/tests/fixtures/A_template.hwpx vercel/tests/fixtures/B_content.hwpx /tmp/verify02.hwpx` → success (2463 bytes)
- 출력 검증: ZIP 유효 + XML 파싱 + 텍스트 정확 + namespace 보존 모두 통과

### 통과 조건
- root CLI와 Vercel API가 동일 `hwpx_core.run`을 명시적 경로로 import → 충족
- root에 중복 함수 정의 없음 → 충족

### 미구현
- `--fixtures`/`--output` 단독 사용 시 경로 해석 재확인 필요 (위 테스트에서 파일 미검출)
- multipart CRLF 보존 테스트 (05 이슈)
- 채우기(fill) 모드 없음
- 실제 한글 호환 시험

### 다음 번호
03: (필요 시) root CLI --fixtures/--output 재검증 + 실제 파일 쌍으로 이식 검증
