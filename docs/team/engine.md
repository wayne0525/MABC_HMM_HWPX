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
