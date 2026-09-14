# -*- coding: utf-8 -*-
"""크기 제한 검증용 테스트.

Vercel 런타임 없이도 핸들러를 직접 호출해,
- A > 5MB → 413
- B > 1MB → 413
- A+B 합계 > 6MB → 413
- 정상 크기 → 200 + C.hwpx (ZIP/XML 검증)
를 확인한다.
"""
from __future__ import annotations

import io
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

# handler import 전에 내부 import(hwpx_core)를 실제 구현으로 해결
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
import vercel.hwpx_core as _hc
sys.modules["hwpx_core"] = _hc

from vercel.api.handler import handler  # 실제 핸들러 계약


def make_dummy_bytes(size_bytes: int) -> bytes:
    # 필드별 크기 제한 확인용 더미. 크기 검사만 통과하면 되므로
    # 유효한 HWPX 구조일 필요는 없다 (handler는 필드 길이만 먼저 본다).
    return b"\x00" * size_bytes


def multipart_body(a_data: bytes, b_data: bytes, boundary: str = "boundary") -> bytes:
    # 실제 handler는 소문자 a/b 필드로 받는다
    h_a = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="a"; filename="A.hwpx"\r\n'
        "Content-Type: application/hwp+zip\r\n"
        "\r\n"
    ).encode()
    h_b = (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="b"; filename="B.hwpx"\r\n'
        "Content-Type: application/hwp+zip\r\n"
        "\r\n"
    ).encode()
    foot = f"\r\n--{boundary}--\r\n".encode()
    return h_a + a_data + h_b + b_data + foot


class Req:
    """handler(request)가 읽는 request 계약: method, headers, get_data()"""

    method = "POST"
    headers = {"content-type": "multipart/form-data; boundary=boundary"}

    def __init__(self) -> None:
        self.body: bytes = b""

    def get_data(self) -> bytes:
        return self.body


def test(
    label: str,
    a: Path,
    b: Path,
    a_data: bytes | None = None,
    b_data: bytes | None = None,
) -> tuple[bytes, int, dict]:
    if a_data is None:
        a_data = a.read_bytes()
    if b_data is None:
        b_data = b.read_bytes()
    body = multipart_body(a_data, b_data)
    req = Req()
    req.body = body
    # handler(request) → (body_bytes, status_int, headers_dict)
    data, status, headers = handler(req)
    print(f"[{label}]")
    print(f"  A={len(a_data)} B={len(b_data)} total={len(a_data)+len(b_data)} body={len(body)}")
    print(f"  status={status}")
    print(f"  Content-Type={headers.get('Content-Type', '')!r}")
    print(f"  response={data[:160]!r}")
    print()
    return data, status, headers


def main() -> None:
    here = Path(__file__).resolve().parent
    fixtures = here / "vercel/tests/fixtures"

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        # 케이스 1: A > 5MB → 413 (실제 전송 바이트 기준, 핸들러 필드 길이 검사)
        a_over = make_dummy_bytes(5 * 1024 * 1024 + 100 * 1024)
        b_small = make_dummy_bytes(10 * 1024)
        data, status, headers = test(
            "A 5.1MB 초과 → 413",
            td / "unused_a",
            td / "unused_b",
            a_data=a_over,
            b_data=b_small,
        )
        assert status == 413, f"예상: 413, 실제: {status}, body={data[:200]!r}"
        assert headers.get("Content-Type") == "text/plain", f"413 응답 Content-Type 예상과 다름: {headers}"

        # 케이스 2: A 4MB + B 2.5MB = 6.5MB → 413 (실제 전송 바이트 기준)
        a_4m = make_dummy_bytes(4 * 1024 * 1024)
        b_2_5m = make_dummy_bytes(2 * 1024 * 1024 + 500 * 1024)
        data, status, headers = test(
            "총합 6.5MB 초과 → 413",
            td / "unused_a",
            td / "unused_b",
            a_data=a_4m,
            b_data=b_2_5m,
        )
        assert status == 413, f"예상: 413, 실제: {status}, body={data[:200]!r}"
        assert headers.get("Content-Type") == "text/plain", f"413 응답 Content-Type 예상과 다름: {headers}"

        # 케이스 3: 정상 크기 (R02 fixture, 실제 hwpx 파일) → 200 + C.hwpx 검증
        a_fixture = fixtures / "A_verified.hwpx"
        b_fixture = fixtures / "B_verified.hwpx"
        assert a_fixture.exists(), f"A fixture 없음: {a_fixture}"
        assert b_fixture.exists(), f"B fixture 없음: {b_fixture}"
        data, status, headers = test("정상 크기 (R02 fixture) → 200 + 검증", a_fixture, b_fixture)

        if status == 200:
            # 결과 ZIP/XML까지 검사 — 손상이면 실패
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = zf.namelist()
                assert len(names) > 0, "ZIP에 파일이 없음"
                xml_names = [n for n in names if n.endswith(".xml")]
                assert len(xml_names) > 0, f"ZIP에 XML 파일이 없음: {names}"
                for xml_name in xml_names[:1]:
                    xml_data = zf.read(xml_name).decode("utf-8")
                    ET.fromstring(xml_data)  # 파싱 불가면 예외 → 테스트 실패
            print("  ZIP/XML 검증 통과")
        else:
            assert False, (
                f"정상 입력인데 handler가 200을 반환하지 않음: status={status}, body={data[:300]!r}. "
                "이는 핸들러 계약의 오류가 아니라 엔진(코자) 내부 구조 손상일 수 있음 — "
                "코어 수정 없이 이 assert 실패로 기록함."
            )


if __name__ == "__main__":
    main()
