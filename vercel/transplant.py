#!/usr/bin/env python3
"""
HWPX 서식 이식(transplant) CLI.

core 로직은 vercel/hwpx_core/core.py에 있고,
이 파일은 CLI 인터페이스만 제공한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "vercel"))
from hwpx_core.core import run, sha256_path  # noqa: E402

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
        "a_sha256", "b_sha256", "out_path", "out_sha256", "out_size", "label",
        "a_charPr", "a_paraPr", "a_styles", "a_borderFill", "a_font_total",
        "b_section_paras", "b_section_tables",
    ]:
        print(f"{k}: {s.get(k)}")

if __name__ == "__main__":
    main()
