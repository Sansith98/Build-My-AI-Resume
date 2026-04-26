# nlp/text_cleanup.py
from __future__ import annotations
import re
from typing import List

_WS = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,;:.!?])")
_MULTI_SEMI = re.compile(r"(;[^;]{0,20}){3,}")  # >2 semicolons in short span → noisy

# Consolidated, global verb-pair fixes (append-only)
_VERB_PAIR_FIXES = [
    # previously added/common
    (r"\b[Aa]nalyzed compiled\b", "Compiled and analyzed"),
    (r"\b[Ee]xecuted crafted\b", "Crafted and executed"),
    (r"\b[Aa]/B tested crafted\b", "A/B tested and crafted"),
    # new additions (global)
    (r"\b[Pp]lanned drove\b", "Planned and drove"),
    (r"\b[Rr]eported compiled\b", "Compiled and reported"),
    (r"\b[Ss]egmented crafted\b", "Crafted and segmented"),
    (r"\b[Ll]aunched compiled\b", "Compiled and launched"),
]

# Mild filler → tighter alternatives (global)
_FLAIR_TRIMS = [
    (r"\bwith a focus on reliability\b", "with reliable execution"),
    (r"\baligned with team objectives\b", "aligned with team goals"),
    (r"\bsupporting scalable operations\b", "supporting scalable operations"),
    (r"\breducing rework and friction\b", "reducing friction"),
    (r"\bin line with best practices\b", "following best practices"),
]

# Redundancy patterns (global)
_REDUNDANT_FIXES = [
    (r"\bto analyze\b\s*\b.*\b\b(analyze|analysis)\b", " to inform analysis"),
    (r"\b(and\s+){2,}", "and "),                # "and and"
    (r"\b(\w+)\s+\1\b", r"\1"),                 # duplicated word
]

def _normalize_whitespace(s: str) -> str:
    s = _SPACE_BEFORE_PUNCT.sub(r"\1", s)  # remove space before punctuation
    s = _WS.sub(" ", s)
    return s.strip()

def _tidy_punctuation(s: str) -> str:
    # collapse many semicolons → commas
    if _MULTI_SEMI.search(s):
        s = s.replace(";", ",")
    s = _SPACE_BEFORE_PUNCT.sub(r"\1", s)
    return s

def _apply_pairs(s: str) -> str:
    for pat, rep in _VERB_PAIR_FIXES:
        s = re.sub(pat, rep, s)
    for pat, rep in _FLAIR_TRIMS:
        s = re.sub(pat, rep, s)
    for pat, rep in _REDUNDANT_FIXES:
        s = re.sub(pat, rep, s, flags=re.IGNORECASE)
    return s

def _limit_clauses(txt: str) -> str:
    """
    Keep bullets/lines tight by limiting to ~3 chunks (two separators).
    Applies to both semicolons and commas.
    """
    parts = re.split(r"(;|,)", txt)
    if len(parts) > 7:  # e.g., text , text , text
        txt = "".join(parts[:7])
    return txt

def cleanup_sentence(s: str) -> str:
    s = _normalize_whitespace(s)
    s = _apply_pairs(s)
    s = _tidy_punctuation(s)
    s = _limit_clauses(s)
    if not re.search(r"[.!?]$", s):
        s = s.rstrip(",;:") + "."
    return s

def cleanup_bullets(lines: List[str]) -> List[str]:
    out: List[str] = []
    seen_stems = set()
    for line in lines or []:
        t = cleanup_sentence(line)
        # nudge if opener duplicates previous bullet's opener
        stem = " ".join(t.split()[:1]).lower()
        if stem in seen_stems:
            t = re.sub(r"^\w+", "Delivered", t, count=1)
        seen_stems.add(stem)
        out.append(t)
    return out

def cleanup_paragraph(p: str) -> str:
    sents = re.split(r"(?<=[.!?])\s+", p or "")
    sents = [cleanup_sentence(s) for s in sents if s.strip()]
    return " ".join(sents)
