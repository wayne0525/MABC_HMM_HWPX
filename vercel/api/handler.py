# -*- coding: utf-8 -*-
"""
Vercel API handler — multipart HWPX 이식 요청 처리.

코어 로직은 hwpx_core.core에서 가져온다 (사본 아님).
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Tuple, Iterator, Optional

# ---- 코어: vercel/hwpx_core (단일 구현) ----
import hwpx_core  # noqa: E402

MAX_A_MB = 5
MAX_B_MB = 1
MAX_TOTAL_MB = 6
MAX_OUT_MB = 5


def _parse_multipart(body: bytes, boundary: bytes):
    """multipart/form-data 바디를 파싱해 필드별 바이트를 반환."""
    boundary_re = re.compile(
        br'--' + re.escape(boundary) + br'(?:--)?\r\n', re.MULTILINE
    )
    parts: list = []
    pos = 0
    for m in boundary_re.finditer(body):
        start = m.end()
        end = body.find(b'\r\n--' + boundary, start)
        if end == -1:
            end = body.find(b'\r\n--' + boundary + b'--', start)
        if end == -1:
            end = len(body)
        parts.append(body[start:end])
    result = {}
    for part in parts:
        hdr_end = part.find(b'\r\n\r\n')
        if hdr_end == -1:
            continue
        headers = part[:hdr_end].decode("utf-8", "replace")
        body_part = part[hdr_end + 4:]
        name_m = re.search(r'name="([^"]+)"', headers)
        if not name_m:
            continue
        name = name_m.group(1)
        filename_m = re.search(r'filename="([^"]+)"', headers)
        result[name] = body_part
    return result


def handler(request) -> Tuple[bytes, int, dict]:
    """Vercel 함수 핸들러 — multipart로 받은 A, B를 이식해 C 반환."""
    if request.method != "POST":
        return (b"Method Not Allowed", 405, {"Content-Type": "text/plain"})

    content_type = request.headers.get("content-type", "")
    body = request.get_data()

    if not content_type.startswith("multipart/form-data"):
        return (b"Bad Request: expected multipart", 400, {"Content-Type": "text/plain"})

    m = re.search(r'boundary=([^;]+)', content_type)
    if not m:
        return (b"Bad Request: no boundary", 400, {"Content-Type": "text/plain"})
    boundary = m.group(1).encode("utf-8")
    if boundary.startswith(b'"') and boundary.endswith(b'"'):
        boundary = boundary[1:-1]

    try:
        fields = _parse_multipart(body, boundary)
    except Exception as e:
        return (f"Parse error: {e}".encode(), 400, {"Content-Type": "text/plain"})

    a_bytes = fields.get("a")
    b_bytes = fields.get("b")
    if a_bytes is None or b_bytes is None:
        return (b"Bad Request: need both 'a' and 'b' fields", 400, {"Content-Type": "text/plain"})

    a_len = len(a_bytes)
    b_len = len(b_bytes)
    if a_len > MAX_A_MB * 1024 * 1024:
        return (f"A too large: {a_len} bytes".encode(), 413, {"Content-Type": "text/plain"})
    if b_len > MAX_B_MB * 1024 * 1024:
        return (f"B too large: {b_len} bytes".encode(), 413, {"Content-Type": "text/plain"})
    if a_len + b_len > MAX_TOTAL_MB * 1024 * 1024:
        return (f"Total too large: {a_len + b_len} bytes".encode(), 413, {"Content-Type": "text/plain"})

    tmpdir = tempfile.mkdtemp(prefix="hwpx_")
    try:
        a_path = Path(tmpdir) / "A.hwpx"
        b_path = Path(tmpdir) / "B.hwpx"
        out_path = Path(tmpdir) / "C.hwpx"
        a_path.write_bytes(a_bytes)
        b_path.write_bytes(b_bytes)

        summary = hwpx_core.run(a_path, b_path, out_path)

        out_bytes = out_path.read_bytes()
        if len(out_bytes) > MAX_OUT_MB * 1024 * 1024:
            return (f"Output too large: {len(out_bytes)} bytes".encode(), 413, {"Content-Type": "text/plain"})

        return (
            out_bytes,
            200,
            {
                "Content-Type": "application/hwp+zip",
                "Content-Disposition": "attachment; filename=C.hwpx",
                "Content-Length": str(len(out_bytes)),
            },
        )
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        return (f"Internal error: {e}\n{tb}".encode(), 500, {"Content-Type": "text/plain"})
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
