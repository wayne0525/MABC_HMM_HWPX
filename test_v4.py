import zipfile, re, sys, os

here = os.path.dirname(os.path.abspath(__file__))
a_path = os.path.join(here, "..", "..", "Downloads", "hwpx-train-pairs", "01_culture_cctv", "A_style.hwpx")
b_path = os.path.join(here, "..", "..", "Downloads", "hwpx-train-pairs", "01_culture_cctv", "B_content.hwpx")

import transplant as T

A = zipfile.ZipFile(a_path)
B = zipfile.ZipFile(b_path)

a_sec = A.read("Contents/section0.xml").decode("utf-8")
b_sec = B.read("Contents/section0.xml").decode("utf-8")

print("A 문단 수:", len(re.findall(r"<hp:p\b", a_sec)))
print("B 문단 수:", len(re.findall(r"<hp:p\b", b_sec)))

new_sec = T.transplant_body_v4(a_sec, b_sec)
print("새 section 문단 수:", len(re.findall(r"<hp:p\b", new_sec)))

a_paras = re.findall(r"<hp:p\b[^>]*>.*?</hp:p>", a_sec, re.S)
new_paras = re.findall(r"<hp:p\b[^>]*>.*?</hp:p>", new_sec, re.S)

print("\n원본 A 마지막 6개 문단:")
for i in range(max(0, len(a_paras) - 6), len(a_paras)):
    t = "".join(re.findall(r"<hp:t[^>]*>(.*?)</hp:t>", a_paras[i], re.S)).strip()
    print(f"  [{i}] {t[:80]!r}")

print("\n새 section 마지막 8개 문단:")
for i in range(max(0, len(new_paras) - 8), len(new_paras)):
    t = "".join(re.findall(r"<hp:t[^>]*>(.*?)</hp:t>", new_paras[i], re.S)).strip()
    print(f"  [{i}] {t[:80]!r}")

print("\n새 section에서 B의 텍스트가 붙은 문단들:")
for i, p in enumerate(new_paras):
    t = "".join(re.findall(r"<hp:t[^>]*>(.*?)</hp:t>", p, re.S)).strip()
    if i >= len(a_paras) or t not in ["".join(re.findall(r"<hp:t[^>]*>(.*?)</hp:t>", a_paras[i], re.S)).strip() for j in [i]][:1]:
        # A의 같은 위치 텍스트와 다른 경우
        a_t = "".join(re.findall(r"<hp:t[^>]*>(.*?)</hp:t>", a_paras[i], re.S)).strip() if i < len(a_paras) else "<추가됨>"
        if a_t != t:
            print(f"  [{i}] NEW: {t[:80]!r}")
