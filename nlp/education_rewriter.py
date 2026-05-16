# nlp/education_rewriter.py
from __future__ import annotations
import os, json, re
from typing import Optional, List, Tuple

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

# nlp/education_rewriter.py

def _tier_targets(length_tier: int) -> Tuple[int, int]:
    if length_tier == 0: return (1, 20)
    if length_tier == 1: return (2, 40)
    if length_tier == 2: return (3, 70)
    if length_tier == 3: return (5, 100)
    return (8, 150)

# ✅ FIXED: Dynamic tone (removes "crisp" from high tiers) + Strict JSON Schema
def _system_prompt(creative_tier: int) -> str:
    if creative_tier <= 1:
        return (
            "Rewrite the following EDUCATION details to fix grammar and formatting. Keep it crisp and concise.\n"
            "CRITICAL: **STRICT FIDELITY.**\n"
            "- Do not invent coursework or projects.\n"
            "- Output JSON strictly in this format: {\"text\": \"your rewritten text\"}"
        )
    elif creative_tier <= 3:
        return (
            "Rewrite EDUCATION details into professional, job-relevant wording.\n"
            "CREATIVE RULES:\n"
            "- Highlight relevant coursework that matches the Target Job.\n"
            "- Smooth out the text to sound more professional and academic.\n"
            "- Output JSON strictly in this format: {\"text\": \"your rewritten text\"}"
        )
    else:
        return (
            "Rewrite and EXPAND the EDUCATION details into highly detailed, impressive descriptions.\n"
            "INVENTIVE RULES:\n"
            "- You MUST expand brief project notes into deep, detailed bullet points.\n"
            "- Elaborate heavily on the significance, technical tools used, and outcomes of the research/thesis/projects.\n"
            "- You may assume standard coursework for this degree if not listed to better align with the target job.\n"
            "- Output JSON strictly in this format: {\"text\": \"your expanded text\"}"
        )

def _user_prompt(text: str, tier: int, target_role: str, job_description: str, why_fit: str, jd_keywords: Optional[List[str]]) -> str:
    max_sents, max_words = _tier_targets(tier)
    return json.dumps({
        "text": (text or "").strip(),
        "tier": tier,
        "targeting": {
            "target_role": (target_role or "").strip(),
            "job_description": (job_description or "").strip(),
            "why_fit": (why_fit or "").strip(),
            "jd_keywords": jd_keywords or [],
        },
        "constraints": {
            "prefer_sentences": max_sents, 
            "max_words": max_words
        },
    }, ensure_ascii=False)

def _cleanup(txt: str) -> str:
    txt = re.sub(r"\s{2,}", " ", (txt or "").strip())
    txt = re.sub(r"[.]{2,}$", ".", txt)
    if txt and not re.search(r"[.!?]$", txt):
        txt += "."
    return txt

class EducationRewriter:
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.model = model
        self.client = None
        key = api_key or os.getenv("OPENAI_API_KEY")
        if key and OpenAI:
            try:
                self.client = OpenAI(api_key=key)
            except Exception:
                self.client = None

    def rewrite_text(
        self,
        text: str,
        *,
        length_tier: int = 1,    # <--- Controls word count limits
        creative_tier: int = 1,  # <--- Controls Strict vs Inventive rules
        target_role: str = "",
        job_description: str = "",
        why_fit: str = "",
        jd_keywords: Optional[List[str]] = None,
        temperature: float = 0.5 
    ) -> str:
        
        # 1. Basic Validation
        if not (text or "").strip():
            return ""

        # 2. Offline Fallback
        if not self.client:
            return _cleanup(text)

        # 3. AI Generation
        try:
            # ✅ Select System Prompt based on CREATIVITY
            sys_msg = _system_prompt(creative_tier)

            # ✅ Select Constraints based on LENGTH
            # Note: Ensure _user_prompt signature matches this call
            usr_msg = _user_prompt(
                text, 
                length_tier, # Pass length constraints here
                target_role, 
                job_description, 
                why_fit, 
                jd_keywords
            )

            rsp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": usr_msg},
                ],
                response_format={"type": "json_object"},
                # Adjust temp: Higher creativity gets slightly higher temp
                temperature=min(temperature + (0.1 if creative_tier >= 3 else 0), 0.95),
                timeout=15,
            )
            
            raw = rsp.choices[0].message.content or "{}"
            data = json.loads(raw)
            out = data.get("text") or text
            return _cleanup(out)
            
        except Exception:
            # Fallback on error
            return _cleanup(text)