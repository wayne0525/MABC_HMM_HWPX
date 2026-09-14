# -*- coding: utf-8 -*-
"""
Fixture 유효성 검사 — 엔진 결과(hwpx_core.run)를 사용하지 않고
ZIP/XML 구조만으로 fixture가 HWPX로서 유효한지 검증한다.

검사 대상 기대 fixture 3개:
- A_verified.hwpx   (train-pair 01_culture_cctv 실제 A)
- B_verified.hwpx   (train-pair 01_culture_cctv 실제 B)
- test_fixtures_only.hwpx (기존 합성 fixture, 실문서 구조로 재작성됨)
"""
from __future__ import annotations

import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _parse_xml_bytes(data: bytes) -> ET.Element:
    """XML 바이트를 파싱해 루트를 반환."""
    return ET.fromstring(data.decode("utf-8"))


def _local_name(tag: str) -> str:
    """namespaced 태그에서 로컬 이름만 추출."""
    return tag.split("}")[-1] if "}" in tag else tag


def _root_element_info(root: ET.Element) -> dict:
    """루트 요소의 태그, 네임스페이스 URI, 속성 목록을 반환."""
    tag = root.tag
    ns_uri = ""
    if "}" in tag:
        ns_uri = tag.split("}")[0].lstrip("{")
    return {
        "tag": tag,
        "local": _local_name(tag),
        "namespace_uri": ns_uri,
        "attrib_keys": list(root.attrib.keys()),
    }


class TestFixtureValidity(unittest.TestCase):
    """fixture ZIP/XML 구조 유효성 검사."""

    def _assert_valid_hwpx_zip(self, path: Path, label: str) -> dict:
        """HWPX ZIP으로서 기본 요건을 검증하고 결과를 dict로 반환."""
        self.assertTrue(path.exists(), f"{label}: 파일 없음 ({path})")
        z = zipfile.ZipFile(path)

        names = z.namelist()
        entries = {n: z.read(n) for n in names}

        result = {
            "path": str(path),
            "entry_names": names,
            "mimetype": entries.get("mimetype", b"").decode("ascii", "replace").strip(),
            "has_mimetype": "mimetype" in names,
            "has_header": "Contents/header.xml" in names,
            "has_section": "Contents/section0.xml" in names,
            "has_manifest": "META-INF/manifest.xml" in names,
            "has_container": "META-INF/container.xml" in names,
        }

        # mimetype 첫 엔트리 & 내용 확인
        self.assertEqual(names[0], "mimetype", f"{label}: mimetype이 첫 엔트리가 아님")
        self.assertEqual(result["mimetype"], "application/hwp+zip", f"{label}: mimetype 내용 불일치")

        # 필수 파트 존재
        for key in ["has_mimetype", "has_header", "has_section", "has_manifest", "has_container"]:
            self.assertTrue(result[key], f"{label}: 필수 파트 누락 ({key})")

        # XML 파싱 가능 여부
        for xml_path in ["Contents/header.xml", "Contents/section0.xml", "META-INF/manifest.xml"]:
            if xml_path in entries:
                try:
                    ET.fromstring(entries[xml_path].decode("utf-8"))
                except ET.ParseError as e:
                    self.fail(f"{label}: {xml_path} XML 파싱 실패: {e}")

        return result

    def _check_section_text_and_table(self, path: Path, label: str, expected_texts: list[str], expect_table: bool = True):
        """section0.xml에서 텍스트와 표 존재 여부를 확인."""
        z = zipfile.ZipFile(path)
        sec_bytes = z.read("Contents/section0.xml")
        root = _parse_xml_bytes(sec_bytes)

        root_info = _root_element_info(root)
        self.assertTrue(
            root_info["namespace_uri"].startswith("http://www.hancom.co.kr/hwpml"),
            f"{label}: 알 수 없는 네임스페이스 URI ({root_info['namespace_uri']})"
        )

        # 텍스트 수집
        all_texts = []
        for t in root.iter():
            if _local_name(t.tag) == "t":
                txt = (t.text or "").strip()
                if txt:
                    all_texts.append(txt)

        # 기대 텍스트 포함 확인
        for exp in expected_texts:
            found = any(exp in txt for txt in all_texts)
            self.assertTrue(found, f"{label}: 기대 텍스트 '{exp}' 미발견 (전체 텍스트: {all_texts})")

        # 표 존재 여부
        if expect_table:
            tbls = [e for e in root.iter() if _local_name(e.tag) == "tbl"]
            self.assertGreater(len(tbls), 0, f"{label}: 표(tbl) 없음")

    def test_A_verified_fixture(self):
        """A_verified.hwpx: train-pair 실제 A 파일 유효성."""
        path = FIXTURES / "A_verified.hwpx"
        result = self._assert_valid_hwpx_zip(path, "A_verified")

        # 실제 문서 기반 기대 텍스트
        self._check_section_text_and_table(
            path, "A_verified",
            expected_texts=["개인영상정보", "청구서", "서울특별시한성백제박물관장"],
            expect_table=False,
        )

    def test_B_verified_fixture(self):
        """B_verified.hwpx: train-pair 실제 B 파일 유효성."""
        path = FIXTURES / "B_verified.hwpx"
        result = self._assert_valid_hwpx_zip(path, "B_verified")

        # 실제 문서 기반 기대 텍스트
        self._check_section_text_and_table(
            path, "B_verified",
            expected_texts=["도혜성", "010-4421-8803", "2026년 9월 10일"],
            expect_table=False,
        )

    def test_test_fixtures_only_fixture(self):
        """test_fixtures_only.hwpx: 기존 합성 fixture, 실문서 구조로 재작성됨."""
        path = FIXTURES / "test_fixtures_only.hwpx"
        result = self._assert_valid_hwpx_zip(path, "test_fixtures_only")

        # 실문서 구조 검증: namespace, 표 존재, 기대 텍스트
        self._check_section_text_and_table(
            path, "test_fixtures_only",
            expected_texts=["2024가합12345", "원고", "피고", "김철수", "이영희"],
            expect_table=True,
        )


if __name__ == "__main__":
    unittest.main()
