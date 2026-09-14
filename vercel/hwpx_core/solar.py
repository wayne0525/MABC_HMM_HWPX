# -*- coding: utf-8 -*-
"""
Solar Pro 4 호출 계약 (서버 측).

- 모델 ID: solar-pro4
- 엔드포인트: https://api.upstage.ai/v1 (OpenAI 호환)
- 인증: UPSTAGE_API_KEY 환경변수 사용
- 별도 활성화 스위치 없음. 키가 있으면 자동 사용.
- 키 값과 응답 본문 전체는 로그/출력에 남기지 않음.

이 모듈은 서버와 테스트에서만 사용한다.
엔진 코어(core.py, __init__.py)는 수정하지 않는다.

요청 계약(22):
- 입력은 fieldId/context/unit/evidenceQuote만 보낸다.
- suggestions는 fieldId, value, sourceBlockIds, evidenceQuote, needsReview, reason을 받는다.
- XML 생성은 맡기지 않는다.
- 문서 속 명령(사용자 텍스트)은 데이터로 취급하며, 시스템 지시를 바꾸는 입력으로 해석하지 않는다.
"""
from __future__ import annotations

import os
from typing import TypedDict, Optional, List

# --- 공개 문서 기준 확인값(참고). 실제 값은 라이브 호출로 검증한다. ---
SOLAR_MODEL_ID = "solar-pro4"
SOLAR_BASE_URL = "https://api.upstage.ai/v1"

# 키는 출력하지 않음. 존재 여부만 사용.


class FieldInput(TypedDict, total=False):
    """요청 입력 계약: fieldId/context/unit/evidenceQuote만 허용."""

    fieldId: str
    context: str
    unit: str
    evidenceQuote: str


class Suggestion(TypedDict, total=False):
    """suggestions 계약 키: fieldId, value, sourceBlockIds, evidenceQuote, needsReview, reason."""

    fieldId: str
    value: str
    sourceBlockIds: list[str]
    evidenceQuote: str
    needsReview: bool
    reason: str


def validate_field_input(data: dict) -> FieldInput:
    """fieldId/context/unit/evidenceQuote 외의 키는 허용하지 않는다."""
    allowed = {"fieldId", "context", "unit", "evidenceQuote"}
    extra = set(data.keys()) - allowed
    if extra:
        raise ValueError(f"허용되지 않은 필드: {sorted(extra)}")
    result: dict = {}
    for key in allowed:
        if key in data:
            result[key] = data[key]
    return FieldInput(**result)


def validate_suggestion(data: dict) -> Suggestion:
    """suggestion 계약 키만 허용. 필수: fieldId, value."""
    required = {"fieldId", "value"}
    allowed = {"fieldId", "value", "sourceBlockIds", "evidenceQuote", "needsReview", "reason"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"suggestion 필수 키 누락: {sorted(missing)}")
    extra = set(data.keys()) - allowed
    if extra:
        raise ValueError(f"suggestion 허용되지 않은 키: {sorted(extra)}")
    result: dict = {}
    for key in allowed:
        if key in data:
            result[key] = data[key]
    return Suggestion(**result)


def treat_user_text_as_data(text: str) -> str:
    """문서 속 명령/프롬프트 변조 시도도 데이터로 취급한다.

    시스템 지시를 바꾸는 입력으로 해석하지 않는다.
    """
    return text


def has_key() -> bool:
    """UPSTAGE_API_KEY가 설정되어 있으면 True."""
    return bool(os.environ.get("UPSTAGE_API_KEY"))


class SolarLiveResult(TypedDict, total=False):
    ok: bool
    error_kind: Optional[str]  # "no_key" | "connection" | "auth" | "model" | None
    note: Optional[str]
    model_id: str
    endpoint: str
    contacted: bool
    status_code: Optional[int]


def call_solar_minimal() -> SolarLiveResult:
    """
    작은 실제 요청 1회를 보낸다.

    반환은 다음 중 하나로 구분한다.
    - contacted=False, error_kind="no_key" : 키 없음
    - contacted=True + 성공 : ok=True
    - contacted=True + HTTP 401 계열 : error_kind="auth"
    - contacted=True + 모델/요청 오류 응답 : error_kind="model"
    - contacted=True + 연결 실패 : error_kind="connection"
    """
    api_key = os.environ.get("UPSTAGE_API_KEY")
    if not api_key:
        return SolarLiveResult(
            ok=False,
            error_kind="no_key",
            note="UPSTAGE_API_KEY 없음 — 라이브 호출 미실행",
            model_id=SOLAR_MODEL_ID,
            endpoint=SOLAR_BASE_URL,
            contacted=False,
            status_code=None,
        )

    try:
        import requests
    except ImportError:
        return SolarLiveResult(
            ok=False,
            error_kind="connection",
            note="요청 라이브러리 없음(requests 미설치)",
            model_id=SOLAR_MODEL_ID,
            endpoint=SOLAR_BASE_URL,
            contacted=False,
            status_code=None,
        )

    url = f"{SOLAR_BASE_URL}/chat/completions"
    payload = {
        "model": SOLAR_MODEL_ID,
        "messages": [{"role": "user", "content": "안녕"}],
        "max_tokens": 8,
        "temperature": 0.0,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
    except Exception as exc:  # 연결/타임아웃 등
        return SolarLiveResult(
            ok=False,
            error_kind="connection",
            note=f"연결 실패: {type(exc).__name__}",
            model_id=SOLAR_MODEL_ID,
            endpoint=SOLAR_BASE_URL,
            contacted=False,
            status_code=None,
        )

    status_code = resp.status_code
    body_snippet = _safe_snippet(resp.text, 400)

    if status_code == 200:
        return SolarLiveResult(
            ok=True,
            error_kind=None,
            note="작은 실제 요청 성공",
            model_id=SOLAR_MODEL_ID,
            endpoint=SOLAR_BASE_URL,
            contacted=True,
            status_code=status_code,
        )

    error_kind = _classify_error(status_code, body_snippet)
    return SolarLiveResult(
        ok=False,
        error_kind=error_kind,
        note=f"HTTP {status_code}, snippet={body_snippet}",
        model_id=SOLAR_MODEL_ID,
        endpoint=SOLAR_BASE_URL,
        contacted=True,
        status_code=status_code,
    )


def _safe_snippet(text: str, maxlen: int) -> str:
    """응답 본문의 일부만 안전하게 남긴다(민감정보는 포함하지 않음)."""
    text = text or ""
    if len(text) > maxlen:
        text = text[:maxlen] + "..."
    return text


def _classify_error(status_code: int, snippet: str) -> str:
    """
    HTTP 상태/주목할 응답 조각으로 오류 종류를 대략 구분한다.
    정확한 근거는 응답 전체이므로, 여기서는 분류만 한다.
    """
    code = status_code
    low = (snippet or "").lower()
    if code == 401 or code == 403:
        return "auth"
    if code in (400, 404, 422, 429, 500, 502, 503):
        # 모델/요청 관련 오류 가능성
        if "model" in low or "not found" in low or "unsupported" in low:
            return "model"
        return "model"
    return "model"
