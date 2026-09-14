# MABC_HMM_HWPX

HWPX 공문서 서식 이식/양식 채우기 서비스.

## 구성

```
.
├── transplant.py          # root CLI — vercel/hwpx_core를 명시적 경로로 import
├── vercel/
│   ├── hwpx_core/         # 단일 실행 코어 (이식/채우기 파이프라인)
│   │   ├── __init__.py
│   │   └── core.py
│   ├── api/
│   │   ├── index.py       # Vercel 함수 entrypoint (handler export)
│   │   └── handler.py     # multipart 파싱 + hwpx_core.run 호출
│   ├── tests/
│   │   ├── fixtures/      # 합성 HWPX fixture (A_template, B_content, B_alt_ns)
│   │   └── test_red_state.py
│   ├── vercel.json
│   └── requirements.txt
├── bench_measure.py
├── bench_out/
├── docs/
│   └── BUILD_STATE.md
└── ...
```

## 실행

### root CLI

```bash
python3 transplant.py A_style.hwpx B_content.hwpx out.hwpx
```

`transplant.py`는 `sys.path.insert(0, str(Path(__file__).parent / "vercel"))`로
`vercel/hwpx_core`를 명시적 경로로 import 한다. 임의 cwd에 의존하지 않는다.

### Vercel 함수

`vercel/api/index.py`가 `handler`를 export 한다.
`vercel/api/handler.py`가 multipart/form-data를 받아 `hwpx_core.run`을 호출한다.

## 코어

`vercel/hwpx_core/core.py`가 단일 출처다.

- `run(a_path, b_path, out_path, label="")` — 이식 파이프라인 (A 서식 유지 + B 텍스트)
- `read_hwpx_zip`, `verify_mimetype`, `read_zip_infos`, `write_hwpx_zip` — ZIP 입출력
- `section_text_runs`, `section_text_only`, `section_table_cells` — 본문 파싱
- `transplant_body_v4`, `replace_t_in_paragraph`, `_build_extra_paras` — 본문 이식
- `count_charPr`, `count_paraPr`, `count_styles_items` 등 — header 통계

정규식 기반으로 동작하며 lxml 등 외부 의존성이 없다(stdlib only).

## 제약 (Vercel)

- A ≤ 5MB, B ≤ 1MB, 합계 ≤ 6MB, 출력 ≤ 5MB
- 결과는 HWPX 파일 하나(application/hwp+zip)만 응답. JSON 보고서 아님.

## 테스트

```bash
cd vercel
python3 -m unittest tests.test_red_state -v
```

합성 fixture 3개로 RED-state 테스트 6건 실행. 5 ok, 1 의도된 RED(multipart CRLF,
05 이슈로 이관).

## 빌드 상태

자세한 진행 상황은 `docs/BUILD_STATE.md` 참고.

## 라이선스

LICENSE 파일 참고.
