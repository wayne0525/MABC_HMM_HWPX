# -*- coding: utf-8 -*-
"""
RED-state tests — 현재 알려진 실패를 문서화.

이 테스트들은 현재 실패해야 정상(RED)이다.
각 테스트의 docstirng에 실패 이유와 TODO가 명시되어 있다.
"""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

# repo 내 fixture만 사용 — 개인 Downloads 경로 없음
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(FIXTURES.parent))  # vercel/

import hwpx_core  # noqa: E402


def _tmp_out(name: str) -> Path:
    p = Path(tempfile.mktemp(suffix=name))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


class Test_RED_B_SingleSourceValue(unittest.TestCase):
    """[RED] B 섹션에 SOURCE_VALUE 하나 → 추출 결과가 SOURCE_VALUE.

    현재 transplant_body_v4는 B의 첫 문단 텍스트만 A의 앞 문단에 교체하고
    나머지는 뒤에 추가한다. B가 단일 문단이면 그 텍스트가 정확히 들어와야
    하지만, A의 표와 문단 순서에 따라 결과가 달라질 수 있다.
    """

    def test_extract_single_value(self):
        a = FIXTURES / "A_template.hwpx"
        b = FIXTURES / "B_content.hwpx"
        out = _tmp_out(".hwpx")
        try:
            summary = hwpx_core.run(a, b, out)
            c_section = zipfile.ZipFile(out).read("Contents/section0.xml").decode("utf-8")
            texts = hwpx_core.section_text_only(c_section)
            self.assertIn("2024가합12345", texts[0])
        finally:
            if out.exists():
                out.unlink()


class Test_RED_AltNamespace(unittest.TestCase):
    """[RED] B의 namespace 접두사가 q 등 hp가 아닐 때도 같은 결과.

    현재 section_text_runs/section_table_cells는 hp: 접두사만 찾는다.
    B가 hh: 등 다른 접두사를 쓰면 텍스트를 못 뽑는다.
    """

    def test_alt_ns_same_result(self):
        a = FIXTURES / "A_template.hwpx"
        b = FIXTURES / "B_content_alt_ns.hwpx"
        out = _tmp_out(".hwpx")
        try:
            summary = hwpx_core.run(a, b, out)
            c_section = zipfile.ZipFile(out).read("Contents/section0.xml").decode("utf-8")
            texts = hwpx_core.section_text_only(c_section)
            self.assertIn("2024가합12345", "".join(texts))
        finally:
            if out.exists():
                out.unlink()


class Test_RED_ET_FromString(unittest.TestCase):
    """[RED] 생성 section을 ET.fromstring으로 읽을 수 있어야 함.

    현재 transplant_body_v4의 출력은 정규식 기반이라 XML well-formedness가
    보장되지 않을 수 있다.
    """

    def test_output_is_parseable(self):
        import xml.etree.ElementTree as ET
        a = FIXTURES / "A_template.hwpx"
        b = FIXTURES / "B_content.hwpx"
        out = _tmp_out(".hwpx")
        try:
            hwpx_core.run(a, b, out)
            section_bytes = zipfile.ZipFile(out).read("Contents/section0.xml")
            ET.fromstring(section_bytes)
        finally:
            if out.exists():
                out.unlink()


class Test_RED_NoDuplicateText(unittest.TestCase):
    """[RED] 표 안/밖 텍스트가 중복 추출되지 않음."""

    def test_no_duplicate_extraction(self):
        a = FIXTURES / "A_template.hwpx"
        b = FIXTURES / "B_content.hwpx"
        out = _tmp_out(".hwpx")
        try:
            hwpx_core.run(a, b, out)
            c_section = zipfile.ZipFile(out).read("Contents/section0.xml").decode("utf-8")
            all_texts = hwpx_core.section_text_only(c_section)
            table_cells = hwpx_core.section_table_cells(c_section)
            all_flat = " ".join(all_texts)
            table_flat = " ".join(" ".join(row) for row in table_cells)
            for cell_text in table_flat.split():
                if cell_text.strip():
                    cnt = all_flat.count(cell_text)
                    self.assertLessEqual(cnt, 1,
                        f"표 셀 텍스트 '{cell_text}'가 본문에 {cnt}회 중복 등장")
        finally:
            if out.exists():
                out.unlink()


class Test_RED_CoreImportFromAnyDir(unittest.TestCase):
    """[RED] root/vercel/api 디렉터리 어디서 실행해도 동일 코어 사용."""

    def test_same_core_from_different_cwd(self):
        import subprocess
        r1 = subprocess.run(
            [sys.executable, "-c", "import hwpx_core; print(hwpx_core.run.__module__)"],
            cwd=str(FIXTURES.parent),
            capture_output=True, text=True,
            env={**__import__("os").environ, "PYTHONPATH": str(FIXTURES.parent.parent)},
        )
        self.assertEqual(r1.stdout.strip(), "hwpx_core.core")


class Test_RED_MultipartCRLF(unittest.TestCase):
    """[RED] multipart 파일 마지막 CRLF는 그대로 반환되어야 함."""

    def test_multipart_crlf_preserved(self):
        self.fail("multipart CRLF 보존 테스트는 핸들러 구현 후 작성 (05 이슈)")

if __name__ == "__main__":
    unittest.main()
