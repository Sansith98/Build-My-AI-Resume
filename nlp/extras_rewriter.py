# nlp/extras_rewriter.py
from __future__ import annotations
import os, re, json
from typing import List, Optional

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

def _tier_targets(length_tier: int) -> int:
    if length_tier == 0: return 15
    if length_tier == 1: return 30
    if length_tier == 2: return 50
    if length_tier == 3: return 80
    return 150

def _format_bullets(txt: str) -> str:
    """Removes prefix and swaps dashes for filled bullets natively."""
    if not txt: return txt
    
    # We REMOVED the colon-stripping logic here because we WANT to keep 
    # the name of the sport/club (e.g., "Cycling Club: ...")
    
    # Just clean up any unwanted prefixes like "Sport: " or "Activity: "
    # without deleting the actual name.
    if txt.lower().startswith("sport:"):
        txt = txt[6:].strip()
    if txt.lower().startswith("activity:"):
        txt = txt[9:].strip()

    # Swap the AI's dashes for pure text bullets
    txt = txt.replace("- ", "")
    
    return txt.strip()

def _truncate_words(txt: str, cap: int) -> str:
    if "\n" in txt: return txt
    w = txt.split()
    if len(w) <= cap: return txt
    return " ".join(w[:cap]).rstrip(",;:.! ") + "."

def _system_prompt(creative_tier: int) -> str:
    # ✅ FIX: The word "JSON" is strictly required by the OpenAI API here
    formatting = (
        "\nCRITICAL INSTRUCTIONS:\n"
        "1. YOU MUST KEEP THE ACTUAL NAME OF THE SPORT, CLUB, OR ACTIVITY. Never erase the noun.\n"
        "2. Keep descriptions concise (maximum 1-2 bullet points per item).\n"
        "3. If there are multiple items within a single text block, format them on separate lines starting with a dash (-).\n"
        "4. OUTPUT JSON ONLY. You must return a strict JSON object where the keys exactly match the input keys.\n"
    )

    if creative_tier <= 1:
        return "You are a strict resume editor. Fix grammar only. Keep it 100% factual." + formatting
    if creative_tier <= 3:
        return (
            "You are an expert resume editor. Polish the text and optionally highlight one related soft skill, "
            "but the actual activity name MUST remain the main focus." + formatting
        )
    return (
        "You are a professional resume strategist. Enhance the extracurricular activity to sound professional without losing the facts.\n"
        "Pattern to follow: '[Name of Activity]: [1 brief professional sentence].'\n"
        "Example 1: 'University Esports Team' -> 'Competitive Esports Player: Coordinated team strategies and analyzed fast-paced gameplay.'\n"
        "Example 2: 'Karting Club' -> 'Karting Club Member: Cultivated focus and quick decision-making in high-pressure racing environments.'\n"
        + formatting
    )

def _user_prompt(items: List[str], length_tier: int, target_role: str, job_description: str, why_fit: str, jd_keywords: List[str]) -> str:
    cap = _tier_targets(length_tier)
    items_dict = {f"item_{i}": text for i, text in enumerate(items)}
    
    return json.dumps({
        "hard_word_cap": cap, 
        "targeting": {
            "target_role": (target_role or "").strip(),
            "job_description": (job_description or "").strip(),
            "why_fit": (why_fit or "").strip(),
            "jd_keywords": jd_keywords or []
        },
        "input_data": items_dict,
        "expected_json_format": items_dict
    }, ensure_ascii=False)

def _validate_item(txt: str, length_tier: int) -> str:
    cap = _tier_targets(length_tier) 
    txt = re.sub(r"[ \t]{2,}", " ", txt or "").strip()
    txt = _format_bullets(txt)
    txt = _truncate_words(txt, cap)
    if not "\n" in txt and not re.search(r"[.!?]$", txt):
        txt += "."
    return txt

class ExtrasRewriter:
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.client = None
        key = api_key or os.getenv("OPENAI_API_KEY")
        if key and OpenAI:
            try:
                self.client = OpenAI(api_key=key)
            except Exception:
                self.client = None
                
        # ✅ THE FIX: If app.py passes an empty string, force it back to a valid model
        self.model = model if model else "gpt-4o-mini"

    def rewrite(
        self, 
        items: List[str], 
        length_tier: int,      
        creative_tier: int,    
        temperature: float = 0.5,
        target_role: str = "",          # <-- NEW 
        job_description: str = "",      # <-- NEW 
        why_fit: str = "",              # <-- NEW 
        jd_keywords: Optional[List[str]] = None # <-- NEW 
    ) -> List[str]:
        
        if not items:
            return []
            
        if not self.client:
            return [_validate_item(i, length_tier) for i in items]

        try:
            sys_msg = _system_prompt(creative_tier)
            # Pass the new job details to the prompt generator
            usr_msg = _user_prompt(items, length_tier, target_role, job_description, why_fit, jd_keywords)

            rsp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role":"system","content":sys_msg},
                    {"role":"user","content":usr_msg}
                ],
                response_format={"type":"json_object"},
                temperature=min(temperature, 0.8),
                timeout=15
            )
            
            raw = rsp.choices[0].message.content or "{}"
            data = json.loads(raw)
            
            ai_items = []
            for i in range(len(items)):
                key = f"item_{i}"
                if key in data:
                    ai_items.append(data[key])
                else:
                    ai_items.append(items[i])
                
            return [_validate_item(i, length_tier) for i in ai_items]
            
        except Exception as e:
            print(f"ExtrasRewriter Error: {e}") 
            return [_validate_item(i, length_tier) for i in items]