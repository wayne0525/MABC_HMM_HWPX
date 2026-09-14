# -*- coding: utf-8 -*-
"""
HWPX core — 이식/채우기 파이프라인 단일 구현.

root transplant.py와 vercel/api/handler.py가 같은 패키지를 import 한다.
ZIP 입출력, XML 파싱/정규식 편집, 이식 본문 조립을 담당한다.
CLI와 Vercel handler는 이 패키지 바깥에서 오케스트레이션만 한다.
"""

from __future__ import annotations

import re
import sys
import shutil
import zipfile
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# ------------------------------------------------------------------
# 네임스페이스
# ------------------------------------------------------------------

NS = {
    "hh": "http://www.hancom.co.kr/hwpml/2011/header",
    "hp": "http://www.hancom.co.kr/hwpml/2011/head",
    "hs": "http://www.hancom.co.kr/hwpml/2011/head",
    "hc": "http://www.hancom.co.kr/hwpml/2011/oxml",
    "hpf": "http://www.hancom.co.kr/hwpml/2011/hpf",
    "xml": "http://www.w3.org/XML/1998/namespace",
}

def _q(tag: str) -> str:
    if ":" in tag:
        prefix, local = tag.split(":", 1)
        uri = NS.get(prefix)
        if uri is None:
            raise ValueError(f"Unknown namespace prefix: {prefix}")
        return f"{{{uri}}}{local}"
    return tag

# ------------------------------------------------------------------
# ZIP 읽기/쓰기
# ------------------------------------------------------------------

def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read_hwpx_zip(path: Path) -> Tuple[bytes, List[Tuple[str, bytes]], Dict[str, bytes]]:
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        if not names or names[0] != "mimetype":
            raise ValueError(f"mimetype이 첫 엔트리가 아님: {names[:3]}")
        mimetype = zf.read("mimetype")
        entries: List[Tuple[str, bytes]] = []
        by_name: Dict[str, bytes] = {}
        for name in names:
            data = zf.read(name)
            entries.append((name, data))
            by_name[name] = data
        return mimetype, entries, by_name

def read_zip_infos(path: Path) -> list:
    with zipfile.ZipFile(path) as zf:
        return zf.infolist()

def verify_mimetype(data: bytes) -> None:
    text = data.decode("ascii", "replace").strip()
    if text != "application/hwp+zip":
        raise ValueError(f"mimetype 내용이 다름: {text!r}")

# ------------------------------------------------------------------
# header.xml 통계
# ------------------------------------------------------------------

def parse_header(data: bytes) -> ET.Element:
    return ET.fromstring(data.decode("utf-8"))

def header_counts(root: ET.Element) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for child in root:
        local = child.tag.split("}")[-1]
        counts[local] = counts.get(local, 0) + 1
    return counts

def count_charPr(header_text: str) -> int:
    return len(re.findall(r"<hh:charPr\b", header_text))

def count_paraPr(header_text: str) -> int:
    return len(re.findall(r"<hh:paraPr\b", header_text))

def count_charPr_items(header_text: str) -> int:
    m = re.search(r'<hh:charProperties[^>]*itemCnt="(\d+)"', header_text)
    return int(m.group(1)) if m else 0

def count_paraPr_items(header_text: str) -> int:
    m = re.search(r'<hh:paraProperties[^>]*itemCnt="(\d+)"', header_text) or re.search(r'<hh:paraPrList[^>]*itemCnt="(\d+)"', header_text)
    return int(m.group(1)) if m else 0

def count_styles_items(header_text: str) -> int:
    m = re.search(r'<hh:styles[^>]*itemCnt="(\d+)"', header_text)
    return int(m.group(1)) if m else 0

def count_borderFill_items(header_text: str) -> int:
    m = re.search(r'<hh:borderFills[^>]*itemCnt="(\d+)"', header_text)
    return int(m.group(1)) if m else 0

def count_fonts(header_text: str) -> Tuple[int, int]:
    m = re.search(r'<hh:fontfaces[^>]*itemCnt="(\d+)"', header_text)
    total = int(m.group(1)) if m else 0
    fonts = len(re.findall(r"<hh:font\b", header_text))
    return total, fonts

# ------------------------------------------------------------------
# 섹션 본문 파싱
# ------------------------------------------------------------------

def attr_value(attrs: str, name: str) -> str:
    m = re.search(rf'{name}="([^"]*)"', attrs)
    return m.group(1) if m else ""

def find_closing_tag(text: str, start: int, tag: str) -> int:
    import re as _re
    # tag는 "p"처럼 로컬 이름만 받거나 "hp:p"처럼 접두사 포함 받을 수 있다
    # 로컬 이름만 받으면 [a-z]+:tag 패턴으로 찾는다
    if ":" in tag:
        open_pat = _re.compile(rf"<{tag}")
        close_pat = _re.compile(rf"</{tag}>")
    else:
        open_pat = _re.compile(rf"<[a-z]+:{tag}")
        close_pat = _re.compile(rf"</[a-z]+:{tag}>")
    depth = 1
    i = start
    while True:
        o = open_pat.search(text, i)
        c = close_pat.search(text, i)
        if o is None and c is None:
            return -1
        if c is not None and (o is None or c.start() < o.start()):
            depth -= 1
            if depth == 0:
                return c.end()
            i = c.end()
        else:
            depth += 1
            i = o.end() if o is not None else (i + 1)

def section_text_runs(section_text: str) -> List[Tuple[str, str, str, List[str]]]:
    """
    섹션 본문에서 문단(p) 단위로 순회해 (id, paraPrIDRef, styleIDRef, 텍스트 리스트)를 반환.
    표의 셀 문단(p)도 포함한다 (호출자가 구분해야 함).
    """
    out: List[Tuple[str, str, str, List[str]]] = []
    for m in re.finditer(r"<[a-z]+:p\b([^>]*)>", section_text):
        attrs = m.group(1)
        pid = attr_value(attrs, "id")
        para = attr_value(attrs, "paraPrIDRef")
        style = attr_value(attrs, "styleIDRef")
        start = m.end()
        end = find_closing_tag(section_text, start, "p")
        block = section_text[start:end] if end > start else ""
        runs_texts: List[str] = []
        for rm in re.finditer(r"<[a-z]+:run\b[^>]*>(.*?)</[a-z]+:run>", block, re.S):
            run_block = rm.group(1)
            for tm in re.finditer(r"<[a-z]+:t\b[^>]*>(.*?)</[a-z]+:t>", run_block, re.S):
                runs_texts.append(tm.group(1))
        out.append((pid, para, style, runs_texts))
    return out

def section_text_only(section_text: str) -> List[str]:
    """각 문단의 텍스트를 단순 리스트로. 구조 판단용."""
    out: List[str] = []
    for pid, para, style, runs in section_text_runs(section_text):
        joined = "".join(runs).strip()
        out.append(joined)
    return out

def section_table_cells(section_text: str) -> List[List[str]]:
    """표의 셀 텍스트를 행×열 리스트로 추출. 표가 여러 개면 앞 표 우선."""
    tbl_match = re.search(r"<[a-z]+:tbl\b", section_text)
    if not tbl_match:
        return []
    tbl_start = tbl_match.start()
    tbl_end = find_closing_tag(section_text, tbl_start, "tbl")
    if tbl_end < 0:
        return []
    tbl_block = section_text[tbl_start:tbl_end]
    rows: List[List[str]] = []
    for tr_match in re.finditer(r"<[a-z]+:tr\b[^>]*>", tbl_block):
        tr_start = tr_match.end()
        tr_end = find_closing_tag(tbl_block, tr_start, "tr")
        if tr_end < 0:
            continue
        tr_block = tbl_block[tr_start:tr_end]
        cells: List[str] = []
        for tc_match in re.finditer(r"<[a-z]+:tc\b[^>]*>", tr_block):
            tc_start = tc_match.end()
            tc_end = find_closing_tag(tr_block, tc_start, "tc")
            if tc_end < 0:
                continue
            tc_block = tr_block[tc_start:tc_end]
            cell_text_parts: List[str] = []
            for p_match in re.finditer(r"<[a-z]+:p\b[^>]*>", tc_block):
                p_start = p_match.end()
                p_end = find_closing_tag(tc_block, p_start, "p")
                if p_end < 0:
                    continue
                p_block = tc_block[p_start:p_end]
                for t_match in re.finditer(r"<[a-z]+:t\b[^>]*>(.*?)</[a-z]+:t>", p_block, re.S):
                    cell_text_parts.append(t_match.group(1))
            cells.append("".join(cell_text_parts).strip())
        rows.append(cells)
    return rows

# ------------------------------------------------------------------
# 텍스트 교체
# ------------------------------------------------------------------

def replace_t_in_paragraph(p_xml: str, new_texts: List[str]) -> str:
    """
    한 hp:p 안에서 hp:run > hp:t 텍스트를 new_texts로 교체.
    run의 개수/순서, 다른 속성은 그대로 보존한다.
    """
    runs = re.findall(r"<[a-z]+:run\b.*?</[a-z]+:run>", p_xml, re.S)
    if not runs:
        return p_xml
    new_runs: List[str] = []
    t_in_runs = [re.findall(r"<[a-z]+:t\b.*?</[a-z]+:t>", r, re.S) for r in runs]
    run_t_counts = [len(x) for x in t_in_runs]
    idx = 0
    for ri, r in enumerate(runs):
        n = run_t_counts[ri] if ri < len(run_t_counts) else 1
        chunk: List[str] = []
        for _ in range(n):
            if idx < len(new_texts):
                chunk.append(new_texts[idx])
                idx += 1
            else:
                chunk.append("")
        new_r = r
        t_matches = re.findall(r"<[a-z]+:t\b.*?</[a-z]+:t>", r, re.S)
        for tm in t_matches:
            new_t = tm
            m = re.match(r"(<[a-z]+:t[^>]*>)(.*?)(</[a-z]+:t>)", tm, re.S)
            if m:
                open_tag, _, close_tag = m.group(1), m.group(2), m.group(3)
                new_t = f"{open_tag}{chunk.pop(0)}{close_tag}"
            new_r = new_r.replace(tm, new_t, 1)
        new_runs.append(new_r)
    if idx < len(new_texts):
        template_run = runs[0] if runs else "<hp:run><hp:t></hp:t></hp:run>"
        for remaining in new_texts[idx:]:
            new_runs_template = template_run
            new_r = re.sub(
                r"<[a-z]+:t\b.*?</[a-z]+:t>",
                f"<hp:t>{remaining}</hp:t>",
                new_runs_template,
                count=1,
                flags=re.S,
            )
            new_runs.append(new_r)
    p_tag = re.match(r"(<[a-z]+:p\b[^>]*>)(.*?)(</[a-z]+:p>)", p_xml, re.S)
    if not p_tag:
        return p_xml
    open_tag, inner, close_tag = p_tag.group(1), p_tag.group(2), p_tag.group(3)
    new_inner = "".join(new_runs)
    return f"{open_tag}{new_inner}{close_tag}"

def drop_linesegarray(text: str) -> str:
    """hp:linesegarray를 제거. 한글에서 재생성하게 둔다."""
    return re.sub(r"<hp:linesegarray\b.*?</hp:linesegarray>", "", text, flags=re.S)

# ------------------------------------------------------------------
# 본문 이식 (이식 모드)
# ------------------------------------------------------------------

def transplant_body_v4(a_section_text: str, b_section_text: str) -> str:
    """
    A의 표 구조·라벨·서명은 그대로 두고, 본문 텍스트만 B로 교체하거나
    추가한다.

    B의 첫 문단들을 A 본문의 앞 문단(paraPrIDRef/name 미지정)에 우선 교체하고,
    남은 B는 A 본문 마지막 뒤에 새 문단으로 추가한다.
    """
    b_texts = section_text_only(b_section_text)
    if not b_texts:
        return a_section_text

    a_paras = re.findall(r"<[a-z]+:p\b.*?</[a-z]+:p>", a_section_text, re.S)
    tbl_match = re.search(r"<[a-z]+:tbl\b", a_section_text)
    tbl_start = tbl_match.start() if tbl_match else None

    para_info = []
    search_start = 0
    for p in a_paras:
        off = a_section_text.find(p, search_start)
        search_start = off + len(p) if off >= 0 else search_start
        para_info.append((p, off))

    pre_paras = [
        (p, off) for p, off in para_info if tbl_start is None or off < tbl_start
    ]

    new_paras = list(a_paras)
    text_idx = 0
    for i, (p_xml, off) in enumerate(pre_paras):
        if "<[a-z]+:tc" in p_xml or "<hp:tc" in p_xml:
            continue
        if text_idx < len(b_texts):
            new_paras[a_paras.index(p_xml)] = replace_t_in_paragraph(
                p_xml, [b_texts[text_idx]]
            )
            text_idx += 1

    remaining = b_texts[text_idx:]
    if remaining:
        new_paras.extend(_build_extra_paras(remaining, a_paras))

    new_inner = "".join(new_paras)
    secpr = re.search(r"<hp:secPr\b.*?</hp:secPr>", a_section_text, re.S)
    # root 요소(hp:hp)의 namespace 선언을 출력 앞에 포함
    root_open = re.search(r"<[a-z]+:hp[^>]*>", a_section_text)
    root_close = re.search(r"</[a-z]+:hp>", a_section_text)
    head = root_open.group(0) + "\n" if root_open else ""
    tail = "\n" + root_close.group(0) if root_close else ""
    body = (secpr.group(0) + "\n" + new_inner) if secpr else new_inner
    new_section = head + body + tail
    new_section = drop_linesegarray(new_section)
    return new_section

def _build_extra_paras(
    texts: List[str],
    a_paras: List[str],
) -> List[str]:
    """
    B에서 교체하고 남은 텍스트를 새 문단 요소로 만들어 반환.

    A의 마지막 문단 템플릿을 참고해 run/t 구조를 만들고, id는 A에 존재하는
    최대 id보다 큰 값으로 순차적으로 부여한다.
    """
    if not a_paras:
        return []
    last = a_paras[-1]
    run_template = re.search(r"<hp:run\b.*?</hp:run>", last, re.S)
    run_tmpl = run_template.group(0) if run_template else "<hp:run><hp:t></hp:t></hp:run>"
    # A에 존재하는 최대 id 찾기
    max_id = 0
    for p in a_paras:
        m = re.search(r'<[a-z]+:p\b[^>]*\bid="(\d+)"', p)
        if m:
            max_id = max(max_id, int(m.group(1)))
    out = []
    for i, t in enumerate(texts):
        new_run = re.sub(
            r"<hp:t\b.*?</hp:t>",
            f"<hp:t>{t}</hp:t>",
            run_tmpl,
            count=1,
            flags=re.S,
        )
        out.append(
            f'<hp:p id="{max_id + 1 + i}" paraPrIDRef="0" styleIDRef="0" '
            f"pageBreak=\"0\" columnBreak=\"0\" merged=\"0\">"
            f"{new_run}"
            f"</hp:p>"
        )
    return out

# ------------------------------------------------------------------
# 스타일 ID 재매핑
# ------------------------------------------------------------------

def build_id_map_from_header(header_text: str) -> Dict[str, Dict[str, int]]:
    """
    A의 header에서 실제 charPr/paraPr/style/borderFill ID 목록을 뽑는다.
    """
    char_ids = [
        m.group(1)
        for m in re.finditer(r'<hh:charPr\b[^>]*id="([^"]+)"', header_text)
    ]
    para_ids = [
        m.group(1)
        for m in re.finditer(r'<hh:paraPr\b[^>]*id="([^"]+)"', header_text)
    ]
    style_ids = [
        m.group(1)
        for m in re.finditer(r'<hh:style\b[^>]*id="([^"]+)"', header_text)
    ]
    border_ids = [
        m.group(1)
        for m in re.finditer(r'<hh:borderFill\b[^>]*id="([^"]+)"', header_text)
    ]
    return {
        "charPr": {cid: i for i, cid in enumerate(char_ids)},
        "paraPr": {pid: i for i, pid in enumerate(para_ids)},
        "style": {sid: i for i, sid in enumerate(style_ids)},
        "borderFill": {bid: i for i, bid in enumerate(border_ids)},
    }

# ------------------------------------------------------------------
# ZIP 재조립
# ------------------------------------------------------------------

def write_hwpx_zip(
    out_path: Path,
    original_infos: list,
    modified: Dict[str, bytes],
    mimetype: bytes,
) -> None:
    """
    출력 HWPX를 쓴다. mimetype은 첫 엔트리, STORED 압축.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w") as zf:
        zi = zipfile.ZipInfo("mimetype")
        zi.compress_type = zipfile.ZIP_STORED
        zi.date_time = (1980, 1, 1, 0, 0, 0)
        zf.writestr(zi, mimetype)
        for info in original_infos:
            name = info.filename
            if name == "mimetype":
                continue
            data = modified.get(name)
            if data is None:
                continue
            out_info = zipfile.ZipInfo(filename=name, date_time=info.date_time)
            out_info.compress_type = info.compress_type
            out_info.external_attr = info.external_attr
            out_info.internal_attr = info.internal_attr
            out_info.create_system = info.create_system
            zf.writestr(out_info, data)

# ------------------------------------------------------------------
# 메인 파이프라인 (이식 모드)
# ------------------------------------------------------------------

def run(
    a_path: Path,
    b_path: Path,
    out_path: Path,
    label: str = "",
) -> Dict:
    """
    A(서식)와 B(내용) HWPX로 새로운 HWPX C를 만들어 out_path에 쓴다.
    """
    a_mimetype, a_entries, a_by_name = read_hwpx_zip(a_path)
    verify_mimetype(a_mimetype)
    a_header = a_by_name["Contents/header.xml"].decode("utf-8")
    a_section = a_by_name["Contents/section0.xml"].decode("utf-8")

    b_mimetype, b_entries, b_by_name = read_hwpx_zip(b_path)
    verify_mimetype(b_mimetype)
    b_header = b_by_name["Contents/header.xml"].decode("utf-8")
    b_section = b_by_name["Contents/section0.xml"].decode("utf-8")

    summary = {
        "a_sha256": sha256_path(a_path),
        "b_sha256": sha256_path(b_path),
        "a_header_size": len(a_header),
        "b_header_size": len(b_header),
        "a_section_size": len(a_section),
        "b_section_size": len(b_section),
        "a_charPr": count_charPr(a_header),
        "a_paraPr": count_paraPr(a_header),
        "a_styles": count_styles_items(a_header),
        "a_borderFill": count_borderFill_items(a_header),
        "a_font_total": count_fonts(a_header)[0],
        "a_font_faces": count_fonts(a_header)[1],
        "b_charPr": count_charPr(b_header),
        "b_paraPr": count_paraPr(b_header),
        "b_section_paras": len(re.findall(r"<hp:p\b", b_section)),
        "b_section_tables": len(re.findall(r"<hp:tbl\b", b_section)),
        "b_table_rows": len(section_table_cells(b_section)),
    }

    b_table_cells = section_table_cells(b_section)
    new_section = transplant_body_v4(a_section, b_section)
    new_header = a_header

    modified: Dict[str, bytes] = {
        "Contents/header.xml": new_header.encode("utf-8"),
        "Contents/section0.xml": new_section.encode("utf-8"),
    }
    for name, data in a_entries:
        if name not in modified and name != "mimetype":
            modified[name] = data

    original_infos = read_zip_infos(a_path)
    write_hwpx_zip(out_path, original_infos, modified, a_mimetype)

    summary["out_path"] = str(out_path)
    summary["out_sha256"] = sha256_path(out_path)
    summary["out_size"] = out_path.stat().st_size
    summary["label"] = label
    return summary
