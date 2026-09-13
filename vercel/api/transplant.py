# -*- coding: utf-8 -*-
"""
Vercel serverless function: HWPX style transplant.
POST /api/transplant  (multipart/form-data)
  fields: style(A), content(B)
  returns: C.hwpx  (Content-Type: application/hwp+zip)
"""
from __future__ import annotations

import os
import re
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Tuple, List, Dict, Optional

# ------------------------------------------------------------------
# multipart/form-data 파서 (stdlib only)
# ------------------------------------------------------------------

def _parse_multipart(body: bytes, boundary: str) -> Dict[str, bytes]:
    """multipart/form-data 본문을 파싱해 필드명->bytes 사전을 반환."""
    delim = b"--" + boundary.encode("ascii")
    parts: Dict[str, bytes] = {}
    # 본문은 delim + CRLF 로 시작, 마지막은 delim + b"--" 로 끝
    chunks = body.split(delim)
    for chunk in chunks:
        chunk = chunk.strip(b"\r\n")
        if not chunk or chunk == b"--":
            continue
        head, _, data = chunk.partition(b"\r\n\r\n")
        if not head:
            continue
        head_text = head.decode("ascii", "replace")
        # Content-Disposition에서 name과 filename 추출
        m_name = re.search(r'name="([^"]+)"', head_text)
        if not m_name:
            continue
        name = m_name.group(1)
        m_fn = re.search(r'filename="([^"]+)"', head_text)
        if m_fn:
            # 파일 파트: 데이터 앞쪽의 CRLF 제거 후 저장
            # data는 body의 일부; 경계 직후 CRLF 다음부터 실제 데이터
            # 이미 partition이 \r\n\r\n 기준으로 나눴으므로 data 그대로 사용
            parts[name] = data
        else:
            # 일반 필드
            parts[name] = data
    return parts

def _extract_file(part_data: bytes) -> bytes:
    """파트 데이터에서 앞쪽 공백/CRLF 정리 후 순수 파일 바이트 반환."""
    # 파일 데이터는 \r\n\r\n 뒤부터 시작. tail에 \r\n--boundary 같은 게 붙을 수 있음.
    # 정리: 앞쪽 CRLF 제거하고, trailing CRLF 제거
    data = part_data
    # 앞쪽 정리
    while data.startswith(b"\r\n"):
        data = data[2:]
    # 뒤쪽 정리: 경계나 CRLF 정리
    while data.endswith(b"\r\n"):
        data = data[:-2]
    return data

# ------------------------------------------------------------------
# 크기 제한
# ------------------------------------------------------------------

MAX_A_BYTES = 5 * 1024 * 1024   # 5 MB
MAX_B_BYTES = 1 * 1024 * 1024   # 1 MB
MAX_TOTAL_BYTES = 6 * 1024 * 1024  # 6 MB
MAX_OUT_BYTES = 5 * 1024 * 1024    # 5 MB

def _size_error(label: str, got: int, max_bytes: int) -> Tuple[str, int]:
    return (f"{label} 파일이 너무 큽니다(최대 {max_bytes} bytes, 실제 {got} bytes).", 400)

# ------------------------------------------------------------------
# HWPX 검증
# ------------------------------------------------------------------

def _is_hwpx_magic(data: bytes) -> bool:
    return data[:4] == b"PK\x03\x04"

def _validate_hwpx(data: bytes, label: str) -> Optional[str]:
    if not _is_hwpx_magic(data):
        return f"{label} 파일은 HWPX가 아닙니다(mimetype 불일치)."
    return None

# ------------------------------------------------------------------
# Vercel handler
# ------------------------------------------------------------------

def handler(request):
    if request.method != "POST":
        return ("Method not allowed", 405, {"Content-Type": "text/plain"})

    content_type = request.content_type or ""
    m = re.search(r'boundary=([^;\s]+)', content_type)
    if not m:
        return ('"Content-Type: multipart/form-data"가 필요합니다.', 400, {"Content-Type": "text/plain"})
    boundary = m.group(1).strip('"')

    body = request.get_data()
    if len(body) > MAX_TOTAL_BYTES:
        msg, _ = _size_error("업로드 전체", len(body), MAX_TOTAL_BYTES)
        return (msg, 400, {"Content-Type": "text/plain"})

    parts = _parse_multipart(body, boundary)
    a_raw = parts.get("style")
    b_raw = parts.get("content")

    if a_raw is None:
        return ("A(서식) 파일이 필요합니다.", 400, {"Content-Type": "text/plain"})
    if b_raw is None:
        return ("B(내용) 파일이 필요합니다.", 400, {"Content-Type": "text/plain"})

    a_data = _extract_file(a_raw)
    b_data = _extract_file(b_raw)

    err = _validate_hwpx(a_data, "A")
    if err:
        return (err, 400, {"Content-Type": "text/plain"})
    err = _validate_hwpx(b_data, "B")
    if err:
        return (err, 400, {"Content-Type": "text/plain"})

    if len(a_data) > MAX_A_BYTES:
        msg, _ = _size_error("A", len(a_data), MAX_A_BYTES)
        return (msg, 400, {"Content-Type": "text/plain"})
    if len(b_data) > MAX_B_BYTES:
        msg, _ = _size_error("B", len(b_data), MAX_B_BYTES)
        return (msg, 400, {"Content-Type": "text/plain"})

    # 임시 파일로 저장 후 이식 실행
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        a_path = tmpdir / "style.hwpx"
        b_path = tmpdir / "content.hwpx"
        c_path = tmpdir / "transplanted.hwpx"
        a_path.write_bytes(a_data)
        b_path.write_bytes(b_data)

        try:
            import transplant
            summary = transplant.run(a_path, b_path, c_path)
        except KeyError as exc:
            return (f"HWPX 패키지에 필요한 항목이 없습니다: {exc}", 400, {"Content-Type": "text/plain"})
        except ValueError as exc:
            return (str(exc), 400, {"Content-Type": "text/plain"})
        except Exception as exc:
            return (f"이식에 실패했습니다: {exc}", 500, {"Content-Type": "text/plain"})

        c_data = c_path.read_bytes()

    if len(c_data) > MAX_OUT_BYTES:
        msg, _ = _size_error("결과 C", len(a_data) + len(b_data), MAX_OUT_BYTES)
        return (msg + " (출력 파일이 너무 큽니다.)", 400, {"Content-Type": "text/plain"})

    headers = {
        "Content-Type": "application/hwp+zip",
        "Content-Disposition": 'attachment; filename="C.hwpx"',
        "Access-Control-Expose-Headers": "Content-Disposition",
    }
    return (c_data, 200, headers)
