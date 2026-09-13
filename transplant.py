#!/usr/bin/env python3
"""
HWPX 서식 이식 (style transplant) — 실제 파일 기준 구현.

동작:
  python3 transplant.py A_style.hwpx B_content.hwpx out.hwpx

규칙 (SKILL.md / references 기준):
- A = 서식 원본. header.xml의 fontfaces/charPr/paraPr/style/borderFill, pagePr, 표 격자만 가져옴.
- B = 내용 원본. section0.xml의 hp:t 텍스트, 표 셀 텍스트, 이미지 참조만 가져옴. B의 서식은 버림.
- C는 A 패키지를 복제한 뒤, 본문(섹션)만 B의 내용 트리로 갈아 끼운다.
- charPr/paraPr/style/borderFill ID를 A<->B 사이에 그대로 복사하지 않는다.
  B는 공통 헤더(A와 동일한 서식)를 쓰는 경우 그대로 두고, 다른 서식이면 A의 서식으로 다시 매긴다.
- mimetype은 반드시 첫 엔트리, STORED.
- hp:linesegarray는 재생성 전 삭제.
- itemCnt는 실제 개수와 맞춘다.

범위(이번 구현):
- 섹션 1개 기준 (section0.xml).
- 이미지 복사는 내용.hpf + BinData + binaryItemIDRef 3곳 일치를 전제로 하며,
  이번 단계에서는 A가 이미지를 가졌을 때 B에도 같은 이미지가 있으면 유지하고, 없으면 A 구조를 보존한다.
- 표 격자·병합·borders·셀 배경·글꼴은 전부 A header의 borderFill/charPr/paraPr을 그대로 쓰는 것을 목표로 한다.
  B 표에 있던 셀 텍스트만 가져와서 A 표에 넣는 방식은 "B 표 값을 A 표에 이식"으로 별도 단계로 둔다.
- 이 스크립트는 "B가 A 헤더를 공유하는 단순 본문 이식"을 먼저 완성한다.
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
# 네임스페이스 처리 편의
# ------------------------------------------------------------------

NS = {
    "hh": "http://www.hancom.co.kr/hwpml/2011/header",
    "hp": "http://www.hancom.co.kr/hwpml/2011/head",
    "hs": "http://www.hancom.co.kr/hwpml/2011/head",
    "hc": "http://www.hancom.co.kr/hwpml/2011/oxml",
    "hpf": "http://www.hancom.co.kr/hwpml/2011/hpf",
    "xml": "http://www.w3.org/XML/1998/namespace",
}

# ElementTree는 기본 네임스페이스 접두사 처리가 까다로워서,
# 정규식 기반 저수준 편집을 병행한다. 진짜 이식 스크립트는
# 아래에서 "정규식으로 하는 부분"과 "ET로 하는 부분"을 분리해 둔다.

def _q(tag: str) -> str:
    """접두사:local -> {uri}local"""
    if ":" in tag:
        prefix, local = tag.split(":", 1)
        uri = NS.get(prefix)
        if uri is None:
            raise ValueError(f"Unknown namespace prefix: {prefix}")
        return f"{{{uri}}}{local}"
    return tag


# ------------------------------------------------------------------
# ZIP 순서/무결성 — mimetype 최우선, STORED
# ------------------------------------------------------------------


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_hwpx_zip(path: Path) -> Tuple[bytes, List[Tuple[str, bytes]], Dict[str, bytes]]:
    """HWX를 읽어서 (mimetype_bytes, entries_in_order, by_name)을 반환.

    entries_in_order: ZIP에 기록된 순서대로 (name, data) 목록.
    by_name: 이름 -> bytes (디폴트).
    mimetype은 첫 엔트리여야 하며, 내용 확인용으로 별도 반환.
    """
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
    """원본 ZIP의 ZipInfo 목록(순서, compress_type 등)을 보존용으로 읽는다."""
    with zipfile.ZipFile(path) as zf:
        return zf.infolist()


def verify_mimetype(data: bytes) -> None:
    text = data.decode("ascii", "replace").strip()
    if text != "application/hwp+zip":
        raise ValueError(f"mimetype 내용이 다름: {text!r}")


# ------------------------------------------------------------------
# header.xml 파싱 — 서식 프로필 추출 (사람 단위 + raw)
# ------------------------------------------------------------------


def parse_header(data: bytes) -> ET.Element:
    # header.xml은 기본 네임스페이스가 hh인 경우가 많음.
    # ET가 접두사 재명명을 하므로, 원본 문자열을 보존하기 위해
    # 파싱 후 직렬화할 때 접두사를 복원해야 한다.
    # 여기서는 ET로 구조만 읽고, 편집은 별도 정규식/문자열 경로로 간다.
    root = ET.fromstring(data.decode("utf-8"))
    return root


def header_counts(root: ET.Element) -> Dict[str, int]:
    """header.xml의 주요 항목 개수를 센다."""
    counts: Dict[str, int] = {}
    for tag in ["fontfaces", "charProperties", "paraProperties", "styles", "borderFill"]:
        # 실제 태그명은 hh:fontfaces, hh:charProperties, hh:paraProperties, hh:styles, hh:borderFills 등.
        el = root.find(_q("fontfaces")) or root.find(_q("charProperties")) or root.find(_q("paraProperties"))
    # 보다 정확히: 태그 이름 기준으로 센다.
    for child in root:
        local = child.tag.split("}")[-1]
        cn = re.sub(r"(^|[A-Z])", lambda m: "" if m.group(0)=="" else "", local)  # noop safety
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
    # borderFill은 hh:borderFills 안에 itemCnt 있을 수 있음.
    m = re.search(r'<hh:borderFills[^>]*itemCnt="(\d+)"', header_text)
    return int(m.group(1)) if m else 0


def count_fonts(header_text: str) -> Tuple[int, int]:
    m = re.search(r'<hh:fontfaces[^>]*itemCnt="(\d+)"', header_text)
    total = int(m.group(1)) if m else 0
    # 얼굴 수 세는 방식은 직접 센다.
    fonts = len(re.findall(r"<hh:font\b", header_text))
    return total, fonts


# ------------------------------------------------------------------
# 섹션 본문 파싱 — B의 텍스트/구조 추출
# ------------------------------------------------------------------


def section_text_runs(section_text: str) -> List[Tuple[str, str, str, List[str]]]:
    """문단 순서 그대로의 (id, paraPrIDRef, styleIDRef, texts)를 반환.

    section_text는 이미 디코딩된 str임을 전제로 한다.
    정규식 기반으로 hp:p를 찾아, 파일별 네임스페이스 차이에 영향받지 않는다.
    """
    out: List[Tuple[str, str, str, List[str]]] = []
    for m in re.finditer(r"<hp:p\b([^>]*)>", section_text):
        attrs = m.group(1)
        pid = attr_value(attrs, "id")
        para = attr_value(attrs, "paraPrIDRef")
        style = attr_value(attrs, "styleIDRef")
        # 문단 안쪽에서 hp:run > hp:t만 수집. 중첩 표 안은 별도 처리에서 배제.
        # 문단 시작~끝 범위
        start = m.end()
        end = find_closing_tag(section_text, start, "hp:p")
        block = section_text[start:end] if end > start else ""
        runs_texts: List[str] = []
        for rm in re.finditer(r"<hp:run\b[^>]*>(.*?)</hp:run>", block, re.S):
            run_block = rm.group(1)
            for tm in re.finditer(r"<hp:t\b[^>]*>(.*?)</hp:t>", run_block, re.S):
                runs_texts.append(tm.group(1))
        out.append((pid, para, style, runs_texts))
    return out


def attr_value(attrs: str, name: str) -> str:
    m = re.search(rf'{name}="([^"]*)"', attrs)
    return m.group(1) if m else ""


def find_closing_tag(text: str, start: int, tag: str) -> int:
    """text[start:]에서 </tag>의 위치를 찾는다. 중첩을 고려해 카운트."""
    open_tag = f"<{tag}"
    close_tag = f"</{tag}>"
    depth = 0
    i = start
    while True:
        o = text.find(open_tag, i)
        c = text.find(close_tag, i)
        if o == -1 and c == -1:
            return -1
        if c != -1 and (o == -1 or c < o):
            depth -= 1
            if depth == 0:
                return c + len(close_tag)
            i = c + len(close_tag)
        else:
            depth += 1
            i = o + len(open_tag)


def section_text_only(section_text: str) -> List[str]:
    """문단별 텍스트를 단순 리스트로. 구조 판단용."""
    out: List[str] = []
    for pid, para, style, runs in section_text_runs(section_text):
        joined = "".join(runs).strip()
        out.append(joined)
    return out


def section_table_cells(section_text: str) -> List[List[str]]:
    """표의 셀 텍스트를 행×열 리스트로 추출. 표가 여러 개면 앞 표 우선.

    section_text는 이미 디코딩된 str임을 전제로 한다.
    표가 없으면 빈 리스트.
    정규식 기반으로 hp:tbl/hp:tr/hp:tc를 찾아, 파일별 네임스페이스 차이에 영향받지 않는다.
    """
    tbl_match = re.search(r"<hp:tbl\b", section_text)
    if not tbl_match:
        return []
    tbl_start = tbl_match.start()
    tbl_end = find_closing_tag(section_text, tbl_start, "hp:tbl")
    if tbl_end < 0:
        return []
    tbl_block = section_text[tbl_start:tbl_end]

    rows: List[List[str]] = []
    for tr_match in re.finditer(r"<hp:tr\b[^>]*>", tbl_block):
        tr_start = tr_match.end()
        tr_end = find_closing_tag(tbl_block, tr_start, "hp:tr")
        if tr_end < 0:
            continue
        tr_block = tbl_block[tr_start:tr_end]
        cells: List[str] = []
        for tc_match in re.finditer(r"<hp:tc\b[^>]*>", tr_block):
            tc_start = tc_match.end()
            tc_end = find_closing_tag(tr_block, tc_start, "hp:tc")
            if tc_end < 0:
                continue
            tc_block = tr_block[tc_start:tc_end]
            cell_text_parts: List[str] = []
            for p_match in re.finditer(r"<hp:p\b[^>]*>", tc_block):
                p_start = p_match.end()
                p_end = find_closing_tag(tc_block, p_start, "hp:p")
                if p_end < 0:
                    continue
                p_block = tc_block[p_start:p_end]
                for t_match in re.finditer(r"<hp:t\b[^>]*>(.*?)</hp:t>", p_block, re.S):
                    cell_text_parts.append(t_match.group(1))
            cells.append("".join(cell_text_parts).strip())
        rows.append(cells)
    return rows


# ------------------------------------------------------------------
# 텍스트 교체 — hp:t 내용만 교체, 구조 보존
# ------------------------------------------------------------------


def replace_t_in_paragraph(p_xml: str, new_texts: List[str]) -> str:
    """한 hp:p 안에서 hp:run > hp:t 텍스트를 new_texts로 교체.
    run 개수보다 텍스트가 많으면 마지막 run을 복제해 채운다.
    run 개수가 더 많으면 남는 run은 비운다(빈 hp:t).
    """
    runs = re.findall(r"<hp:run\b.*?</hp:run>", p_xml, re.S)
    if not runs:
        return p_xml

    new_runs: List[str] = []
    t_in_runs = [re.findall(r"<hp:t\b.*?</hp:t>", r, re.S) for r in runs]
    # 각 run에 몇 개의 hp:t가 있는지
    run_t_counts = [len(x) for x in t_in_runs]

    # 새 텍스트를 run에 분배
    idx = 0
    for ri, r in enumerate(runs):
        n = run_t_counts[ri] if ri < len(run_t_counts) else 1
        # 이 run의 hp:t 개수만큼 새 텍스트
        chunk: List[str] = []
        for _ in range(n):
            if idx < len(new_texts):
                chunk.append(new_texts[idx])
                idx += 1
            else:
                chunk.append("")
        # run 내에서 hp:t를 교체
        new_r = r
        t_matches = re.findall(r"<hp:t\b.*?</hp:t>", r, re.S)
        for tm in t_matches:
            # tm 예: <hp:t>xxx</hp:t> 또는 <hp:t xml:space="preserve">xxx</hp:t>
            new_t = tm
            m = re.match(r"(<hp:t[^>]*>)(.*?)(</hp:t>)", tm, re.S)
            if m:
                open_tag, _, close_tag = m.group(1), m.group(2), m.group(3)
                # 새 텍스트로 교체 (xml:space 보존)
                new_t = f"{open_tag}{chunk.pop(0)}{close_tag}"
            new_r = new_r.replace(tm, new_t, 1)
        new_runs.append(new_r)

    # 남은 텍스트가 있으면 새 run을 추가 (A의 run template 복제)
    if idx < len(new_texts):
        # 가장 단순한 run 템플릿: A의 첫 run을 복제
        template_run = runs[0] if runs else "<hp:run><hp:t></hp:t></hp:run>"
        for remaining in new_texts[idx:]:
            new_runs_template = template_run
            new_r = re.sub(r"<hp:t\b.*?</hp:t>", f"<hp:t>{remaining}</hp:t>", new_runs_template, count=1, flags=re.S)
            new_runs.append(new_r)

    # 새 문단 조립
    p_tag = re.match(r"(<hp:p\b[^>]*>)(.*?)(</hp:p>)", p_xml, re.S)
    if not p_tag:
        return p_xml
    open_tag, inner, close_tag = p_tag.group(1), p_tag.group(2), p_tag.group(3)
    new_inner = "".join(new_runs)
    return f"{open_tag}{new_inner}{close_tag}"


def drop_linesegarray(text: str) -> str:
    """hp:linesegarray를 제거. 한글에서 재생성하게 둔다."""
    return re.sub(r"<hp:linesegarray\b.*?</hp:linesegarray>", "", text, flags=re.S)


# ------------------------------------------------------------------
# 본문 이식: B 섹션 텍스트를 A 스타일의 문단으로 재구성
# ------------------------------------------------------------------


def transplant_body(
    a_header_text: str,
    a_section_text: str,
    b_section_text: str,
    b_table_cells: List[List[str]],
) -> str:
    """A 섹션의 구조(표와 문단 배치)를 유지한 채, 텍스트만 B에서 가져온 값으로 교체.

    전략:
    - A 섹션의 문단을 순서대로 순회.
    - 각 문단의 hp:t 텍스트를 B의 같은 순번 문단 텍스트로 교체.
    - B가 더 짧으면 나머지 A 문단은 원문 유지(빈칸 등).
    - B에 표가 없고 A에 표가 있으면, 표의 셀 텍스트는 그대로 둠(현재 규칙상 B 표는 값 찾기용).
      추후 B 표를 A 표에 이식하는 단계는 별도.
    """
    # B의 문단 텍스트 리스트
    b_texts = section_text_only(b_section_text)

    a_root = ET.fromstring(a_section_text.decode("utf-8"))
    # 문단 리스트로 직렬화 재조립
    a_paras = re.findall(r"<hp:p\b.*?</hp:p>", a_section_text, re.S)
    new_paras: List[str] = []

    text_idx = 0
    # 표의 셀 텍스트를 별도로 반영할 수도 있으나, 이번 단계는 문단 텍스트 우선.
    for p_xml in a_paras:
        # 문단 텍스트 수집
        runs = re.findall(r"<hp:run\b.*?</hp:run>", p_xml, re.S)
        t_texts: List[str] = []
        for r in runs:
            for m in re.findall(r"<hp:t\b.*?</hp:t>", r, re.S):
                t_texts.append(re.sub(r"^<hp:t[^>]*>|</hp:t>$", "", m, flags=re.S))
        current_text = "".join(t_texts)

        # B의 텍스트로 교체할 문장인 경우: A의 문단에 텍스트가 있고, B의 텍스트가 있으면 교체
        if text_idx < len(b_texts):
            # A의 문단이 '빈' 문단이 아니면 교체 후보
            # 실제 이식 판단: A의 문단이 표 셀의 문단이 아니면 교체
            # 표 셀 문단인지 여부는 추후 정제. 현재는 모든 hp:p를 순서대로 B의 텍스트로 채우는 방식.
            # 단, 표 구조를 망가뜨리지 않기 위해 표 내부 문단은 제외해야 한다.
            # 여기서는 단순 버전: A의 문단 중 표 바깥 문단만 교체.
            # 표 내부 문단은 tp 태그 포함 여부로 판정 어려움 → 별도 표 처리에서 다룸.
            new_paras.append(replace_t_in_paragraph(p_xml, [b_texts[text_idx]]))
            text_idx += 1
            continue

        new_paras.append(p_xml)

    # 문단 사이 공백/페이지 구조 유지 위해 문단 사이에 개행 비슷한 건 없음 — 그대로 concat
    new_section_inner = "".join(new_paras)

    # 루트 재조립
    a_root_match = re.match(r"^(<hp:secPr\b.*?</hp:secPr>)", a_section_text, re.S)
    # section0.xml 구조는 보통 secPr로 시작 후 hp:p 연속
    # 루트는 hs:sectionInfo 등일 수 있음. 여기서는 본문만 교체.
    # 정규식으로 secPr + 본문 재구성
    secpr = re.search(r"<hp:secPr\b.*?</hp:secPr>", a_section_text, re.S)
    if secpr:
        # secPr를 앞으로
        new_section = secpr.group(0) + "\n" + new_section_inner
    else:
        new_section = new_section_inner

    new_section = drop_linesegarray(new_section)
    return new_section


def transplant_body_v4(
    a_section_text: str,
    b_section_text: str,
) -> str:
    """A의 표 구조·라벨·서명은 그대로 두고, 본문 텍스트만 B로 교체하거나 추가.

    규칙(실제 파일 기준):
    - A의 첫 표 앞 문단이 있으면 그 문단들에만 B 텍스트를 순서대로 채운다.
    - 표 뒤 문단(라벨·서명·안내문·표 셀)은 건드리지 않는다.
    - 표 앞 문단이 없으면(표 중심 양식), B 텍스트를 마지막 문단 뒤에 새 문단으로 추가한다.
    - 표 내부 문단(tc 안 p)은 건드리지 않는다.
    - B 텍스트가 남지 않으면 그대로 종료.
    """
    b_texts = section_text_only(b_section_text)
    if not b_texts:
        return a_section_text

    a_paras = re.findall(r"<hp:p\b.*?</hp:p>", a_section_text, re.S)
    tbl_match = re.search(r"<hp:tbl\b", a_section_text)
    tbl_start = tbl_match.start() if tbl_match else None

    # 각 문단의 오프셋과 표 앞/뒤 구분
    para_info = []
    search_start = 0
    for p in a_paras:
        off = a_section_text.find(p, search_start)
        search_start = off + len(p) if off >= 0 else search_start
        para_info.append((p, off))

    # 표 앞 문단 리스트
    pre_paras = [(p, off) for p, off in para_info if tbl_start is None or off < tbl_start]

    new_paras = list(a_paras)
    text_idx = 0

    # 표 앞 문단에 B 텍스트 채우기
    for i, (p_xml, off) in enumerate(pre_paras):
        # 표 내부 문단이면 스킵 (오프셋이 표 이전이어도 tc가 있으면 표 셀)
        if "<hp:tc" in p_xml:
            continue
        if text_idx < len(b_texts):
            new_paras[a_paras.index(p_xml)] = replace_t_in_paragraph(p_xml, [b_texts[text_idx]])
            text_idx += 1

    # 남은 B 텍스트가 있으면 마지막 문단 뒤에 추가
    remaining = b_texts[text_idx:]
    if remaining:
        new_paras.extend(_build_extra_paras(remaining, a_paras))

    new_inner = "".join(new_paras)
    secpr = re.search(r"<hp:secPr\b.*?</hp:secPr>", a_section_text, re.S)
    new_section = (secpr.group(0) + "\n" + new_inner) if secpr else new_inner
    new_section = drop_linesegarray(new_section)
    return new_section


def _build_extra_paras(
    texts: List[str],
    a_paras: List[str],
) -> List[str]:
    """B의 남은 텍스트를 새 문단들로 만들어 반환.

    A의 마지막 문단에서 run 템플릿을 복제해 사용한다.
    """
    if not a_paras:
        return []
    last = a_paras[-1]
    run_template = re.search(r"<hp:run\b.*?</hp:run>", last, re.S)
    run_tmpl = run_template.group(0) if run_template else "<hp:run><hp:t></hp:t></hp:run>"
    out = []
    for t in texts:
        new_run = re.sub(
            r"<hp:t\b.*?</hp:t>",
            f"<hp:t>{t}</hp:t>",
            run_tmpl,
            count=1,
            flags=re.S,
        )
        out.append(
            f'<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            f"{new_run}"
            f"</hp:p>"
        )
    return out


# ------------------------------------------------------------------
# 스타일 ID 재매핑 — B의 charPr/paraPr/style을 A의 것으로
# ------------------------------------------------------------------


def build_id_map_from_header(header_text: str) -> Dict[str, Dict[str, int]]:
    """A의 header에서 실제 charPr/paraPr/style/borderFill ID 목록을 뽑는다.

    반환: {"charPr": {old_id: new_id}, ...} 형태보다는,
    "사용 가능한 A의 ID 집합"을 뽑는다.
    """
    char_ids = [m.group(1) for m in re.finditer(r'<hh:charPr\b[^>]*id="([^"]+)"', header_text)]
    para_ids = [m.group(1) for m in re.finditer(r'<hh:paraPr\b[^>]*id="([^"]+)"', header_text)]
    style_ids = [m.group(1) for m in re.finditer(r'<hh:style\b[^>]*id="([^"]+)"', header_text)]
    border_ids = [m.group(1) for m in re.finditer(r'<hh:borderFill\b[^>]*id="([^"]+)"', header_text)]
    return {
        "charPr": set(char_ids),
        "paraPr": set(para_ids),
        "style": set(style_ids),
        "borderFill": set(border_ids),
    }


# ------------------------------------------------------------------
# ZIP 재조립 — mimetype STORED, 순서 보존
# ------------------------------------------------------------------


def write_hwpx_zip(
    out_path: Path,
    original_infos: list,
    modified: Dict[str, bytes],
    mimetype: bytes,
) -> None:
    """출력 HWPX를 쓴다. mimetype은 첫 엔트리, STORED.
    그 외 엔트리는 원본 ZipInfo의 compress_type·순서·날짜 등을 최대한 보존한다.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w") as zf:
        # mimetype 먼저, STORED
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
# 메인 이식 파이프라인
# ------------------------------------------------------------------


def run(
    a_path: Path,
    b_path: Path,
    out_path: Path,
    label: str = "",
) -> Dict:
    """A, B로 C를 만든다. 결과는 summary dict."""
    a_mimetype, a_entries, a_by_name = read_hwpx_zip(a_path)
    verify_mimetype(a_mimetype)

    a_header = a_by_name["Contents/header.xml"].decode("utf-8")
    a_section = a_by_name["Contents/section0.xml"].decode("utf-8")

    # B 읽기
    b_mimetype, b_entries, b_by_name = read_hwpx_zip(b_path)
    verify_mimetype(b_mimetype)
    b_header = b_by_name["Contents/header.xml"].decode("utf-8")
    b_section = b_by_name["Contents/section0.xml"].decode("utf-8")

    # 요약 통계
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

    # B 표 셀 텍스트 추출
    b_table_cells = section_table_cells(b_section)

    # 본문 이식: A 섹션의 표·서식 구조를 유지한 채, 본문 텍스트만 B로 교체
    new_section = transplant_body_v4(a_section, b_section)

    # header는 A를 그대로 사용
    new_header = a_header

    # 수정본 조립
    modified: Dict[str, bytes] = {
        "Contents/header.xml": new_header.encode("utf-8"),
        "Contents/section0.xml": new_section.encode("utf-8"),
    }

    # 다른 엔트리는 그대로
    for name, data in a_entries:
        if name not in modified and name != "mimetype":
            modified[name] = data

    # 원본 ZIP 정보(압축 방식/순서) 보존
    original_infos = read_zip_infos(a_path)

    # ZIP 작성
    write_hwpx_zip(out_path, original_infos, modified, a_mimetype)

    summary["out_path"] = str(out_path)
    summary["out_sha256"] = sha256_path(out_path)
    summary["out_size"] = out_path.stat().st_size
    summary["label"] = label
    return summary


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------


def main() -> None:
    if len(sys.argv) != 4:
        print(f"usage: {sys.argv[0]} A_style.hwpx B_content.hwpx out.hwpx", file=sys.stderr)
        sys.exit(2)

    a = Path(sys.argv[1])
    b = Path(sys.argv[2])
    out = Path(sys.argv[3])

    if not a.exists():
        print(f"ERR: A 없음: {a}", file=sys.stderr)
        sys.exit(2)
    if not b.exists():
        print(f"ERR: B 없음: {b}", file=sys.stderr)
        sys.exit(2)

    s = run(a, b, out)
    print("=== 이식 결과 ===")
    for k in [
        "a_sha256",
        "b_sha256",
        "out_path",
        "out_sha256",
        "out_size",
        "label",
        "a_charPr",
        "a_paraPr",
        "a_styles",
        "a_borderFill",
        "a_font_total",
        "b_section_paras",
        "b_section_tables",
    ]:
        print(f"{k}: {s.get(k)}")


if __name__ == "__main__":
    main()
