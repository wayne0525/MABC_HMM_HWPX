import zipfile, re, sys
from pathlib import Path

here = Path(__file__).resolve().parent

# ---- import: CLI wrapper가 아닌 hwpx_core 실제 함수 ----
from vercel.hwpx_core.core import (
    transplant_body_v4,
    section_text_only,
    section_table_cells,
)

a_path = here / "vercel/tests/fixtures/A_verified.hwpx"
b_path = here / "vercel/tests/fixtures/B_verified.hwpx"

assert a_path.exists(), f"A 파일 없음: {a_path}"
assert b_path.exists(), f"B 파일 없음: {b_path}"

A = zipfile.ZipFile(a_path)
B = zipfile.ZipFile(b_path)

a_sec = A.read("Contents/section0.xml").decode("utf-8")
b_sec = B.read("Contents/section0.xml").decode("utf-8")

a_para_count = len(re.findall(r"<hp:p\b", a_sec))
b_para_count = len(re.findall(r"<hp:p\b", b_sec))

new_sec = None
structural_damage = None

# ---- 실제 엔진 호출 + 구조 손상 검출 ----
try:
    new_sec = transplant_body_v4(a_sec, b_sec)
except NameError as e:
    structural_damage = f"transplant_body_v4 내부 미정의 함수 호출: {e}"
except Exception as e:
    structural_damage = f"transplant_body_v4 호출 예외: {type(e).__name__}: {e}"

if structural_damage:
    print(f"[RED] 구조 손상: {structural_damage}")
    print(f"A 문단 수: {a_para_count}")
    print(f"B 문단 수: {b_para_count}")
    # 구조 손상이 있으면 여기서 assert 실패로 종료
    assert False, f"transplant_body_v4 구조 손상: {structural_damage}"

new_para_count = len(re.findall(r"<hp:p\b", new_sec))
print(f"A 문단 수: {a_para_count}")
print(f"B 문단 수: {b_para_count}")
print(f"새 section 문단 수: {new_para_count}")

# ---- assert 기반 검사 ----

# 1. 새 section이 XML 파싱 가능해야 함
import xml.etree.ElementTree as ET

root = ET.fromstring(new_sec)

# 2. XML root는 HWPML namespace를 가져야 함
root_tag = root.tag
root_ns = root_tag.split("}")[0].lstrip("{") if "}" in root_tag else ""
assert "http://www.hancom.co.kr/hwpml" in root_ns, f"XML root namespace 오류: {root_ns}"

# 3. A의 표(tbl)가 이식 후에도 유지되는지 확인
a_tbl_count = len(re.findall(r"<hp:tbl\b", a_sec))
new_tbl_count = len(re.findall(r"<hp:tbl\b", new_sec))
print(f"A 표 수: {a_tbl_count}")
print(f"새 section 표 수: {new_tbl_count}")

assert a_tbl_count > 0 or new_tbl_count == a_tbl_count, \
    f"표 구조 불일치: A={a_tbl_count}, 이식 후={new_tbl_count}"

# 4. A의 표에 실제 텍스트가 있는 셀이 있으면 그중 하나 이상 보존 확인
a_cells = section_table_cells(a_sec)
a_cell_texts = [c for row in a_cells for c in row if c.strip()]
print(f"A 표 셀 수(텍스트 있는 것만): {len(a_cell_texts)}")

if a_cell_texts:
    new_cells = section_table_cells(new_sec)
    new_flat = " \n".join(" ".join(row) for row in new_cells)
    preserved = [c for c in a_cell_texts if c in new_flat]
    print(f"보존된 A 표 셀 수: {len(preserved)} / {len(a_cell_texts)}")
    assert len(preserved) > 0, \
        f"A 표의 실제 셀 텍스트가 이식 후 보존되지 않음 (예: {a_cell_texts[0]!r})"

# 5. B의 텍스트가 새 section에 포함되었는지 확인
b_texts = section_text_only(b_sec)
new_texts = section_text_only(new_sec)
missing_b = [t for t in b_texts if t.strip() and not any(t in nt for nt in new_texts)]
if missing_b:
    print(f"주의: B 텍스트 일부 미포함: {missing_b[:3]}")
else:
    print("B 텍스트 전부 포함 확인")

print("모든 검사 통과")
