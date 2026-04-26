# nlp/proofreader.py
from __future__ import annotations
import re
from typing import List

try:
    import language_tool_python  # pip install language-tool-python
    _LT = language_tool_python.LanguageToolPublicAPI('en-US')
except Exception:
    _LT = None  # graceful no-op if lib/Internet unavailable

# Micro-fixes that grammar tools sometimes miss in resumes
_FIXES = [
    (r"\b[Pp]lanned drove\b", "Planned and drove"),
    (r"\b[Aa]nalyzed compiled\b", "Compiled and analyzed"),
    (r"\b[Rr]eported compiled\b", "Compiled and reported"),
    (r"\b[Ll]aunched compiled\b", "Compiled and launched"),
    (r"\b[Ss]egmented crafted\b", "Crafted and segmented"),
    (r"\b[Ee]xecuted crafted\b", "Crafted and executed"),
    (r"\b[Aa]/B tested crafted\b", "A/B tested and crafted"),
]

def _micro_fix(s: str) -> str:
    for pat, rep in _FIXES:
        s = re.sub(pat, rep, s)
    s = re.sub(r"\b(and\s+){2,}", "and ", s)              # and and
    s = re.sub(r"\b(\w+)\s+\1\b", r"\1", s, flags=re.I)   # word word
    return s

def _lt_fix(text: str) -> str:
    if not _LT:
        return text
    try:
        return _LT.correct(text)
    except Exception:
        return text

def proofread_sentence(s: str) -> str:
    return _lt_fix(_micro_fix(s))

def proofread_paragraph(p: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", p or "")
    parts = [proofread_sentence(x) for x in parts if x.strip()]
    return " ".join(parts)

def proofread_bullets(lines: List[str]) -> List[str]:
    return [proofread_sentence(x) for x in (lines or [])]
