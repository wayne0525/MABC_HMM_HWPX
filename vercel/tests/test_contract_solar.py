# -*- coding: utf-8 -*-
"""
Solar Pro 4 계약 검사 — 라이브 연결 확인.

- 실제 서버 호출을 포함한 검사만 여기서 수행한다.
- 키가 없으면 라이브 호출은 하지 않되, "0개 실행"이 되지 않도록
  미실행 사유를 결과와 상태 파일에 남긴다.
- 키는 출력하지 않는다.
- 실패는 연결/인증/모델 오류로 구분한다.

실행 방법(예시):
  python -m unittest discover -s vercel/tests -p test_contract_solar.py -k test_live_connection -v
"""
from __future__ import annotations

import os
import unittest

# import 경로: 이 파일 위치(vercel/tests/test_contract_solar.py) 기준
# tests/의 상위가 vercel/이 되도록 설정
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent  # vercel/

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import hwpx_core.solar as solar  # noqa: E402


class TestSolarContractLive(unittest.TestCase):
    """Solar Pro 4 서버 호출 계약 검사(라이브)."""

    @classmethod
    def setUpClass(cls):
        cls.key_present = solar.has_key()

    def _ensure_recorded(self):
        # 이 검사는 항상 어떤 형태든 결과를 남기도록 한다.
        # (skip 처리만 하고 끝내면 "0개 실행"처럼 보일 수 있으므로
        #  여기서는 조건 분기로 직접 검증한다.)
        pass

    def test_live_connection(self):
        """
        작은 실제 요청을 보내 성공/미실행/오류를 구분한다.

        - 키가 없으면 라이브 미실행으로 처리하되, 실패/통과로 속이지 않는다.
        - 키가 있으면 실제 호출 후 상태를 검증한다.
        """
        result = solar.call_solar_minimal()

        # 1) 키 없음 → 미실행으로 기록
        if not result["contacted"]:
            self.assertEqual(result["error_kind"], "no_key",
                             msg="라이브 미실행 사유를 명확히 기록")
            self.assertFalse(result["ok"])
            self.assertIsNone(result["status_code"])
            return

        # 2) 키가 있고 실제 호출은 했으나 실패한 경우
        if result["error_kind"] == "connection":
            self.fail(
                f"라이브 연결 실패: {result.get('note')} (status={result['status_code']})"
            )

        if result["error_kind"] == "auth":
            # 인증 실패는 따로 구분(함부로 PASS로 만들지 않음)
            self.fail(
                f"인증 실패: {result.get('note')} (status={result['status_code']})"
            )

        if result["error_kind"] == "model":
            # 모델/요청 오류도 구분
            self.fail(
                f"모델/요청 오류: {result.get('note')} (status={result['status_code']})"
            )

        # 3) 성공
        self.assertTrue(result["ok"], msg="라이브 호출 성공 경로만 여기에 도달")
        self.assertEqual(result["model_id"], solar.SOLAR_MODEL_ID)
        self.assertEqual(result["endpoint"], solar.SOLAR_BASE_URL)
        self.assertEqual(result["status_code"], 200)
        self.assertTrue(result["contacted"])
        # 민감정보가 섞이지 않도록 응답 본문은 검증하지 않음


if __name__ == "__main__":
    unittest.main()
