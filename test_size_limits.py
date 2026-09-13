# -*- coding: utf-8 -*-
"""크기 제한 검증용 테스트.

Vercel 런타임 없이도 핸들러를 직접 호출해,
- A > 5MB → 400
- A+B 합계 > 6MB → 400
- 정상 크기 → 200 + C.hwpx
를 확인한다.
"""
from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
import sys
import os

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vercel.api.document import handle_request  # type: ignore[import-not-found]


def make_dummy_hwpx(out_path: Path, size_bytes: int) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zfi = zipfile.ZipInfo("mimetype")
        zfi.compress_type = zipfile.ZIP_STORED
        zf.writestr(zfi, "application/hwp+zip")
        remaining = max(0, size_bytes - 19)
        zf.writestr("section0.xml", "<?xml version=\"1.0\"?><hp:secPr/>" + "x" * (remaining - 30))


def multipart_body(a_data: bytes, b_data: bytes, boundary: str = "boundary") -> bytes:
    h_a = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="A"; filename="A.hwpx"\r\n'
        "Content-Type: application/hwp+zip\r\n"
        "\r\n"
    ).encode()
    h_b = (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="B"; filename="B.hwpx"\r\n'
        "Content-Type: application/hwp+zip\r\n"
        "\r\n"
    ).encode()
    foot = f"\r\n--{boundary}--\r\n".encode()
    return h_a + a_data + h_b + b_data + foot


class Req:
    method = "POST"
    headers = {"content-type": "multipart/form-data; boundary=boundary"}
    body: bytes = b""


def test(label: str, a: Path, b: Path) -> None:
    a_data = a.read_bytes()
    b_data = b.read_bytes()
    body = multipart_body(a_data, b_data)
    req = Req()
    req.body = body
    status, headers, data = handle_request(req, body)
    print(f"[{label}]")
    print(f"  A={len(a_data)} B={len(b_data)} total={len(a_data)+len(b_data)} body={len(body)}")
    print(f"  status={status}")
    print(f"  response={data[:160]!r}")
    print()


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        # 케이스 1: A 5.1MB → MAX_A 위반
        make_dummy_hwpx(td / "a_5_1.hwpx", 5 * 1024 * 1024 + 100 * 1024)
        make_dummy_hwpx(td / "b_small.hwpx", 10 * 1024)
        test("A 5.1MB 초과", td / "a_5_1.hwpx", td / "b_small.hwpx")

        # 케이스 2: A 4MB + B 2.5MB = 6.5MB → MAX_TOTAL 위반
        make_dummy_hwpx(td / "a_4_0.hwpx", 4 * 1024 * 1024)
        make_dummy_hwpx(td / "b_2_5.hwpx", 2 * 1024 * 1024 + 500 * 1024)
        test("총합 6.5MB 초과 (4MB + 2.5MB)", td / "a_4_0.hwpx", td / "b_2_5.hwpx")

        # 케이스 3: 정상 크기 → 200 + C.hwpx
        make_dummy_hwpx(td / "a_0_5.hwpx", 500 * 1024)
        make_dummy_hwpx(td / "b_0_2.hwpx", 200 * 1024)
        test("정상 크기 (0.5MB + 0.2MB)", td / "a_0_5.hwpx", td / "b_0_2.hwpx")


if __name__ == "__main__":
    main()
