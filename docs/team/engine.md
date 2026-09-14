# team/engine.md

## 담당

- 엔진(코어 + API 핸들러 + CLI 래퍼) 담당: 담당자 1
- 공통 BUILD_STATE.md 관리: 담당자 1만 수정

## 현재 상태(준비 커밋 기준)

- 코어 단일 구현: `vercel/hwpx_core/core.py`
- 서버 API: `vercel/api/handler.py`의 `handler(request)`가 multipart 파싱 후 `hwpx_core.run` 호출
- entrypoint: `vercel/api/index.py`
- root CLI: `transplant.py`는 `hwpx_core`를 명시적 경로로 import하는 래퍼
- 이식(transplant) 모드만 구현됨. 채우기/분석/제안/생성 JSON API 계약은 `docs/TEAM_CONTRACT.md`에 정리됨
- RED-state 테스트: `vercel/tests/test_red_state.py`
  - ok 5건: extract_single_value, alt_ns_same_result, output_is_parseable, no_duplicate_extraction, same_core_from_different_cwd
  - 의도된 RED 1건: multipart_crlf_preserved

## 진행 규칙

- 새 검사(R00~)는 team/engine 브랜치에서 하나씩 실행
- 코어 통합이 이미 되어 있으면 재작업하지 않음
- 검사가 실제 실패까지 도달하면 RED로 기록하되, 엔진 완료로 표시하지 않음
- fixtures는 필요 시 그때그때 준비

## R03 연결 완료 (기록: 2026-09-15)

- 검사: `python test_v4.py` (test_v4.py)
- import: CLI wrapper가 아닌 `vercel.hwpx_core.core`의 실제 함수(transplant_body_v4 등)
- 입력/경로: R02 fixture (`vercel/tests/fixtures/A_verified.hwpx`, `B_verified.hwpx`)
- 출력 형태: print 기반 → assert 기반
- 실제 검사 결과: **엔진 실행까지 도달 + RED**
  - 이식 함수 호출 시점까지는 도달
  - NameError: `name '_build_extra_paras' is not defined` → assert 실패, exit 1
- 기록 원칙: 이 RED는 엔진 완료가 아님. 코어 수정 없이 구조 손상으로 남김.
- 함수 임시 복원/기대값 완화 없음.

## R04 연결 완료 (기록: 2026-09-15)

- 검사: `python test_size_limits.py`
- import 대상: `vercel.api.handler.handler(request)` (handler(request)만 사용, method/headers/get_data() 계약)
- 입력 구성: 실제 multipart body(bytes). 초과 케이스는 더미 바이트로 필드 길이 검사만 통과하도록 구성, 정상 케이스는 R02 fixture(A_verified.hwpx, B_verified.hwpx)
- a/b 필드: 핸들러 필드는 소문자 a/b로 전달. 초과 시 413 응답(message=bytes, Content-Type=text/plain)
- 실제 검사 결과:
  - 케이스1(A 5.1MB 초과): status 413 확인
  - 케이스2(A 4MB + B 2.5MB = 6.5MB 초과): status 413 확인
  - 케이스3(정상 크기 R02 fixture): handler가 200 대신 500 반환 → assert 실패(exit 1)
    - 원인: handler 내부 `hwpx_core.run(...)` 호출 시 `NameError: name '_build_extra_paras' is not defined`
    - handler 계약/요청 구성 오류가 아니라 엔진(코자) 내부 미정의 함수 호출로 인한 구조 손상
- 기록 원칙: 이 RED는 handler 완성/엔진 완료가 아님. 코어 수정 없이 구조 손상으로 남김.
- 함수 임시 복원/기대값 완화 없음.
