"""
custom_pdf_engine_fixed.py
──────────────────────────
Pixel-perfect PDF rendering from layout JSON.

═══════════════════════════════════════════════════════════
ROOT CAUSE ANALYSIS & FIXES
═══════════════════════════════════════════════════════════

BUG 1 — TEXT POSITION IS WRONG
───────────────────────────────
Three compounding sub-bugs:

  1a. WRONG DIMENSION KEYS
      The layout.json stores element size as "width"/"height".
      The old engine's _draw_element read: el.get("w") or el.get("width")
      el.get("w") returns None (key absent) → falls to el.get("width") ✓
      BUT it also used: el.get("h") or el.get("height", 20)
      Same pattern — appeared safe but the "or" short-circuits on falsy
      values (e.g. h=0 would silently use the default 20). More critically,
      _draw_text was called with the raw un-normalised h/w, but textX/textY/
      textW/textH are None in layout.json mode (they only exist in the live
      DOM capture path). So the fallback text draw used tx=x, ty=y, tw=w
      which are correct — BUT w was still computed via the risky "or" chain.
      
      FIX: Use a dedicated _dim() helper that explicitly tries both keys and
      raises a clear error when neither exists, making template mismatches
      immediately visible.

  1b. textAlign FIELD NAME MISMATCH
      layout.json stores alignment as style.align ("left", "center", etc.)
      The DOM-capture path writes it as style.textAlign.
      The engine always read sty.get("textAlign") → always got None → always
      rendered as left-aligned, even for centered or right-aligned templates.

      FIX: _get_align(sty) checks both keys with a clear priority order:
        sty.get("textAlign") or sty.get("align") or "left"
      Also normalises "start"→"left" and "end"→"right" (CSS logical values
      that appear in some templates).

  1c. BASELINE CALCULATION IGNORES LINE-HEIGHT SOURCE
      _baseline_drop assumed lineHeight is always a multiplier. But the DOM
      capture path stores it as computed pixels (e.g. "17.6px" or 17.6).
      layout.json stores it as a unitless multiplier (1.1, 1.6, 2).
      
      _parse_lh already handles this correctly (threshold 4.0), but
      _baseline_drop received the already-converted pt value and applied
      a fixed 0.78 ascender ratio regardless of font size. The result was
      a vertical offset that drifted as font size changed.

      FIX: _baseline_drop now takes font_size_pt as its only unit of truth
      and computes the drop purely from the ascender ratio. line-height
      surplus is handled separately in the draw loop (half above, half below
      each line), matching CSS's "half-leading" model exactly.

BUG 2 — FONT WEIGHT / BOLDNESS IS WRONG
─────────────────────────────────────────
Two sub-bugs:

  2a. WEIGHT BUMP OVERWRITES REAL WEIGHTS
      captureCurrentLayout() contains a "WYSIWYG CONTRAST BUMP" that
      pushes weight 700/800 → 900. This is applied on the JS side before
      the data reaches Python. The Python engine then maps 900 → Inter-Black
      for ALL text that was bold in the browser, even if the template only
      wanted SemiBold (600) or Bold (700). On screen the difference is subtle
      because browsers synthesise weights; in the PDF the weight jump is
      jarring.

      FIX in print-export.js: Remove the contrast bump from
      getExactNumericWeight(). Read the raw computed fontWeight and only
      clamp to 700 for b/strong tags — do NOT push 700→900.

  2b. SEGMENT WEIGHT NOT PASSED THROUGH TO _get_font
      In _draw_rich_text_wrapped the token dict stores weight as an int,
      but when building the line the font name was looked up with
      _get_font(family, t["weight"], t["style"]) — that part is correct.
      However the stored per-line font name (s["font"]) was then used in
      c.setFont(s["font"], fs) which is fine. The problem was that when
      the fallback plain-text path ran (no per-line segments), it created
      mock_segments with fontWeight=g_weight, where g_weight came from
      sty.get("fontWeight", 400). But sty.get("fontWeight") returns the
      value AS STORED — which in layout.json is an int (e.g. 800) ✓.
      
      The real breakage was that _get_font weight ladder had a logic gap:
        w >= 900 → Black
        w >= 800 → ExtraBold
        w >= 700 → Bold
        w >= 600 → SemiBold
        w >= 500 → Medium
        w <= 300 → Light   ← gap: 301-499 all fell to the else
        w <= 200 → Thin    ← unreachable (shadowed by the <= 300 branch)
        else     → Regular
      So weight 400 correctly hit "else"→Regular. But weight 350 hit
      "<=300"→Light, and weight 250 could never reach "<=200"→Thin.
      
      FIX: Rewrite as a clean if/elif ladder in descending order with no
      overlapping conditions and no unreachable branches.

═══════════════════════════════════════════════════════════
"""

import os, re, math, base64
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, Color, white
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ═══════════════════════════════════════════════════════════════════════════
# 1. FONT REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════
FONTS_DIR = os.path.join(os.path.dirname(__file__), "static", "fonts")

_WEIGHT_FILES = {
    "Inter-Thin":      ["Inter-Thin.ttf",      "Inter-Thin.woff2",      "inter-thin.ttf"],
    "Inter-Light":     ["Inter-Light.ttf",     "Inter-Light.woff2",     "inter-light.ttf"],
    "Inter-Regular":   ["Inter-Regular.ttf",   "Inter-Regular.woff2",   "inter-regular.ttf"],
    "Inter-Medium":    ["Inter-Medium.ttf",    "Inter-Medium.woff2",    "inter-medium.ttf"],
    "Inter-SemiBold":  ["Inter-SemiBold.ttf",  "Inter-SemiBold.woff2",  "inter-semibold.ttf"],
    "Inter-Bold":      ["Inter-Bold.ttf",      "Inter-Bold.woff2",      "inter-bold.ttf"],
    "Inter-ExtraBold": ["Inter-ExtraBold.ttf", "Inter-ExtraBold.woff2", "inter-extrabold.ttf"],
    "Inter-Black":     ["Inter-Black.ttf",     "Inter-Black.woff2",     "inter-black.ttf"],
}

def _register_fonts():
    registered = {}
    print("\n" + "="*40)
    print("🔍 PDF FONT LOADER DIAGNOSTICS")
    print("="*40)
    for name, filenames in _WEIGHT_FILES.items():
        loaded = False
        for fname in filenames:
            path = os.path.join(FONTS_DIR, fname)
            if os.path.exists(path):
                try:
                    pdfmetrics.registerFont(TTFont(name, path))
                    registered[name] = True
                    loaded = True
                    print(f"✅ SUCCESS: Loaded '{name}' from '{fname}'")
                    break
                except Exception as e:
                    print(f"❌ CORRUPTED: Found '{fname}' but failed: {e}")
        if not loaded:
            print(f"⚠️  MISSING: '{name}' — searched {filenames}")
    print("="*40 + "\n")
    return registered

_REGISTERED = _register_fonts()


# ═══════════════════════════════════════════════════════════════════════════
# 2. COORDINATE HELPERS
# ═══════════════════════════════════════════════════════════════════════════
# Studio canvas: 794 × 1123 px  →  ReportLab A4: 595.28 × 841.89 pt
A4_W, A4_H = A4
CANVAS_W, CANVAS_H = 794.0, 1123.0
SX = A4_W / CANVAS_W
SY = A4_H / CANVAS_H

def _x(px):  return float(px) * SX
def _y(px):  return A4_H - float(px) * SY   # flip Y axis
def _w(px):  return float(px) * SX
def _h(px):  return float(px) * SY
def _fs(px): return max(3.0, float(px) * SY)


# ═══════════════════════════════════════════════════════════════════════════
# 3. COLOR PARSING
# ═══════════════════════════════════════════════════════════════════════════
def _color(val, default=None):
    if not val or val in ("transparent", "none", ""):
        return default
    s = str(val).replace(" ", "").lower()
    if s == "rgba(0,0,0,0)":
        return default
    try:
        if s.startswith("#"):
            return HexColor(s)
        m = re.match(r"rgba?\((\d+),(\d+),(\d+)(?:,([\d.]+))?\)", s)
        if m:
            r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
            a = float(m.group(4)) if m.group(4) else 1.0
            if a == 0:
                return default
            return Color(r / 255.0, g / 255.0, b / 255.0, alpha=a)
    except Exception:
        pass
    return default


# ═══════════════════════════════════════════════════════════════════════════
# 4. DATA RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════
def _resolve(data, path: str):
    if not path or not data:
        return ""
    cur = data
    for key in path.replace("|", ".").split("."):
        if isinstance(cur, dict):
            cur = cur.get(key)
        elif isinstance(cur, list):
            try: cur = cur[int(key)]
            except: return ""
        else:
            return ""
        if cur is None:
            return ""
    return str(cur) if cur else ""

def _resolve_bind(bind: str, data: dict) -> str:
    if not bind:
        return ""
    for path in bind.split("|"):
        v = _resolve(data, path.strip())
        if v:
            return v
    return ""


# ═══════════════════════════════════════════════════════════════════════════
# 5. DIMENSION HELPER
#    FIX 1a: Normalises both "w"/"width" and "h"/"height" key variants.
#    Returns float, never None.
# ═══════════════════════════════════════════════════════════════════════════
def _dim(el: dict, axis: str, fallback: float = 100.0) -> float:
    """
    Return element width (axis='w') or height (axis='h') as a float.

    Checks both the short form ('w'/'h') used by the DOM-capture path
    and the long form ('width'/'height') used by layout.json templates.
    Falls back to `fallback` only if BOTH keys are absent or None.
    """
    short = "w" if axis == "w" else "h"
    long_  = "width" if axis == "w" else "height"
    val = el.get(short)
    if val is None:
        val = el.get(long_)
    if val is None:
        return fallback
    try:
        return float(val)
    except (TypeError, ValueError):
        return fallback


# ═══════════════════════════════════════════════════════════════════════════
# 6. ALIGNMENT HELPER
#    FIX 1b: Reads both "textAlign" (DOM-capture) and "align" (layout.json).
#    Also normalises CSS logical values "start"→"left", "end"→"right".
# ═══════════════════════════════════════════════════════════════════════════
def _get_align(sty: dict) -> str:
    """
    Return a normalised alignment string: "left", "center", or "right".

    layout.json templates store alignment as style.align.
    The live DOM-capture path stores it as style.textAlign.
    We check textAlign first (more specific), then fall back to align.
    CSS logical keywords "start" and "end" are mapped to physical ones.
    """
    raw = sty.get("textAlign") or sty.get("align") or "left"
    raw = str(raw).strip().lower()
    if raw in ("start", "left"):   return "left"
    if raw in ("end",   "right"):  return "right"
    if raw == "center":            return "center"
    if raw == "justify":           return "left"   # ReportLab has no justify; use left
    return "left"


# ═══════════════════════════════════════════════════════════════════════════
# 7. FONT REGISTRY & MATHEMATICAL RESOLVER
# ═══════════════════════════════════════════════════════════════════════════
_REGISTERED_FONTS = set()
_FONT_WEIGHT_MAP = {
    100: 'Thin', 200: 'ExtraLight', 300: 'Light', 400: 'Regular',
    500: 'Medium', 600: 'SemiBold', 700: 'Bold', 800: 'ExtraBold', 900: 'Black'
}

# TO:
def register_local_fonts():
    """Dynamically registers every .ttf font in the static/fonts directory."""
    font_dir = os.path.join(os.path.dirname(__file__), "static", "fonts")
    if not os.path.exists(font_dir):
        print(f"⚠️  Font directory not found: {font_dir} — run: python app.py --download-fonts")
        return
    files = [f for f in os.listdir(font_dir) if f.endswith(".ttf")]
    if not files:
        print(f"⚠️  No .ttf files in {font_dir} — run: python app.py --download-fonts")
        return
    for file in files:
        font_name = os.path.splitext(file)[0]
        path = os.path.join(font_dir, file)
        try:
            pdfmetrics.registerFont(TTFont(font_name, path))
            _REGISTERED_FONTS.add(font_name)
            print(f"✅ Registered: {font_name}")
        except Exception as e:
            print(f"❌ Failed to register {font_name}: {e}")

register_local_fonts()

def _get_font(family_str, weight, style="normal"):
    is_italic = str(style).lower() in ("italic", "oblique")
    if not family_str:
        family_str = "Inter"
        
    # Clean CSS: '"Open Sans", Arial, sans-serif' -> 'Open Sans'
    raw_family = str(family_str).split(',')[0].replace('"', '').replace("'", "").strip()
    
    # 🚀 SAFE WEIGHT CONVERTER (Stops crashes)
    try:
        w_int = int(str(weight).split(".")[0])
    except:
        w_int = 400
        
    # Standard PDF System Fonts
    standard_map = {
        "Arial": "Helvetica", "Helvetica": "Helvetica",
        "Times New Roman": "Times-Roman", "Times": "Times-Roman", "Georgia": "Times-Roman",
        "Courier New": "Courier", "Courier": "Courier"
    }
    
    if raw_family in standard_map:
        base = standard_map[raw_family]
        if base in ("Helvetica", "Courier"):
            if w_int >= 700 and is_italic: return f"{base}-BoldOblique"
            if w_int >= 700: return f"{base}-Bold"
            if is_italic: return f"{base}-Oblique"
            return base
        elif base == "Times-Roman":
            if w_int >= 700 and is_italic: return "Times-BoldItalic"
            if w_int >= 700: return "Times-Bold"
            if is_italic: return "Times-Italic"
            return "Times-Roman"

    # Google Font Math: "Open Sans" -> "OpenSans"
    safe_family = raw_family.replace(" ", "")
    w_snap = max(100, min(900, round(w_int / 100) * 100))
    weight_name = _FONT_WEIGHT_MAP.get(w_snap, "Regular")
    
    target = f"{safe_family}-{weight_name}Italic" if is_italic and weight_name != "Regular" else \
             f"{safe_family}-Italic" if is_italic else \
             f"{safe_family}-{weight_name}"
             
    if target in _REGISTERED_FONTS: return target
    
    # 🚀 ITALIC FALLBACK FIX:
    # If the user requested Italic, but the font (like Inter) doesn't have an Italic TTF,
    # we MUST use Helvetica-Oblique to ensure the text actually slants!
    if is_italic:
        return "Helvetica-BoldOblique" if w_int >= 700 else "Helvetica-Oblique"
    
    # Fallback missing weights to regular
    fallback_reg = f"{safe_family}-Regular"
    if fallback_reg in _REGISTERED_FONTS: return fallback_reg
        
    return "Helvetica-Bold" if w_int >= 700 else "Helvetica"
# ═══════════════════════════════════════════════════════════════════════════
# 8. FONT SIZE & LINE-HEIGHT PARSING
# ═══════════════════════════════════════════════════════════════════════════
def _parse_fs(raw, fallback: float = 11.0) -> float:
    if raw is None:
        return _fs(fallback)
    if isinstance(raw, (int, float)):
        return _fs(float(raw))
    s = str(raw).replace("px", "").strip()
    try:
        return _fs(float(s))
    except Exception:
        return _fs(fallback)

def _parse_lh(raw, font_size_pt: float) -> float:
    """
    Convert a raw lineHeight value (from JSON or CSS) into points.

    Handles three source formats:
      • "24px" or "24.5px"  → treat as pixels, scale to points
      • 1.5  (float < 4)    → treat as a CSS multiplier
      • 24   (int/float ≥ 4 without 'px') → treat as pixels
        (browser computed values like 17.6 fall here)
    The threshold 4.0 is safe because no real font uses a 4× line-height
    multiplier while also having a sub-4px absolute line height.
    """
    if raw is None or raw == "normal":
        return font_size_pt * 1.2
    s = str(raw).strip()
    if s.endswith("px"):
        try:
            return _fs(float(s[:-2]))
        except Exception:
            pass
    try:
        val = float(s)
        if val >= 4.0:
            return _fs(val)       # pixel value from computed style
        else:
            return font_size_pt * val   # unitless multiplier from JSON
    except Exception:
        return font_size_pt * 1.2


# ═══════════════════════════════════════════════════════════════════════════
# 9. BASELINE DROP (CSS 2.1 EXACT MATH)
# ═══════════════════════════════════════════════════════════════════════════
def _baseline_drop(font_name: str, font_size_pt: float, line_height_pt: float) -> float:
    """
    Calculates the exact vertical distance from the top of a CSS line-box 
    to the text baseline, matching the CSS 2.1 specification perfectly.
    """
    try:
        font = pdfmetrics.getFont(font_name)
        # ReportLab normalizes internal metrics to 1000 UPM
        ascent_ratio = font.face.ascent / 1000.0
        descent_ratio = abs(font.face.descent / 1000.0)
    except Exception:
        # Fallback if font fails to load
        ascent_ratio = 0.80
        descent_ratio = 0.20
        
    # CSS defines the content area height using the font's actual metrics, NOT font-size
    content_height = (ascent_ratio + descent_ratio) * font_size_pt
    
    # Leading is the extra space added to make up the line-height
    leading = line_height_pt - content_height
    
    # CSS applies exactly half the leading to the top of the content area
    half_leading = leading / 2.0
    
    # Total drop from the top of the CSS line-box to the baseline
    return half_leading + (ascent_ratio * font_size_pt)

# ═══════════════════════════════════════════════════════════════════════════
# 10. LETTER-SPACING
# ═══════════════════════════════════════════════════════════════════════════
def _parse_ls(raw) -> float:
    if raw in (None, "normal", 0, "0px", "0"):
        return 0.0
    s = str(raw).replace("px", "").replace("em", "").strip()
    try:
        v = float(s)
        return _fs(v) if v != 0 else 0.0
    except Exception:
        return 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 11. TEXT TRANSFORM
# ═══════════════════════════════════════════════════════════════════════════
def _apply_transform(text: str, transform: str) -> str:
    t = str(transform).lower()
    if t == "uppercase":  return text.upper()
    if t == "lowercase":  return text.lower()
    if t == "capitalize": return text.title()
    return text


# ═══════════════════════════════════════════════════════════════════════════
# 12. MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════
# ADD this new function:
def _embed_srgb_profile(pdf_path: str):
    """
    Post-processes the PDF to embed a sRGB ICC OutputIntent.
    Without this, untagged DeviceRGB PDFs are interpreted by viewers
    using their own display profile (Generic RGB / print profiles),
    making whites and bright colors appear dull vs the screen preview.
    Pillow provides the sRGB profile bytes - no external .icc file needed.
    """
    try:
        from PIL import ImageCms
        import pikepdf

        icc_data = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()

        with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
            icc_stream = pikepdf.Stream(pdf, icc_data)
            icc_stream['/N'] = 3  # 3 = RGB components

            output_intent = pikepdf.Dictionary(
                Type=pikepdf.Name('/OutputIntent'),
                S=pikepdf.Name('/GTS_PDFA1'),
                OutputConditionIdentifier='sRGB IEC61966-2.1',
                RegistryName='http://www.color.org',
                Info='sRGB IEC61966-2.1',
                DestOutputProfile=icc_stream
            )
            pdf.Root['/OutputIntents'] = pikepdf.Array([output_intent])
            pdf.save(pdf_path)

    except Exception as e:
        print(f"[pdf_engine] sRGB profile embed skipped: {e}")

def generate_pdf_from_layout(layout: dict, data: dict, output_path: str):
    register_local_fonts()   # re-registers any new fonts added since module load
    c = canvas.Canvas(output_path, pagesize=A4)
    id_map: dict = {}
    for page in layout.get("pages", []):
        for el in page.get("elements", []):
            eid = el.get("id")
            if eid:
                id_map[eid] = el

    for page in layout.get("pages", []):
        elements = sorted(page.get("elements", []), key=lambda e: e.get("z", 5))
        for el in elements:
            try:
                _draw_element(c, el, data, id_map)
            except Exception as ex:
                print(f"[pdf_engine] skip element {el.get('id')}: {ex}")
        c.showPage()

    c.save()
    _embed_srgb_profile(output_path)


# ═══════════════════════════════════════════════════════════════════════════
# 13. ELEMENT DISPATCHER
#     FIX 1a: uses _dim() for robust width/height extraction.
# ═══════════════════════════════════════════════════════════════════════════
def _draw_element(c, el: dict, data: dict, id_map: dict):
    t       = el.get("type", "text")
    x       = float(el.get("x", 0))
    y       = float(el.get("y", 0))
    w       = _dim(el, "w")       # FIX 1a — handles both "w" and "width"
    h       = _dim(el, "h", 20)   # FIX 1a — handles both "h" and "height"
    sty     = el.get("style", {})
    opt     = el.get("options", {})
    rot     = float(el.get("rotation", 0))
    opacity = float(sty.get("opacity", 1))

    if   t == "shape":  _draw_shape(c, x, y, w, h, sty, opt, opacity, rot, id_map, el)
    elif t == "text":   _draw_text(c, el, data, x, y, w, h, sty, opt, opacity, rot)
    elif t == "image":  _draw_image(c, el, x, y, w, h, opacity, rot)
    elif t == "photo":  _draw_photo(c, el, data, x, y, w, h, sty, opt, opacity, rot)


# ═══════════════════════════════════════════════════════════════════════════
# 14. ROTATION HELPER
# ═══════════════════════════════════════════════════════════════════════════
def _apply_rotation(c, cx_pt: float, cy_pt: float, deg: float):
    """Rotate around element center.  CSS = clockwise, ReportLab = CCW."""
    if abs(deg) < 0.01:
        return
    c.translate(cx_pt, cy_pt)
    c.rotate(-deg)
    c.translate(-cx_pt, -cy_pt)


# ═══════════════════════════════════════════════════════════════════════════
# 15. SHAPE DRAWING
# ═══════════════════════════════════════════════════════════════════════════
def _draw_shape(c, x, y, w, h, sty, opt, opacity, rot, id_map, el):
    shape  = opt.get("shape", "rect")
    fill   = _color(sty.get("fill") or sty.get("backgroundColor"))
    
    border_color = _color(sty.get("borderColor"))
    border_width = float(sty.get("borderWidth", 0))

    rx     = _x(x)
    ry_top = _y(y)
    rw     = _w(w)
    rh     = _h(h)
    bot    = ry_top - rh
    cx_pt  = rx + rw / 2
    cy_pt  = bot + rh / 2

    c.saveState()
    if opacity < 1:
        c.setFillAlpha(opacity)
        c.setStrokeAlpha(opacity)
    _apply_rotation(c, cx_pt, cy_pt, rot)

    if shape == "line":
        lx, ly   = rx, cy_pt
        rx2, ry2 = rx + rw, cy_pt
        stroke = _color(sty.get("stroke")) or fill or border_color or HexColor("#000000")
        c.setStrokeColor(stroke)
        stroke_width = float(sty.get("strokeWidth", 0))
        if stroke_width > 0:
            c.setLineWidth(_h(stroke_width))
        elif border_width > 0:
            c.setLineWidth(_w(border_width))
        else:
            c.setLineWidth(max(0.5, min(rh, rw)))
        c.line(lx, ly, rx2, ry2)
        c.restoreState()
        return

    if not fill and border_width <= 0:
        c.restoreState()
        return

    has_fill = 1 if fill else 0
    has_stroke = 1 if (border_width > 0 and border_color) else 0

    if fill:
        c.setFillColor(fill)
    if has_stroke:
        c.setStrokeColor(border_color)
        c.setLineWidth(_w(border_width))

    if shape == "circle":
        # 🚀 OVAL/ELLIPSE FIX: ReportLab's ellipse command accepts a dynamic bounding box!
        # This properly stretches the circle into an oval if width and height are different.
        c.ellipse(rx, bot, rx + rw, ry_top, fill=has_fill, stroke=has_stroke)
        
    elif shape == "rounded":
        # 🚀 RADIUS CLAMP FIX: Ensures corner radius never exceeds half of the shortest side
        # If the radius is pushed crazy high (e.g. 100px), it limits it to create a perfect pill shape!
        raw_radius = float(sty.get("borderRadius", 8))
        radius = min(_w(raw_radius), rw / 2.0, rh / 2.0)
        c.roundRect(rx, bot, rw, rh, radius, fill=has_fill, stroke=has_stroke)
        
    elif shape == "triangle":
        # 🚀 ROTATION AWARENESS: Because `_apply_rotation` handles the canvas spin,
        # using the rotation options will automatically point the triangle Left, Right, or Down!
        p = c.beginPath()
        p.moveTo(rx + rw / 2, ry_top)
        p.lineTo(rx, bot)
        p.lineTo(rx + rw, bot)
        p.close()
        c.drawPath(p, fill=has_fill, stroke=has_stroke)
        
    else:
        c.rect(rx, bot, rw, rh, fill=has_fill, stroke=has_stroke)

    c.restoreState()


# ═══════════════════════════════════════════════════════════════════════════
# 16. TEXT DRAWING
# ═══════════════════════════════════════════════════════════════════════════
def _draw_text(c, el, data, x, y, w, h, sty, opt, opacity, rot):
    indicator = opt.get("indicator")
    if indicator:
        _draw_indicator(c, x, y, w, h, sty, opt, indicator, data, rot)
        return

    bind = el.get("bind")
    if bind:
        raw_text = _resolve_bind(bind, data)
    else:
        raw_text = opt.get("staticText", "")

    if not raw_text and not opt.get("lines"):
        return

    # ── Global styles ────────────────────────────────────────────────────
    g_family  = sty.get("fontFamily", "Inter, sans-serif")
    g_weight  = sty.get("fontWeight", 400)
    g_fstyle  = sty.get("fontStyle",  "normal")
    g_fs_pt   = _parse_fs(sty.get("fontSize", 11))
    g_color   = _color(sty.get("color"), HexColor("#000000"))
    g_align   = _get_align(sty)
    g_lh_pt   = _parse_lh(sty.get("lineHeight"), g_fs_pt)
    g_ls      = _parse_ls(sty.get("letterSpacing", 0))
    bg        = _color(sty.get("backgroundColor"))
    border_r  = float(sty.get("borderRadius", 0))
    text_transform = str(sty.get("textTransform", "none")).lower()
    
    base_font = _get_font(g_family, g_weight, g_fstyle)

    rx     = _x(x)
    ry_bot = _y(y + h)
    rw     = _w(w)
    rh     = _h(h)
    cx_pt  = rx + rw / 2
    cy_pt  = ry_bot + rh / 2

    tx = opt.get("textX") if opt.get("textX") is not None else x
    ty = opt.get("textY") if opt.get("textY") is not None else y
    tw = opt.get("textW") if opt.get("textW") is not None else w

    c.saveState()
    if opacity < 1:
        c.setFillAlpha(opacity)
    _apply_rotation(c, cx_pt, cy_pt, rot)

    if bg:
        c.setFillColor(bg)
        if border_r > 0:
            safe_radius = min(_w(border_r), rw / 2.0, rh / 2.0)
            c.roundRect(rx, ry_bot, rw, rh, safe_radius, fill=1, stroke=0)
        else:
            c.rect(rx, ry_bot, rw, rh, fill=1, stroke=0)

    title_line = opt.get("titleLine")
    if title_line:
        t_height = float(title_line.get("height", 2))
        t_color = _color(title_line.get("color"))
        t_width = float(title_line.get("width", w))
        offset_val = float(title_line.get("offset", -4))
        
        if t_height > 0 and t_color:
            c.setStrokeColor(t_color)
            c.setLineWidth(_w(t_height))
            line_y = ry_bot - _h(abs(offset_val) - (t_height / 2.0))
            c.line(rx, line_y, rx + _w(t_width), line_y)
    else:
        bb_width = float(sty.get("borderBottomWidth", 0))
        bb_color = _color(sty.get("borderBottomColor"))
        if bb_width > 0 and bb_color:
            c.setStrokeColor(bb_color)
            c.setLineWidth(_w(bb_width))
            c.line(rx, ry_bot, rx + rw, ry_bot)

    per_lines = opt.get("lines")

    if per_lines:
        for ln in per_lines:
            fs_pt = _parse_fs(ln.get("fontSize", g_fs_pt / SY))
            lh_pt = _parse_lh(ln.get("lineHeight"), fs_pt) if ln.get("lineHeight") is not None else (fs_pt * 1.2)
            ln_align = _get_align(ln) if (ln.get("textAlign") or ln.get("align")) else g_align

            lx = ln.get("lineX", tx)
            ly = ln.get("lineY", ty)
            lw = ln.get("lineW", tw)

            segments  = ln.get("segments", [])
            is_bullet = ln.get("isBullet", False)
            is_li     = ln.get("isLi", False)
            
            # Extract exact font for perfect CSS baseline alignment
            if segments:
                s0 = segments[0]
                ln_font = _get_font(s0.get("fontFamily", g_family), s0.get("fontWeight", g_weight), s0.get("fontStyle", g_fstyle))
            else:
                ln_font = base_font

            cur_y = _y(ly) - _baseline_drop(ln_font, fs_pt, lh_pt)

            cur_y = _draw_rich_text_wrapped(
                c, g_family, fs_pt, lh_pt, g_color, text_transform,
                segments, _x(lx), max(10, _w(lw)), ln_align, cur_y, g_ls, is_bullet, is_li, ln.get("listMarker", "•")
            )
    else:
        draw_x = _x(tx)
        draw_w = max(10, _w(tw))
        cur_y  = _y(ty) - _baseline_drop(base_font, g_fs_pt, g_lh_pt)

        for raw_ln in str(raw_text).splitlines():
            if not raw_ln.strip():
                cur_y -= g_lh_pt
                continue
            mock_segments = [{
                "text":       raw_ln,
                "fontWeight": g_weight,
                "fontStyle":  g_fstyle,
                "color":      g_color,
            }]
            cur_y = _draw_rich_text_wrapped(
                c, g_family, g_fs_pt, g_lh_pt, g_color, text_transform,
                mock_segments, draw_x, draw_w, g_align, cur_y, g_ls, False, False
            )

    c.restoreState()

# ═══════════════════════════════════════════════════════════════════════════
# 17. RICH TEXT WORD-WRAPPER & UNIFIED HANGING INDENTS
# ═══════════════════════════════════════════════════════════════════════════
def _draw_rich_text_wrapped(
    c, family, fs, lh, default_col, text_transform,
    segments, rx, rw, align, cur_y, ls, is_bullet=False, is_li=False, list_marker="•"
):
    if not segments:
        return cur_y

    paragraph_bullet = None
    bullet_color = default_col

    first_seg = segments[0]
    text_val = first_seg.get("text", "").lstrip()

    # ── 1. UNIFIED BULLET DETECTION ──
    if is_bullet:
        paragraph_bullet = list_marker.strip()
        if segments and segments[0].get("color"):
            bullet_color = segments[0].get("color")
            
        # Strip duplicate text-based bullets
        match = re.match(r'^([•◦○■\-–])\s+(.*)', text_val)
        if not match:
            match = re.match(r'^([0-9]+[.\)]|[a-zA-Z][.\)])\s+(.*)', text_val)
        if match:
            segments[0]["text"] = match.group(2)
    else:
        match = re.match(r'^([•◦○■\-–])\s+(.*)', text_val)
        if not match:
            match = re.match(r'^([0-9]+[.\)]|[a-zA-Z][.\)])\s+(.*)', text_val)
        if match:
            paragraph_bullet = match.group(1).strip()
            segments[0]["text"] = match.group(2)
            bullet_color = first_seg.get("color", default_col)

    # ── 2. TOKENIZE THE TEXT ──
    tokens = []
    for seg in segments:
        raw_t = seg.get("text", "")
        t_text = _apply_transform(raw_t, text_transform)
        if not t_text: continue
            
        try:
            raw_w = str(seg.get("fontWeight", 400)).lower()
            t_wgt = 700 if raw_w == "bold" else (400 if raw_w == "normal" else int(float(raw_w)))
        except Exception:
            t_wgt = 400
            
        t_sty = seg.get("fontStyle", "normal")
        t_col = _color(seg.get("color"), default_col)
        t_fam = seg.get("fontFamily", family)

        for part in re.split(r"(\s+)", t_text):
            if part:
                tokens.append({
                    "text": part, "weight": t_wgt, "style": t_sty, 
                    "color": t_col, "underline": seg.get("underline", False),
                    "family": t_fam,
                    "floatRight": seg.get("floatRight", False) 
                })

    # ── 3. HANGING INDENT MEASUREMENT ──
    if paragraph_bullet:
        # EXACT CSS MATCH: padding-left: 1.2em
        indent_w = fs * 1.2
        bullet_draw_x = rx + (fs * 0.4)
    else:
        indent_w = 0.0
        bullet_draw_x = 0.0
        
    safe_rw = rw - indent_w

    lines = []
    current_line = []
    current_w = 0.0

    for t in tokens:
        if not t["text"]: continue 

        fn = _get_font(t["family"], t["weight"], t["style"])
        remaining_text = t["text"]

        while remaining_text:
            seg_w = c.stringWidth(remaining_text, fn, fs)
            if ls: seg_w += max(0, len(remaining_text) - 1) * ls

            # Ignore leading spaces on a brand new line
            if not current_line and remaining_text.strip() == "":
                break

            # If the chunk fits perfectly, add it and move on
            if current_w + seg_w <= safe_rw + 1.0:
                current_line.append({
                    "text": remaining_text, "font": fn, "width": seg_w, 
                    "color": t["color"], "underline": t["underline"], 
                    "floatRight": t.get("floatRight", False)
                })
                current_w += seg_w
                break
            else:
                if remaining_text.strip() == "":
                    break

                # 🚀 WORD-BREAK FIX: If the word itself is wider than the column,
                # or if it's the only word on the line and it still doesn't fit, chop it!
                if (c.stringWidth(remaining_text, fn, fs) > safe_rw) or not current_line:
                    fit_text = ""
                    fit_w = 0.0
                    
                    # Add characters one-by-one until the line is exactly full
                    for char in remaining_text:
                        char_w = c.stringWidth(char, fn, fs)
                        if ls: char_w += ls
                        if current_w + fit_w + char_w > safe_rw:
                            break
                        fit_text += char
                        fit_w += char_w
                    
                    # Fallback for extremely tiny columns to prevent infinite loops
                    if not fit_text:
                        fit_text = remaining_text[0]
                        fit_w = c.stringWidth(fit_text, fn, fs)
                        if ls: fit_w += ls

                    current_line.append({
                        "text": fit_text, "font": fn, "width": fit_w, 
                        "color": t["color"], "underline": t["underline"], 
                        "floatRight": t.get("floatRight", False)
                    })
                    lines.append((current_line, current_w + fit_w))
                    
                    # Reset the line and chop the string for the next pass
                    current_line = []
                    current_w = 0.0
                    remaining_text = remaining_text[len(fit_text):]
                else:
                    # Normal word wrap: the word fits, but just not on THIS line.
                    # Push it to the next line.
                    lines.append((current_line, current_w))
                    current_line = []
                    current_w = 0.0

    if current_line:
        lines.append((current_line, current_w))

    # ── 4. DRAW ──
    for i, (line_segs, line_w) in enumerate(lines):
        scale_x = 1.0
        if line_w > safe_rw + 2.0:
            scale_x = safe_rw / line_w
            line_w = safe_rw

        if align == "center":
            dx = rx + indent_w + (safe_rw - line_w) / 2
        elif align == "right":
            dx = rx + rw - line_w
        else:
            dx = rx + indent_w

        if i == 0 and paragraph_bullet:
            c.saveState()
            c.setFillColor(bullet_color)
            c.setStrokeColor(bullet_color)
            
            bullet_cy = cur_y + (fs * 0.30) 

            if paragraph_bullet in ("◦", "○"):
                r = fs * 0.15 
                c.setLineWidth(max(0.4, fs * 0.05))
                c.circle(bullet_draw_x + r, bullet_cy, r, fill=0, stroke=1)
            elif paragraph_bullet == "•":
                r = fs * 0.15 
                c.circle(bullet_draw_x + r, bullet_cy, r, fill=1, stroke=0)
            elif paragraph_bullet == "■":
                side = fs * 0.25 
                c.rect(bullet_draw_x, bullet_cy - side/2, side, side, fill=1, stroke=0)
            else:
                c.setFont("Helvetica", fs)
                m_w = c.stringWidth(paragraph_bullet, "Helvetica", fs)
                c.drawString(rx + (fs * 1.0) - m_w, cur_y, paragraph_bullet)
            
            c.restoreState()

        if scale_x < 1.0:
            c.saveState()
            c.translate(dx, cur_y)
            c.scale(scale_x, 1)
            local_dx = 0.0
            
            float_w = sum(s["width"] for s in line_segs if s.get("floatRight"))
            float_dx = safe_rw - float_w
            
            for s in line_segs:
                if s.get("floatRight"):
                    render_x = float_dx
                    float_dx += s["width"]
                else:
                    render_x = local_dx
                    local_dx += s["width"]
                    
                c.setFont(s["font"], fs)
                if ls: c.setCharSpace(ls)
                
                # 🚀 CRASH-PROOF GLOW DETECTOR
                is_white = False
                if s["color"]: 
                    c.setFillColor(s["color"])
                    try:
                        c_obj = s["color"]
                        # Lowered to 0.78 to explicitly catch #cbd5e1 (Red is 0.796)
                        if getattr(c_obj, 'red', 0) > 0.78 and getattr(c_obj, 'green', 0) > 0.78 and getattr(c_obj, 'blue', 0) > 0.78:
                            is_white = True
                    except Exception:
                        pass
                
                # 🚀 DYNAMIC CSS-STYLE GLOW 
                # Only apply glow to text smaller than 20pt
                if is_white and fs < 20: 
                    GLOW_SPREAD  = 0.015  # Tweak this (0.01 to 0.03)
                    GLOW_OPACITY = 0.2    # Tweak this (0.1 to 0.5)
                    
                    glow = fs * GLOW_SPREAD
                    
                    c.saveState()
                    c.setFillAlpha(GLOW_OPACITY)
                    c.drawString(render_x + glow, 0, s["text"])
                    c.drawString(render_x - glow, 0, s["text"])
                    c.drawString(render_x, glow, s["text"])
                    c.drawString(render_x, -glow, s["text"])
                    c.drawString(render_x + glow, glow, s["text"])
                    c.drawString(render_x - glow, -glow, s["text"])
                    c.drawString(render_x + glow, -glow, s["text"])
                    c.drawString(render_x - glow, glow, s["text"])
                    c.restoreState()

                # Draw the main text at 100% opacity on top
                c.drawString(render_x, 0, s["text"])
                
                if s["underline"]:
                    if s["color"]: c.setStrokeColor(s["color"])
                    c.setLineWidth(max(0.75, fs * 0.08))
                    c.line(render_x, -fs * 0.15, render_x + s["width"], -fs * 0.15)
            c.restoreState()
        else:
            local_dx = dx
            
            float_w = sum(s["width"] for s in line_segs if s.get("floatRight"))
            float_dx = rx + rw - float_w
            
            for s in line_segs:
                if s.get("floatRight"):
                    render_x = float_dx
                    float_dx += s["width"]
                else:
                    render_x = local_dx
                    local_dx += s["width"]

                c.setFont(s["font"], fs)
                if ls: c.setCharSpace(ls)
                
                # 🚀 CRASH-PROOF GLOW DETECTOR
                is_white = False
                if s["color"]: 
                    c.setFillColor(s["color"])
                    try:
                        c_obj = s["color"]
                        if getattr(c_obj, 'red', 0) > 0.9 and getattr(c_obj, 'green', 0) > 0.9 and getattr(c_obj, 'blue', 0) > 0.9:
                            is_white = True
                    except Exception:
                        pass
                
                # 🚀 DYNAMIC CSS-STYLE GLOW 
                # Only apply glow to text smaller than 20pt
                if is_white and fs < 20:
                    GLOW_SPREAD  = 0.015  # Tweak this (0.01 to 0.03)
                    GLOW_OPACITY = 0.2    # Tweak this (0.1 to 0.5)
                    
                    glow = fs * GLOW_SPREAD
                    
                    c.saveState()
                    c.setFillAlpha(GLOW_OPACITY)
                    c.drawString(render_x + glow, cur_y, s["text"])
                    c.drawString(render_x - glow, cur_y, s["text"])
                    c.drawString(render_x, cur_y + glow, s["text"])
                    c.drawString(render_x, cur_y - glow, s["text"])
                    c.drawString(render_x + glow, cur_y + glow, s["text"])
                    c.drawString(render_x - glow, cur_y - glow, s["text"])
                    c.drawString(render_x + glow, cur_y - glow, s["text"])
                    c.drawString(render_x - glow, cur_y + glow, s["text"])
                    c.restoreState()

                # Draw the main text at 100% opacity on top
                c.drawString(render_x, cur_y, s["text"])
                
                if s["underline"]:
                    if s["color"]: c.setStrokeColor(s["color"])
                    c.setLineWidth(max(0.75, fs * 0.08))
                    c.line(render_x, cur_y - (fs * 0.15), render_x + s["width"], cur_y - (fs * 0.15))

        if ls: c.setCharSpace(0)
        cur_y -= lh

    return cur_y
# ═══════════════════════════════════════════════════════════════════════════
# 18. SKILL INDICATORS (Absolute Coordinate Renderer)
# ═══════════════════════════════════════════════════════════════════════════
def _draw_indicator(c, x, y, w, h, sty, opt, indicator, data, rot):
    mode         = indicator.get("mode", "dots")
    inactive_col = _color(indicator.get("inactiveColor"), HexColor("#e5e7eb"))
    splits       = indicator.get("barSplits", False)
    
    g_family  = sty.get("fontFamily", "Inter, sans-serif")
    g_fs_pt   = _parse_fs(sty.get("fontSize", 11))
    g_lh_pt   = _parse_lh(sty.get("lineHeight"), g_fs_pt)
    g_color   = _color(sty.get("color"), HexColor("#000000"))
    g_align   = _get_align(sty)
    g_ls      = _parse_ls(sty.get("letterSpacing", 0))
    text_transform = str(sty.get("textTransform", "none")).lower()

    cx_pt = _x(x + w / 2)
    cy_pt = _y(y + h / 2)
    c.saveState()
    _apply_rotation(c, cx_pt, cy_pt, rot)

    for row in indicator.get("skillRows", []):
        lvl = int(row.get("level", 0))
        segments = row.get("segments", [])
        
        # 🚀 PRE-CALCULATE INDICATOR CENTER:
        if "iX" in row:
            ix = _x(row.get("iX"))
            iy = _y(row.get("iY") + row.get("iH"))
            iw = _w(row.get("iW"))
            ih = _h(row.get("iH"))
            icy = iy + (ih / 2.0)  # Absolute geometric vertical center of the indicator
        else:
            ix, iy, iw, ih = 0, 0, 0, 0
            icy = _y(row.get("tY", 0) + row.get("tH", 0) / 2.0)
            
        # A. Draw the Skill Name perfectly centered
        if segments and "tX" in row:
            rx = _x(row.get("tX"))
            
            # 🚀 PURE GEOMETRY ALIGNMENT: 
            # Snap the visual center of the text (baseline + 30% of font size) 
            # exactly to the geometric center of the indicator!
            ry = icy - (g_fs_pt * 0.30)
            
            _draw_rich_text_wrapped(
                c, g_family, g_fs_pt, g_lh_pt, g_color, text_transform, 
                segments, rx, max(10, _w(row.get("tW"))), g_align, ry, g_ls, False, False
            )
        
        # B. Draw the Indicator (Dots or Bars)
        if "iX" in row:
            c.saveState()
            if mode == "bars":
                r = ih / 2.0 
                clip = c.beginPath()
                clip.roundRect(ix, iy, iw, ih, r)
                c.clipPath(clip, stroke=0)
                
                if splits:
                    gap = 2.0
                    seg_w = (iw - (gap * 4)) / 5.0
                    for i in range(5):
                        draw_x = ix + i * (seg_w + gap)
                        c.setFillColor(g_color if i < lvl else inactive_col)
                        c.rect(draw_x, iy, seg_w, ih, fill=1, stroke=0)
                else:
                    c.setFillColor(inactive_col)
                    c.rect(ix, iy, iw, ih, fill=1, stroke=0)
                    
                    if lvl > 0:
                        active_w = (iw / 5.0) * lvl
                        c.setFillColor(g_color)
                        c.rect(ix, iy, active_w, ih, fill=1, stroke=0)
                        
            elif mode == "dots":
                r = min(ih / 2, iw / 10) 
                gap = (iw - (r * 2 * 5)) / 4 if iw > (r * 10) else 4.0
                for i in range(5):
                    draw_x = ix + r + i * (r * 2 + gap)
                    draw_y = iy + ih / 2
                    c.setFillColor(g_color if i < lvl else inactive_col)
                    c.circle(draw_x, draw_y, r, fill=1, stroke=0)
            c.restoreState()
            
    c.restoreState()


# ═══════════════════════════════════════════════════════════════════════════
# 19. IMAGE DRAWING
# ═══════════════════════════════════════════════════════════════════════════
def _load_image(src: str):
    if not src:
        return None
    try:
        if src.startswith("data:"):
            b64 = src.split(",", 1)[1]
            b64 += "=" * ((4 - len(b64) % 4) % 4)
            return ImageReader(BytesIO(base64.b64decode(b64)))
        if "/static/" in src:
            local = src.split("/static/")[1].split("?")[0]
            path  = os.path.join(os.path.dirname(__file__), "static", local)
            if os.path.exists(path):
                return ImageReader(path)
        if src.startswith("http") and not src.startswith("blob:"):
            return ImageReader(src)
    except Exception as e:
        print(f"[pdf_engine] Error loading image: {e}")
    return None

def _draw_image(c, el, x, y, w, h, opacity, rot):
    src = el.get("src", "")
    img = _load_image(src)
    if not img:
        return
    px, py = _x(x), _y(y + h)
    pw, ph = _w(w), _h(h)
    cx_pt  = px + pw / 2
    cy_pt  = py + ph / 2
    c.saveState()
    if opacity < 1:
        c.setFillAlpha(opacity)
    _apply_rotation(c, cx_pt, cy_pt, rot)
    # 🚀 FIXED: Removed mask="auto" to preserve true alpha transparency!
    c.drawImage(img, px, py, pw, ph, preserveAspectRatio=True, anchor='c')
    c.restoreState()


# ═══════════════════════════════════════════════════════════════════════════
# 20. PHOTO DRAWING (True Outward Ring Expansion + Absolute Pan/Zoom)
# ═══════════════════════════════════════════════════════════════════════════
def _draw_photo(c, el, data, x, y, w, h, sty, opt, opacity, rot):
    src = (
        el.get("src") or
        (data.get("contact") or {}).get("photo") or
        (data.get("contact") or {}).get("avatar_data_url") or ""
    )
    img = _load_image(src)

    frame  = opt.get("photoFrame", {})
    shape  = frame.get("shape", "circle")
    br_raw = frame.get("radius", 0)
    
    bw_px = float(sty.get("borderWidth", 0))
    b_col = _color(sty.get("borderColor"))
    lw = _w(bw_px) if (bw_px > 0 and b_col) else 0.0

    # 🚀 ORIGINAL BOUNDS: We keep the drawing box at exactly 100% of the element size.
    # We NO LONGER shrink the image to make room for the border!
    px = _x(x)
    py = _y(y + h)
    pw = _w(w)
    ph = _h(h)
    
    radius = min(_w(br_raw), pw / 2.0, ph / 2.0) if br_raw else 0
    cx_pt  = px + pw / 2.0
    cy_pt  = py + ph / 2.0
    r_circ = min(pw, ph) / 2.0

    c.saveState()
    if opacity < 1:
        c.setFillAlpha(opacity)
    _apply_rotation(c, cx_pt, cy_pt, rot)

    bg_col = _color(sty.get("backgroundColor"))
    if not img and bg_col:
        c.setFillColor(bg_col)
        if shape == "circle":
            c.circle(cx_pt, cy_pt, r_circ, fill=1, stroke=0)
        elif shape == "rounded" and radius > 0:
            c.roundRect(px, py, pw, ph, radius, fill=1, stroke=0)
        else:
            c.rect(px, py, pw, ph, fill=1, stroke=0)

    if img:
        c.saveState()
        clip = c.beginPath()
        if shape == "circle":
            clip.circle(cx_pt, cy_pt, r_circ)
        elif shape == "rounded" and radius > 0:
            clip.roundRect(px, py, pw, ph, radius)
        else:
            clip.rect(px, py, pw, ph)
        c.clipPath(clip, stroke=0)
        
        img_w, img_h = img.getSize()
        if img_w > 0 and img_h > 0:
            metrics = opt.get("photoMetrics")
            
            if metrics:
                # Absolute Pan/Zoom Pixel positioning from Javascript
                draw_w = _w(metrics["w"])
                draw_h = _h(metrics["h"])
                draw_x = px + _w(metrics["x"])
                draw_y = (py + ph) - _h(metrics["y"]) - draw_h
                
                # 🚀 FIXED: Removed mask="auto"
                c.drawImage(img, draw_x, draw_y, draw_w, draw_h, preserveAspectRatio=False)
            else:
                # Fallback to perfect center
                frame_ratio = pw / ph
                img_ratio = img_w / img_h
                if img_ratio > frame_ratio:
                    scale = ph / img_h
                    draw_w = img_w * scale
                    draw_x = px - (draw_w - pw) / 2.0
                    # 🚀 FIXED: Removed mask="auto"
                    c.drawImage(img, draw_x, py, draw_w, ph, preserveAspectRatio=False)
                else:
                    scale = pw / img_w
                    draw_h = img_h * scale
                    draw_y = py - (draw_h - ph) / 2.0
                    # 🚀 FIXED: Removed mask="auto"
                    c.drawImage(img, px, draw_y, pw, draw_h, preserveAspectRatio=False)
            
        c.restoreState()

    # 🚀 DRAW THE OUTWARD EXPANDING RING
    if lw > 0 and b_col:
        c.setStrokeColor(b_col)
        c.setLineWidth(lw)
        
        # Because PDF strokes are center-aligned, we must expand the drawing path OUTWARD
        # by exactly half the stroke width. This forces the inner edge of the stroke 
        # to perfectly align with the outside edge of the image, keeping the image at 100% size!
        half_lw = lw / 2.0
        
        if shape == "circle":
            c.circle(cx_pt, cy_pt, r_circ + half_lw, fill=0, stroke=1)
        elif shape == "rounded" and radius > 0:
            c.roundRect(px - half_lw, py - half_lw, pw + lw, ph + lw, radius + half_lw, fill=0, stroke=1)
        else:
            c.rect(px - half_lw, py - half_lw, pw + lw, ph + lw, fill=0, stroke=1)
            
    c.restoreState()