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
  B 표에 있던 셀 텍스트만 가져와서 A 표에 넣는 방식은 'B 표 값을 A 표에 이식'으로 별도 단계로 둔다.
- 이 스크립트는 'B가 A 헤더를 공유하는 단순 본문 이식'을 먼저 완성한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---- 명시적 패키지 경로: vercel/hwpx_core ----
sys.path.insert(0, str(Path(__file__).parent / "vercel"))
import hwpx_core

run = hwpx_core.run
sha256_path = hwpx_core.sha256_path


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