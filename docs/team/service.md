작업 번호: 22
작업: Solar 요청 계약 검사 (test_request_contract)
변경 파일: vercel/hwpx_core/solar.py, vercel/tests/test_contract_solar.py, docs/team/service.md
검사 명령: python -m unittest discover -s vercel/tests -p test_contract_solar.py -k test_request_contract -v
테스트 개수: 6
exit code: 0
Solar 요청 계약: 검증됨 (mock 기반)
- 입력 필드 제한: fieldId/context/unit/evidenceQuote만 허용
- suggestions 필드: fieldId, value, sourceBlockIds, evidenceQuote, needsReview, reason
- 문서 속 명령은 데이터로 취급, 시스템 지시 변경 불가
- XML 생성 미포함
다음 작업: 23
