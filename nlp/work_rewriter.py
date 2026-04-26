# nlp/work_rewriter.py
from __future__ import annotations
import os, re, json, time
from typing import List, Dict, Tuple, Optional

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    from nlp.text_cleanup import cleanup_bullets
except Exception:
    def cleanup_bullets(lines: List[str]) -> List[str]:
        return [l.strip() for l in (lines or []) if str(l).strip()]

try:
    from nlp.proofreader import proofread_bullets
except Exception:
    def proofread_bullets(lines: List[str]) -> List[str]: return lines

SPLIT_RX = re.compile(r"(?<=[.!?])\s+")

def _sentences_of(t: str) -> List[str]:
    return [p.strip() for p in SPLIT_RX.split(t or "") if p.strip()]

def _truncate_words(t: str, max_words: int) -> str:
    if not t: return t
    w = t.split()
    if len(w) <= max_words: return t
    return " ".join(w[:max_words]).rstrip(",;:.! ") + "."

# ✅ UPDATED: High word counts
# nlp/work_rewriter.py

# 1. CONTROLS LENGTH (Detail Slider)
def _tier_targets(length_tier: int) -> Tuple[int, int]:
    # (max_sentences, max_words)
    if length_tier == 0: return (1, 10)    # ✅ ULTRA CONCISE
    if length_tier == 1: return (2, 30) 
    if length_tier == 2: return (3, 60) 
    if length_tier == 3: return (5, 100) 
    return (8, 180)                        # ✅ MASSIVE DETAIL                      # ✅ MASSIVE DETAIL                     # Very Long

_FORBIDDEN_STARTS = ["Assisted", "Responsible for", "Tasked with", "Duties included", "Helped", "Worked on", "Participated in"]

_VERBS = {
    "marketing": ["launched","optimized","scaled","orchestrated","refined","analyzed","iterated","drove","boosted","expanded","partnered","collaborated","tested","segmented"],
    "software": ["implemented","designed","refactored","optimized","automated","containerized","deployed","instrumented","integrated","hardened","debugged","profiled"],
    "data": ["analyzed","modeled","visualized","cleaned","validated","experimented","segmented","forecasted","benchmarked","synthesized","queried","joined"],
    "ops": ["streamlined","standardized","documented","retooled","reduced","coordinated","scheduled","prioritized","tracked","resolved","audited"],
    "sales": ["prospected","qualified","negotiated","closed","expanded","upsold","demoed","nurtured","engaged","converted","pitched"],
    "product": ["synthesized","prioritized","scoped","validated","iterated","aligned","launched","measured","partnered","drove","discovered","framed"],
    "generic": ["delivered","improved","coordinated","organized","prepared","created","developed","maintained","enhanced","owned","led","collaborated"]
}

def _guess_domain(title: str, company: str = "", bullets: List[str] = None) -> str:
    t = f"{title} {company} {' '.join(bullets or [])}".lower()
    if any(k in t for k in ["campaign","social","brand","seo","sem","content","marketing","paid media"]): return "marketing"
    if any(k in t for k in ["api","deploy","frontend","backend","microservice","python","react","engineering","software","system"]): return "software"
    if any(k in t for k in ["analysis","sql","tableau","power bi","dataset","experiment","model","statistic","data","a/b"]): return "data"
    if any(k in t for k in ["ops","operation","logistic","vendor","sop","warehouse","inventory"]): return "ops"
    if any(k in t for k in ["sales","crm","pipeline","quota","lead","deal","account"]): return "sales"
    if any(k in t for k in ["product","roadmap","discovery","spec","user story","backlog"]): return "product"
    return "generic"

# 2. CONTROLS TRUTH (Creativity Slider)
def _system_prompt(creative_tier: int) -> str:
    # Base Instructions (Always Active)
    base = (
        "You are an expert resume bullet editor. Rewrite each bullet FULLY with new wording.\n"
        "STYLE GUIDELINES:\n"
        "- Start with a strong action verb (e.g., 'Engineered', 'Launched', 'Reduced').\n"
        "- Do NOT start with weak phrases like 'Assisted', 'Responsible for', 'Tasked with', or 'Helped'.\n"
        "- Avoid stacking verbs (e.g., avoid 'Planned drove'; use 'Planned and drove').\n"
        "- Use professional, global English. No buzzword spam.\n"
    )

    # Dynamic Rules based on Creativity Slider
    if creative_tier <= 1:
        return base + (
            "CRITICAL SAFETY RULES:\n"
            "1. **STRICT TRUTH:** Do NOT invent tools, numbers, or outcomes. Use ONLY what is provided.\n"
            "2. **NO HALLUCINATIONS:** If the input says 'Fixed bug', do NOT add 'using React' unless specified.\n"
            "Output JSON only: {\"bullets\": [ ... ]}."
        )
    elif creative_tier <= 3:
        return base + (
            "CREATIVE RULES:\n"
            "1. **INFER CONTEXT:** If the job description mentions specific tools (e.g. Jira, AWS) and the user has a matching generic role, you may imply familiarity.\n"
            "2. **ELABORATE:** You may expand on the 'Why' and 'Result' to create a stronger bullet.\n"
            "Output JSON only: {\"bullets\": [ ... ]}."
        )
    else:
        # INVENTIVE RULES (NO LIMITS)
        return base + (
            "MISSION: You are a professional ghostwriter. "
            "KEEP THE USER'S FACTS, but you are EXPECTED to expand these bullets significantly. "
            "If the user didn't provide results, you MUST assume likely metrics "
            "(e.g., 'improving efficiency by 15%') to build the strongest possible bullet. "
            "Transform brief notes into powerful, detailed professional statements."
        )
def _user_prompt(bullets: List[str], tier: int, domain: str, verbs: List[str], target_role: str, job_description: str, why_fit: str, jd_keywords: Optional[List[str]]) -> str:
    max_sents, cap = _tier_targets(tier)
    return json.dumps({
        "tier": tier,
        "guidance": {
            "max_sentences": max_sents,
            "hard_word_cap": cap,
            "forbidden_starts": _FORBIDDEN_STARTS,
            "preferred_verbs": verbs[:10]
        },
        "targeting": {
            "target_role": (target_role or "").strip(),
            "job_description": (job_description or "").strip(),
            "why_fit": (why_fit or "").strip(),
            "jd_keywords": jd_keywords or [],
        },
        "domain": domain,
        "bullets": bullets
    }, ensure_ascii=False)

def _limit_clauses(txt: str) -> str:
    parts = re.split(r"(;|,)", txt)
    if len(parts) > 7:
        txt = "".join(parts[:7])
    return txt

def _validate_line(txt: str, tier: int) -> str:
    max_s, cap = _tier_targets(tier)
    for bad in _FORBIDDEN_STARTS:
        if txt.strip().startswith(bad):
            txt = re.sub(rf"^{re.escape(bad)}\b", "Delivered", txt.strip())
            break
    txt = _limit_clauses(txt)
    sents = _sentences_of(txt)
    if len(sents) > max_s:
        txt = " ".join(sents[:max_s])
    return _truncate_words(txt, cap)

class WorkBulletRewriter:
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.model = model
        self.client = None
        key = api_key or os.getenv("OPENAI_API_KEY")
        if key and OpenAI:
            try:
                self.client = OpenAI(api_key=key)
            except Exception:
                self.client = None

    def rewrite(
        self,
        bullets: List[str],
        length_tier: int,      # <--- Controls constraints (Word Count)
        creative_tier: int,    # <--- Controls logic (Strict vs Inventive)
        title: str = "",
        company: str = "",
        *,
        target_role: str = "",
        job_description: str = "",
        why_fit: str = "",
        jd_keywords: Optional[List[str]] = None,
        temperature: float = 0.6
    ) -> List[str]:

        if not bullets:
            return []

        # 1. Helper Logic (Verbs & Domain)
        try:
            domain = _guess_domain(title, company, bullets)
            verbs = _VERBS.get(domain, _VERBS["generic"])
        except NameError:
            # Fallback if helpers aren't defined
            verbs = ["Delivered", "Managed", "Engineered", "Created"]

        # 2. OFFLINE FALLBACK (Uses Length Tier only)
        if not self.client:
            out = []
            for i, b in enumerate(bullets):
                strong = b.strip()
                if any(strong.startswith(x) for x in _FORBIDDEN_STARTS):
                    strong = re.sub(
                        r"^(Assisted|Responsible for|Tasked with|Helped|Worked on|Participated in|Supported|Involved in)\b",
                        verbs[i % len(verbs)].title(),
                        strong
                    )
                out.append(_validate_line(strong, length_tier)) # Uses Length Tier
            cleaned = cleanup_bullets(out)
            return proofread_bullets(cleaned)

        # 3. ONLINE AI GENERATION
        try:
            # ✅ Get System Prompt based on CREATIVITY TIER
            sys_msg = _system_prompt(creative_tier)

            # ✅ Get User Prompt based on LENGTH TIER (constraints)
            usr_msg = _user_prompt(
                bullets, 
                length_tier, # Pass length constraints here
                target_role, job_description, why_fit, jd_keywords
            )

            rsp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": usr_msg}
                ],
                response_format={"type": "json_object"},
                # Adjust temp slightly higher if creative tier is high
                temperature=min(temperature + (0.1 if creative_tier >= 3 else 0), 0.95),
                presence_penalty=0.2 if length_tier==0 else (0.4 if length_tier==1 else 0.6),
                frequency_penalty=0.4 if length_tier==0 else (0.6 if length_tier==1 else 0.8),
                timeout=20,
            )
            
            raw = rsp.choices[0].message.content or "{}"
            data = json.loads(raw)
            outs = []
            
            # Validate outputs against LENGTH TIER
            for b in (data.get("bullets") or []):
                outs.append(_validate_line(b, length_tier))
            
            outs = cleanup_bullets(outs) or [_validate_line(b, length_tier) for b in bullets]
            outs = proofread_bullets(outs)
            
            # Post-process repeated verbs
            for i in range(1, len(outs)):
                if outs[i].split()[:1] == outs[i-1].split()[:1]:
                    outs[i] = re.sub(r"^\w+", verbs[(i+1) % len(verbs)].title(), outs[i], count=1)
            
            return outs

        except Exception:
            # Fallback on error
            return proofread_bullets(cleanup_bullets([_validate_line(b, length_tier) for b in bullets]))