# BUILD_STATE.md — MABC_HMM_HWPX

## 기준
- main: e945e98973f264f19eb59d90eee35fd394cf9c75
- 원격: https://github.com/wayne0525/MABC_HMM_HWPX

## 현재 상태 (2026-09-13)
- 이식(transplant) 모드 코드만 존재. 채우기(fill) 모드 없음.
- transplant.py: run(A, B, out) → A 서식 유지 + B 텍스트 표 앞 문단 채움. 표 칸 매핑 없음.
- vercel/api/index.py: stub (b"ok" 반환). 실제 이식/채우기 로직 없음.
- SERVICE_BASELINE.md 없음. Service 폴더 없음. prompt 파일 없음.

## 발견된 현재 코드 오류 (00-공통지시-2.md 기준)
1. find_closing_tag 호출 위치/깊이 불일치로 단순 B 문장이 빈 문자열 됨.
2. transplant_body_v4가 section 루트·namespace·표 밖 구조를 잃음.
3. 잘못된 XML을 run이 성공으로 반환. bench_out 11개가 같은 XML 오류.
4. 표 입력란 탐지/값 매핑/Solar 호출 없음.
5. Vercel handler가 지원되는 클래스/app 계약이 아님 (stub).
6. multipart 파서가 CRLF 바이트 삭제. 동일 이름 import도 위치 의존.
7. 테스트가 저장소 밖 파일/없는 모듈에 의존.

## 다음 단계
- docs/BUILD_STATE.md 기록 시작
