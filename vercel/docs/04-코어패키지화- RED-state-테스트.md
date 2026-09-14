# 04단계: 코어 패키지화 + RED-state 테스트

## 변경 파일
- `vercel/hwpx_core/__init__.py` — 신규: 단일 출처 패키지 export
- `vercel/hwpx_core/core.py` — 신규: 이식 코어 (ZIP/XML/이식 본문)
- `vercel/api/handler.py` — 신규: multipart 핸들러, hwpx_core.import
- `vercel/api/index.py` — 수정: handler 재수출
- `vercel/tests/fixtures/` — 신규: 합성 HWPX fixture 3개
- `vercel/tests/test_red_state.py` — 신규: RED-state 테스트 6건
- `vercel/transplant.py` — 제거: 코어 중복 제거
- `vercel/vercel.json` — 수정: functions entry를 api/index.py로

## 검증 명령/결과
- `cd vercel && python3 -c "import hwpx_core; print(hwpx_core.run.__module__)"` → `hwpx_core.core`
- `cd vercel && python3 -m unittest tests.test_red_state -v` → 5 ok, 1 fail (의도된 RED: multipart CRLF, 05 이슈)
- `cd vercel && python3 -c "from api.index import handler; print(handler)"` → handler callable

## 미구현
- multipart CRLF 보존 테스트 (05 이슈로 이관)
- root transplant.py CLI → hwpx_core.import 전환 (현재 root는 self-contained 유지, API만 새 패키지 사용 중)
- 실제 한글 호환 시험 (한컴 오피스에서 열기) — 합성 fixture로 ZIP 유효성만 확인

## 다음 번호
05: multipart CRLF 보존 테스트 + 실제 파일 쌍(01_culture_cctv)으로 이식 검증 + Vercel 배포 재도전
