# TEAM_CONTRACT.md — MABC_HMM_HWPX 팀 계약

현재 제품의 실제 상태와 팀이 합의한 최종 계약만 담는다. 빈 구현 stub은 적지 않는다.

## 1. 제품 현황(2026-09-14 기준)

- 이식(transplant) 모드만 구현됨: 파일 A의 서식 + 파일 B의 내용 → 새 HWPX C.
- 채우기(fill)/편집/제안/보고서 JSON 모드는 아직 없음.
- 코어는 단일 구현: `vercel/hwpx_core/core.py`.
- 서버 API는 multipart 전용: `vercel/api/handler.py`의 `handler(request)`가 `hwpx_core.run`을 호출해 HWPX 바이너리를 반환.
- 클라이언트 예제(`vercel/public/index.html`)는 `/api/transplant`로 POST하며 FormData 필드명을 `style`/`content`로 씀.
- 시험 코드(`test_size_limits.py`)는 `vercel.api.document.handle_request(req, body)`를 가정하나, 그런 모듈은 없음.

## 2. 코어 함수의 실제 import 경로·입력·반환값

### 2.1 A 분석 (서식 프로필 추출)

- 실제 import 경로: `hwpx_core.core`
- 관련 함수:
  - `read_hwpx_zip(path: Path) -> Tuple[bytes, List[Tuple[str, bytes]], Dict[str, bytes]]`
  - `parse_header(data: bytes) -> ET.Element`
  - `header_counts(root: ET.Element) -> Dict[str, int]`
  - `count_charPr(header_text: str) -> int`
  - `count_paraPr(header_text: str) -> int`
  - `count_styles_items(header_text: str) -> int`
  - `count_borderFill_items(header_text: str) -> int`
  - `count_fonts(header_text: str) -> Tuple[int, int]`
  - `build_id_map_from_header(header_text: str) -> Dict[str, Dict[str, int]]`
- 입력: 파일 A의 Path(또는 bytes). 출력은 사람이 읽는 서식 프로필이며, 스키마는 `schemas/style-profile.schema.json`.
- 반환값 성격: A는 **서식만** 추출하며 문장을 저장하지 않음. 값은 XML에서 읽었으면 `source: "xml"`, 못 읽었으면 `unknown` + 이유. 없는 값은 날조하지 않음.

### 2.2 B 추출 (내용 골격 추출)

- 실제 import 경로: `hwpx_core.core`
- 관련 함수:
  - `section_text_runs(section_text: str) -> List[Tuple[str, str, str, List[str]]]`
  - `section_text_only(section_text: str) -> List[str]`
  - `section_table_cells(section_text: str) -> List[List[str]]`
- 입력: 파일 B의 섹션 XML 텍스트.
- 출력: B의 문단/표 구조를 보존한 내용 골격. 스키마는 `schemas/content-skeleton.schema.json`.
- 반환값 성격: B의 서식(charPr/paraPr)은 모두 버림. 텍스트는 원문 그대로. 빈 셀은 빈 문자열.

### 2.3 규칙 연결 (역할 맵)

- 대상: B가 아니라, B의 각 블록을 A의 서식 슬롯에 연결하는 규칙.
- 근거 문서: `references/05-role-classification.md`, `references/06-mapping-and-id-remap.md`.
- 결과: `roleMap` 배열. 각 항목은 `fromB`(B 블록 유형/설명), `toASlot`(A 슬롯명), `fallback`(불리언), `note`(문자열).
- 스키마는 `schemas/transplant-report.schema.json`의 `roleMap`과 호환.

### 2.4 A 해시 확인과 선택 편집 생성

- A 해시: `hwpx_core.core.sha256_path(path: Path) -> str`.
- 편집 생성: 현재 이식 모드는 편집 객체 목록을 반환하지 않고, 본문 교체 후 HWPX를 직접 쓴다. 채우기/편집 모드가 생기면, 편집은 **서버가 원본 A와 B의 재검증 후** 생성하는 내부 객체로 시작한다.
- Solar는 XML을 생성하지 않음. 제안 보강은 서버가 규칙 처리 후 호출하며, Solar 출력은 편집 후보 텍스트/주석 수준이고, 최종 편집 적용은 서버가 A의 실제 ID/구조로 검증한 뒤에만 반영.

## 3. 필드/편집/보고서 계약의 필수 키·타입

### 3.1 필드 항목 (문서 내 편집 단위)

- `fieldId`: 문자열. 서버 내부에서 할당/관리. 클라이언트가 임의 ID를 강제 지정한다는 보장은 계약에 포함하지 않음.
- `label`: 문자열. 사람이 보는 필드명.
- `context`: 문자열. 주변 문단/표 셀 등 위치 설명.
- `unit`: 문자열 또는 null. 예: `pt`, `mm`, `%`, `#RRGGBB`, `boolean`.
- `source`: 문자열. 원문 근거. 예: `"A header.xml"`, `"B section0.xml"`, `"frequency"`, `"visual-estimate"`.
- `warning`: 문자열 또는 null. 충돌·미선택·위험 표시.
- `editable`: 불리언. 클라이언트가 수정 제안 가능한지의 **서버 판단**. 실제 적용 권한은 서버가 가짐.
- 값 관련: `valueRaw`(서버 저장값), `valueDisplay`(사람 단위 표시), 둘 다 서버에서 제공.

### 3.2 sourceBlock

- B가 출처인 블록 참조. 예: 문단 인덱스/표 좌표/셀 좌표.
- 필수 키: 최소한 블록 유형과 위치 식별자. 타입은 서버 내부 표현에 따르되, 클라이언트가 임의의 바이트 오프셋을 지정해 편집을 강제하는 계약은 아님.

### 3.3 edit

- 서버가 생성/승인하는 편집 단위.
- 필수 키 후보: `fieldId`, `kind`(예: `replaceText`, `setStyleRef`, `replaceValue`), `oldValue`, `newValue`, `source`(근거), `editable`, `status`(예: `proposed`, `applied`, `rejected`), `note`.
- 실제 키는 채우기 모드 구현 시 확정. 지금은 "서버가 원본 A와 편집을 재검증한 뒤에만 적용"된다는 원칙만 계약에 둔다.

### 3.4 report

- 현재 이식 모드의 보고서는 HWPX 파일 하나와 내부 요약 dict 수준.
- 채우기/편집 모드의 보고서는 `schemas/transplant-report.schema.json` 계열의 `roleMap`, `applied`, `gaps`, `output`를 포함.
- 보고서 크기는 전송 예산에 포함.

## 4. 빈 값·미선택·충돌·수동 편집·부분 실패 처리 규칙

- 빈 값: B는 빈 셀을 빈 문자열로 유지. 서버가 임의로 "해당없음"을 채우지 않음.
- 미선택: A가 특정 슬롯을 갖지 않으면 `present: false` + `unknownReason`. 없는 서식을 창작하지 않음.
- 충돌: A와 B의 서식/값이 상충하면 A가 우선. 예: A의 표 선과 B의 표 선이 다르면 A 선 사용. B가 아니라 A.
- 수동 편집: 클라이언트가 수정 후보를 제시해도, 서버가 원본 A와 B의 정합성 검증 후 적용 여부를 결정. 클라이언트 지정 바이트 위치로 직접 편집을 강제하지 않음.
- 부분 실패: 일부는 이식/편집되고 일부는 실패하면, 성공분과 실패 사유를 함께 보고. 전체를 중단할지 부분 반환할지는 서버가 판단하며, 실패 시 오류 code/message/details를 함께 제공.

## 5. API 단일 경로 계약

### 5.1 최종 이름과 불일치 해소

- 외부 엔드포인트는 하나로 통일: **`/api/fill`**.
- reason: 현재 `/api/transplant`(클라이언트 예제)와 `api/index.py`(Vercel 설정) 및 `handle_request`(시험 코드 가정)가 서로 다르다. 앞으로는 단일 경로 `/api/fill`로 통합.
- 요청 필드명도 통일: **`a`(서식 원본)와 `b`(내용 원본)**.
- reason: 현재 클라이언트 예제는 `style`/`content`를 쓰고, 코어 내부는 `a_path`/`b_path`다. 외부 계약 필드명은 `a`/`b`로 고정하고, 내부 변수명과 무관하게 계약한다.

### 5.2 요청

- 메서드: `POST`
- 경로: `/api/fill`
- 전송 방식: multipart/form-data 또는 JSON+base64 중 서버가 지원하는 한 가지 방식으로 통일. 계약은 둘 중 **서버가 실제 선택한 한 방식**만 문서에 남긴다(현재 구현에서는 multipart가 실제 사용되고 있음).
- multipart인 경우:
  - 필드 `a`: 파일 A(bytes)
  - 필드 `b`: 파일 B(bytes)
  - 추가 필드는 연산 유형에 따라 확장
- JSON인 경우:
  - body에 base64 인코딩된 `a`, `b`와 연산 정보를 포함
- 연산 유형: `status`, `analyze`, `suggest`, `generate` 중 하나. 단일 경로에서 연산 타입 필드로 구분.

### 5.3 응답

- 성공 시:
  - `generate` 계열은 결과 HWPX를 반환(바이너리 또는 base64).
  - `analyze`/`suggest`/`status`는 JSON 응답.
- 응답 JSON 공통 요소:
  - `status`: 요청 처리 상태
  - `analyze`: A/B 분석 결과(서식 프로필/내용 골격 요약)
  - `suggest`: 제안 편집/보정 후보
  - `generate`: 생성 결과(파일 또는 보고서)
- base64 파일: JSON 응답에서 파일을 포함할 때는 base64로 전달. 단, 실제 구현이 바이너리 응답이면 그 방식을 우선.
- 오류 응답:
  - `code`: 기계 판독 가능한 오류 코드
  - `message`: 사람이 읽는 설명
  - `details`: 선택적 세부 정보(배열 또는 객체)

### 5.4 연산별 요약

- `status`: 입력 유효성, 크기, 기본 상태 반환.
- `analyze`: 규칙 기반 A/B 분석. 이후 서버가 Solar 호출로 제안 보강 가능.
- `suggest`: 분석 + Solar 보강 기반 편집 후보 반환. Solar는 XML을 생성하지 않으며, 제안은 서버가 검증 가능한 형태로만 받음.
- `generate`: 서버에서 원본 A와 편집을 재검증한 뒤 최종 결과 생성. 결과는 HWPX 또는 보고서 JSON.

### 5.5 요청/응답 JSON 예(작은 예)

#### status 성공
```json
{
  "status": "ok",
  "analyze": {
    "a": { "valid": true, "mimetype": "application/hwp+zip", "sizeBytes": 12345 },
    "b": { "valid": true, "mimetype": "application/hwp+zip", "sizeBytes": 6789 }
  }
}
```

#### suggest 빈 제안
```json
{
  "status": "ok",
  "suggest": {
    "edits": [],
    "note": "규칙상 적용 가능한 편집 후보 없음"
  }
}
```

#### generate 부분 실패
```json
{
  "status": "partial",
  "generate": {
    "outputFormat": "hwpx",
    "output": "<base64 또는 바이너리 응답으로 대체>",
    "report": {
      "roleMap": [],
      "applied": [],
      "gaps": ["B의 표 2 병합 셀은 재구성하지 않음"]
    }
  },
  "errors": [
    {
      "code": "PARTIAL_FAILURE",
      "message": "일부 블록은 이식하지 못함",
      "details": { "failedBlocks": ["table:2"] }
    }
  ]
}
```

#### overflow 경고
```json
{
  "status": "warning",
  "errors": [
    {
      "code": "SIZE_LIMIT_EXCEEDED",
      "message": "입력 합계가 제한을 초과함",
      "details": { "totalBytes": 6700000, "limitBytes": 6291456 }
    }
  ]
}
```

#### 구조 실패
```json
{
  "status": "error",
  "errors": [
    {
      "code": "INVALID_HWPX_STRUCTURE",
      "message": "A 섹션 XML이 예상한 구조를 벗어나 이식 불가",
      "details": { "reason": "section0.xml에 hp:secPr 없음" }
    }
  ]
}
```

## 6. 필드 위치/미리보기 데이터와 편집 바이트 위치

- 필드 위치/표·문단 구조 미리보기용 데이터는 서버가 제공. 예: 블록 유형, 문단 인덱스, 표 행·열 좌표, 셀 텍스트 요약.
- 서버 내부의 실제 편집 바이트 위치는 클라이언트가 임의 지정하지 못함. 편집은 필드/블록 단위로 요청하고, 서버가 내부 위치로 변환해 적용.

## 7. 전송 예산(실제 제한)

현재 handler에 구현된 제한:
- A 최대 5MB
- B 최대 1MB
- 합계 최대 6MB
- 출력 최대 5MB

보고서/응답 JSON 크기는 별도 상수로 확정하지 않았고, 현재는 바이너리 반환이 기본. 추후 JSON 보고서가 생기면 출력 예산 안에서 관리.

## 8. 현재 RED 상태(엔진 완료로 표시하지 않음)

의도된 RED:
- `test_multipart_crlf_preserved` — 핸들러 구현 후 작성(05 이슈).

그 외 5건은 현재 ok.

## 9. 미정 항목(아직 채우지 않는 것)

- `/api/fill`의 정확한 multipart vs JSON/base64 방식 확정(서버 구현 선택 후 확정).
- edit/report의 최종 키 목록은 채우기 모드 구현 시점에 확정.
- `fieldId` 생성 규칙과 클라이언트 지정 가능 범위는 서버 내부 설계 후 확정.
- 전송 예산의 JSON 보고서 크기 상수는 추후 추가.
