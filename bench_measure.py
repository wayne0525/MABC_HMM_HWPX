# -*- coding: utf-8 -*-
"""이식 핸들러 성능/크기 측정.

Vercel 서버리스 함수에서 쓸 제한(MAX_A_BYTES 등)을 정하기 위한 근거 측정.
"""
from __future__ import annotations

import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import transplant


def measure(pair_dir: Path, out_dir: Path) -> dict:
    a = pair_dir / "A_style.hwpx"
    b = pair_dir / "B_content.hwpx"
    out = out_dir / f"{pair_dir.name}_C.hwpx"

    t0 = time.perf_counter()
    result = transplant.run(a, b, out)
    dt = time.perf_counter() - t0

    out_size = out.stat().st_size
    a_size = a.stat().st_size
    b_size = b.stat().st_size

    # ZIP 구성 확인
    z = zipfile.ZipFile(out)
    infos = {i.filename: i.compress_type for i in z.infolist()}
    mimetype_ok = z.read("mimetype") == b"application/hwp+zip"

    return {
        "pair": pair_dir.name,
        "a_bytes": a_size,
        "b_bytes": b_size,
        "total_input_bytes": a_size + b_size,
        "out_bytes": out_size,
        "elapsed_s": round(dt, 3),
        "mimetype_ok": mimetype_ok,
        "out_entries": len(z.namelist()),
        "out_compress_types": infos,
        "out_sha256_head": transplant.sha256_path(out)[:16],
    }


def main():
    pairs_root = Path(r"C:\Users\halle\Downloads\hwpx-train-pairs")
    out_dir = Path(r"C:\Users\halle\Downloads\hwpx-style-transplant\bench_out")
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for d in sorted(pairs_root.iterdir()):
        if not d.is_dir():
            continue
        a = d / "A_style.hwpx"
        b = d / "B_content.hwpx"
        if not a.exists() or not b.exists():
            print(f"건너뜀({d.name}): A/B 없음")
            continue
        r = measure(d, out_dir)
        results.append(r)

    # 표로 출력
    print(f"{'pair':22s} {'A bytes':>8s} {'B bytes':>8s} {'total':>8s} {'out bytes':>9s} {'s':>6s} {'mime':>5s}")
    for r in results:
        print(
            f"{r['pair']:22s} "
            f"{r['a_bytes']:8d} "
            f"{r['b_bytes']:8d} "
            f"{r['total_input_bytes']:8d} "
            f"{r['out_bytes']:9d} "
            f"{r['elapsed_s']:6.3f} "
            f"{'OK' if r['mimetype_ok'] else 'BAD':>5s}"
        )

    # 요약
    max_input = max(r["total_input_bytes"] for r in results)
    max_out = max(r["out_bytes"] for r in results)
    max_time = max(r["elapsed_s"] for r in results)
    print()
    print("요약:")
    print(f"  최대 입력 합계: {max_input} bytes ({max_input/1024:.1f} KB)")
    print(f"  최대 출력 크기: {max_out} bytes ({max_out/1024:.1f} KB)")
    print(f"  최대 처리 시간: {max_time} s")
    print(f"  측정 쌍 수: {len(results)}")


if __name__ == "__main__":
    main()
