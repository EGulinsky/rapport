"""Normalization helpers for duplicate detection across all sync paths."""

import re

_CORP = re.compile(
    r'\b(gmbh\s*&?\s*co\.?\s*kg|gmbh|ag|se|kg|inc|ltd|llc|bv|nv|s\.?a\.?|s\.?a\.?s\.?|plc|oy|ab|group|holding|holdings|international|global)\b\.?',
    re.IGNORECASE,
)
_GENDER = re.compile(r'\s*\(m\s*/\s*[wf]\s*/\s*[dx]\)\s*|\s*\(all\s+genders?\)\s*|\s*\(w/m/d\)\s*', re.IGNORECASE)
_NOISE = re.compile(r'[&+]')
_WS    = re.compile(r'\s+')


def norm_firma(s: str) -> str:
    s = s.lower().strip()
    s = _CORP.sub(' ', s)
    s = _NOISE.sub(' ', s)
    s = _WS.sub(' ', s).strip()
    return s


def norm_rolle(s: str) -> str:
    s = _GENDER.sub('', s)
    s = _WS.sub(' ', s).lower().strip()
    return s


def dedup_key(firma: str, rolle: str) -> str:
    return f"{norm_firma(firma)}|{norm_rolle(rolle)}"
