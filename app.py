# app.py
# -----------------------------------------------------------------------------
# Public-ready AI Resume Builder (single-slider)
# - Creativity 0..100 + switch tone_crisp
# - Domain-agnostic rewrite + contextual skill augmentation
# - Global cleaner for awkward AI phrasing (“Implemented doing…”, etc.)
# - Template roots: templates/resumes/* and templates/resume/*
# -----------------------------------------------------------------------------

import os
import re
import json
import time
import sys
import base64
import tempfile
import secrets
import textwrap
import traceback
import requests  # <--- WE ADDED THIS LINE
from flask import send_from_directory, current_app
from copy import deepcopy
from xml.etree import ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from nlp.profile_rewriter import ProfileRewriter
from nlp.work_rewriter import WorkBulletRewriter
from nlp.extras_rewriter import ExtrasRewriter
from nlp.education_rewriter import EducationRewriter
from dotenv import load_dotenv, find_dotenv
from werkzeug.exceptions import HTTPException
from flask import (
    Flask, jsonify, request, abort, send_file,
    render_template, url_for, make_response, send_from_directory, redirect, session, render_template_string
)
from playwright.sync_api import sync_playwright
from jinja2 import Environment, FileSystemLoader, select_autoescape

from dotenv import load_dotenv
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = find_dotenv(usecwd=True) or os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_PATH, override=False)

# =============================================================================
# Paths & Flask
# =============================================================================
BASE_DIR = Path(__file__).resolve().parent
APP_TEMPLATES = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = STATIC_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

RESUMES_DIR = APP_TEMPLATES / "resumes"   # plural
RESUME_DIR  = APP_TEMPLATES / "resume"    # singular

BASE_TPL = os.path.join('templates', 'resumes')

ET.register_namespace('', 'http://www.w3.org/2000/svg')
ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')

def _template_roots() -> List[Path]:
    """
    Order:
      1) RESUME_TEMPLATES_DIR env override (relative to ./templates)
      2) ./templates/resumes
      3) ./templates/resume
    """
    roots: List[Path] = []
    override = (os.getenv("RESUME_TEMPLATES_DIR") or "").strip()
    if override:
        p = APP_TEMPLATES / override
        if p.exists() and p.is_dir():
            roots.append(p)
    if RESUMES_DIR.exists() and RESUMES_DIR.is_dir():
        roots.append(RESUMES_DIR)
    if RESUME_DIR.exists() and RESUME_DIR.is_dir():
        roots.append(RESUME_DIR)
    # de-dup keep order
    seen = set(); out=[]
    for r in roots:
        rp = r.resolve()
        if rp not in seen:
            seen.add(rp); out.append(r)
    return out

app = Flask(
    __name__,
    template_folder=str(APP_TEMPLATES),
    static_folder=str(STATIC_DIR),
)

# Create a secure session key
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(16))

# The password to unlock the site (if not set, the site is public)
SITE_PASSWORD = os.getenv("SITE_PASSWORD") 

@app.before_request
def check_site_password():
    # If no password is set in the environment, let everyone in
    if not SITE_PASSWORD:
        return
        
    # Always allow access to static files (CSS/JS), the login page, and the invisible PDF bot
    if request.endpoint in ['login', 'static', 'export_headless']:
        return
        
    # If they are not logged in, redirect them to the login page
    if session.get('site_unlocked') != True:
        return redirect(url_for('login', next=request.url))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = ""
    if request.method == 'POST':
        if request.form.get('password') == SITE_PASSWORD:
            session['site_unlocked'] = True
            next_url = request.args.get('next') or url_for('home')
            return redirect(next_url)
        else:
            error = "<p style='color:red;'>Incorrect password.</p>"

    # A very simple, clean login screen (no extra HTML file needed)
    return render_template_string(f'''
    <!doctype html>
    <html lang="en">
    <head>
        <title>Private Beta</title>
        <style>
            body {{ font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; background: #f3f4f6; }}
            .box {{ background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); text-align: center; }}
            input[type="password"] {{ padding: 10px; width: 80%; margin: 10px 0; border: 1px solid #ccc; border-radius: 6px; }}
            input[type="submit"] {{ padding: 10px 20px; background: #2563eb; color: white; border: none; border-radius: 6px; cursor: pointer; }}
        </style>
    </head>
    <body>
        <div class="box">
            <h2>Website is currently in Private Beta</h2>
            {error}
            <form method="post">
                <input type="password" name="password" placeholder="Enter Developer Password" required>
                <br><br>
                <input type="submit" value="Unlock Site">
            </form>
        </div>
    </body>
    </html>
    ''')

# =============================================================================
# (Optional) OpenAI client (safe fallback if not configured)
# =============================================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
_DISABLE_OPENAI = os.getenv("DISABLE_OPENAI", "").strip().lower() in ("1", "true", "yes")
_profile_rw  = ProfileRewriter(api_key="", model="")
_work_rw     = WorkBulletRewriter(api_key="", model="")
_extras_rw   = ExtrasRewriter(api_key="", model="")
_edu_rw      = EducationRewriter(api_key="", model="")



print(f"DEBUG - KEY LENGTH: {len(OPENAI_API_KEY)}")
print(f"DEBUG - DISABLE FLAG: {_DISABLE_OPENAI}")
from openai import OpenAI
_openai_client = OpenAI(api_key=OPENAI_API_KEY) if (OPENAI_API_KEY and not _DISABLE_OPENAI) else None




@app.route('/templates/resumes/<path:filename>')
def serve_resume_layout(filename):
    """Safely serves the layout.json files to the frontend Javascript"""
    resumes_dir = os.path.join(current_app.root_path, 'templates', 'resumes')
    return send_from_directory(resumes_dir, filename)
# =============================================================================
# CORS, Error handling, Health
# =============================================================================
@app.after_request
def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp



@app.errorhandler(Exception)
def _json_error(e):
    # Let standard HTTP errors (like a missing image or 404) behave normally
    if isinstance(e, HTTPException):
        return e
        
    import traceback, sys
    traceback.print_exc(file=sys.stderr)
    return jsonify(ok=False, error=str(e)[:400]), 500

@app.get("/healthz")
def _health():
    return jsonify(ok=True, roots=[str(p) for p in _template_roots()])

# =============================================================================
# Export (preview → export) - FIXED FOR MULTI-WORKER
# =============================================================================
import os, tempfile, json

EXPORT_DIR = os.path.join(tempfile.gettempdir(), "resume_exports")
os.makedirs(EXPORT_DIR, exist_ok=True)
EXPORT_TTL_SEC = 60 * 60 * 24 * 7  # 7 days

def _save_to_disk(eid, data_dict):
    file_path = os.path.join(EXPORT_DIR, f"{eid}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data_dict, f)

@app.post("/api/save_export")
def save_export():
    data = request.get_json(force=True)
    html  = data.get("html", "")
    slug  = data.get("slug", "resume")
    eid   = secrets.token_urlsafe(16)
    
    _save_to_disk(eid, {"ts": time.time(), "slug": slug, "html": html, "structured": {}})
    return jsonify(ok=True, eid=eid)

def _get_export_payload(eid: str) -> Dict[str, Any]:
    if not eid or "/" in eid or "\\" in eid:
        abort(404)
        
    file_path = os.path.join(EXPORT_DIR, f"{eid}.json")
    if not os.path.exists(file_path):
        abort(404)
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            item = json.load(f)
    except Exception:
        abort(404)
        
    if (time.time() - item.get("ts", 0)) > EXPORT_TTL_SEC:
        try: os.remove(file_path)
        except: pass
        abort(404)
        
    return item


def _to_str_list(x):
    """
    Return clean list[str] from string / list[str] / list[dict].
    Splits on newlines/semicolons and common bullet markers.
    Also converts inline ' - ' bullet separators into separate lines.
    """
    import re

    def split_lines(s: str):
        if not s:
            return []
        # Normalize common bullet markers to newlines
        s = s.replace("•", "\n").replace("·", "\n")

        # Convert inline " - " separators to newlines (for inputs like: "- a - b - c")
        # Avoid breaking date ranges that use an EN DASH (–), not a hyphen.
        # We also keep hyphenated words intact; this only targets space-hyphen-space.
        s = s.replace(" - ", "\n- ")

        # Strip any leading bullet symbols at line starts
        s = re.sub(r"(?m)^\s*[-–•]\s+", "", s)

        # Now split on newlines or semicolons (avoid global comma split)
        parts = re.split(r"[\n;]+", s)
        return [p.strip() for p in parts if p and p.strip()]

    out = []
    if isinstance(x, (list, tuple)):
        for item in x:
            if isinstance(item, str):
                out.extend(split_lines(item))
            elif isinstance(item, dict):
                v = (
                    item.get("description")
                    or item.get("text")
                    or item.get("title")
                    or item.get("name")
                    or item.get("label")
                    or item.get("value")
                    or ""
                )
                out.extend(split_lines(str(v)))
        return [p for p in out if p]
    if isinstance(x, str):
        return split_lines(x)
    return []



    
def _normalize_work(work):
    """
    Ensure work is a list of dicts with:
      {title:str, company:str, from:str, to:str, bullets:list[str]}
    Accepts loose keys like 'employer', 'organization', 'role', 'start', 'end',
    and string bullets. Falls back gracefully if something is missing.
    """
    out = []
    if not work:
        return out
    for item in work:
        if isinstance(item, dict):
            company = (item.get("company") or item.get("employer") or item.get("organization") or "").strip()
            title   = (item.get("title") or item.get("role") or "").strip()
            start   = (item.get("from") or item.get("start") or item.get("start_date") or "").strip()
            end     = (item.get("to") or item.get("end") or item.get("end_date") or "").strip()
            bullets = item.get("bullets") or item.get("responsibilities") or item.get("highlights") or item.get("points") or []
            bullets = _to_str_list(bullets)
            out.append({"title": title, "company": company, "from": start, "to": end, "bullets": bullets})
        elif isinstance(item, str):
            out.append({"title": "", "company": "", "from": "", "to": "", "bullets": [item.strip()]})
    return out



# =============================================================================
# Templates
# =============================================================================
def _title_from_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()

def _read_meta(dirpath: Path) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    mj = dirpath / "meta.json"
    nt = dirpath / "name.txt"
    if mj.exists():
        try:
            meta = json.loads(mj.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    if not meta.get("name") and nt.exists():
        meta["name"] = nt.read_text(encoding="utf-8").strip()
    if not meta.get("name"):
        meta["name"] = _title_from_slug(dirpath.name)
    meta.setdefault("enabled", True)
    meta.setdefault("order", 1000)
    return meta

def find_template_dir(slug: str) -> Optional[Path]:
    s = (slug or "").strip()
    if not s:
        return None
    l = s.lower()
    for root in _template_roots():
        direct = root / s
        if direct.exists() and direct.is_dir():
            return direct
        for d in root.iterdir():
            if d.is_dir() and d.name.lower() == l:
                return d
    return None

def list_resume_templates() -> List[Dict[str, Any]]:
    out_map: Dict[str, Dict[str, Any]] = {}
    for root in _template_roots():
        if not root.exists():
            continue
        for d in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if not d.is_dir():
                continue
            # Changed this to look for the new layout.json file instead of template.html
            if not (d / "layout.json").exists():
                continue
            meta = _read_meta(d)
            if not meta.get("enabled", True):
                continue
            slug = d.name
            out_map.setdefault(slug, {
                "slug": slug,
                "name": meta.get("name") or _title_from_slug(slug),
                "preview": url_for("template_preview", slug=slug),
                "order": meta.get("order", 1000),
                "tags": meta.get("tags") or [],
                "description": meta.get("description") or "",
            })
    out = list(out_map.values())
    out.sort(key=lambda x: (int(x.get("order", 1000)), x.get("name", "")))
    return out

def _render_template(slug: str, data: dict) -> str:
    tdir = find_template_dir(slug)
    if not tdir:
        raise FileNotFoundError(f"Template '{slug}' not found")
    env = Environment(
        # allow includes from the active template dir AND the global templates/ root
        loader=FileSystemLoader([str(tdir), str(APP_TEMPLATES)]),
        autoescape=select_autoescape(["html", "xml"]),
        enable_async=False,
    )
    tpl = env.get_template("template.html")
    return tpl.render(d=data)


# =============================================================================
# Creativity mapping helpers (required by generate_resume)
# =============================================================================
def _to_int(val, default=50):
    try:
        return int(val)
    except Exception:
        return default

def _tier_from_creativity(creativity: int) -> int:
    x = max(0, min(100, _to_int(creativity, 50)))
    if x < 40: return 0
    if x < 70: return 1
    return 2

def _verbosity_from_creativity(creativity: int) -> int:
    x = max(0, min(100, _to_int(creativity, 50)))
    if x < 30: return 0
    if x < 70: return 1
    return 2

# =============================================================================
# Text Wrapping
# =============================================================================

import textwrap
import re
# (you already import textwrap and re at the top, so if they are
#  already present, you don't need to add them again)


def _split_bullet_into_chunks(text: str, max_len: int = 90) -> list[str]:
    """
    Split a long bullet into smaller chunks that are each <= max_len characters,
    preferring to break at sentence boundaries or commas.
    """
    text = (text or "").strip()
    if not text:
        return []

    # First split on sentence-like boundaries.
    parts = re.split(r'(?<=[\.\!\?\;])\s+', text)
    chunks: list[str] = []

    for part in parts:
        part = part.strip()
        if not part:
            continue

        if len(part) <= max_len:
            chunks.append(part)
        else:
            # Further wrap long parts using textwrap
            wrapped = textwrap.wrap(
                part,
                width=max_len,
                break_long_words=False,
                break_on_hyphens=False,
            )
            for w in wrapped:
                w = w.strip()
                if w:
                    chunks.append(w)

    return chunks


def _wrap_all_text_sections(struct: dict, max_len: int = 90) -> None:
    """Wraps text and ensures the REAL bullet character is used so the frontend editor can align it."""
    if not isinstance(struct, dict): return

    def _format_real_bullet(text: str) -> str:
        text = str(text).strip()
        # 1. Strip AI's fake bullets (dashes, asterisks, middle dots)
        text = re.sub(r"^[-*·]\s*", "", text)
        
        # 2. Prepend the ACTUAL bullet character that the frontend editor recognizes
        if not text.startswith("•"):
            text = f"• {text}"
            
        chunks = _split_bullet_into_chunks(text, max_len)
        if not chunks: return ""
        
        # Join with pure newlines. No space hacks. Let studio.js handle the alignment!
        return "\n".join(chunks)

    # Apply to all bulleted sections
    for job in struct.get("work", []):
        if isinstance(job, dict) and job.get("bullets"):
            job["bullets"] = [_format_real_bullet(b) for b in job["bullets"]]

    for edu in struct.get("education", []):
        if isinstance(edu, dict) and edu.get("research"):
            # 🚀 FIX: Do not force bullets on our custom Secondary Education layout!
            if edu.get("type") == "Secondary Education":
                continue
            edu["research"] = [_format_real_bullet(r) for r in edu["research"]]

    for key in ["sports", "achievements"]:
        if isinstance(struct.get(key), list):
            struct[key] = [_format_real_bullet(item) for item in struct[key]]

    # Extras and Profile usually don't need forced bullets unless they are lists
    for ex in struct.get("extras", []):
        if isinstance(ex, dict) and ex.get("description"):
            ex["description"] = "\n".join(_split_bullet_into_chunks(str(ex["description"]), max_len))
            
    if struct.get("profile"):
        struct["profile"] = "\n".join(_split_bullet_into_chunks(str(struct["profile"]), max_len=100))




# =============================================================================
# Utilities
# =============================================================================
def _compact(obj: Any) -> Any:
    if isinstance(obj, dict):
        res = {}
        for k, v in obj.items():
            if isinstance(v, str):
                if v.strip(): res[k] = v
            elif isinstance(v, list):
                vv = [_compact(x) for x in v]
                vv = [x for x in vv if x not in ("", None, {}, [])]
                if vv: res[k] = vv
            elif isinstance(v, dict):
                vv = _compact(v)
                if vv: res[k] = vv
            elif isinstance(v, (int, float, bool)):
                res[k] = v
        return res
    if isinstance(obj, list):
        vv = [_compact(x) for x in obj]
        return [x for x in vv if x not in ("", None, {}, [])]
    return obj

def _skills_from_csv(text) -> List[str]:
    """Convert input to a clean, deduplicated list of skills (handles both str and list)."""
    if not text:
        return []

    raw: List[str] = []

    # If input is already a list, process each element as text
    if isinstance(text, list):
        candidates = [str(x) for x in text if x]
    else:
        # Split by line first if it's a string
        candidates = str(text).splitlines()

    for ln in candidates:
        # Replace semicolons with commas, then split again
        for p in ln.replace(";", ",").split(","):
            p = (p or "").strip()
            if p:
                raw.append(p)

    # Deduplicate while keeping order
    out, seen = [], set()
    for p in raw:
        lp = p.lower()
        if lp not in seen:
            out.append(p)
            seen.add(lp)

    return out


def _normalize_skills_structured(raw) -> List[Dict[str, Any]]:
    """
    Accepts either:
      - list[dict]: [{name, level5, level100}, ...]
      - JSON string encoding the same
      - list[str] (names only)
    Returns: [{"name": str, "level5": 0..4, "level100": 0..100}, ...]
    """
    import json
    out: List[Dict[str, Any]] = []

    if not raw:
        return out
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = []

    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                name = (item.get("name") or "").strip()
                if not name:
                    continue
                l5 = item.get("level5")
                l100 = item.get("level100")
                try:
                    l5 = int(l5)
                except Exception:
                    try:
                        l100 = int(l100)
                        l5 = round((l100 / 100) * 4)
                    except Exception:
                        l5 = 2
                l5 = max(0, min(4, l5))
                l100 = int(round((l5 / 4) * 100))
                # level5 is 0..4 in the UI, show 1..5 dots for humans
                out.append({
                    "name": name,
                    "level5": l5,
                    "level100": l100,
                    "level": int(l5) + 1,   # used by SVG dot renderer
                })
            elif isinstance(item, str) and item.strip():
                out.append({
                    "name": item.strip(),
                    "level5": 2,
                    "level100": 50,
                    "level": 3,             # neutral 3/5 by default
                })
    return out



def _lines(text) -> List[str]:
    """Return a clean list of lines from either a string or list input."""
    if not text:
        return []
    
    # If input is a list, flatten it first
    if isinstance(text, list):
        lines = []
        for item in text:
            if isinstance(item, str):
                lines.extend([ln.strip("-• ").strip() for ln in item.splitlines() if ln.strip()])
            else:
                lines.append(str(item).strip())
        return lines

    # Otherwise treat it as a string
    return [ln.strip("-• ").strip() for ln in str(text).splitlines() if ln.strip()]


def _month_name(m: str) -> str:
    try: i = int(m)
    except Exception: return ""
    mo = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    return mo[i-1] if 1 <= i <= 12 else ""

def _period(fm: str, fy: str, tm: str, ty: str) -> str:
    def part(m, y):
        if not y and not m: return ""
        if y and m: return f"{_month_name(str(m))} {y}"
        return str(y or "")
    s = part(fm, fy)
    e = "Present" if (ty == "Present") else part(tm, ty)
    if s or e:
        return f"{s} – {e}" if s and e else (s or e)
    return ""


def _format_skills_markdown(struct: Dict[str, Any]) -> str:
    """
    Build the Skills section lines with levels.
    Uses struct['skills_structured'] if available, else falls back to names.
    """
    items = struct.get("skills_structured") or []

    # Fallback: if only a newline/CSV string exists, seed neutral levels
    if not items and struct.get("skills"):
        # If _skills_from_csv exists, use it; otherwise split on newlines/commas
        try:
            names = _skills_from_csv(struct["skills"])  # pragma: no cover
        except Exception:
            raw = struct.get("skills", "")
            names = [s.strip() for s in re.split(r"[\r\n,;]+", raw) if s.strip()]
        items = [{"name": n, "level5": 2, "level100": 50} for n in names]

    lines: List[str] = []
    for s in items:
        name = (s.get("name") or "").strip()
        if not name:
            continue

        l5 = s.get("level5")
        l100 = s.get("level100")

        # Derive if needed
        try:
            if l5 is None and l100 is not None:
                l5 = round(int(l100) / 100 * 4)
        except Exception:
            l5 = None

        if l5 is None:
            l5 = 2  # neutral default

        # Display as 1..5 for humans (your UI stores 0..4)
        lines.append(f"- {name} — {int(l5) + 1}/5")

    return "\n".join(lines)    

def _derive_current_title(work: List[Dict[str, Any]]) -> str:
    for w in work:
        if "present" in (w.get("period") or "").lower():
            return w.get("title") or ""
    if work:
        return work[0].get("title") or ""
    return ""

def _save_data_url_image(data_url: str) -> str:
    if not data_url or not data_url.startswith("data:image/"): return ""
    try:
        header, b64data = data_url.split(",", 1)
    except ValueError:
        return ""
    ext = "png"
    if ";base64" in header:
        try:
            sub = header.split(";")[0].split("/")[1].lower()
            if sub in {"png","jpg","jpeg","webp"}: ext = sub
        except Exception:
            pass
    try:
        raw = base64.b64decode(b64data)
    except Exception:
        return ""
    fname = f"{int(time.time())}_{os.urandom(4).hex()}.{ext}"
    path = UPLOADS_DIR / fname
    with open(path, "wb") as f: f.write(raw)
    return f"/static/uploads/{fname}"


def _build_certs_from_arrays(form):
    cN  = form.get("certName")        or []
    cI  = form.get("certIssuer")      or []
    cIM = form.get("certIssueMonth")  or []
    cIY = form.get("certIssueYear")   or []
    cXM = form.get("certExpireMonth") or []
    cXY = form.get("certExpireYear")  or []
    cNE = form.get("certNoExpiry")    or []
    cID = form.get("certId")          or []
    cURL= form.get("certUrl")         or []
    cDS = form.get("certDescription") or []
    MONTH = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    def _fmt(mm, yy):
        mm = str(mm or "").strip(); yy = str(yy or "").strip()
        if not mm and not yy: return ""
        try: mn = MONTH[int(mm)]
        except: mn = mm
        return f"{mn} {yy}".strip()
    certs = []
    L = max(len(cN),len(cI),len(cIM),len(cIY),len(cXM),len(cXY),len(cNE),len(cID),len(cURL),len(cDS)) if any([cN,cI,cIM,cIY,cXM,cXY,cNE,cID,cURL,cDS]) else 0
    for i in range(L):
        name   = (cN[i]  if i < len(cN)  else "").strip()
        issuer = (cI[i]  if i < len(cI)  else "").strip()
        issue  = _fmt(cIM[i] if i < len(cIM) else "", cIY[i] if i < len(cIY) else "")
        noexp  = str(cNE[i] if i < len(cNE) else "").lower()
        expiry = "" if noexp in ("on","true","1","yes") else _fmt(cXM[i] if i < len(cXM) else "", cXY[i] if i < len(cXY) else "")
        cred_id= (cID[i] if i < len(cID) else "").strip()
        url    = (cURL[i]if i < len(cURL)else "").strip()
        desc   = (cDS[i] if i < len(cDS) else "").strip()
        if any([name, issuer, issue, expiry, cred_id, url, desc]):
            certs.append({"name":name,"issuer":issuer,"issue":issue,"expiry":expiry,"credential_id":cred_id,"url":url,"description":desc})
    return certs   

# =============================================================================
# Structure from form (no AI)
# =============================================================================


def _structure_from_form(form: Dict[str, Any]) -> Dict[str, Any]:
    # =========================================================================
    # 🚀 DATA WIPING FIX
    # If the frontend sends structured JSON, return it immediately!
    # (The Fallback Engine is now safely handled by Javascript)
    # =========================================================================
    if isinstance(form.get("secondary"), dict) or isinstance(form.get("work"), list) or isinstance(form.get("education"), list):
        d = dict(form)
        # If certifications not yet structured, build it from parallel arrays
        if not d.get("certifications") and d.get("certName"):
            d["certifications"] = _build_certs_from_arrays(d)
        return d

    # --- NORMAL FLAT PARSING FOR RAW HTML FORMS ---
    d: Dict[str, Any] = {}

    d["profile"] = form.get("jobDescription", "") or ""

    email = form.get("email", "") or ""
    phone = form.get("phone", "") or ""
    address = form.get("address", "") or ""
    linkedin = form.get("linkedin", "") or ""
    portfolio = form.get("portfolio", "") or ""
    github = form.get("github", "") or ""
    contact_line = " • ".join([v for v in [address, email, phone] if v])

    skills = _skills_from_csv(form.get("skills", ""))
    skills_struct = _normalize_skills_structured(form.get("skillsStructured"))

    if not skills_struct and skills:
        skills_struct = [{
            "name": s,
            "level5": 2,
            "level100": 50,
            "level": 3,   # neutral 3/5 so dots show nicely
        } for s in skills]
        
    # University education
    edu = []
    
    types = form.get("eduType", []) or []
    types = form.get("eduType", []) or []
    unis = form.get("eduUniversity", []) or []
    progs = form.get("eduProgram", []) or []
    grades = form.get("eduGrade", []) or []
    grades = form.get("eduGrade", []) or []
    gpas = form.get("eduGPA", []) or []
    theses = form.get("eduThesis", []) or []
    fM = form.get("eduFromMonth", []) or []
    fY = form.get("eduFromYear", []) or []
    tM = form.get("eduToMonth", []) or []
    tY = form.get("eduToYear", []) or []
    research = form.get("eduResearch", []) or []
    L = max(len(types),len(unis),len(progs),len(grades),len(gpas),len(theses),len(fM),len(fY),len(tM),len(tY),len(research))
    for i in range(L):
        typ = (types+[""])[i]
        uni = (unis+[""])[i]
        prog = (progs+[""])[i]
        grd = (grades+[""])[i] if i < len(grades) else ""
        gpa = (gpas+[""])[i] if i < len(gpas) else ""
        the = (theses+[""])[i] if i < len(theses) else ""
        per = _period((fM+[""])[i], (fY+[""])[i], (tM+[""])[i], (tY+[""])[i])
        # research (string -> list of bullet lines)
        res = (research + [""])[i] if i < len(research) else ""
        bullets = _to_str_list(res)

        # prepend meta as bullets if present
        meta = []
        if the:  bullets.insert(0, f"Thesis: {the}")
        if grd:  meta.append(f"Grade: {grd}")
        if gpa:  meta.append(f"GPA: {gpa}")
        if meta:
            bullets.insert(0, " • ".join(meta))

        item = {
            "type": typ,
            "university": uni,
            "program": prog,
            "grade": grd,
            "gpa": gpa,
            "thesis": the,
            "period": per,
            "research": bullets,  # <-- list (required for bullets repeater)
            "degree_name": prog or typ,
            "degree_and_type": f"{typ} — {prog}" if (typ and prog) else (prog or typ),
        }


        if any(v for v in item.values()):
            edu.append(item)




    # Secondary
    schools = []
    schN = form.get("schoolName", []) or []
    sFM = form.get("schoolFromMonth", []) or []
    sFY = form.get("schoolFromYear", []) or []
    sTM = form.get("schoolToMonth", []) or []
    sTY = form.get("schoolToYear", []) or []
    Ls = max(len(schN),len(sFM),len(sFY),len(sTM),len(sTY))
    for i in range(Ls):
        sch = {"name": (schN+[""])[i], "period": _period((sFM+[""])[i], (sFY+[""])[i], (sTM+[""])[i], (sTY+[""])[i])}
        if sch["name"] or sch["period"]:
            schools.append(sch)
    ol = [{"subject": s, "grade": g} for s, g in zip(form.get("olSubject", []) or [], form.get("olGrade", []) or []) if s or g]
    al = [{"subject": s, "grade": g} for s, g in zip(form.get("alSubject", []) or [], form.get("alGrade", []) or []) if s or g]

    secondary = {"schools": schools, "ol": ol, "al": al, "ol_year": form.get("olYear"), "al_year": form.get("alYear")}

    

    d["education"] = edu
    d["secondary"] = secondary
    d["skills"] = skills
    d["skills_structured"] = skills_struct 


    # Contact
    photo = form.get("photo") or form.get("photoDataUrl") or form.get("avatar_data_url") or ""

    contact = {
        "full_name": form.get("fullName") or form.get("name") or "",
        "current_title": form.get("jobTitle") or "",
        "contact_line": contact_line,
        "email": email,
        "phone": phone,
        "address": address,
        "linkedin": linkedin,
        "portfolio": portfolio,
        "github": github,
    }

    # Pass the photo/base64 through so SVG can use it
    if photo:
        contact["avatar_data_url"] = photo
        contact["photo"] = photo

    d["contact"] = contact



    # ---- build WORK from parallel arrays in form ----
    job_titles = form.get("jobTitleExp") or []
    companies  = form.get("company") or []
    wfm = form.get("workFromMonth") or []
    wfy = form.get("workFromYear") or []
    wtm = form.get("workToMonth") or []
    wty = form.get("workToYear") or []
    wdesc = form.get("workDescription") or []

    work = []
    max_len = max(len(job_titles), len(companies), len(wfm), len(wfy), len(wtm), len(wty), len(wdesc)) if any([
        job_titles, companies, wfm, wfy, wtm, wty, wdesc
    ]) else 0

    def _fmt_mmyy(mm, yy):
        mm = (str(mm or "")).strip()
        yy = (str(yy or "")).strip()
        if not mm and not yy: return ""
        MONTH = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        try:
            mname = MONTH[int(mm)]
        except Exception:
            mname = mm
        return (f"{mname} {yy}").strip()

    for i in range(max_len):
        title = (job_titles[i] if i < len(job_titles) else "").strip()
        comp  = (companies[i]  if i < len(companies)  else "").strip()
        frm   = _fmt_mmyy(wfm[i] if i < len(wfm) else "", wfy[i] if i < len(wfy) else "")
        to    = _fmt_mmyy(wtm[i] if i < len(wtm) else "", wty[i] if i < len(wty) else "")
        bullets = _to_str_list(wdesc[i] if i < len(wdesc) else "")

        # NEW: build a human-readable period (SVG binds to 'period' first)
        period = ""
        if frm or to:
            period = f"{frm} – {to}" if (frm and to) else (frm or to)

        work.append({
            "title": title,
            "company": comp,
            "from": frm,
            "to": to,
            "period": period,     # ← add this line
            "bullets": bullets
        })


    d["work"] = work


        # ---- build CERTIFICATIONS from parallel arrays ----
    cN  = form.get("certName")        or []
    cI  = form.get("certIssuer")      or []
    cIM = form.get("certIssueMonth")  or []
    cIY = form.get("certIssueYear")   or []
    cXM = form.get("certExpireMonth") or []
    cXY = form.get("certExpireYear")  or []
    cNE = form.get("certNoExpiry")    or []
    cID = form.get("certId")          or []
    cURL= form.get("certUrl")         or []
    cDS = form.get("certDescription") or []

    def _fmt_mmyy(mm, yy):
        mm = (str(mm or "").strip())
        yy = (str(yy or "").strip())
        if not mm and not yy:
            return ""
        MONTH = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        try:
            mname = MONTH[int(mm)]
        except Exception:
            mname = mm
        return (f"{mname} {yy}").strip()

    certs = []
    Lc = max(len(cN), len(cI), len(cIM), len(cIY), len(cXM), len(cXY), len(cNE), len(cID), len(cURL), len(cDS)) if any([
        cN, cI, cIM, cIY, cXM, cXY, cNE, cID, cURL, cDS
    ]) else 0

    for i in range(Lc):
        name   = (cN[i]  if i < len(cN)  else "").strip()
        issuer = (cI[i]  if i < len(cI)  else "").strip()
        issue  = _fmt_mmyy(cIM[i] if i < len(cIM) else "", cIY[i] if i < len(cIY) else "")
        # honour "No expiry" checkbox
        noexp  = (cNE[i] if i < len(cNE) else "")
        expiry = "" if (str(noexp).lower() in ("on","true","1","yes")) else _fmt_mmyy(cXM[i] if i < len(cXM) else "", cXY[i] if i < len(cXY) else "")
        cred_id= (cID[i] if i < len(cID) else "").strip()
        url    = (cURL[i]if i < len(cURL)else "").strip()
        desc   = (cDS[i] if i < len(cDS) else "").strip()

        cert = {
            "name": name, "issuer": issuer,
            "issue": issue, "expiry": expiry,
            "credential_id": cred_id, "url": url,
            "description": desc,
        }
        # keep rows that have at least a name or issuer
        if any(v for v in (name, issuer, issue, expiry, cred_id, url, desc)):
            certs.append(cert)

    d["certifications"] = certs


    # ---- build EXTRAS from names + descriptions ----



    # ---- build REFEREES from parallel arrays ----
    r_names = form.get("refName") or []
    r_pos   = form.get("refPosition") or []
    r_eml   = form.get("refEmail") or []
    r_tel   = form.get("refMobile") or []
    refs = []
    max_len_ref = max(len(r_names), len(r_pos), len(r_eml), len(r_tel)) if any([r_names, r_pos, r_eml, r_tel]) else 0
    
    ref_canvas_blocks = [] # ✅ NEW: We will build the beautifully stacked text here!
    
    for i in range(max_len_ref):
        ref = {
            "name":     (r_names[i] if i < len(r_names) else "").strip(),
            "position": (r_pos[i]   if i < len(r_pos)   else "").strip(),
            "email":    (r_eml[i]   if i < len(r_eml)   else "").strip(),
            "mobile":   (r_tel[i]   if i < len(r_tel)   else "").strip(),   
        }
        if any(ref.values()):
            refs.append(ref)
            
            # ✅ FIX: Stack every detail onto a new line specifically for the Canvas Editor
            lines = []
            if ref["name"]: lines.append(ref["name"])
            if ref["position"]: lines.append(ref["position"])
            if ref["email"]: lines.append(f"Email: {ref['email']}")
            if ref["mobile"]: lines.append(f"Mobile: {ref['mobile']}")
            if lines:
                ref_canvas_blocks.append("\n".join(lines))

    d["referees"] = refs
    d["refereesText"] = "\n\n".join(ref_canvas_blocks) # ✅ Send the stacked text to studio.html!


    # ---- build EXTRAS as {name, description} objects ----
    xN = form.get("extraName", []) or []
    xD = form.get("extraDescription", []) or []
    extras = []
    Le = max(len(xN), len(xD)) if (xN or xD) else 0
    for i in range(Le):
        nm = (xN[i] if i < len(xN) else "").strip()
        ds = (xD[i] if i < len(xD) else "").strip()
        if nm or ds:
                extras.append({"name": nm.strip().upper(), "description": ds})



    d["extras"] = extras
        # Sports & Extracurricular + Achievements & Awards
    # (form.html sends them as multiline textareas)
    d["sports"] = _to_str_list(form.get("sports") or "")
    d["achievements"] = _to_str_list(form.get("achievements") or "")

    # ---- build PUBLICATIONS from parallel arrays (LOCAL ONLY) ----
    pT  = form.get("pubTitle")        or form.get("publicationTitle")        or form.get("publicationTitle[]")        or []
    pV  = form.get("pubVenue")        or form.get("publicationVenue")        or form.get("publicationVenue[]")        or []
    pM  = form.get("pubMonth")        or form.get("publicationMonth")        or form.get("publicationMonth[]")        or []
    pY  = form.get("pubYear")         or form.get("publicationYear")         or form.get("publicationYear[]")         or []
    pA  = form.get("pubAuthors")      or form.get("publicationAuthors")      or form.get("publicationAuthors[]")      or []
    pL  = form.get("pubLink")         or form.get("publicationLink")         or form.get("publicationLink[]")         or []
    pD  = form.get("pubDescription")  or form.get("publicationDescription")  or form.get("publicationDescription[]")  or []

    publications = []
    Lp = max(len(pT), len(pV), len(pM), len(pY), len(pA), len(pL), len(pD)) if any([pT,pV,pM,pY,pA,pL,pD]) else 0
    for i in range(Lp):
        item = {
            "title":    (pT[i] if i < len(pT) else "").strip(),
            "venue":    (pV[i] if i < len(pV) else "").strip(),
            "month":    (pM[i] if i < len(pM) else "").strip(),
            "year":     (pY[i] if i < len(pY) else "").strip(),
            "authors":  (pA[i] if i < len(pA) else "").strip(),
            "link":     (pL[i] if i < len(pL) else "").strip(),
            "description": (pD[i] if i < len(pD) else "").strip(),
        }
        if any(item.values()):
            publications.append(item)

    d["publications"] = publications

    return d


def _apply_case(s: str, mode: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    s = s.replace("_", " ")
    mode = (mode or "none").lower()
    if mode == "upper":
        return s.upper()
    if mode == "title":
        return s.title()
    return s


# =============================================================================
# Minimal enhancer (identity) — keep structure as-is; local tweaks can be added
# =============================================================================
def _enhance_struct(struct: Dict[str, Any], tier: int, verbosity: int,
                    enforce: bool, job_title: str, job_desc: str,
                    tone_crisp: bool, tone_quantify: bool, creativity: int) -> Dict[str, Any]:
    # For now, just return the struct unchanged.
    return json.loads(json.dumps(struct))

# =============================================================================
# Markdown preview (always includes Skills if present)
# =============================================================================

# =============================================================================
# AI payload selection & merge helpers (send only 4 sections to AI)
# =============================================================================
def _text_font_size(node, default=12.0):
    """Read font-size on <text> or inherit from parent; fallback to default."""
    try:
        if 'font-size' in node.attrib:
            return float(str(node.get('font-size')).replace('px',''))
        # look up one level for a size on parent <text>
        parent = node.getparent() if hasattr(node, 'getparent') else None
        if parent is not None and 'font-size' in parent.attrib:
            return float(str(parent.get('font-size')).replace('px',''))
    except Exception:
        pass
    return float(default)

def _wrap_words(text, max_px, font_px):
    """
    Very-lightweight word wrapper.
    Approximates character width as 0.55 * font_px (works well for UI sans).
    Returns list[str] lines.
    """
    if not text:
        return []
    words = str(text).split()
    if not words:
        return [text]

    avg = 0.55 * float(font_px)
    lines, cur = [], ""
    for w in words:
        candidate = (w if not cur else (cur + " " + w))
        if len(candidate) * avg <= max_px:
            cur = candidate
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines



def _pick_ai_payload(struct: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "profile": struct.get("profile") or "",
        "work": struct.get("work") or [],
        "education": struct.get("education") or [],
        "achievements": struct.get("achievements") or []
    }

def _call_openai_sections(ai_payload: Dict[str, Any], tier: int = 1, verbosity: int = 1, temperature: float = 0.6) -> Dict[str, Any]:
    # REQUIRE OpenAI for these sections; no pass-through
    if _openai_client is None:
        raise RuntimeError("OpenAI client is not initialized. Set DISABLE_OPENAI=0 and OPENAI_API_KEY in .env")
    if os.getenv("DISABLE_OPENAI", "").strip().lower() in ("1", "true", "yes"):
        raise RuntimeError("DISABLE_OPENAI is set. Turn it off to generate Profile/Work/Education/Achievements via OpenAI.")

    # Pull optional context we attached in generate_resume()
    context = ai_payload.pop("_context", {})
# Pull optional context we attached in generate_resume()
    context = ai_payload.pop("_context", {})
    
    # ✅ DYNAMIC SYSTEM PROMPT: Switches based on Creative Slider
    if tier >= 3:
        # INVENTIVE MODE
        system = (
            "You are a high-end resume strategist. "
            "MISSION: Transform this resume into a top-tier document for the target role. "
            "CREATIVE FREEDOM: Use the user's provided data as the absolute foundation. Do NOT delete core facts. "
            "If the input is thin, you MUST expand the narrative and fill in gaps with impressive, "
            "industry-standard achievements and results that fit the candidate's level. "
            "Maximize impact. Use Inventive language."
        )
    else:
        # STRICT MODE
        system = (
            "You are a strict resume editor. Polish grammar and flow only. "
            "CRITICAL RULE: DO NOT invent roles, numbers, or facts. Stay 100% true to the input. "
            "Keep it grounded and conservative."
        )
    
    system += "\nReturn strict JSON with keys: profile, work, education, achievements."

    # IMPORTANT: allow bullet generation only when bullets are missing
    user_obj = {
        "instructions": {
            "tone": "crisp",
            "verbosity": int(verbosity),
            "rules": [
                "Do not add new employers, titles, or degrees.",
                "Profile must be written in FIRST-PERSON implied voice (no 'this individual', no 'the candidate').",
                "For general_resume mode: make the profile transferable across similar roles; avoid overfitting to one job post.",
                "Profile must include 4–7 concrete skills/tools grounded in the user data (not generic soft skills only).",
                "Profile structure: [Identity + domain] + [core technical strengths] + [proof/impact or research focus] + [collaboration/style].",
                "Do not change dates.",
                "If a work entry exists but its 'bullets' are empty: "
                "when context.job_specific is true, derive 3–6 truthful bullets from context.job_description; "
                "when context.general_resume is true, derive 3–6 truthful bullets from the role title/company and existing resume content "
                "(no job-post-specific language).",
                "Use action verbs and measurable impact when possible.",
                "Preserve all existing work entries; do not drop, merge, or reorder roles.",
                "Preserve title/company and from/to; edit wording and bullets only."
            ]
        },
        "context": context,
        "sections": ai_payload
    }






    rsp = _openai_client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user_obj, ensure_ascii=False)}
        ],
        response_format={"type": "json_object"},
        temperature=temperature,  # ✅ Uses the slider value
        timeout=45,
    )
    content = rsp.choices[0].message.content or "{}"
    data = json.loads(content)
    out = dict(ai_payload)
    if isinstance(data, dict):
        for k in ("profile", "work", "education", "achievements"):
            if k in data and data[k] is not None:
                out[k] = data[k]
    return out



# [ADD] --- SVG helpers ---------------------------------------------

def _resolve_path(obj, expr):
    """
    Support dotted paths and simple [index], returns None if any step is missing.
    Example: 'work[0].title'
    """
    cur = obj
    for raw in expr.split('.'):
        part = raw.strip()
        if not part:
            return None
        if '[' in part and part.endswith(']'):
            base, idx = part[:-1].split('[', 1)
            # dict step
            cur = cur.get(base) if isinstance(cur, dict) else None
            if cur is None:
                return None
            # list index
            try:
                i = int(idx)
                cur = cur[i] if isinstance(cur, list) and 0 <= i < len(cur) else None
            except Exception:
                return None
        else:
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur is None:
            return None
    return cur

def _meta_path(theme):
    return os.path.join(BASE_TPL, theme, 'meta.json')

def load_meta(theme):
    p = _meta_path(theme)
    if not os.path.isfile(p):
        raise FileNotFoundError(f"meta.json not found for theme '{theme}'")
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f)

def _set_text(node, val):
    """Write text into <text> or its first <tspan> if present."""
    s = ('' if val is None else str(val)).strip()
    for child in list(node):
        tag = child.tag.rsplit('}', 1)[-1].lower()
        if tag == 'tspan':
            child.text = s
            return
    node.text = s



def _set_image_href(el, data_url):
    # Supports both href and xlink:href
    el.set('{http://www.w3.org/1999/xlink}href', data_url)
    el.set('href', data_url)

def _find_parent(root, child):
    # stdlib ElementTree has no getparent()
    for p in root.iter():
        for c in list(p):
            if c is child:
                return p
    return None

def inject_data_into_svg(svg_src: str, data: dict, page_limit_y: float = 1060.0, incoming_spill=None):
    """
    Render an SVG template with data bindings and repeaters.

    Supported bindings:
      - data-key / data-bind="a|b|c"   -> first non-empty value from data paths.
      - data-repeat="work" (optional data-repeat-alt="experience.jobs")
        * The FIRST child of the repeat container is the prototype row.
        * Repeaters may be nested (e.g., bullets inside each work row).
      - data-y-start, data-y-gap on a repeat container (floats).
      - data-line-h on a repeat container (fallback for row height).
      - data-skill-dots on a group; child nodes use data-dot="1..5".
      - In repeaters, data-key="." binds the current item (string or value).

    Spill/continuation:
      - If a row would extend beyond page_limit_y, remaining items are returned
        in 'spill'. The caller can pass that list back in 'incoming_spill' on
        a follow-up page; if provided, we use it to drive the (first) top-level
        repeater encountered.

    Auto-size & push-down (cards/section containers):
      - For any <g> section that contains a <rect> (the card), we will expand that
        rect's height so that all content in the section fits inside it.
      - Then we stack sections in each column based on:
          data-pad-bottom="N"   bottom padding inside card (default: 12)
          data-gap-after="N"    vertical gap after card before the next section (default: 10)
    """
    import copy, re
    from xml.etree import ElementTree as ET

    # ---------------- XML parse (light sanitizer for stray &)
    def _safe_src(s: str) -> str:
        # Replace bare & that are not entities
        return re.sub(r'&(?!#\d+;|#x[0-9a-fA-F]+;|[A-Za-z][A-Za-z0-9]+;)', '&amp;', s)

    try:
        root = ET.fromstring(_safe_src(svg_src))
    except Exception as e:
        raise RuntimeError(f"SVG parse error: {e}")

    brand   = "#0ea5e9"
    dot_off = "#e5e7eb"

    # ---------------- Helpers
    def _get_path(obj, path):
        """Get value by dot.path from dict/list with support for int indexes."""
        if obj is None:
            return None
        cur = obj
        for seg in path.split('.'):
            if seg == "":
                return None
            if isinstance(cur, (list, tuple)) and seg.isdigit():
                idx = int(seg)
                if 0 <= idx < len(cur):
                    cur = cur[idx]
                else:
                    return None
            elif isinstance(cur, dict):
                if seg in cur:
                    cur = cur.get(seg)
                else:
                    return None
            else:
                return None
        return cur

    def _get_with_fallbacks(ctx, keys, default=None):
        """
        keys may be 'a|b|c' or '.'
        '.' binds the current item directly
        """
        if not keys:
            return default
        ks = keys.strip()
        if ks == ".":
            return ctx if ctx not in (None, "") else default
        for k in [k.strip() for k in ks.split("|")]:
            if not k:
                continue
            v = _get_path(ctx, k)
            if v not in (None, "", []):
                return v
        return default

    def _first_y(node) -> float:
        ys = []
        for el in node.iter():
            y = el.attrib.get("y")
            if y is not None:
                try:
                    ys.append(float(y))
                except Exception:
                    pass
        return min(ys) if ys else 0.0

    def _first_x(node) -> float:
        xs = []
        for el in node.iter():
            x = el.attrib.get("x")
            if x is not None:
                try:
                    xs.append(float(x))
                except Exception:
                    pass
        return min(xs) if xs else 0.0

    def _bbox_bottom(node) -> float:
        ys = []
        for el in node.iter():
            y = el.attrib.get("y")
            if y is not None:
                try:
                    ys.append(float(y))
                except Exception:
                    pass
        return max(ys) if ys else _first_y(node)


    def _translate(node, dy: float, dx: float = 0.0):
        """
        Shift a row by dy (vertical) and dx (horizontal):
        """
        if abs(dy) < 1e-9 and abs(dx) < 1e-9:
            return

        def _shift_transform(tval, dy_inner, dx_inner):
            if not tval or "translate" not in tval:
                return tval
            try:
                before, after = tval.split("translate", 1)
                inside = after.split("(", 1)[1].split(")", 1)[0]
                rest = after.split(")", 1)[1]  
                parts = re.split(r"[,\s]+", inside.strip())
                if len(parts) >= 1:
                    x = float(parts[0]) + dx_inner
                    y = float(parts[1]) + dy_inner if len(parts) >= 2 else dy_inner
                    parts[0] = str(x)
                    if len(parts) >= 2:
                        parts[1] = str(y)
                    else:
                        parts.append(str(y))
                    new_inside = ",".join(parts)
                    return f"{before}translate({new_inside}){rest}"
            except Exception:
                return tval
            return tval

        for el in node.iter():
            if "y" in el.attrib:
                try: el.attrib["y"] = str(float(el.attrib["y"]) + dy)
                except Exception: pass
            if "x" in el.attrib:
                try: el.attrib["x"] = str(float(el.attrib["x"]) + dx)
                except Exception: pass
            if "transform" in el.attrib:
                el.attrib["transform"] = _shift_transform(el.attrib["transform"], dy, dx)


    def _set_text(el, val):
        ns = "{http://www.w3.org/2000/svg}"
        
        # Preserve base attributes from the template's first <tspan>
        first_tspan = el.find(f".//{ns}tspan")
        base_x = first_tspan.get("x") if first_tspan is not None else None
        base_dx = first_tspan.get("dx") if first_tspan is not None else None
        
        # Clear old tspans
        for t in list(el.findall(f".//{ns}tspan")):
            el.remove(t)

        if val is None: val = ""
        if isinstance(val, list):
            val = "\n".join(str(v).strip() for v in val if v is not None and str(v).strip() != "")

        s = str(val)
        lines = s.splitlines() if "\n" in s else [s]
        el.text = ""

        for i, line in enumerate(lines):
            tspan = ET.Element(f"{ns}tspan")
            
            # 🚀 INLINE STYLE PARSER
            is_bold = False
            is_under = False
            
            if "<b>" in line and "</b>" in line:
                is_bold = True
                line = line.replace("<b>", "").replace("</b>", "")
            if "<u>" in line and "</u>" in line:
                is_under = True
                line = line.replace("<u>", "").replace("</u>", "")

            # 🚀 ALIGNMENT PARSER: Check for our secret delimiter
            grade_text = None
            if "|||" in line:
                line, grade_text = line.split("|||", 1)

            tspan.text = line
            
            if is_bold:
                tspan.set("font-weight", "bold")
            if is_under:
                tspan.set("text-decoration", "underline")
            
            target_x = base_x if base_x is not None else el.get("x", "0")
            
            if i == 0:
                if base_x is not None: tspan.set("x", base_x)
                if base_dx is not None: tspan.set("dx", base_dx)
            else:
                tspan.set("dy", "1.05em")
                tspan.set("x", target_x)
                    
            el.append(tspan)

            # 🚀 ALIGNMENT PARSER: Draw the grade right-aligned against the far border!
            if grade_text is not None:
                g_tspan = ET.Element(f"{ns}tspan")
                g_tspan.text = grade_text
                if is_bold: g_tspan.set("font-weight", "bold")
                
                # 🚀 FIX: Anchor the text to the END (Right-Align)
                g_tspan.set("text-anchor", "end") 
                
                try:
                    # Push the invisible right-wall to exactly 400 pixels from the left edge
                    curr_x = float(str(target_x).replace('px', ''))
                    g_tspan.set("x", str(curr_x + 400)) 
                except Exception:
                    g_tspan.set("dx", "150") 
                
                el.append(g_tspan)

    def _skill_filled_0_5(item) -> int:
        # Accept level 0..5, or score 0..1, or parse "name (3/5)"
        lvl = None
        if isinstance(item, dict):
            for k in ("level", "lvl", "rating", "score"):
                if isinstance(item.get(k), (int, float)):
                    lvl = item[k]
                    if k == "score":  # assume 0..1
                        lvl = round(float(lvl) * 5)
                    break
            if lvl is None:
                name = item.get("name") or item.get("title") or ""
                import re as _re
                m = _re.search(r'(\d)\s*/\s*5', str(name))
                if m:
                    lvl = int(m.group(1))
        elif isinstance(item, str):
            import re as _re
            m = _re.search(r'(\d)\s*/\s*5', item)
            if m:
                lvl = int(m.group(1))
        lvl = max(0, min(5, int(lvl))) if isinstance(lvl, (int, float)) else 3
        return lvl

    def _as_list(x):
        """Always return a list for repeaters."""
        if isinstance(x, list):
            return x
        if isinstance(x, tuple):
            return list(x)
        if isinstance(x, dict):
            for k in ("items", "data", "list", "values", "bullets", "points", "highlights"):
                v = x.get(k)
                if isinstance(v, list):
                    return v
            return [x]
        if x in (None, "", []):
            return []
        return [x]

    def _scalar_from_item(item):
        """Return a printable scalar for data-key='.'."""
        if isinstance(item, dict):
            for k in ("description", "text", "title", "name", "label", "value"):
                v = item.get(k)
                if v not in (None, ""):
                    return v
            return ""
        if isinstance(item, (list, tuple)):
            return " ".join(str(x) for x in item if x not in (None, ""))
        return item

    def _to_printable(val):
        if isinstance(val, dict):
            return ""
        if isinstance(val, (list, tuple)):
            return " ".join(str(x) for x in val if x not in (None, ""))
        return val

    # ---------------- First pass: bind simple non-repeater nodes
    for el in list(root.iter()):
        if el.attrib.get("data-repeat"):
            continue
        dk = el.attrib.get("data-key") or el.attrib.get("data-bind")
        if not dk:
            continue
        v = _get_with_fallbacks(data, dk, "")
        tag = el.tag.lower()
        # Images: bind href/xlink:href instead of text
        if tag.endswith("image"):
            val = _to_printable(v)
            if val:
                href = str(val)
                el.set("{http://www.w3.org/1999/xlink}href", href)
                el.set("href", href)
        else:
            _set_text(el, _to_printable(v))

    # ---------------- Nested repeater expansion (used inside a row)
    def _expand_repeats_within(node, ctx):
        local_repeats = [n for n in list(node.iter()) if n.attrib.get("data-repeat")]
        for rep in local_repeats:
            key = rep.attrib.get("data-repeat")
            alt = rep.attrib.get("data-repeat-alt")
            arr = _get_with_fallbacks(ctx, key, [])
            if (not isinstance(arr, (list, tuple))) and alt:
                arr = _get_with_fallbacks(ctx, alt, [])
            arr = _as_list(arr)

            kids = list(rep)
            if not kids:
                continue
            proto = kids[0]
            for ch in kids:
                rep.remove(ch)

            y_start = float(rep.attrib.get("data-y-start", "0"))
            y_gap   = float(rep.attrib.get("data-y-gap", "16"))
            line_h  = float(rep.attrib.get("data-line-h", "14"))
            cursor_y = y_start

            for item in arr:
                row = copy.deepcopy(proto)

                # Fill simple bindings in row
                for sub in row.iter():
                    dk = sub.attrib.get("data-key") or sub.attrib.get("data-bind")
                    if not dk:
                        continue
                    sub_tag = sub.tag.lower()
                    if sub_tag.endswith("image"):
                        if dk.strip() == ".":
                            v = _scalar_from_item(item)
                        else:
                            v = _get_with_fallbacks(item, dk, "")
                        val = _to_printable(v)
                        if val:
                            href = str(val)
                            sub.set("{http://www.w3.org/1999/xlink}href", href)
                            sub.set("href", href)
                    else:
                        if dk.strip() == ".":
                            v = _scalar_from_item(item)
                        else:
                            v = _get_with_fallbacks(item, dk, "")
                        _set_text(sub, _to_printable(v))

                # Skills dots within row
                for sub in row.iter():
                    if sub.attrib.get("data-skill-dots") is not None:
                        filled = _skill_filled_0_5(item)
                        for dot in sub.iter():
                            dnum = dot.attrib.get("data-dot")
                            if not dnum:
                                continue
                            try:
                                i = int(dnum)
                            except Exception:
                                i = 0
                            dot.set("fill", brand if (1 <= i <= filled) else dot_off)

                # Recurse for deeper nested repeaters
                _expand_repeats_within(row, item)

                # Place and advance by actual bottom + gap
                base_y = _first_y(row)
                _translate(row, cursor_y - base_y)
                rep.append(row)

                bottom = _bbox_bottom(row)
                if bottom == base_y:
                    bottom = cursor_y + line_h
                cursor_y = bottom + y_gap

    # ---------------- Top-level repeaters (paginated / spillable)
    spills = {}
    top_reps = [n for n in list(root.iter()) if n.attrib.get("data-repeat")]

    used_incoming_for = False  # consume incoming_spill once

    for rep in top_reps:
        key = rep.attrib.get("data-repeat")
        alt = rep.attrib.get("data-repeat-alt")
        arr = _get_with_fallbacks(data, key, [])
        if (not isinstance(arr, (list, tuple))) and alt:
            arr = _get_with_fallbacks(data, alt, [])

        # If we have incoming_spill, prefer it for the first top-level repeat
        if (incoming_spill and not used_incoming_for):
            arr = incoming_spill
            used_incoming_for = True

        arr = _as_list(arr)

        kids = list(rep)
        if not kids:
            continue
        proto = kids[0]
        for ch in kids:
            rep.remove(ch)

        y_start = float(rep.attrib.get("data-y-start", "0"))
        y_gap   = float(rep.attrib.get("data-y-gap", "16"))
        line_h  = float(rep.attrib.get("data-line-h", "14"))
        
        # ✅ NEW: Read column variables
        cols_count = int(rep.attrib.get("data-cols", "1"))
        col_gap_x  = float(rep.attrib.get("data-col-gap-x", "180")) # Adjust 180 based on how wide you want the columns
        
        cursor_y = y_start

        remaining = []
        overflow = False

        for idx, item in enumerate(arr):
            row = copy.deepcopy(proto)
            col_index = idx % cols_count # Returns 0 for Left, 1 for Right

            # Fill row bindings
            for sub in row.iter():
                dk = sub.attrib.get("data-key") or sub.attrib.get("data-bind")
                if not dk:
                    continue
                sub_tag = sub.tag.lower()
                if sub_tag.endswith("image"):
                    if dk.strip() == ".":
                        v = _scalar_from_item(item)
                    else:
                        v = _get_with_fallbacks(item, dk, "")
                    val = _to_printable(v)
                    if val:
                        href = str(val)
                        sub.set("{http://www.w3.org/1999/xlink}href", href)
                        sub.set("href", href)
                else:
                    if dk.strip() == ".":
                        v = _scalar_from_item(item)
                    else:
                        v = _get_with_fallbacks(item, dk, "")
                    _set_text(sub, _to_printable(v))

            # Skills dots in the row
            for sub in row.iter():
                if sub.attrib.get("data-skill-dots") is not None:
                    filled = _skill_filled_0_5(item)
                    for dot in sub.iter():
                        dnum = dot.attrib.get("data-dot")
                        if not dnum:
                            continue
                        try:
                            i = int(dnum)
                        except Exception:
                            i = 0
                        dot.set("fill", brand if (1 <= i <= filled) else dot_off)

            # Expand nested repeaters (e.g., bullets)
            _expand_repeats_within(row, item)

            # Place and compute bottom
            base_y = _first_y(row)
            
            # ✅ Shift Right if it is in column 2, 3, etc.
            tx = col_index * col_gap_x
            _translate(row, cursor_y - base_y, tx)
            
            row_bottom = _bbox_bottom(row)
            if row_bottom == base_y:
                row_bottom = cursor_y + line_h

            # Check page limit before appending
            if row_bottom > page_limit_y:
                overflow = True
                remaining = arr[idx:]
                break

            rep.append(row)
            
            # ✅ Only push the Y cursor down when the row is FULL (e.g. after the right column is placed)
            if col_index == cols_count - 1 or idx == len(arr) - 1:
                cursor_y = row_bottom + y_gap

        if overflow and remaining:
            spills[key] = remaining

    # ---------------- Auto-size cards so rects fit their content
    def _rects_in_group(g):
        return [ch for ch in list(g) if ch.tag.lower().endswith('rect')]

    sections = []
    for g in root.iter():
        if g.tag.lower().endswith('g'):
            rects = _rects_in_group(g)
            if not rects:
                continue
            r = rects[0]
            ry = r.attrib.get("y")
            rh = r.attrib.get("height")
            if ry is None or rh is None:
                continue
            try:
                ryf = float(ry)
                rhf = float(rh)
            except Exception:
                continue

            content_bottom = 0.0
            for el in g.iter():
                if el is r:
                    continue
                y = el.attrib.get("y")
                if y is not None:
                    try:
                        yy = float(y)
                        if yy > content_bottom:
                            content_bottom = yy
                    except Exception:
                        pass

            sections.append({
                "g": g,
                "rect": r,
                "rect_y": ryf,
                "rect_h": rhf,
                "top_y": _first_y(g),
                "left_x": _first_x(g),
                "content_bottom": content_bottom
            })

    for sec in sections:
        r = sec["rect"]
        rect_y = sec["rect_y"]
        rect_h = sec["rect_h"]

        pad_bottom = float(r.attrib.get("data-pad-bottom", "12"))
        min_h     = float(r.attrib.get("data-min-h", str(rect_h)))

        needed_h = max(min_h, max(0.0, sec["content_bottom"] - rect_y + pad_bottom))
        if needed_h > rect_h + 0.01:
            r.set("height", f"{needed_h}")

    # ---------------- Stack sections in each column for clean vertical gaps
    def _stack_sections(section_ids, start_y=None):
        """
        Stack the given <g id="..."> sections vertically based on their rect height,
        data-pad-bottom, and data-gap-after. Keeps each section's X; recomputes Y.
        """
        ns = "{http://www.w3.org/2000/svg}"

        def _parse_translate(tval):
            if not tval or "translate" not in tval:
                return 0.0, 0.0
            try:
                inside = tval.split("(", 1)[1].split(")", 1)[0]
                parts = [p.strip() for p in inside.replace(" ", "").split(",")]
                if len(parts) == 2:
                    return float(parts[0]), float(parts[1])
            except Exception:
                pass
            return 0.0, 0.0

        # Collect groups + rects
        groups = []
        for sec_id in section_ids:
            g = root.find(f".//{ns}g[@id='{sec_id}']")
            if g is None:
                continue
            rect = g.find(f"{ns}rect")
            if rect is None:
                continue
            groups.append((g, rect))

        if not groups:
            return

        # Determine initial Y from the first group's current transform if not given
        first_g, _ = groups[0]
        tx0, ty0 = _parse_translate(first_g.get("transform"))
        if start_y is None:
            current_y = ty0
        else:
            current_y = float(start_y)

        # Preserve each group's X (from its own transform) where possible
        for g, rect in groups:
            tx, ty = _parse_translate(g.get("transform"))
            x = tx

            rect_h = float(rect.get("height", "0"))
            pad_bottom = float(rect.get("data-pad-bottom", "12"))
            gap_after = float(rect.get("data-gap-after", "10"))

            g.set("transform", f"translate({x},{current_y})")

            # Advance: card height + padding inside + external gap
            current_y += rect_h + pad_bottom + gap_after

    # Right column stack (page 1 + page 2)
    _stack_sections(
        [
            "profile", "experience", "education",  # page 1
            "certs-card", "secondary",                                      # page 2
        ],
        start_y=None
    )

    # Left column stack for page 1
    _stack_sections(["contact-card", "skills-card", "pubs-card"], start_y=None)

    # --- Special handling: extras above referees on left ribbon of page 2
    try:
        ns = "{http://www.w3.org/2000/svg}"

        def _parse_translate_xy(tval):
            if not tval or "translate" not in tval:
                return 0.0, 0.0
            try:
                inside = tval.split("(", 1)[1].split(")", 1)[0]
                parts = [p.strip() for p in inside.replace(" ", "").split(",")]
                if len(parts) == 2:
                    return float(parts[0]), float(parts[1])
            except Exception:
                pass
            return 0.0, 0.0

        extras_g = root.find(f".//{ns}g[@id='extras-list']")
        refs_g   = root.find(f".//{ns}g[@id='referees']")

        if extras_g is not None:
            ex_tx, ex_ty = _parse_translate_xy(extras_g.get("transform"))
            base_y = 0.0
            if refs_g is not None:
                _, base_y = _parse_translate_xy(refs_g.get("transform"))
            extras_g.set("transform", f"translate({ex_tx},{base_y})")

            extra_top_local    = _first_y(extras_g)
            extra_bottom_local = _bbox_bottom(extras_g)
            extra_height       = max(0.0, extra_bottom_local - extra_top_local)

            card_rect = extras_g.find(f".//{ns}rect")
            if card_rect is not None:
                try:
                    pad_bottom = float(card_rect.get("data-pad-bottom", "12") or 0)
                except Exception:
                    pad_bottom = 12.0
                try:
                    gap_after = float(card_rect.get("data-gap-after", "10") or 0)
                except Exception:
                    gap_after = 10.0
            else:
                pad_bottom = 12.0
                gap_after = 10.0

            next_y = base_y + extra_height + pad_bottom + gap_after

            custom_gap = 75  # visual gap between extras and referees
            next_y += custom_gap

            if refs_g is not None:
                r_tx, r_ty = _parse_translate_xy(refs_g.get("transform"))
                refs_g.set("transform", f"translate({r_tx},{next_y})")
    except Exception:
        # Never break SVG generation due to layout refinement issues
        pass

    # ---------------- Return SVG + spill
    svg_bytes = ET.tostring(root, encoding="utf-8")
    svg_out = svg_bytes.decode("utf-8")

    merged_spill = []
    for _, v in spills.items():
        merged_spill.extend(v)

    return {"svg": svg_out, "spill": merged_spill}





    
def _merge_ai_back(struct: Dict[str, Any], ai_result: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(struct)
    
    if "profile" in ai_result and ai_result["profile"]:
        merged["profile"] = ai_result["profile"]
        
    if "achievements" in ai_result and ai_result["achievements"]:
        merged["achievements"] = ai_result["achievements"]

    # 🚀 SMART MERGE FOR WORK: Protects layout keys while applying AI text!
    if "work" in ai_result and isinstance(ai_result["work"], list):
        orig_work = merged.get("work", [])
        ai_work = ai_result["work"]
        for i in range(min(len(orig_work), len(ai_work))):
            if "bullets" in ai_work[i]:
                orig_work[i]["bullets"] = ai_work[i]["bullets"]
            if "title" in ai_work[i]:
                orig_work[i]["title"] = ai_work[i]["title"]
            if "company" in ai_work[i]:
                orig_work[i]["company"] = ai_work[i]["company"]
        merged["work"] = orig_work

    # 🚀 SMART MERGE FOR EDUCATION: Prevents AI from erasing 'university' and 'degree_and_type'!
    if "education" in ai_result and isinstance(ai_result["education"], list):
        orig_edu = merged.get("education", [])
        ai_edu = ai_result["education"]
        for i in range(min(len(orig_edu), len(ai_edu))):
            # AI often renames "research" to "bullets" or "description", this catches all of them safely
            new_research = ai_edu[i].get("research") or ai_edu[i].get("bullets") or ai_edu[i].get("description")
            if new_research is not None:
                orig_edu[i]["research"] = new_research
        merged["education"] = orig_edu

    return merged



def _markdown_from_struct(d: Dict[str, Any]) -> str:
    out: List[str] = []
    c = d.get("contact", {})
    name = c.get("full_name") or "Your Name"
    title = c.get("current_title") or ""
    line = c.get("contact_line") or ""
    out.append(f"# {name}")
    if title: out.append(f"*{title}*  ")
    if line: out.append(line)
    out.append("")
    if d.get("profile"):
        out.append("## Profile"); out.append(d["profile"]); out.append("")
# ---------- Work Experience ----------
    work = _normalize_work(d.get("work"))

    # extra debug so we can see what the renderer sees
    print("DEBUG RENDER WORK COUNT:", len(work))
    if work:
        out.append("## Work Experience")
        for idx, w in enumerate(work, 1):
            title   = (w.get("title") or "").strip()
            company = (w.get("company") or "").strip()
            period  = " – ".join([x for x in [(w.get("from") or "").strip(), (w.get("to") or "").strip()] if x])

            header_bits = [b for b in [title, company] if b]
            if header_bits:
                out.append("### " + " — ".join(header_bits))
            if period:
                out.append(f"- {period}  ")

            for b in _to_str_list(w.get("bullets")):
                out.append(f"- {b}  ")

            out.append("")


    skills_md = _format_skills_markdown(d)
    if skills_md.strip():
        out.append("## Skills")
        out.append(skills_md)
        out.append("")

        
    # ---------- Education (University) ----------
    has_uni   = bool(d.get("education"))
    certs     = d.get("certifications") or []

    # Secondary education data
    secondary = d.get("secondary") or {}
    schools   = secondary.get("schools") or []
    ol_list   = secondary.get("ol") or []
    al_list   = secondary.get("al") or []
    has_sec   = bool(schools or ol_list or al_list)

    # Decide: if NO university education, fold certs + secondary INTO ## Education
    # If there IS university education, keep certs and secondary as separate sections
    has_any_edu = has_uni or certs or has_sec

    def _write_certs(out, certs):
        """Write certification entries (no heading — caller adds heading)."""
        for c in certs:
            head_bits = [x for x in [(c.get("name") or "").strip(), (c.get("issuer") or "").strip()] if x]
            if head_bits:
                out.append("**" + " — ".join(head_bits) + "**")
            meta = []
            if c.get("issue"):         meta.append("Issued: " + c["issue"])
            if c.get("expiry"):        meta.append("Expires: " + c["expiry"])
            if c.get("credential_id"): meta.append("ID: " + c["credential_id"])
            if meta:
                out.append("- " + " • ".join(meta))
            if c.get("url"):
                out.append("- " + c["url"])
            for ln in (c.get("description") or "").splitlines():
                ln = ln.strip()
                if ln:
                    out.append(ln if ln.startswith(("-", "•")) else f"- {ln}")
            out.append("")

    def _write_secondary(out, schools, al_list, ol_list):
        """Write secondary school entries (no heading — caller adds heading).
        Grades use ||| separator so the SVG engine right-aligns them correctly."""
        for s in schools:
            name   = (s.get("name") or "").strip()
            period = (s.get("period") or "").strip()
            if not (name or period):
                continue
            line = f"**{name}**"
            if period:
                line += f"  \n- {period}"
            out.append(line)
            out.append("")

        if al_list:
            out.append("")
            out.append("<u>ADVANCED LEVEL RESULTS:</u>")
            for subj in al_list:
                sname = (subj.get("subject") or "").strip()
                grade = (subj.get("grade") or "").strip()
                if not (sname or grade):
                    continue
                # ||| delimiter → SVG engine renders grade right-aligned
                out.append(f"{sname}|||{grade}" if grade else sname)
            out.append("")

        if ol_list:
            out.append("")
            out.append("<u>ORDINARY LEVEL RESULTS:</u>")
            for subj in ol_list:
                sname = (subj.get("subject") or "").strip()
                grade = (subj.get("grade") or "").strip()
                if not (sname or grade):
                    continue
                out.append(f"{sname}|||{grade}" if grade else sname)
            out.append("")

    if has_any_edu:
        out.append("## Education")

        # University entries always go first
        for e in (d.get("education") or []):
            deg = e.get("degree_and_type") or e.get("degree_name") or ""
            uni = e.get("university") or ""
            head = f"**{deg}**" + (f"  \n**{uni}**" if uni else "")
            out.append(head)
            bits = []
            if e.get("period"): bits.append(e["period"])
            if e.get("grade"):  bits.append(f"Grade: {e['grade']}")
            if e.get("gpa"):    bits.append(f"GPA: {e['gpa']}")
            if bits: out.append("- " + " • ".join(bits) + "  ")
            if e.get("thesis"): out.append(f"- Thesis: {e['thesis']}")
            for r in _lines(e.get("research", "")): out.append(f"- {r}")
            out.append("")

        if not has_uni:
            # No university data → merge certs + secondary under ## Education
            if certs:
                _write_certs(out, certs)
            if has_sec:
                _write_secondary(out, schools, al_list, ol_list)

    if d.get("achievements"):
        out.append("## Achievements")
        for a in d.get("achievements", []): out.append(f"- {a}")
        out.append("")

    # Certifications as own section only when university education exists
    if certs and has_uni:
        out.append("## Certifications")
        _write_certs(out, certs)
            
    # ==== Publications (Markdown) ====
# ==== Publications (Markdown) ====
    if d.get("publications"):
        out.append("## Publications")
        for p in d["publications"]:
            title   = (p.get("title") or "").strip()
            authors = (p.get("authors") or "").strip()
            month   = (p.get("month") or "").strip()
            year    = (p.get("year") or "").strip()
            venue   = (p.get("venue") or "").strip()
            link    = (p.get("link") or "").strip()
            desc    = (p.get("description") or "")

            # Combine month and year
            date_str = " ".join(x for x in [month, year] if x)

            head = []
            if title: head.append(f"**{title}**")
            meta_bits = []
            if date_str: meta_bits.append(f"({date_str})")
            if authors:  meta_bits.append(f"— {authors}")
            if meta_bits and head:
                head[-1] = f"{head[-1]} {' '.join(meta_bits)}"
            out.append(" ".join(head) if head else "")

            if venue:
                out.append(f"*{venue}*")
            if link:
                out.append(f"[Link]({link})")
            for ln in _lines(desc):
                out.append(f"- {ln}")
            out.append("")

       
    

    if d.get("sports"):
        out.append("## Sports & Extracurriculars")
        for s in d.get("sports", []):
            out.append(f"- {s}")
        out.append("")


    # ---------- Additional ----------
    # ---------- Extra Sections ----------
    extras = d.get("extras") or []
    if extras:
        out.append("## Additional")
        for ex in extras:
            mode = (((d.get("extrasOptions") or {}).get("titleCase")) or "none").strip().lower()
            raw  = (ex.get("name") or "").strip().replace("_", " ")

            if mode == "upper":
                title = raw.upper()
            elif mode == "title":
                title = raw.title()
            else:
                title = raw

            desc  = (ex.get("description") or "").strip()

            if title:
                out.append(f"**{title}**")
            if desc:
                for line in _lines(desc):
                    out.append(f"- {line}")
            out.append("")


    # Secondary Education as own section only when university education exists
    if has_sec and has_uni:
        out.append("## Secondary Education")
        _write_secondary(out, schools, al_list, ol_list)



    



    # ---------- Referees ----------
        
    if d.get("referees"):
        out.append("## Referees")
        for r in d.get("referees"):
            nm = r.get("name") or ""; pos = r.get("position") or ""
            em = (r.get("email") or "").strip()
            mb = (r.get("mobile") or r.get("phone") or r.get("tel") or "").strip()
            
            # Print each item on a new line (the two spaces at the end ensure Markdown line breaks)
            if nm: out.append(f"**{nm}** ")
            if pos: out.append(f"{pos}  ")
            if em: out.append(f"Email: {em}  ")
            if mb: out.append(f"Mobile: {mb}  ")
            
            out.append("") # Adds a blank line between multiple referees
    return "\n".join(out).strip() + "\n"

# =============================================================================
# Routes
# =============================================================================




@app.get("/studio/<eid>")
def studio(eid):
    import os
    from flask import json as _json

    # 1. Load the original SVG icons (for your existing Icon Panel)
    old_svg_folder = os.path.join(BASE_DIR, 'templates', 'resumes', 'SVG')
    available_svgs = []
    if os.path.exists(old_svg_folder):
        for filename in os.listdir(old_svg_folder):
            if filename.lower().endswith('.svg'):
                available_svgs.append(f"/templates/SVG/{filename}")

    # 2. Load the New SVG Shapes (for your new Shape Menu)
    shape_folder = os.path.join(BASE_DIR, 'templates', 'resumes', 'SVG SHAPES')
    svg_list = []
    if os.path.exists(shape_folder):
        svg_list = [f for f in os.listdir(shape_folder) if f.endswith('.svg')]

    # 3. Send BOTH lists safely to studio.html
    return render_template("studio.html", 
                         eid=eid, 
                         eid_json=_json.dumps(eid), 
                         available_svgs=available_svgs,
                         svg_list=svg_list)


@app.route("/")
def home():
    return render_template("index.html")

# 🚀 NEW: Dedicated routes for your Legal documents
@app.route("/terms")
def terms():
    return render_template("terms.html")

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/form")
def form_page():
    templates = list_resume_templates()
    initial = templates[0] if templates else {"slug": "", "name": "—"}
    return render_template("form.html", initial_template=initial)


@app.route("/templates")
def templates_list():
    return jsonify(list_resume_templates())

@app.route("/template_preview/<slug>")
def template_preview(slug):
    sub = find_template_dir(slug)
    if not sub: abort(404)
    exts = {".png",".jpg",".jpeg",".webp",".gif"}
    cand = None
    for p in sub.iterdir():
        if p.is_file() and p.suffix.lower() in exts and p.stem.lower() in {"preview","thumbnail","thumb"}:
            cand = p; break
    if not cand:
        for p in sorted(sub.iterdir()):
            if p.is_file() and p.suffix.lower() in exts:
                cand = p; break
    if cand:
        ext = cand.suffix.lower()
        mt = "image/png" if ext == ".png" else ("image/webp" if ext == ".webp" else "image/jpeg")
        return send_file(cand, mimetype=mt)
    placeholder = STATIC_DIR / "pngwing.png"
    if placeholder.exists():
        return send_file(placeholder, mimetype="image/png")
    from io import BytesIO
    BLANK = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=")
    return send_file(BytesIO(BLANK), mimetype="image/png")

@app.route("/templates/<path:filename>")
def serve_template_assets(filename):
    for root in _template_roots():
        target = root / filename
        if target.exists() and target.is_file():
            try:
                target.resolve().relative_to(root.resolve())
            except Exception:
                continue
            return send_file(str(target))
    abort(404)




# [ADD] --- Route: generate SVG pages as JSON ------------------------

# --- Route: generate SVG pages as JSON (safe for raw form OR structured data) ---
@app.post("/generate_resume_svg")
def generate_resume_svg():
    import os, json, traceback

    body = request.get_json(force=True) or {}
    theme = (body.get("theme") or "").strip()
    data  = body.get("data") or {}

    # Normalize raw form payload to the SVG schema if needed
    def _looks_structured(d):
        return (
            isinstance(d, dict) and (
                isinstance(d.get("contact"), dict)
                or isinstance(d.get("work"), list)
                or isinstance(d.get("education"), list)
            )
        )

    try:
        if not _looks_structured(data):

            # falls back to your existing helper that builds the correct schema
            data = _structure_from_form(data)
    except Exception:
        # Never fail just because structuring hit a partial/edge case
        pass

    try:
        _wrap_all_text_sections(data, max_len=90)
    except Exception:
        pass 

    # -------------------------------------------------------------------------
    # Apply layout-driven extras title casing (extras_block.options.extrasTitleCase)
    # -------------------------------------------------------------------------
    try:
        layout_path = os.path.join("templates", "resumes", theme, "layout.json")
        extras_case = ""

        if os.path.isfile(layout_path):
            with open(layout_path, "r", encoding="utf-8") as f:
                layout = json.load(f)

            # layout can be {pages:[{elements:[...]}]} in your project
            for pg in (layout.get("pages") or []):
                for el in (pg.get("elements") or []):
                    if el.get("id") == "extras_block":
                        extras_case = ((el.get("options") or {}).get("extrasTitleCase") or "").strip().lower()
                        break
                if extras_case:
                    break

        if extras_case:
            if not isinstance(data.get("extrasOptions"), dict):
                data["extrasOptions"] = {}
            # supported: upper/title/lower/none
            data["extrasOptions"]["titleCase"] = extras_case

    except Exception:
        pass





    theme_dir = os.path.join("templates", "resumes", theme)
    meta_path = os.path.join(theme_dir, "meta.json")
    if not os.path.exists(meta_path):
        return jsonify(ok=False, error=f"meta.json not found for theme '{theme}'"), 400

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception as e:
        return jsonify(ok=False, error=f"meta.json parse error: {e}"), 400

    pages_cfg = (meta.get("svg") or {}).get("pages") or []
    if not pages_cfg:
        return jsonify(ok=False, error="No SVG pages listed in meta.json"), 400

    out_pages, spill = [], []
    svg_src_for_continuations = None

    for idx, fname in enumerate(pages_cfg):
        svg_path = os.path.join(theme_dir, fname)
        if not os.path.exists(svg_path):
            return jsonify(ok=False, error=f"SVG not found: {svg_path}"), 400

        try:
            with open(svg_path, "r", encoding="utf-8") as sf:
                svg_src = sf.read()
            svg_src_for_continuations = svg_src  # keep last successfully loaded page as base
            out = inject_data_into_svg(svg_src, data, page_limit_y=1060.0, incoming_spill=spill)
        except Exception as err:
            # Best-effort friendly error including line/col snippet if it's an XML parse issue
            try:
                # Try to extract a line/col from the error text (if provided by the parser)
                err_s = str(err)
                line = col = None
                m = re.search(r'line (\d+), column (\d+)', err_s)
                if m:
                    line, col = int(m.group(1)), int(m.group(2))
                snippet = ""
                if line:
                    with open(svg_path, "r", encoding="utf-8") as sf:
                        lines = sf.readlines()
                    lo = max(1, line - 2)
                    hi = min(len(lines), line + 2)
                    numbered = [f"{i:>5}: {lines[i-1].rstrip()}" for i in range(lo, hi+1)]
                    pointer = f"\n{' ' * 7}{' ' * (col-1)}^" if col and 1 <= col <= 200 else ""
                    snippet = "\n".join(numbered) + pointer
                tips = (
                    "Tip: ensure root <svg> has xmlns='http://www.w3.org/2000/svg'; "
                    "escape raw '&' as '&amp;'; avoid '--' inside comments; "
                    "add xmlns:xlink if you use xlink:href."
                )
                return jsonify(
                    ok=False,
                    error=f"SVG parse/inject failed in '{fname}': {err}\n{snippet}\n{tips}"
                ), 400
            except Exception:
                return jsonify(ok=False, error=f"SVG parse/inject failed in '{fname}': {err}"), 400

        out_pages.append(out["svg"])
        spill = out["spill"]

        # If we still have spill on the last configured page, generate continuation pages
        if idx == len(pages_cfg) - 1 and spill:
            safety = 8  # prevent infinite growth
            # Use the last page's svg as the continuation skeleton
            cont_src = svg_src_for_continuations or svg_src
            while spill and safety > 0:
                try:
                    out = inject_data_into_svg(cont_src, data, page_limit_y=1060.0, incoming_spill=spill)
                except Exception as e:
                    return jsonify(ok=False, error=f"Continuation page failed in '{fname}': {e}"), 400
                out_pages.append(out["svg"])
                spill = out["spill"]
                safety -= 1

    return jsonify(ok=True, pages=out_pages)







# [ADD] --- Route: preview page (simple shell that calls the above) --
# --- Route: preview page (shell that immediately calls the JSON route) ---
@app.post('/preview_svg')
def preview_svg():
    body  = request.get_json(silent=True) or request.form
    theme = body.get('theme') or body.get('template') or ''

    raw = body.get('data') or {}
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
    else:
        data = raw
    if isinstance(data, dict):
        print("[EXTRAS-DBG] incoming keys:", list(data.keys())[:20])
        print("[EXTRAS-DBG] incoming extrasOptions:", data.get("extrasOptions"))
    else:
        print("[EXTRAS-DBG] incoming data type:", type(data), "value:", str(data)[:200])

    # Normalize here as well (helps client-side devtools/inspection)
    def _looks_structured(d):
        return (
            isinstance(d, dict) and (
                isinstance(d.get("contact"), dict)
                or isinstance(d.get("work"), list)
                or isinstance(d.get("education"), list)
            )
        )
    # --- NEW: default extras title casing from layout.json (if not provided by input) ---
    try:
        layout_path = os.path.join("templates", "resumes", theme, "layout.json")
        if os.path.isfile(layout_path):
            with open(layout_path, "r", encoding="utf-8") as f:
                layout = json.load(f)

            extras_case = None
            for pg in (layout.get("pages") or []):
                for el in (pg.get("elements") or []):
                    if el.get("id") == "extras_block":
                        extras_case = ((el.get("options") or {}).get("extrasTitleCase") or "").strip()
                        break
                if extras_case:
                    break

            if extras_case:
                if not isinstance(data.get("extrasOptions"), dict):
                    data["extrasOptions"] = {}
                data["extrasOptions"]["titleCase"] = extras_case
                print("[EXTRAS-DBG] layout extrasTitleCase:", extras_case)
                print("[EXTRAS-DBG] after layout override extrasOptions:", data.get("extrasOptions"))


    except Exception:
        pass

    # Normalize raw form payload to the SVG schema if needed
    try:
        if not _looks_structured(data):
            data = _structure_from_form(data)
            print("[EXTRAS-DBG] after _structure_from_form extrasOptions:", data.get("extrasOptions"))

    except Exception:
        pass


    return render_template('preview_svg.html', theme=theme, data=data)





# =============================================================================
# AI generation (single slider → tier & verbosity; global skill logic)
# =============================================================================
@app.post("/generate_resume")
def generate_resume():
    try:
        data = request.get_json(force=True, silent=False) or {}
    except Exception as e:
        traceback.print_exc()
        return jsonify(ok=False, error="AI_REQUIRED", message=str(e)), 503

    compact = _compact(data); compact.pop("photo", None)

    # -------------------------------------------------------------------------
    # 🚀 CLOUDFLARE TURNSTILE VERIFICATION
    # -------------------------------------------------------------------------
    cf_token = compact.get("cfToken")
    cf_secret = os.getenv("MY_SECRET_KEY") # <--- Grabs your hidden .env key
    
    if not cf_token:
        return jsonify(ok=False, error="SECURITY_FAILED", message="Missing CAPTCHA token."), 400
        
    try:
        cf_response = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": cf_secret, "response": cf_token},
            timeout=10
        )
        cf_result = cf_response.json()
        
        if not cf_result.get("success"):
            print(f"🕵️ Turnstile Blocked Request! Reason: {cf_result.get('error-codes')}")
            return jsonify(ok=False, error="SECURITY_FAILED", message="CAPTCHA verification failed. Are you a bot?"), 403
            
    except requests.exceptions.RequestException as e:
        print("🕵️ Turnstile API Error:", e)
        return jsonify(ok=False, error="SECURITY_FAILED", message="Security servers are currently down. Please try again later."), 503

    # 1. READ INPUTS
    creativity_val = int(compact.get("creativity") or 50)  # 0..100 (Truth/Creativity)
    detail_val     = int(compact.get("detailLevel") or 50) # 0..100 (Length/Detail)

    # 2. SEPARATE LOGIC MAPPING (0-100 -> 0-4)
    def _map_5_tier(v):
        if v <= 20: return 0
        if v <= 40: return 1
        if v <= 60: return 2
        if v <= 80: return 3
        return 4

    # KEY CHANGE: Two separate tiers
    length_tier = _map_5_tier(detail_val)       # Controls Word Count
    creative_tier = _map_5_tier(creativity_val) # Controls Rules/Hallucinations

    # Verbosity (Number of bullets) still follows Detail Level
    verbosity = 0 if detail_val < 30 else (1 if detail_val < 70 else 2)
    tone_crisp = bool(compact.get("tone_crisp"))

    # Calculate Temperature based on CREATIVITY slider only
# ✅ INCREASE RANGE: 0% = 0.2 (Cold/Strict), 100% = 1.2 (Creative/Hot)
    ai_temp = 0.2 + (creativity_val / 100.0) * 1.0

    # Front-end toggles (safe defaults)
    content_mode = (compact.get("contentMode") or compact.get("content_mode") or "ai").strip().lower()
    resume_target = (compact.get("resumeTarget") or compact.get("resume_target") or "general").strip().lower()
    ai_enabled = content_mode in ("ai", "enhanced", "ai_enhanced", "ai-enhanced", "aienhanced")
    job_specific = resume_target in ("job", "job_specific", "job-specific", "specific")


    job_title = (compact.get("jobTitle") or "").strip()
    job_desc  = (compact.get("jobDescription") or "").strip()

    # whyFit can come as whyFit (frontend) or why_fit (older JSON)
    why_fit = (compact.get("whyFit") or compact.get("why_fit") or "").strip()

    if ai_enabled and job_specific:
        why_fit = (compact.get("whyFit") or compact.get("why_fit") or "").strip()

    why_fit   = (compact.get("whyFit") or "") if (ai_enabled and job_specific) else ""

    # Lightweight keyword extraction for job-specific targeting only
    _STOP = {
        "the","and","for","with","to","of","in","on","a","an","at","is","are","as","or","be",
        "this","that","these","those","we","you","your","our","will","would","should","can","may",
        "responsibilities","responsibility","requirements","required","preferred","include","including",
        "ability","skills","experience","knowledge","strong","basic","solid","plus","work","working"
    }
    _kw_tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9+/#-]{2,}", f"{job_title} {job_desc}".lower())
    jd_keywords = []
    for t in _kw_tokens:
        if t in _STOP:
            continue
        if t not in jd_keywords:
            jd_keywords.append(t)
        if len(jd_keywords) >= 14:
            break




    base_skills_text = compact.get("skills") or ""
    skills_len = len(_skills_from_csv(base_skills_text))

# ... inside generate_resume ...

    def _should_quantify() -> bool:
        jt = f"{job_title} {job_desc}".lower()
        # FIX: Use 'creativity_val' instead of 'creativity'
        return creativity_val >= 65 or bool(re.search(r"(\d|percent|%|\bk\b|\bm\b|roi|revenue|conversion|increased|reduced)", jt))

    def _should_enforce() -> bool:
        # FIX: Use 'creativity_val' instead of 'creativity'
        return bool(job_title.strip()) or skills_len > 12 or creativity_val >= 60

    tone_quant  = _should_quantify()
    enforce     = _should_enforce()

    base_struct = _structure_from_form(data)
    base_struct["work"] = _normalize_work(base_struct.get("work"))
    # If user provided no work entries, seed one so AI can fill bullets
    if not base_struct.get("work") and job_title:
        base_struct["work"] = [{
            "title": job_title,
            "company": "",
            "from": "",
            "to": "",
            "bullets": []
        }]

    # Always rewrite profile using the new module (all tiers, incl. tier 0)
    # Always rewrite profile first
    # AI Enhanced mode: rewrite sections before struct enhancement
    # AI Enhanced mode: rewrite sections before struct enhancement
# AI Enhanced mode: rewrite sections before struct enhancement
    if ai_enabled:
        # Profile Rewrite
        rewritten_profile = _profile_rw.rewrite(
            data, base_struct, 
            length_tier=length_tier,     
            creative_tier=creative_tier, 
            tone_crisp=tone_crisp, 
            tone_quantify=tone_quant, 
            temperature=ai_temp,
            job_description=job_desc if job_specific else "",  # <--- NEW: Passes the Job Description
            why_fit=why_fit                                    # <--- NEW: Passes "Why you fit"
        )
        if rewritten_profile:
            base_struct["profile"] = rewritten_profile

        # Work Rewrite
        for w in base_struct.get("work", []):
            args = {
                "bullets": w.get("bullets", []),
                "length_tier": length_tier,     # <--- NEW
                "creative_tier": creative_tier, # <--- NEW
                "title": w.get("title",""),
                "company": w.get("company",""),
                "temperature": ai_temp
            }
            if job_specific:
                args.update({
                    "target_role": job_title,
                    "job_description": job_desc,
                    "why_fit": why_fit,
                    "jd_keywords": jd_keywords
                })
            w["bullets"] = _work_rw.rewrite(**args)

        # Education Rewrite
        if job_specific:
            for e in (base_struct.get("education") or []):
                for k in ("research", "thesis", "details", "notes"):
                    if isinstance(e.get(k), str) and e.get(k).strip():
                        e[k] = _edu_rw.rewrite_text(
                            e[k],
                            length_tier=length_tier,     # <--- NEW
                            creative_tier=creative_tier, # <--- NEW
                            target_role=job_title,
                            job_description=job_desc,
                            why_fit=why_fit,
                            jd_keywords=jd_keywords,
                            temperature=ai_temp
                        )

        # Extras Rewrite
        extras_args = {
            "length_tier": length_tier,
            "creative_tier": creative_tier,
            "temperature": ai_temp
        }
        
        # Inject the Job targeting context if the user requested it!
        if job_specific:
            extras_args.update({
                "target_role": job_title,
                "job_description": job_desc,
                "why_fit": why_fit,
                "jd_keywords": jd_keywords
            })

        if base_struct.get("achievements"):
            base_struct["achievements"] = _extras_rw.rewrite(
                base_struct["achievements"], **extras_args
            )
            
        if base_struct.get("sports"):
            base_struct["sports"] = _extras_rw.rewrite(
                base_struct["sports"], **extras_args
            )
        
        if base_struct.get("extras"):
            combined_inputs = []
            for e in base_struct["extras"]:
                name = e.get("name", "").strip()
                desc = e.get("description", "").strip()
                combined_inputs.append(f"{name}: {desc}" if name else desc)

            valid_indices = [i for i, d in enumerate(combined_inputs) if d.strip()]
            valid_items = [combined_inputs[i] for i in valid_indices]

            if valid_items:
                rewritten_items = _extras_rw.rewrite(valid_items, **extras_args)
                
                for idx, new_text in zip(valid_indices, rewritten_items):
                    # ✅ NEW FIX: Check if the AI echoed the category name back, and strip it!
                    cat_name = base_struct["extras"][idx].get("name", "").strip()
                    if cat_name and new_text.lower().startswith(f"{cat_name.lower()}:"):
                        new_text = new_text[len(cat_name) + 1:].strip()
                        
                    base_struct["extras"][idx]["description"] = new_text


# Normalize lists first
    base_struct["sports"] = _to_str_list(base_struct.get("sports"))
    base_struct["achievements"] = _to_str_list(base_struct.get("achievements"))

        

    # Proceed with structured enhancement (bullets, achievements, sports, skills)
    struct = _enhance_struct(
        base_struct, length_tier, verbosity, # Use length_tier instead of 'tier' (which is undefined now too)
        enforce, job_title, job_desc,
        tone_crisp, tone_quant, creativity_val # <--- FIX: Use 'creativity_val'
    )



    

    # OpenAI polish — MANDATORY for profile/work/education/achievements
    try:
        ai_payload = _pick_ai_payload(struct)
        # Provide context to OpenAI so it knows whether to target a JD or stay general
        ai_payload["_context"] = {
            "job_specific": bool(job_specific),
            "target_role": (job_title if job_specific else ""),
            "job_description": (job_desc if job_specific else ""),
            "why_fit": (why_fit if job_specific else ""),
            "jd_keywords": (jd_keywords if job_specific else []),

            # General mode hint
            "general_resume": bool(ai_enabled and (not job_specific)),
        }


        ai_result  = _call_openai_sections(ai_payload, tier=creative_tier, verbosity=verbosity, temperature=ai_temp)
        struct     = _merge_ai_back(struct, ai_result)
    except Exception as e:
        traceback.print_exc()
        return jsonify(ok=False, error="AI_REQUIRED", message=str(e)), 503

    # C) normalize work after AI
    struct["work"] = _normalize_work(struct.get("work"))
    for w in struct["work"]:
        f = (w.get("from") or "").strip()
        t = (w.get("to") or "").strip()
        w["period"] = (f + (" – " + t if (f and t) else "")) if (f or t) else ""


    # D) optional debug (you can remove later)
    print("DEBUG WORK AFTER AI:", struct.get("work"))

    # build markdown
    md = _markdown_from_struct(struct)

    mode = "negligible" if length_tier == 0 else ("moderate" if length_tier <= 2 else "greatest")
    return jsonify(ok=True, structured=struct, markdown=md, mode=mode)







# =============================================================================
# Preview (Skills are passed to template)
# =============================================================================

@app.post("/preview_template")
def preview_template():
    try:
        payload = request.get_json(force=True, silent=False) or {}
    except Exception:
        return make_response("Invalid JSON", 400)

    slug = (payload.get("template") or "").strip()
    if not slug:
        form = payload.get("form") or {}
        slug = (form.get("template") or form.get("template_slug") or "").strip()
    if not slug:
        return make_response("Missing template", 400)

    form = (payload.get("form") or {})
    ai_struct = payload.get("structured") or payload.get("ai_structured") or {}

    # Use the new 5-tier mapping helper
    def _map_v2(v):
        if v <= 20: return 0
        if v <= 40: return 1
        if v <= 60: return 2
        if v <= 80: return 3
        return 4

    detail_val = int(form.get("detailLevel") or 50)
    length_tier = _map_v2(detail_val)
    tier = length_tier # Keep variable name 'tier' so the rest of the preview function works

    # Prefer AI-structured preview when available (any tier).
    if ai_struct:
        structured = ai_struct
    elif tier == 0:
        # Tier 0 can preview from raw form without "Generate"
        structured = _structure_from_form(form)
    else:
        # Tier 1/2 require "Generate" first so preview matches export.
        msg = """<!doctype html><html><head><meta charset="utf-8"/>
<style>body{font-family:Arial;padding:24px;background:#f9fafb}</style></head>
<body>
<h2>Preview needs generated content</h2>
<p>Please click <b>Generate</b> first. Moderate/Greatest preview displays the generated output only.</p>
</body></html>"""
        return make_response(msg, 200)


    # Ensure contact title + photo passthrough
    structured["contact"] = structured.get("contact") or {}
    if not structured["contact"].get("current_title"):
        structured["contact"]["current_title"] = _derive_current_title(structured.get("work") or [])
    photo_dataurl = (form.get("photo") or "").strip()
    if photo_dataurl.startswith("data:image/"):
        structured["contact"]["photo"] = photo_dataurl

    try:
        html = _render_template(slug, structured)
    except FileNotFoundError:
        return make_response(f"Template '{slug}' not found", 404)
    except Exception as e:
        err = f"""<!doctype html><html><body style="font-family:Arial;padding:24px">
        <h3>Render error</h3><pre style="white-space:pre-wrap">{str(e)}</pre></body></html>"""
        return make_response(err, 200)

    eid = secrets.token_urlsafe(16)
    _save_to_disk(eid, {"ts": time.time(), "slug": slug, "structured": structured, "html": html})

    shell = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Preview — {slug}</title>
<style>
  html,body{{height:100%;margin:0;background:#f3f4f6;}}
  header{{position:sticky;top:0;background:#fff;border-bottom:1px solid #e5e7eb;padding:10px 16px;display:flex;gap:10px;align-items:center;z-index:10}}
  header .sp{{flex:1}}
  .btn{{background:#2563eb;color:#fff;border:none;border-radius:8px;padding:10px 14px;cursor:pointer;text-decoration:none}}
  .btn.ghost{{background:#fff;color:#2563eb;border:1px solid #2563eb}}
  iframe{{position:absolute;inset:56px 0 0 0;width:100%;height:calc(100% - 56px);border:0;background:#fff}}
</style>
</head>
<body>
  <header>
    <strong>Preview: {slug}</strong>
    <span class="sp"></span>
    <a class="btn ghost" href="/">Change Template</a>
    <a class="btn" href="/export/{eid}">Next →</a>
  </header>
  <iframe srcdoc='{html.replace("'", "&#39;")}' title="Resume Preview"></iframe>
</body></html>"""
    resp = make_response(shell)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp

# =============================================================================
# Export
# =============================================================================
@app.get("/export/<eid>", endpoint="export")
def export_options(eid):
    item = _get_export_payload(eid)
    slug = item["slug"]
    html = item["html"]
    page = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>Export — {slug}</title>
<style>
  body{{margin:0;background:#f3f4f6;font-family:Arial,Helvetica,sans-serif;color:#111}}
  .wrap{{max-width:1080px;margin:30px auto;padding:20px;background:#fff;border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,.08)}}
  .actions{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}}
  .btn{{background:#2563eb;color:#fff;border:none;border-radius:10px;padding:12px 16px;cursor:pointer;text-decoration:none;display:inline-block}}
  .btn.ghost{{background:#fff;color:#2563eb;border:1px solid #2563eb}}
  iframe{{width:100%;height:calc(100vh - 240px);border:0;background:#fff}}
  .hint{{color:#555;font-size:14px;margin-top:6px}}
</style>
</head>
<body>
  <div class="wrap">
    <h2>Export Options</h2>
    <div class="actions">
      <a class="btn" href="/studio/{eid}">Preview & Edit</a>
      <a class="btn" href="/export/print/{eid}" target="_blank">Open Print View</a>
      <a class="btn ghost" href="/" title="Back">Back to Home</a>
    </div>
    <div class="hint">For pixel-perfect color PDFs: choose <b>Save as PDF</b> and enable <b>Background graphics</b> in the print dialog.</div>
    <iframe srcdoc='{html.replace("'", "&#39;")}'></iframe>
  </div>
</body>
</html>
"""
    return make_response(page, 200)

@app.get("/export/print/<eid>")
def export_print(eid):
    item = _get_export_payload(eid)
    slug = item["slug"]
    html = item["html"]
    page = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>{slug} — Print</title>
<style>
  @page {{ size: A4; margin: 0; }}
  @media print {{
    html, body {{ background: #fff !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  }}
  body{{margin:0;background:#fff}}
</style>
</head>
<body onload="setTimeout(()=>window.print(), 150)">
{html}
</body>
</html>
"""
    return make_response(page, 200)


@app.get("/export/headless/<eid>")
def export_headless(eid):
    import re
    item = _get_export_payload(eid)
    slug = item["slug"]
    raw_html = item.get("html", "")
    
    # Stitch pages together if sent as a list
    if isinstance(raw_html, list):
        html_content = "\n".join(raw_html)
    else:
        html_content = str(raw_html)
    
    css_injection = """
    <style>
      /* 🚀 FORCE FONT DOWNLOAD TO PREVENT LINUX FALLBACKS */
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

      /* 🚀 PDF GLOBAL RESET */
      @page { size: 794px 1123px; margin: 0; }
      
      html, body { 
          margin: 0 !important; padding: 0 !important; background: #fff !important; 
          height: auto !important; overflow: visible !important; 
          -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; 
          font-family: 'Inter', sans-serif !important;
      }
      
      /* 🚀 FIX 1: Blank Second Page Fix. */
      body > div, .app-root, #root {
          position: static !important; overflow: visible !important; height: auto !important; width: auto !important;
          background: transparent !important; padding: 0 !important; margin: 0 !important;
      }

      /* 🚀 FIX 2: Page clip fix. */
      .a4, .a4-page, .page-export-wrapper div[style*="position: absolute"] {
          page-break-after: always !important; break-after: page !important;
          display: block !important; position: relative !important; transform: none !important; zoom: 1 !important;
          width: 794px !important; height: 1123px !important;
          margin: 0 !important; padding: 0 !important;
          box-shadow: none !important; border: none !important; overflow: hidden !important;
      }

      /* 🚀 FIX 3: TEXT WRAPPING SAFETY NET */
      /* This allows inner text divs to stretch slightly if Linux needs 1-2 extra pixels, preventing line breaks */
      .text, .normal-line, .bullet-line {
          min-width: 102% !important; 
          overflow: visible !important;
      }

      * {
          -webkit-font-smoothing: antialiased !important;
          -moz-osx-font-smoothing: grayscale !important;
          text-rendering: optimizeLegibility !important;
      }
    </style>
    """  
    
    # Prevent nested documents
    if "<html" in html_content.lower():
        # Inject style tag nicely
        page = re.sub(r'(?i)</head>', css_injection + '</head>', html_content)
        if css_injection not in page: page = css_injection + html_content
    else:
        # Wrap raw content
        page = f"<!doctype html><html><head><meta charset='utf-8'/><title>{slug}</title>{css_injection}</head><body>{html_content}</body></html>"
        
    return make_response(page, 200)

@app.get("/static/fonts/<path:filename>")
def serve_font(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'static', 'fonts'), filename)

@app.get("/export/hq-pdf/<eid>")
def export_hq_pdf(eid):
    import tempfile
    import os
    import re
    from playwright.sync_api import sync_playwright

    # 1. Grab the HTML locally (Bypasses the Server Deadlock entirely!)
    item = _get_export_payload(eid)
    raw_html = item.get("html", "")
    html_content = "\n".join(raw_html) if isinstance(raw_html, list) else str(raw_html)
    
    css_injection = """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
      @page { size: 794px 1123px; margin: 0; }
      html, body { 
          margin: 0 !important; padding: 0 !important; background: #fff !important; 
          height: auto !important; overflow: visible !important; 
          -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; 
          font-family: 'Inter', sans-serif !important;
      }
      body > div, .app-root, #root {
          position: static !important; overflow: visible !important; height: auto !important; width: auto !important;
          background: transparent !important; padding: 0 !important; margin: 0 !important;
      }
      .a4, .a4-page, .page-export-wrapper div[style*="position: absolute"] {
          page-break-after: always !important; break-after: page !important;
          display: block !important; position: relative !important; transform: none !important; zoom: 1 !important;
          width: 794px !important; height: 1123px !important; margin: 0 !important; padding: 0 !important;
          box-shadow: none !important; border: none !important; overflow: hidden !important;
      }
      .text, .normal-line, .bullet-line { min-width: 102% !important; overflow: visible !important; }
      * { -webkit-font-smoothing: antialiased !important; -moz-osx-font-smoothing: grayscale !important; text-rendering: optimizeLegibility !important; }
    </style>
    """  
    if "<html" in html_content.lower():
        final_html = re.sub(r'(?i)</head>', css_injection + '</head>', html_content)
        if css_injection not in final_html: final_html = css_injection + html_content
    else:
        final_html = f"<!doctype html><html><head><meta charset='utf-8'/>{css_injection}</head><body>{html_content}</body></html>"

    temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf_path = temp_pdf.name
    temp_pdf.close()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--enable-font-antialiasing',
                    '--force-color-profile=srgb',
                    '--font-render-hinting=none',
                ]
            )

            context = browser.new_context(
                viewport={"width": 794, "height": 1123},
                device_scale_factor=1,
                ignore_https_errors=True,
            )
            page = context.new_page()

            # 2. Inject HTML directly into Playwright
            page.set_content(final_html, wait_until="networkidle", timeout=30000)

            # Wait for ALL fonts to fully load
            page.evaluate("""async () => {
                await document.fonts.ready;
                document.body.getBoundingClientRect();
                await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
                const allFonts = [...document.fonts];
                await Promise.all(allFonts.map(f => f.loaded.catch(() => null)));
            }""")

            page.wait_for_timeout(2500)
            page.emulate_media(media="screen")

            page.pdf(
                path=pdf_path,
                width="210mm",
                height="297mm",
                print_background=True,
                margin={"top": "0px", "bottom": "0px", "left": "0px", "right": "0px"},
                prefer_css_page_size=False,
                scale=1.0
            )
            browser.close()

        return send_file(
            pdf_path, 
            as_attachment=True, 
            download_name=f"HQ_Resume_{eid}.pdf",
            mimetype="application/pdf"
        )
        
    except Exception as e:
        return f"Error generating PDF: {str(e)}", 500
        
    finally:
        if os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except:
                pass

# =============================================================================
# SEO Routes (Robots & Sitemap)
# =============================================================================
@app.route('/robots.txt')
def serve_robots():
    return send_from_directory(BASE_DIR, 'robots.txt')

@app.route('/sitemap.xml')
def serve_sitemap():
    return send_from_directory(BASE_DIR, 'sitemap.xml')                
# =============================================================================
# Run & Font Downloader
# =============================================================================



if '--download-fonts' in sys.argv:
    import requests, re
    from pathlib import Path
    FONT_URLS = [
        "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap",
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0"}
    
    # Safely define font_dir using Path
    font_dir = Path(__file__).resolve().parent / "static" / "fonts"
    font_dir.mkdir(parents=True, exist_ok=True)
    
    for font_url in FONT_URLS:
        css = requests.get(font_url, headers=headers).text
        for url in re.findall(r'url\((https://fonts\.gstatic\.com/[^)]+)\)', css):
            filename = url.split('/')[-1]
            dest = font_dir / filename
            if not dest.exists():
                print(f"Downloading {filename}...")
                dest.write_bytes(requests.get(url).content)
    print("All fonts downloaded to static/fonts/")
    sys.exit(0)




if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)

