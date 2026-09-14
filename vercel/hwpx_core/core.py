# -*- coding: utf-8 -*-
"""
HWPX core — 이식/채우기 파이프라인을 위한 단일 구현.

root transplant.py와 vercel/api/handler.py가 같은 패키지를 import 한다.
ZIP 입출력, XML 파싱/정규식 편집, 이식 본문 조립을 담당한다.
CLI와 Vercel handler는 이 패키지 바깥에서 오케스트레이션만 수행한다.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Tuple, Dict, List

# ------------------------------------------------------------------
# ZIP 읽기/쓰기 (ZIP 매직 기반 mimetype 검증 포함)
# ------------------------------------------------------------------


def sha256_path(path: Path) -> str:
    import hashlib
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
    """mimetype 파일 내용이 application/hwp+zip 인지 확인한다."""
    text = data.decode("ascii", "replace").strip()
    if text != "application/hwp+zip":
        raise ValueError(f"mimetype 내용이 다름: {text!r}")


def _mimetype_is_hwpx(path: Path) -> bool:
    """ZIP 매직 바이트(PK\\x03\\x04)로 HWPX 여부를 빠르게 판별한다."""
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
        return magic == b"PK\x03\x04"
    except Exception:
        return False


# ------------------------------------------------------------------
# header.xml 파싱 — 서식 프로필 추출 (사람 단위 + raw)
# ------------------------------------------------------------------


def parse_header(data: bytes) -> "ET.Element":
    """header.xml 바이트를 파싱해 ElementTree 루트를 반환."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(data.decode("utf-8"))
    return root


def header_counts(root: "ET.Element") -> Dict[str, int]:
    """header.xml의 직계 자식 element 태그별 개수를 센다."""
    counts: Dict[str, int] = {}
    for child in root:
        local = child.tag.split("}")[-1]
        counts[local] = counts.get(local, 0) + 1
    return counts


def count_charPr(header_text: str) -> int:
    """header.xml 텍스트에서 <hh:charPr ...> 개수를 센다."""
    return len(_re.findall(r"<hh:charPr\b", header_text))


def count_paraPr(header_text: str) -> int:
    """header.xml 텍스트에서 <hh:paraPr ...> 개수를 센다."""
    return len(_re.findall(r"<hh:paraPr\b", header_text))


def count_charPr_items(header_text: str) -> int:
    """charProperties itemCnt 속성 값을 반환. 없으면 0."""
    m = _re.search(r'<hh:charProperties[^>]*itemCnt="(\d+)"', header_text)
    return int(m.group(1)) if m else 0


def count_paraPr_items(header_text: str) -> int:
    """paraProperties / paraPrList itemCnt 속성 값을 반환. 없으면 0."""
    m = (
        _re.search(r'<hh:paraProperties[^>]*itemCnt="(\d+)"', header_text)
        or _re.search(r'<hh:paraPrList[^>]*itemCnt="(\d+)"', header_text)
    )
    return int(m.group(1)) if m else 0


def count_styles_items(header_text: str) -> int:
    """styles itemCnt 속성 값을 반환. 없으면 0."""
    m = _re.search(r'<hh:styles[^>]*itemCnt="(\d+)"', header_text)
    return int(m.group(1)) if m else 0


def count_borderFill_items(header_text: str) -> int:
    """borderFills itemCnt 속성 값을 반환. 없으면 0."""
    m = _re.search(r'<hh:borderFills[^>]*itemCnt="(\d+)"', header_text)
    return int(m.group(1)) if m else 0


def count_fonts(header_text: str) -> Tuple[int, int]:
    """
    fontfaces itemCnt와 font 요소 개수를 반환.

    Returns:
        (itemCnt, font_element_count)
    """
    m = _re.search(r'<hh:fontfaces[^>]*itemCnt="(\d+)"', header_text)
    total = int(m.group(1)) if m else 0
    fonts = len(_re.findall(r"<hh:font\b", header_text))
    return total, fonts


# ------------------------------------------------------------------
# 섹션 본문 파싱 — B의 텍스트/구조 추출
# ------------------------------------------------------------------


def section_text_runs(
    section_text: str,
) -> List[Tuple[str, str, str, List[str]]]:
    """
    섹션 본문에서 문단 순서대로 (id, paraPrIDRef, styleIDRef, 텍스트를 담은
    hp:t 리스트)를 반환한다.

    Returns:
        [(id, paraPrIDRef, styleIDRef, [text, ...]), ...]
    """
    out: List[Tuple[str, str, str, List[str]]] = []
    for m in _re.finditer(r"<hp:p\b([^>]*)>", section_text):
        attrs = m.group(1)
        pid = attr_value(attrs, "id")
        para = attr_value(attrs, "paraPrIDRef")
        style = attr_value(attrs, "styleIDRef")
        start = m.end()
        end = find_closing_tag(section_text, start, "hp:p")
        block = section_text[start:end] if end > start else ""
        runs_texts: List[str] = []
        for rm in _re.finditer(r"<hp:run\b[^>]*>(.*?)</hp:run>", block, _re.S):
            run_block = rm.group(1)
            for tm in _re.finditer(r"<hp:t\b[^>]*>(.*?)</hp:t>", run_block, _re.S):
                runs_texts.append(tm.group(1))
        out.append((pid, para, style, runs_texts))
    return out


def attr_value(attrs: str, name: str) -> str:
    """공백 구분 속성 문자열에서 name="value"를 뽑아 반환."""
    m = _re.search(rf'{name}="([^"]*)"', attrs)
    return m.group(1) if m else ""


def find_closing_tag(text: str, start: int, tag: str) -> int:
    """
    text[start:]에서 <tag>...</tag>의 닫는 태그 끝을 찾는다.
    중첩을 고려해 깊이를 세며, 없으면 -1을 반환.

    tag 인자는 "hp:p"처럼 접두사 포함이거나 "p"처럼 로컬 이름만 받을 수 있다.
    로컬 이름만 받으면 [a-z]+:{tag} 형태의 모든 접두사를 찾는다.
    """
    import re as _re
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


def section_text_only(section_text: str) -> List[str]:
    """각 문단의 hp:t 텍스트를 합쳐서 문단별 텍스트 리스트로 반환."""
    out: List[str] = []
    for pid, para, style, runs in section_text_runs(section_text):
        joined = "".join(runs).strip()
        out.append(joined)
    return out


def section_table_cells(section_text: str) -> List[List[str]]:
    """
    섹션에서 첫 번째 표의 셀 텍스트를 행×열 리스트로 추출.

    표가 없으면 빈 리스트를 반환.
    """
    tbl_match = _re.search(r"<hp:tbl\b", section_text)
    if not tbl_match:
        return []
    tbl_start = tbl_match.start()
    tbl_end = find_closing_tag(section_text, tbl_start, "hp:tbl")
    if tbl_end < 0:
        return []
    tbl_block = section_text[tbl_start:tbl_end]
    rows: List[List[str]] = []
    for tr_match in _re.finditer(r"<hp:tr\b[^>]*>", tbl_block):
        tr_start = tr_match.end()
        tr_end = find_closing_tag(tbl_block, tr_start, "hp:tr")
        if tr_end < 0:
            continue
        tr_block = tbl_block[tr_start:tr_end]
        cells: List[str] = []
        for tc_match in _re.finditer(r"<hp:tc\b[^>]*>", tr_block):
            tc_start = tc_match.end()
            tc_end = find_closing_tag(tr_block, tc_start, "hp:tc")
            if tc_end < 0:
                continue
            tc_block = tr_block[tc_start:tc_end]
            cell_text_parts: List[str] = []
            for p_match in _re.finditer(r"<hp:p\b[^>]*>", tc_block):
                p_start = p_match.end()
                p_end = find_closing_tag(tc_block, p_start, "hp:p")
                if p_end < 0:
                    continue
                p_block = tc_block[p_start:p_end]
                for t_match in _re.finditer(r"<hp:t\b[^>]*>(.*?)</hp:t>", p_block, _re.S):
                    cell_text_parts.append(t_match.group(1))
            cells.append("".join(cell_text_parts).strip())
        rows.append(cells)
    return rows


# ------------------------------------------------------------------
# 텍스트 교체 — hp:t 내용만 교체, 구조 보존
# ------------------------------------------------------------------


def replace_t_in_paragraph(p_xml: str, new_texts: List[str]) -> str:
    """
    한 hp:p 안에서 hp:run > hp:t 텍스트를 new_texts로 교체.

    run의 개수/순서, 다른 속성은 그대로 보존한다.
    """
    runs = _re.findall(r"<hp:run\b.*?</hp:run>", p_xml, _re.S)
    if not runs:
        return p_xml
    new_runs: List[str] = []
    t_in_runs = [_re.findall(r"<hp:t\b.*?</hp:t>", r, _re.S) for r in runs]
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
        t_matches = _re.findall(r"<hp:t\b.*?</hp:t>", r, _re.S)
        for tm in t_matches:
            new_t = tm
            m = _re.match(r"(<hp:t[^>]*>)(.*?)(</hp:t>)", tm, _re.S)
            if m:
                open_tag, _, close_tag = m.group(1), m.group(2), m.group(3)
                new_t = f"{open_tag}{chunk.pop(0)}{close_tag}"
            new_r = new_r.replace(tm, new_t, 1)
        new_runs.append(new_r)
    if idx < len(new_texts):
        template_run = runs[0] if runs else "<hp:run><hp:t></hp:t></hp:run>"
        for remaining in new_texts[idx:]:
            new_runs_template = template_run
            new_r = _re.sub(
                r"<hp:t\b.*?</hp:t>",
                f"<hp:t>{remaining}</hp:t>",
                new_runs_template,
                count=1,
                flags=_re.S,
            )
            new_runs.append(new_r)
    p_tag = _re.match(r"(<hp:p\b[^>]*>)(.*?)(</hp:p>)", p_xml, _re.S)
    if not p_tag:
        return p_xml
    open_tag, inner, close_tag = p_tag.group(1), p_tag.group(2), p_tag.group(3)
    new_inner = "".join(new_runs)
    return f"{open_tag}{new_inner}{close_tag}"


def drop_linesegarray(text: str) -> str:
    """
    hp:linesegarray 요소를 제거.

    한글에서 다시 계산하게 두기 위한 조치.
    """
    return _re.sub(
        r"<hp:linesegarray\b.*?</hp:linesegarray>", "", text, flags=_re.S
    )


# ------------------------------------------------------------------
# 본문 이식: B 섹션 텍스트를 A 스타일의 문단으로 재구성 (v4)
# ------------------------------------------------------------------


def transplant_body_v4(
    a_section_text: str,
    b_section_text: str,
) -> str:
    """
    A 문서의 표 구조·라벨·서명은 그대로 두고, 본문 텍스트만 B로 교체하거나
    추가한다.

    B의 첫 문단들을 A 본문의 앞 문단(paraPrIDRef/name 미지정)에 우선 교체하고,
    남은 B는 A 본문 마지막 뒤에 새 문단으로 추가한다.
    """
    b_texts = section_text_only(b_section_text)
    if not b_texts:
        return a_section_text

    a_paras = _re.findall(r"<hp:p\b.*?</hp:p>", a_section_text, _re.S)
    tbl_match = _re.search(r"<hp:tbl\b", a_section_text)
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
        if "<hp:tc" in p_xml:
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
    secpr = _re.search(r"<hp:secPr\b.*?</hp:secPr>", a_section_text, _re.S)
    if secpr:
        new_section = secpr.group(0) + "\n" + new_inner
    else:
        new_section = new_inner
    new_section = drop_linesegarray(new_section)

    # root <hp:hp> wrapper + namespace declaration
    ns_m = _re.search(r'xmlns:hp="([^"]+)"', a_section_text)
    ns_uri = ns_m.group(1) if ns_m else "http://www.hancom.co.kr/hwpml/2011/oxml"
    root_open = f'<hp:hp xmlns:hp="{ns_uri}">'
    root_close = "</hp:hp>"
    wrapped = root_open + "\n" + new_section + "\n" + root_close
    return wrapped



    """
    B에서 교체하고 남은 텍스트를 새 문단 요소로 만들어 반환.

    A의 마지막 문단 템플릿을 참고해 run/t 구조를 만든다.
    """
    if not a_paras:
        return []
    last = a_paras[-1]
    run_template = _re.search(r"<hp:run\b.*?</hp:run>", last, _re.S)
    if run_template:
        run_tmpl = run_template.group(0)
    else:
        run_tmpl = "<hp:run><hp:t></hp:t></hp:run>"
    # A에서 최대 id 찾아 +1부터 순차 부여 (중복 방지)
    max_id = 0
    for p_xml in a_paras:
        m = _re.search(r'<hp:p[^>]*id="(\d+)"', p_xml)
        if m:
            max_id = max(max_id, int(m.group(1)))
    next_id = max_id + 1

    out = []
    for t in texts:
        new_run = _re.sub(
            r"<hp:t.*?</hp:t>",
            f"<hp:t>{t}</hp:t>",
            run_tmpl,
            count=1,
            flags=_re.S,
        )
        out.append(
            f'<hp:p id="{next_id}" paraPrIDRef="0" styleIDRef="0" '
            f"pageBreak=\"0\" columnBreak=\"0\" merged=\"0\">"
            f"{new_run}"
            f"</hp:p>"
        )
        next_id += 1
    return out


# ------------------------------------------------------------------
# 스타일 ID 재매핑 — B의 charPr/paraPr/style을 A의 것으로
# ------------------------------------------------------------------


def build_id_map_from_header(header_text: str) -> Dict[str, Dict[str, int]]:
    """
    A의 header에서 실제 charPr/paraPr/style/borderFill ID 목록을 뽑는다.

    Returns:
        {"charPr": {id: idx, ...}, "paraPr": {...}, "style": {...},
         "borderFill": {...}}
    """
    char_ids = [
        m.group(1)
        for m in _re.finditer(r'<hh:charPr\b[^>]*id="([^"]+)"', header_text)
    ]
    para_ids = [
        m.group(1)
        for m in _re.finditer(r'<hh:paraPr\b[^>]*id="([^"]+)"', header_text)
    ]
    style_ids = [
        m.group(1)
        for m in _re.finditer(r'<hh:style\b[^>]*id="([^"]+)"', header_text)
    ]
    border_ids = [
        m.group(1)
        for m in _re.finditer(r'<hh:borderFill\b[^>]*id="([^"]+)"', header_text)
    ]
    return {
        "charPr": {cid: i for i, cid in enumerate(char_ids)},
        "paraPr": {pid: i for i, pid in enumerate(para_ids)},
        "style": {sid: i for i, sid in enumerate(style_ids)},
        "borderFill": {bid: i for i, bid in enumerate(border_ids)},
    }


from re import compile as _re_compile

# 모듈 레벨 re alias (위에서 _re로 쓴 것들의 실제 정의)
import re as _re
# ------------------------------------------------------------------
# ZIP 재조립 — mimetype STORED, 순서 보존
# ------------------------------------------------------------------


def write_hwpx_zip(
    out_path: Path,
    original_infos: list,
    modified: Dict[str, bytes],
    mimetype: bytes,
) -> None:
    """
    출력 HWPX를 쓴다.

    mimetype은 첫 엔트리, STORED 압축. 나머지 엔트리는 원본 ZIP의
    ZipInfo 순서·압축 타입을 최대한 보존한다.
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
# 메인 이식 파이프라인
# ------------------------------------------------------------------


def run(
    a_path: Path,
    b_path: Path,
    out_path: Path,
    label: str = "",
) -> Dict:
    """
    A(서식)와 B(내용) HWPX로 새로운 HWPX C를 만들어 out_path에 쓴다.

    Returns:
        요약 dict (sha256, 크기, 카운터 등).
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
        "b_section_paras": len(_re.findall(r"<hp:p\b", b_section)),
        "b_section_tables": len(_re.findall(r"<hp:tbl\b", b_section)),
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
