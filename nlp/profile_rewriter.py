# nlp/profile_rewriter.py
# ======================================================================
# Expanded, production-ready profile rewriter
# Features: Anti-Hallucination, High Word Counts (up to 180), Safety Rules
# ======================================================================

from __future__ import annotations
import os
import re
import json
import time
import hashlib
from typing import Dict, Any, List, Tuple, Optional

# --------------------------- Optional deps -----------------------------

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    from nlp.text_cleanup import cleanup_paragraph
except Exception:
    def cleanup_paragraph(p: str) -> str:
        return re.sub(r"\s{2,}", " ", (p or "")).strip()

try:
    from nlp.proofreader import proofread_paragraph
except Exception:
    def proofread_paragraph(p: str) -> str:
        return p

# ----------------------------- Utilities ------------------------------

SPLIT_RX = re.compile(r"(?<=[.!?])\s+")

def _sentences_of(text: str) -> List[str]:
    if not text:
        return []
    return [p.strip() for p in SPLIT_RX.split(text) if p and p.strip()]

def _truncate_words(text: str, max_words: int) -> str:
    if not text:
        return text
    words = text.split()
    if len(words) <= max_words:
        if not re.search(r"[.!?]$", text.strip()):
            return text.rstrip(",;: ") + "."
        return text
    clipped = " ".join(words[:max_words]).rstrip(",;:.! ")
    if not re.search(r"[.!?]$", clipped):
        clipped += "."
    return clipped

def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s{2,}", " ", (text or "")).strip()

def _safe_join_sentences(sents: List[str], max_sentences: int) -> str:
    sents = [s.strip() for s in sents if s and s.strip()]
    if len(sents) > max_sentences:
        sents = sents[:max_sentences]
    joined = " ".join(
        s if re.search(r"[.!?]$", s) else (s.rstrip(",;: ") + ".")
        for s in sents
    )
    if not re.search(r"[.!?]$", joined):
        joined = joined.rstrip(",;: ") + "."
    return joined

# ---------------------------- JD keywords -----------------------------

def _jd_keywords(text: str, k: int = 10) -> List[str]:
    if not text:
        return []
    stop = {
        "and","or","for","with","the","a","an","to","of","in","on","at","by",
        "from","as","is","are","this","that","it","we","you","our","their"
    }
    words = re.findall(r"[A-Za-z][A-Za-z+/.-]{1,}", text.lower())
    freq: Dict[str, int] = {}
    for w in words:
        if w in stop or len(w) < 3:
            continue
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: (-x[1], x[0]))[:k]]

# ------------------------------ Facts ---------------------------------

def _compose_facts(form: Dict[str, Any], struct: Dict[str, Any]) -> Dict[str, Any]:
    education = [{
        "type": e.get("type",""),
        "program": e.get("program",""),
        "university": e.get("university",""),
        "period": e.get("period",""),
        "grade": e.get("grade",""),
        "gpa": e.get("gpa","")
    } for e in (struct.get("education") or [])]

    work = [{
        "title": w.get("title",""),
        "company": w.get("company",""),
        "period": w.get("period",""),
        "bullets": w.get("bullets", [])
    } for w in (struct.get("work") or [])]

    facts = {
        "full_name": (form.get("fullName") or "").strip(),
        "target_role": (form.get("jobTitle") or "").strip(),
        "education": education,
        "work": work,
        "skills": struct.get("skills", []),
        "achievements": struct.get("achievements", []),
        "sports": struct.get("sports", []),
        "job_description": (form.get("jobDescription") or "").strip(),
        "why_fit": (form.get("whyFit") or "").strip(),
        "jd_keywords": _jd_keywords(form.get("jobDescription",""))
    }
    return facts

# --------------------------- Tier targets -----------------------------

# nlp/profile_rewriter.py

def _tier_targets(length_tier: int) -> Tuple[int, int, int]:
    # (max_sentences, hard_word_cap, min_sentences)
    if length_tier == 0: return (1, 25, 1)   # ✅ SHORT SNIPPET
    if length_tier == 1: return (3, 70, 2)
    if length_tier == 2: return (5, 120, 3)
    if length_tier == 3: return (8, 200, 5)
    return (15, 400, 10)                     # ✅ FULL NARRATIVE              # ✅ DEEP NARRATIVE

# ---------------------- Opener bans and variants ----------------------

_FORBIDDEN_OPENERS = [
    "Enthusiastic", "Dynamic", "Motivated professional",
    "Professional with a focus", "With a strong focus",
    "Passionate about", "Results-driven professional",
    "As a ",
    "A .* skilled in"
]

def _opening_variants(role: str, kws: List[str], tier: int, tone_crisp: bool) -> List[str]:
    role = (role or "professional").strip()
    kw1 = kws[0] if kws else ""
    kw2 = kws[1] if len(kws) > 1 else ""
    out: List[str] = []

    if tier <= 0:
        if kw1:
            out.append(f"{role.title()} focused on {kw1}.")
        out.append(f"Early-career {role} seeking opportunities.")
        out.append(f"{role.title()} targeting relevant roles.")
        if kw2:
            out.append(f"{role.title()} with exposure to {kw1} and {kw2}.")
        return out

    if tier == 1:
        if kw1 and kw2:
            out.append(f"{role.title()} applying {kw1} and {kw2} to deliver reliable outcomes.")
        out.append(f"{role.title()} known for clear communication and dependable execution.")
        out.append(f"{role.title()} combining structured problem solving with team collaboration.")
        if kw1:
            out.append(f"{role.title()} experienced in {kw1}, committed to steady delivery.")
        return out

    # Tier 2
    if kw1 and kw2:
        out.append(f"Blends data-informed judgement with creative execution across {kw1} and {kw2}.")
    if kw1:
        out.append(f"Combines analytical thinking with practical delivery in {kw1}.")
    out.append(f"Translates goals into measurable progress through clear communication and ownership.")
    out.append(f"Brings structure, curiosity, and initiative to complex, collaborative work.")
    if tone_crisp:
        out.append(f"Balances speed with clarity to land work that others can build on.")
    return out

def _pick_opening(role: str, kws: List[str], tier: int, tone_crisp: bool, salt: str = "") -> str:
    variants = _opening_variants(role, kws, tier, tone_crisp)
    if not variants:
        return f"{(role or 'professional').title()} targeting relevant opportunities."
    h = hashlib.sha1(("|".join([role, ",".join(kws), str(tier), salt])).encode()).hexdigest()
    idx = int(h[:8], 16) % len(variants)
    return variants[idx]

# ---------------------------- Prompts ---------------------------------

def _system_prompt(creative_tier: int) -> str:
    base = (
        "You are an expert resume writer. Rewrite the PROFILE section.\n"
        "STYLE GUIDELINES:\n"
        "- Do NOT use templatey openers like 'Enthusiastic', 'Dynamic', 'Motivated professional', or 'As a ...'. Start fresh.\n"
        "- Use FIRST-PERSON implied voice (no 'this individual', no 'he/she').\n"
        "- Prefer specific, factual strengths over generic soft-skill lists.\n"
    )

    if creative_tier <= 1:
        return base + (
            "CRITICAL RULES:\n"
            "1. **STRICT TRUTH:** Do NOT invent skills, tools, or experiences. Use ONLY what is provided.\n"
            "2. **NO HALLUCINATIONS:** If the user data is thin, keep the profile short. Do not fill gaps.\n"
            "Output JSON only: {\"profile\": \"...\"}."
        )
    elif creative_tier <= 3:
        return base + (
            "CREATIVE RULES:\n"
            "1. **ALIGNMENT:** Aggressively align the profile to the Target Job, using relevant keywords.\n"
            "2. **INFER:** You may bridge small gaps in the narrative using industry standard context.\n"
            "Output JSON only: {\"profile\": \"...\"}."
        )
    else:
        # INVENTIVE RULES (NO LIMITS)
        return base + (
            "INVENTIVE RULES: You are encouraged to fill gaps creatively. "
            "Write a compelling, detailed story. You may assume the candidate "
            "possesses standard skills for their level. Transform their brief "
            "notes into a high-impact professional summary that fills the page."
        )

def _user_prompt(scaffold: List[str], max_sentences: int, hard_cap: int,
                 jd_keywords: List[str], why_fit: str, 
                 target_role: str, job_description: str,
                 forbid: List[str], seed: str, facts: Dict[str, Any]) -> str:
    
    # Extract strict data highlights for the model
    user_skills = facts.get("skills", [])
    user_edu = [e.get("program","") for e in facts.get("education", []) if e.get("program")]

    style_notes = [
        "Professional, natural, global English",
        "No invented facts; avoid employer names unless provided",
        "Prefer specific, factual strengths over generic soft-skill lists.",
        "Keep it 3–5 sentences maximum, clean and ATS-friendly.",
        "Use FIRST-PERSON implied voice (no 'this individual', no 'he/she').",
        "Start with a clear professional identity based on the user’s background.",
        "Include 4–7 concrete skills/tools pulled from the user data.",
        "Prefer present-tense capability statements",
        "Avoid verb stacking and duplicate concepts",
        "Vary rhythm; avoid repetitive clauses",
        "TARGETING INSTRUCTION: actively mirror the terminology found in 'targeting.keywords' and 'targeting.job_description' where honest and relevant."
    ]

    # ✅ THIS IS THE MISSING MAGIC YOU NOTICED!
    if why_fit:
        style_notes.append(f"CRITICAL: The candidate explicitly stated why they fit this role: '{why_fit}'. You MUST heavily embed this specific value proposition and reasoning directly into the profile to impress the recruiter.")
    if job_description:
        style_notes.append("CRITICAL: Align the tone, emphasis, and keywords of the profile to directly match the target job description.")

    payload = {
        "instruction": {
            "rewrite": "Rewrite into a cohesive FIRST-PERSON resume profile. You MUST use the provided 'targeting' data. 1) Adapt the 'target_role' into the opening. 2) Integrate key themes from 'job_description'. 3) If 'candidate_why_fit' is provided, rewrite it professionally and include it.",
            "max_sentences": max_sentences,
            "hard_word_cap": hard_cap,
            "style_notes": style_notes,
            "targeting": {
                "target_role": target_role,
                "job_description": job_description,
                "candidate_why_fit": why_fit,
                "keywords": jd_keywords or []
            },
            "user_data_highlights": {
                "verified_skills": user_skills,
                "verified_education": user_edu
            },
            "forbidden_openers": forbid,
            "seed": seed
        },
        "scaffold_sentences": scaffold
    }
    return json.dumps(payload, ensure_ascii=False)


# ------------------------- Tier scaffolding ---------------------------

def _scaffold_profile(tier: int, facts: Dict[str, Any],
                      tone_crisp: bool, tone_quantify: bool) -> List[str]:
    role = facts.get("target_role") or "professional"
    kws = facts.get("jd_keywords", []) or []

    edu_line = ""
    if facts.get("education"):
        e0 = facts["education"][0]
        bits = []
        if e0.get("type"):       bits.append(e0["type"])
        if e0.get("program"):    bits.append(e0["program"])
        if e0.get("university"): bits.append(f"({e0['university']})")
        edu_line = " ".join(bits).strip()

    strengths = "clear communication, structured problem solving, and attention to detail"
    if tone_crisp:
        strengths = "crisp communication, structured problem solving, and bias for action"

    opener = _pick_opening(role, kws, tier, tone_crisp, salt=facts.get("full_name","") + role)

    sents: List[str] = []
    sents.append(opener if opener.endswith((".", "!", "?")) else (opener + "."))

    # ✅ THE BULLETPROOF FIX: Physically inject "Why You Fit" into the base text!
    if facts.get("why_fit"):
        sents.append(facts["why_fit"] if facts["why_fit"].endswith((".", "!", "?")) else facts["why_fit"] + ".")

    if tier <= 0:
        sents.append(f"Strengths include {strengths}.")
        return sents

    if tier == 1:
        sents.append(f"Strengths include {strengths}.")
        if edu_line:
            sents.append(f"Educational foundation: {edu_line}.")
        sents.append("Applies data-driven insights and practical problem solving to deliver value.")
        if tone_quantify:
            sents.append("Comfortable tying work to measurable outcomes and iterative improvements.")
        return sents

    # tier 2
    sents.append(f"Strengths include {strengths}.")
    if edu_line:
        sents.append(f"Educational foundation: {edu_line}.")
    sents.append("Combines data-informed decision making with creative problem solving.")
    if tone_quantify:
        sents.append("Recognized for contributions that support measurable business outcomes.")
    sents.append("Committed to continuous learning, growth, and pragmatic innovation.")
    return sents

# ----------------------------- Validation -----------------------------

def _validate(text: str, max_sentences: int, hard_cap: int, min_sentences: int) -> Tuple[bool, str]:
    text = _normalize_spaces(text)
    if not text:
        return (False, "empty")

    sents = _sentences_of(text)
    if len(sents) > max_sentences:
        text = " ".join(sents[:max_sentences])
        sents = _sentences_of(text)

    text = _truncate_words(text, hard_cap)

    if not re.search(r"[.!?]$", text):
        text += "."

    if len(sents) < min_sentences:
        return (False, "too few sentences")

    return (True, text)

# ------------------------------ Class ---------------------------------

class ProfileRewriter:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.client = None
        if self.api_key and OpenAI:
            try:
                self.client = OpenAI(api_key=self.api_key)
            except Exception:
                self.client = None
                
    def _compose_online(self, scaffold: List[str], facts: Dict[str, Any], 
                        max_sents: int, hard_cap: int, 
                        creative_tier: int, 
                        tone_crisp: bool,
                        temperature: float = 0.6) -> Optional[str]:
        if not self.client:
            return None

        sys = _system_prompt(creative_tier)
        seed = hashlib.md5(("|".join(scaffold) + "|" + facts.get("full_name","") + "|" + facts.get("target_role","")).encode()).hexdigest()[:8]
        usr = _user_prompt(
            scaffold,
            max_sents,
            hard_cap,
            facts.get("jd_keywords", []),
            facts.get("why_fit", ""),
            facts.get("target_role", ""),
            facts.get("job_description", ""),
            _FORBIDDEN_OPENERS,
            seed,
            facts
        )

        for _ in range(2):
            try:
                rsp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": sys},
                        {"role": "user",   "content": usr}
                    ],
                    response_format={"type": "json_object"},
                    temperature=min(temperature, 0.8),
                    # ✅ FIXED THE CRASH TYPOS HERE
                    presence_penalty=0.2 if creative_tier==0 else (0.4 if creative_tier==1 else 0.6),
                    frequency_penalty=0.4 if creative_tier==0 else (0.6 if creative_tier==1 else 0.8),
                    timeout=20,
                )
                raw = rsp.choices[0].message.content or "{}"
                data = json.loads(raw)
                prof = (data.get("profile") or "").strip()

                for bad in _FORBIDDEN_OPENERS:
                    if re.match(rf"^{bad}", prof):
                        parts = _sentences_of(prof)
                        opener = _pick_opening(
                            facts.get("target_role",""),
                            facts.get("jd_keywords",[]),
                            creative_tier, tone_crisp,
                            salt=facts.get("full_name","") + (facts.get("target_role","") or "")
                        )
                        fresh = opener if opener.endswith((".", "!", "?")) else opener + "."
                        prof = _safe_join_sentences([fresh] + parts[1:], max_sents)
                        break

                prof = cleanup_paragraph(prof)
                prof = proofread_paragraph(prof)

                # ✅ FIXED THE CRASH TYPO HERE
                ok, fixed = _validate(prof, max_sents, hard_cap, min_sentences=max(1, 1 if creative_tier==0 else (3 if creative_tier==1 else 4)))
                if ok:
                    return fixed

                time.sleep(0.25)
            except Exception:
                time.sleep(0.35)
                continue

        return None

    def _compose_fallback(self, scaffold: List[str], max_sents: int, hard_cap: int,
                          min_sents: int) -> str:
        joined = _safe_join_sentences(scaffold, max_sents)
        joined = cleanup_paragraph(joined)
        joined = proofread_paragraph(joined)
        ok, fixed = _validate(joined, max_sents, hard_cap, min_sents)
        return fixed if ok else joined

    # ✅ ADDED THE MISSING ARGUMENTS HERE
    def rewrite(self, form: Dict[str, Any], struct: Dict[str, Any],
                length_tier: int, creative_tier: int,
                tone_crisp: bool, tone_quantify: bool,
                temperature: float = 0.6,
                job_description: str = "", why_fit: str = "") -> Optional[str]:
        
        facts = _compose_facts(form, struct)
        
        # ✅ FORCE THE NEW FACTS INTO THE DICTIONARY
        if job_description:
            facts["job_description"] = job_description
        if why_fit:
            facts["why_fit"] = why_fit

        max_sents, hard_cap, min_sents = _tier_targets(length_tier)
        
        scaffold = _scaffold_profile(length_tier, facts, tone_crisp, tone_quantify)
        prof = self._compose_online(scaffold, facts, max_sents, hard_cap, creative_tier, tone_crisp, temperature=temperature)
        
        if prof:
            return prof

        return self._compose_fallback(scaffold, max_sents, hard_cap, min_sents)