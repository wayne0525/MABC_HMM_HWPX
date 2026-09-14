# team/server.md

## 담당

- 서버(Vercel 함수, API 경로, 핸들러, 크기 제한, 오류 응답) 담당: 담당자 2

## 현재 상태(준비 커밋 기준)

- 현재 서버 진입점: `vercel/api/index.py` → `api.handler.handler`
- 현재 라우팅 설정: `vercel/vercel.json`의 `api/index.py`
- 현재 실제 요청 방식: multipart/form-data
- 현재 핸들러 시그니처: `handler(request) -> Tuple[bytes, int, dict]`
- 현재 크기 제한(핸들러에 구현됨):
  - A 최대 5MB
  - B 최대 1MB
  - 합계 최대 6MB
  - 출력 최대 5MB
- 현재 응답은 HWPX 바이너리 중심. JSON 보고서 응답은 미구현

## 계약상 정리된 불일치(최종 이름 포함)

- 외부 엔드포인트는 하나로 통일: `/api/fill`
- 요청 필드명은 `a`(서식 원본), `b`(내용 원본)로 통일
- 연산 구분은 단일 경로에서 연산 타입 필드로 처리: `status`, `analyze`, `suggest`, `generate`
- 오류 응답은 `code`, `message`, `details` 구조로 통일
- 상세 계약은 `docs/TEAM_CONTRACT.md` 참조

## 진행 규칙

- `/api/fill`의 실제 전송 방식(multipart vs JSON/base64)은 서버 구현 선택 후 확정
- 클라이언트 예제(`vercel/public/index.html`)의 경로/필드명과 서버 계약 불일치는 이 브랜치에서 해소
