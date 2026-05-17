/* print-export.js - 3 BUTTON EXPORT VERSION (STANDARD + BROWSER HQ + PLAYWRIGHT) */
(function () {
  const PAGE_SELECTOR = ".a4";
  const SLOT_ID = "export-slot";

  // ============================================================
  // UI INJECTION — Renders the buttons into the export slot
  // ============================================================
  // ============================================================
  // UI INJECTION — Single button + Animated Modal
  // ============================================================
  // ============================================================
  // UI INJECTION — Single button + Animated Modal
  // ============================================================
  function injectUI() {
    const slot = document.getElementById(SLOT_ID);
    if (!slot) return;

    // 1. Inject ONLY the CSS and the Button into the toolbar slot
    slot.innerHTML = `
    <style>
      /* --- MAIN DOWNLOAD BUTTON --- */
      #mainExportBtn {
        background: linear-gradient(135deg, #0ea5e9, #6366f1);
        color: #fff; border: none; padding: 12px 24px; border-radius: 30px;
        font-weight: 600; font-size: 15px; cursor: pointer;
        display: flex; align-items: center; gap: 8px;
        box-shadow: 0 4px 12px rgba(14, 165, 233, 0.3);
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
      }
      #mainExportBtn:hover { 
        transform: translateY(-2px); 
        box-shadow: 0 6px 16px rgba(14, 165, 233, 0.4); 
      }
      
      /* --- MODAL BACKDROP --- */
      #export-modal-backdrop {
        position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
        background: rgba(0,0,0,0.5); backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px);
        z-index: 999999; display: flex; align-items: center; justify-content: center;
        opacity: 0; visibility: hidden; transition: all 0.3s ease;
      }
      #export-modal-backdrop.show {
        opacity: 1; visibility: visible;
      }

      /* --- MODAL CARD --- */
      #export-modal-card {
        background: var(--card, #ffffff); 
        border-radius: 16px; width: 90%; max-width: 420px; padding: 24px;
        box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25);
        transform: translateY(20px) scale(0.95); 
        transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        position: relative; border: 1px solid var(--line, #e5e7eb);
      }
      #export-modal-backdrop.show #export-modal-card {
        transform: translateY(0) scale(1);
      }
      
      /* --- MODAL CLOSE BUTTON --- */
      .modal-close-btn {
        position: absolute; top: 16px; right: 16px; background: transparent; border: none;
        color: var(--muted, #6b7280); cursor: pointer; padding: 6px; border-radius: 50%; 
        transition: background 0.2s; display: flex; align-items: center; justify-content: center;
      }
      .modal-close-btn:hover { background: var(--line, #f3f4f6); color: var(--ink, #111); }
      .modal-header { margin-top: 0; margin-bottom: 20px; font-size: 1.25rem; font-weight: 700; color: var(--ink, #1f2937); }
      
      /* --- EXPORT OPTION BUTTONS --- */
      .export-opt-btn {
        display: flex; flex-direction: column; align-items: flex-start;
        width: 100%; padding: 16px; margin-bottom: 12px;
        border: 2px solid var(--line, #e5e7eb); border-radius: 12px;
        background: transparent; cursor: pointer; text-align: left;
        transition: all 0.2s ease;
      }
      .export-opt-btn:hover {
        border-color: #0ea5e9; background: rgba(14, 165, 233, 0.04); transform: translateY(-2px);
      }
      .export-opt-btn:last-child { margin-bottom: 0; }
      
      .export-opt-title { 
        font-weight: 700; font-size: 15px; color: var(--ink, #1f2937); 
        margin-bottom: 6px; display: flex; align-items: center; gap: 8px;
      }
      .export-opt-desc { 
        font-size: 13px; color: var(--muted, #6b7280); line-height: 1.4; 
      }
      
      /* --- DARK MODE SUPPORT --- */
      [data-theme="dark"] #export-modal-card { background: var(--card, #1e293b); border-color: var(--line, #334155); }
      [data-theme="dark"] .modal-header { color: var(--ink, #f8fafc); }
      [data-theme="dark"] .export-opt-btn { border-color: var(--line, #334155); }
      [data-theme="dark"] .export-opt-btn:hover { border-color: #0ea5e9; background: rgba(14, 165, 233, 0.1); }
      [data-theme="dark"] .export-opt-title { color: var(--ink, #f8fafc); }
      [data-theme="dark"] .export-opt-desc { color: var(--muted, #94a3b8); }
      [data-theme="dark"] .modal-close-btn:hover { background: var(--line, #334155); color: var(--ink, #f8fafc); }
    </style>

    <div style="display:flex; gap:10px; align-items:center;">
          <button id="mainExportBtn">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
              <polyline points="7 10 12 15 17 10"></polyline>
              <line x1="12" y1="15" x2="12" y2="3"></line>
            </svg>
            Download PDF
          </button>
      </div>
    `;

    // 2. Inject the Modal directly into the document body
    // This escapes the toolbar's CSS restrictions and centers it perfectly on the screen
    if (!document.getElementById("export-modal-backdrop")) {
      const modalDiv = document.createElement("div");
      modalDiv.id = "export-modal-backdrop";
      modalDiv.innerHTML = `
        <div id="export-modal-card">
          <button class="modal-close-btn" id="closeExportModal" aria-label="Close">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
          
          <h3 class="modal-header">Select Export Quality</h3>

          <button class="export-opt-btn" id="modalProExportBtn">
            <div class="export-opt-title">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
              </svg>
              Professional Grade (Recommended)
            </div>
            <div class="export-opt-desc">
              High-fidelity vector rendering perfectly optimized for printing and ATS software. Delivers the sharpest text and graphics.
              <br><br>
              <span style="color: #0ea5e9; font-weight: 600;"><i>Note: Includes a brief ad to keep this premium feature free!</i></span>
            </div>
          </button>
        
          <button class="export-opt-btn" id="modalStdExportBtn">
            <div class="export-opt-title">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
                <polyline points="10 9 9 9 8 9"></polyline>
              </svg>
              Standard Document
            </div>
            <div class="export-opt-desc">Quick export using your browser's native print engine. Ideal for fast drafting or immediate sharing.</div>
          </button>
        </div>
      `;
      document.body.appendChild(modalDiv);
    }

    // --- Wiring up the Modal Logic ---
    const backdrop = document.getElementById("export-modal-backdrop");
    const mainBtn = document.getElementById("mainExportBtn");
    const closeBtn = document.getElementById("closeExportModal");
    const proBtn = document.getElementById("modalProExportBtn");
    const stdBtn = document.getElementById("modalStdExportBtn");

    function showModal() { backdrop.classList.add("show"); }
    function hideModal() { backdrop.classList.remove("show"); }

    // Open Modal
    mainBtn.addEventListener("click", showModal);
    
    // Close Modal via 'X' button or clicking the dark backdrop
    closeBtn.addEventListener("click", hideModal);
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) hideModal();
    });

    // Trigger Exports & close modal
    proBtn.addEventListener("click", () => {
        hideModal();
        triggerCustomPdfExport();
    });

    stdBtn.addEventListener("click", () => {
      hideModal();
      triggerPrint('standard');
    });

    // 🚀 NEW: Debug Button Click Logic
    // 🚀 THE ULTIMATE DEEP DEBUGGER
    const debugBtn = document.getElementById('debugLayoutBtn');
    if (debugBtn) {
        debugBtn.addEventListener('click', async () => {
            debugBtn.innerText = "Analyzing...";
            const layoutData = await captureCurrentLayout();

            console.clear();
            console.log("%c========================================", "color: #0ea5e9; font-weight: bold;");
            console.log("%c🔍 DOM-TO-PDF TEXT & STYLE INSPECTOR", "color: #0ea5e9; font-size: 16px; font-weight: bold;");
            console.log("%c========================================", "color: #0ea5e9; font-weight: bold;");

            // 🚀 SPECIAL LIST ROOT-CAUSE DEBUGGER V2
            console.groupCollapsed(`%c🎯 SPECIAL LIST ROOT-CAUSE DETECTOR V2`, 'color: #ec4899; font-weight: bold; font-size: 14px;');
            const allLists = document.querySelectorAll('.a4 li, .a4 [data-list]');
            if (allLists.length === 0) {
                console.log("%c❌ CRITICAL FAILURE: No <li> tags found!", "color: #ef4444; font-size: 12px;");
            } else {
                console.log("%c✅ HTML Lists Found! Here is exactly how the browser sees them:", "color: #10b981; font-size: 12px;");
                const listData = Array.from(allLists).map((li, idx) => ({
                    "Item #": idx + 1,
                    "Parent Tag": li.parentElement ? li.parentElement.tagName.toLowerCase() : "None",
                    "Data-List Attr": li.getAttribute('data-list') || "None",
                    "CSS Classes": li.className || "None",
                    "Computed Shape": window.getComputedStyle(li).listStyleType,
                    "Text Preview": li.innerText.substring(0, 30)
                }));
                console.table(listData);
            }
            console.groupEnd();

            const elements = layoutData.pages[0].elements;
            const textEls = elements.filter(e => e.type === 'text' && e.options?.lines);

            textEls.forEach(el => {
                console.groupCollapsed(`%c📝 Text Block: "${el.options.staticText.substring(0, 30)}..."`, 'color: #f59e0b; font-weight: bold; font-size: 14px;');
                
                el.options.lines.forEach((line, i) => {
                    if (line.isBullet) {
                        console.log(`%c[List Marker Detected] Line ${i+1}: "${line.listMarker}"`, 'color: #ef4444; font-weight: bold;');
                    }
                    
                    if (line.segments && line.segments.length > 0) {
                        console.table(line.segments.map(seg => ({
                            Text: seg.text,
                            Weight: seg.fontWeight,
                            Style: seg.fontStyle,
                            UNDERLINE: seg.underline ? "✅ YES" : "❌ NO"
                        })));
                    }
                });
                console.groupEnd();
            });

            const formattedJson = JSON.stringify(layoutData, null, 2);
            await navigator.clipboard.writeText(formattedJson);
            
            console.log("%c✅ Full layout JSON safely copied to clipboard!", "color: #22c55e; font-weight: bold;");
            alert("Analysis Complete. Press F12 to view the results in the Console!");
            debugBtn.innerText = "🐞 Debug";
        });
    }
  }



async function triggerCustomPdfExport() {
    const btn = document.getElementById("mainExportBtn");
    const originalHTML = btn.innerHTML;
    btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation:spin 1s linear infinite"><path d="M21 12a9 9 0 1 1-6.219-8.56"></path></svg> Generating...`;
    btn.style.opacity = "0.7";
    btn.style.pointerEvents = "none";

    try {
        const layoutData = await captureCurrentLayout();
        const resumeData = window.__currentResumeData || {};

        // Removed the broken debug API! Straight to PDF generation.
        const res = await fetch("/api/generate_custom_pdf", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ layout: layoutData, data: resumeData })
        });

        if (!res.ok) { 
            const errText = await res.text();
            throw new Error(`Server Error ${res.status}: ${errText}`);
        }

        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'Resume.pdf';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

    } catch(err) {
        console.error("Export crashed:", err);
        alert("Export Failed! Here is the root cause:\\n" + err.message);
    } finally {
        btn.innerHTML = originalHTML;
        btn.style.opacity = "1";
        btn.style.pointerEvents = "auto";
    }
}

// ── Helper: SVG element → base64 PNG (returns a Promise) ──────────────────
// ── Helper: SVG element → base64 PNG (returns a Promise) ──────────────────
function svgElementToPngBase64(svgEl, exactW, exactH, padPx = 0) {
    return new Promise((resolve) => {
        try {
            const clone = svgEl.cloneNode(true);
            
            if (!clone.getAttribute("xmlns")) {
                clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
            }

            // 🚀 STROKE CLIP & ANTI-SHRINK FIX
            let vb = clone.getAttribute("viewBox");
            if (!vb) vb = `0 0 ${exactW} ${exactH}`;
            
            const vbParts = vb.split(/[\s,]+/).map(Number);
            if (vbParts.length >= 4) {
                const unitRatioX = vbParts[2] / exactW;
                const unitRatioY = vbParts[3] / exactH;
                const padUnitX = padPx * unitRatioX;
                const padUnitY = padPx * unitRatioY;
                clone.setAttribute("viewBox", `${vbParts[0] - padUnitX} ${vbParts[1] - padUnitY} ${vbParts[2] + padUnitX * 2} ${vbParts[3] + padUnitY * 2}`);
            }

            const totalW = exactW + (padPx * 2);
            const totalH = exactH + (padPx * 2);

            // 🚀 ULTRA-HD VECTOR RESOLUTION
            const targetSize = 400;
            const maxDim = Math.max(exactW, exactH);
            let scaleMultiplier = maxDim > 0 ? (targetSize / maxDim) : 10;
            
            if (scaleMultiplier < 3) scaleMultiplier = 3;
            if (scaleMultiplier > 25) scaleMultiplier = 25;

            clone.setAttribute("width", totalW * scaleMultiplier);
            clone.setAttribute("height", totalH * scaleMultiplier);

            const compStyle = window.getComputedStyle(svgEl);
            const rawColor = compStyle.color || "#000000";
            
            clone.querySelectorAll("*").forEach(p => {
                const currentFill = p.getAttribute("fill") || window.getComputedStyle(p).fill;
                const currentStroke = p.getAttribute("stroke") || window.getComputedStyle(p).stroke;
                
                if (currentFill === "currentColor") p.setAttribute("fill", rawColor);
                if (currentStroke === "currentColor") p.setAttribute("stroke", rawColor);
            });

            if (clone.getAttribute("fill") === "currentColor") clone.setAttribute("fill", rawColor);
            if (clone.getAttribute("stroke") === "currentColor") clone.setAttribute("stroke", rawColor);

            const svgData = new XMLSerializer().serializeToString(clone);
            const svgBlob = new Blob([svgData], { type: "image/svg+xml;charset=utf-8" });
            const url = URL.createObjectURL(svgBlob);

            const img = new Image();
            img.onload = () => {
                const canvas = document.createElement("canvas");
                canvas.width  = totalW * scaleMultiplier;
                canvas.height = totalH * scaleMultiplier;
                const ctx = canvas.getContext("2d");
                
                ctx.imageSmoothingEnabled = true;
                ctx.imageSmoothingQuality = "high";

                // We NO LONGER fill the background with white here. 
                // We leave the canvas completely transparent.
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                URL.revokeObjectURL(url);
                
                // 🚀 Reverted back to Transparent PNG!
                resolve(canvas.toDataURL("image/png")); 
            };
            img.onerror = () => { URL.revokeObjectURL(url); resolve(""); };
            img.src = url;
        } catch(e) {
            resolve("");
        }
    });
}
// ── Helper: Image to Base64 (Crucial for Studio Blob Uploads) ─────────────
function imageToDataUrl(imgEl) {
    return new Promise((resolve) => {
        if (!imgEl || !imgEl.src) return resolve("");
        if (imgEl.src.startsWith("data:")) return resolve(imgEl.src);
        
        const img = new Image();
        
        // 🚀 BLOB FIX: Never apply CORS to a local blob URL, otherwise the canvas conversion crashes!
        if (!imgEl.src.startsWith("blob:")) {
            img.crossOrigin = "Anonymous"; 
        }
        
        img.onload = () => {
            try {
                const canvas = document.createElement("canvas");
                canvas.width = img.naturalWidth || 800;
                canvas.height = img.naturalHeight || 800;
                const ctx = canvas.getContext("2d");
                ctx.drawImage(img, 0, 0);
                resolve(canvas.toDataURL("image/png"));
            } catch (err) {
                resolve(imgEl.src);
            }
        };
        img.onerror = () => resolve(imgEl.src);
        img.src = imgEl.src;
    });
}

// ── Helper: extract rotation degrees from a transform string ──────────────
function parseRotation(transformStr) {
    if (!transformStr || transformStr === 'none') return 0;
    
    // 🚀 ROTATION FIX 1: Mathematically extract the angle from the browser's matrix
    if (transformStr.startsWith('matrix')) {
        const values = transformStr.split('(')[1].split(')')[0].split(',');
        const a = parseFloat(values[0]);
        const b = parseFloat(values[1]);
        return Math.round(Math.atan2(b, a) * (180 / Math.PI));
    }
    
    // Fallback for raw rotate() strings
    const m = transformStr.match(/rotate\(([-0-9.]+)deg\)/);
    return m ? parseFloat(m[1]) : 0;
}

// ── Helper: get the exact font info from the deepest text node ────────────
function getDeepFontStyle(el) {
    // Walk into the element to find the deepest node that has real text
    // This captures per-span font overrides made in the studio editor
    let target = el;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
        if (node.textContent.trim()) {
            target = node.parentElement;
            break;
        }
    }
    return window.getComputedStyle(target);
}

// ── Main layout capture (async for SVG conversion) ────────────────────────
// ── Main layout capture (async for SVG conversion) ────────────────────────
// ── Main layout capture (async for SVG conversion) ────────────────────────
async function captureCurrentLayout() {
    const layout = { pages: [] };

    // 🚀 NEW: Bulletproof Font Weight Parser (Translates words into exact numbers)
    function getExactNumericWeight(element) {
        if (!element) return 400;
        const comp = window.getComputedStyle(element);
        let w = comp.fontWeight;
        
        if (w === 'bold') w = 700;
        else if (w === 'normal') w = 400;
        else if (w === 'lighter') w = 300;
        else if (w === 'bolder') w = 800;
        
        let num = parseInt(w, 10);
        if (isNaN(num) || !num) {
            if (element.closest('b, strong, .ql-bold')) num = 700;
            else num = 400;
        }
        return num;
    }

    for (let pageIndex = 0; pageIndex < document.querySelectorAll('.a4').length; pageIndex++) {
        const pageEl = document.querySelectorAll('.a4')[pageIndex];
        const pageRect = pageEl.getBoundingClientRect();

        const CANVAS_W = 794;
        const CANVAS_H = 1123;
        const scaleX = pageRect.width  / CANVAS_W;
        const scaleY = pageRect.height / CANVAS_H;

        const pageObj = { id: `page-${pageIndex + 1}`, elements: [] };
        const designEls = Array.from(pageEl.querySelectorAll('.design-el'));

        for (const el of designEls) {
            const cs = window.getComputedStyle(el);
            const elRect = el.getBoundingClientRect();

            let type = "text";
            if (el.classList.contains('photo-el'))         type = "photo";
            else if (
                el.classList.contains('shape-el')    ||
                el.classList.contains('rect-el')     ||
                el.classList.contains('rounded-rect-el') ||
                el.classList.contains('ellipse-el')  ||
                el.classList.contains('triangle-el') ||
                el.classList.contains('line-el')
            ) type = "shape";
            else if (
                el.classList.contains('image-el') ||
                el.classList.contains('svg-el')
            ) type = "image";

            const cxScreen = elRect.left + elRect.width  / 2 - pageRect.left;
            const cyScreen = elRect.top  + elRect.height / 2 - pageRect.top;
            
            const cxStudio = cxScreen / scaleX;
            const cyStudio = cyScreen / scaleY;

            const trueW = el.offsetWidth;
            const trueH = el.offsetHeight;

            const x = cxStudio - trueW / 2;
            const y = cyStudio - trueH / 2;
            const w = trueW;
            const h = trueH;

            const rotation = parseRotation(cs.transform || el.style.transform || "");            
            const tcs = getDeepFontStyle(el);
            const baseBoxWeight = getExactNumericWeight(el);

            const elData = {
                id:       el.id || el.dataset.id || `el_${Math.random().toString(36).substr(2,6)}`,
                type:     type,
                bind:     null,
                x, y, w, h,
                rotation: rotation,
                z:        parseInt(el.style.zIndex, 10) || 5,
                style: {
                    fontFamily:      tcs.fontFamily,
                    fontSize:        parseFloat(tcs.fontSize),
                    fontWeight:      baseBoxWeight,
                    fontStyle:       tcs.fontStyle,
                    color:           tcs.color,
                    backgroundColor: cs.backgroundColor,
                    textAlign:       tcs.textAlign,
                    lineHeight:      tcs.lineHeight,
                    letterSpacing:   tcs.letterSpacing,
                    opacity:         parseFloat(cs.opacity) || 1,
                    borderRadius:    parseFloat(cs.borderRadius) || 0,
                    textTransform:   tcs.textTransform,
                },
                options: {}
            };

            // ── TEXT ──────────────────────────────────────────────────
            if (type === 'text') {
                elData.options.staticText = el.innerText.trim();
                
                // Pass hideIfEmpty so the PDF engine can skip drawing empty title boxes
                if (el.dataset.hideIfEmpty !== undefined && el.dataset.hideIfEmpty !== '') {
                    elData.options.hideIfEmpty = el.dataset.hideIfEmpty;
                }

                const innerEl = el.querySelector('.text-content, .text, .ql-editor') || el;
                const ics = window.getComputedStyle(innerEl);

                // 🚀 LOCAL HELPER: Convert RGB to Hex so the Python PDF Engine doesn't crash!
                const rgbToHex = (rgb) => {
                    if (!rgb || rgb === 'rgba(0, 0, 0, 0)') return "transparent";
                    const match = rgb.match(/^rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
                    if (!match) return rgb;
                    return `#${parseInt(match[1]).toString(16).padStart(2, '0')}${parseInt(match[2]).toString(16).padStart(2, '0')}${parseInt(match[3]).toString(16).padStart(2, '0')}`;
                };

                // 3. Typography Styles (Crucial for PDF Engine)
                elData.style.fontFamily = ics.fontFamily.replace(/"/g, '');
                elData.style.fontSize = parseFloat(ics.fontSize);
                elData.style.fontWeight = ics.fontWeight === 'bold' ? 700 : (parseInt(ics.fontWeight) || 400);
                elData.style.fontStyle = ics.fontStyle === 'italic' ? 'italic' : 'normal';
                elData.style.textDecoration = ics.textDecoration.includes('underline') ? 'underline' : 'none';
                elData.style.color = rgbToHex(ics.color);
                elData.style.align = ics.textAlign;
                if (ics.lineHeight !== "normal") {
                    elData.style.lineHeight = Math.round((parseFloat(ics.lineHeight) / elData.style.fontSize) * 10) / 10;
                }

                // 4. Background Color
                const bgCol = cs.backgroundColor !== 'rgba(0, 0, 0, 0)' ? cs.backgroundColor : ics.backgroundColor;
                if (bgCol && bgCol !== 'rgba(0, 0, 0, 0)' && bgCol !== 'transparent') {
                    elData.style.backgroundColor = rgbToHex(bgCol);
                }
                
                // 5. Border Radius (with % conversion)
                const brStr = cs.borderRadius !== "0px" ? cs.borderRadius : ics.borderRadius || "0";
                let br = parseFloat(brStr) || 0;
                if (brStr.includes('%')) br = (br / 100) * Math.min(w, h);
                if (br > 0) {
                    elData.style.borderRadius = br;
                    elData.style.overflow = "hidden";
                }

                // 6. Title Line Extraction
                const autoTitleLine = el.querySelector('.auto-title-line');
                if (autoTitleLine) {
                    const atcs = window.getComputedStyle(autoTitleLine);
                    elData.options.titleLine = {
                        color: rgbToHex(atcs.backgroundColor), // 🚀 Safely converted to Hex!
                        height: parseFloat(atcs.height) || 2,
                        width: autoTitleLine.offsetWidth || w,
                        offset: parseFloat(atcs.bottom) || 0
                    };
                }

                elData.options.textX = x;
                elData.options.textY = y;
                elData.options.textW = w;
                elData.options.textH = h;
                
                const lines = [];
                let orderCounter = 0;

                const elLevelUnderline = (el.style.textDecoration || '').includes('underline') ||
                                         (el.style.textDecorationLine || '').includes('underline');

                let lineElements = Array.from(el.querySelectorAll('.normal-line, .bullet-line, li, .ql-editor p, .ql-editor h1, .ql-editor h2'));
                
                if (lineElements.length === 0) {
                    lineElements = [el];
                }
                
                lineElements.forEach(lineEl => {
                    const lcs = window.getComputedStyle(lineEl);
                    
                    let relX = 0;
                    let relY = 0;
                    if (lineEl !== el) {
                        relX = lineEl.offsetLeft;
                        relY = lineEl.offsetTop;
                        let curr = lineEl.offsetParent;
                        while (curr && curr !== el && !curr.classList.contains('design-el')) {
                            relX += curr.offsetLeft;
                            relY += curr.offsetTop;
                            curr = curr.offsetParent;
                        }
                        const elBorderTop = parseFloat(window.getComputedStyle(el).borderTopWidth) || 0;
                        const elBorderLeft = parseFloat(window.getComputedStyle(el).borderLeftWidth) || 0;
                        relY += elBorderTop;
                        relX += elBorderLeft;
                    }
                    
                    const segments = [];
                    
                    const filter = {
                        acceptNode: function(node) {
                            let curr = node.parentElement;
                            while (curr && curr !== lineEl && curr !== el && !curr.classList.contains('design-el')) {
                                if (
                                    curr.classList.contains('normal-line') || 
                                    curr.classList.contains('bullet-line') || 
                                    curr.tagName.toLowerCase() === 'li' || 
                                    curr.tagName.toLowerCase() === 'p'
                                ) {
                                    return NodeFilter.FILTER_REJECT;
                                }
                                curr = curr.parentElement;
                            }
                            return NodeFilter.FILTER_ACCEPT;
                        }
                    };

                    const walker = document.createTreeWalker(lineEl, NodeFilter.SHOW_TEXT, filter, false);
                    let node;
                    while ((node = walker.nextNode())) {
                        let textVal = node.nodeValue.replace(/[\r\n]+/g, ' '); 
                        if (!textVal || textVal.trim() === "" && textVal.length > 2) continue;

                        let isBold = false;
                        let isItalic = false;
                        let isUnderline = elLevelUnderline;
                        let explicitColor = null;
                        let isFloatRight = false;
                        
                        const comp = window.getComputedStyle(node.parentElement);
                        let currNode = node.parentElement;
                        let explicitFamily = null;

                        while (currNode && currNode !== el && !currNode.classList.contains('design-el')) {
                            const tag = currNode.tagName ? currNode.tagName.toUpperCase() : '';
                            const cStyle = window.getComputedStyle(currNode);

                            if (cStyle.flexShrink === '0' || currNode.style.flexShrink === '0' || cStyle.float === 'right') {
                                isFloatRight = true;
                            }

                            if (!explicitFamily && cStyle.fontFamily && cStyle.fontFamily !== 'inherit') {
                                explicitFamily = cStyle.fontFamily;
                            }

                            if (tag === 'B' || tag === 'STRONG' || currNode.classList.contains('ql-bold') || 
                                cStyle.fontWeight === 'bold' || parseInt(cStyle.fontWeight) >= 600) {
                                isBold = true;
                            }
                            
                            if (tag === 'I' || tag === 'EM' || currNode.classList.contains('ql-italic') || 
                                cStyle.fontStyle === 'italic' || cStyle.fontStyle === 'oblique') {
                                isItalic = true;
                            }
                            
                            if (tag === 'U' || currNode.classList.contains('ql-underline') || 
                               (currNode.style && currNode.style.textDecoration && currNode.style.textDecoration.includes('underline')) ||
                               (cStyle.textDecorationLine && cStyle.textDecorationLine.includes('underline')) ||
                               (cStyle.textDecoration && cStyle.textDecoration.includes('underline'))) {
                                isUnderline = true;
                            }
                            
                            if (!explicitColor && cStyle.color && cStyle.color !== 'inherit' && cStyle.color !== 'rgba(0, 0, 0, 0)') {
                                explicitColor = cStyle.color;
                            }
                            
                            currNode = currNode.parentElement;
                        }

                        const baseWeight = getExactNumericWeight(el) || 400;
                        segments.push({
                            text: textVal,
                            fontFamily: explicitFamily || comp.fontFamily || lcs.fontFamily || tcs.fontFamily || "Inter",
                            fontWeight: isBold ? Math.max(700, baseWeight) : baseWeight,
                            fontStyle: isItalic ? 'italic' : (lcs.fontStyle || "normal"),
                            color: explicitColor || comp.color || lcs.color,
                            underline: isUnderline,
                            floatRight: isFloatRight
                        });
                    }

                    if (segments.length === 0) {
                        if (lineEl.textContent.trim() !== "") {
                            return; 
                        }
                        segments.push({ 
                            text: " ", 
                            fontWeight: getExactNumericWeight(lineEl) || 400, 
                            fontStyle: lcs.fontStyle || "normal",
                            color: lcs.color || tcs.color,
                            underline: false
                        });
                    }

                    let listMarker = "";
                    const isBullet = lineEl.classList.contains('bullet-line') || lineEl.tagName.toLowerCase() === 'li';

                    function toRoman(num) {
                        const roman = {M:1000,CM:900,D:500,CD:400,C:100,XC:90,L:50,XL:40,X:10,IX:9,V:5,IV:4,I:1};
                        let str = '';
                        for (let i of Object.keys(roman)) {
                            let q = Math.floor(num / roman[i]);
                            num -= q * roman[i];
                            str += i.repeat(q);
                        }
                        return str.toLowerCase();
                    }

                    if (isBullet) {
                        const parentTag = lineEl.parentElement ? lineEl.parentElement.tagName.toLowerCase() : '';
                        const listTypeAttr = lineEl.getAttribute('data-list') || '';
                        const listClass = lineEl.className || '';
                        const computedShape = window.getComputedStyle(lineEl).listStyleType;

                        const isOrdered = parentTag === 'ol' || listTypeAttr === 'ordered' || listClass.includes('ordered') || 
                                          ['decimal', 'lower-roman', 'upper-roman', 'lower-alpha', 'upper-alpha'].includes(computedShape);

                        if (isOrdered) {
                            orderCounter++;
                            if (computedShape.includes('roman') || listClass.includes('ql-indent-2') || listTypeAttr === 'roman') {
                                listMarker = toRoman(orderCounter) + ". ";
                            } 
                            else if (computedShape.includes('alpha') || listClass.includes('ql-indent-1') || listTypeAttr === 'alpha') {
                                listMarker = String.fromCharCode(96 + orderCounter) + ". ";
                            } 
                            else {
                                listMarker = orderCounter + ". ";
                            }
                        } else {
                            if (computedShape === 'circle' || listClass.includes('ql-indent-1') || listTypeAttr === 'hollow') {
                                listMarker = "◦ "; 
                            } 
                            else if (computedShape === 'square' || listClass.includes('ql-indent-2') || listTypeAttr === 'square') {
                                listMarker = "■ ";
                            } 
                            else {
                                listMarker = "• ";
                            }
                        }
                    } else {
                        orderCounter = 0;
                    }

                    lines.push({
                        segments:   segments, 
                        fontSize:   parseFloat(lcs.fontSize),
                        textAlign:  lcs.textAlign || tcs.textAlign,
                        lineHeight: parseFloat(lcs.lineHeight) || (parseFloat(lcs.fontSize) * 1.25),
                        isBullet:   isBullet,
                        isLi:       lineEl.tagName.toLowerCase() === 'li',
                        listMarker: listMarker,
                        lineX:      x + relX,
                        lineY:      y + relY,
                        lineW:      lineEl.offsetWidth
                    });                
                });
                
                if (lines.length > 0) elData.options.lines = lines;            
            }

            // ── SKILLS INDICATORS ──────────────────────────────────────
            if (el.id === 'skills_dots' || el.dataset.id === 'skills_dots') {
                const mode         = el.getAttribute('data-dotstyle') || 'dots';
                const inactiveColor= el.style.getPropertyValue('--inactive-color') || getComputedStyle(el).getPropertyValue('--inactive-color') || '#e5e7eb';
                const barSplits    = el.classList.contains('bar-splits');

                const skillRows = [];
                
                el.querySelectorAll('.normal-line, .skill-row').forEach(row => {
                    const dotsEl = row.querySelector('.skill-dots, .skill-bar, [data-level]');
                    if (!dotsEl) return;

                    const level = parseInt(dotsEl.dataset.level || 0);
                    const dRect = dotsEl.getBoundingClientRect();
                    
                    const indX = (dRect.left - pageRect.left) / scaleX;
                    const indY = (dRect.top  - pageRect.top)  / scaleY;
                    const indW = dRect.width  / scaleX;
                    const indH = dRect.height / scaleY;

                    const textEl = row.querySelector('span, .text') || row;
                    const tRect = textEl.getBoundingClientRect();
                    const tX = (tRect.left - pageRect.left) / scaleX;
                    const tY = (tRect.top  - pageRect.top)  / scaleY;
                    const tW = tRect.width  / scaleX;
                    const tH = tRect.height / scaleY;

                    const segments = [];
                    const walker = document.createTreeWalker(textEl, NodeFilter.SHOW_TEXT, null, false);
                    let node;
                    while ((node = walker.nextNode())) {
                        let textVal = node.nodeValue.replace(/[\r\n]+/g, ' ').trim(); 
                        if (!textVal) continue;
                        segments.push({
                            text: textVal,
                            fontWeight: getExactNumericWeight(node.parentElement),
                            fontStyle: window.getComputedStyle(node.parentElement).fontStyle || "normal",
                            color: window.getComputedStyle(node.parentElement).color || tcs.color
                        });
                    }

                    skillRows.push({
                        level: level,
                        tX: tX, tY: tY, tW: tW, tH: tH, segments: segments,
                        iX: indX, iY: indY, iW: indW, iH: indH
                    });
                });

                elData.options.indicator = {
                    mode: mode,
                    inactiveColor: inactiveColor.trim(),
                    barSplits: barSplits,
                    skillRows: skillRows
                };
                
                elData.options.lines = []; 
            }

            // ── SHAPE ─────────────────────────────────────────────────
            if (type === 'shape') {
                // 🚀 FIX 1: Extract true background color (handles triangles which use ::before and transparent backgrounds)
                let fillColor = cs.backgroundColor;
                if (el.classList.contains('triangle-el') || fillColor === 'rgba(0, 0, 0, 0)' || fillColor === 'transparent') {
                    fillColor = el.style.getPropertyValue('--shape-fill') || cs.getPropertyValue('--shape-fill') || '#cfe8ff';
                }
                elData.style.fill = fillColor;
                
                const brStr = cs.borderRadius || el.style.borderRadius || "0";
                let br = parseFloat(brStr) || 0;
                if (brStr.includes('%')) {
                    br = (br / 100) * Math.min(w, h);
                }
                
                // 🚀 FIX 2: Only consider it a circle if it's explicitly an ellipse element!
                // This stops highly-rounded rectangles from accidentally becoming squashed circles.
                let shapeType = 'rect';
                
                if (el.classList.contains('line-el') || el.classList.contains('shape-line')) {
                    shapeType = 'line';
                } else if (el.classList.contains('ellipse-el') || el.classList.contains('shape-circle')) {
                    shapeType = 'circle'; // This will now be drawn as a dynamic ellipse in Python!
                } else if (el.classList.contains('rounded-rect-el') || el.classList.contains('shape-rounded') || br > 0) {
                    shapeType = 'rounded';
                } else if (el.classList.contains('triangle-el') || el.classList.contains('shape-triangle')) {
                    shapeType = 'triangle';
                }
                
                elData.options.shape = shapeType;
                elData.style.borderRadius = br;

                const pxMatches = [...(cs.boxShadow || '').matchAll(/([-\d.]+)px/g)].map(m => parseFloat(m[1]));
                const colorMatch = (cs.boxShadow || '').match(/(rgba?\([^)]+\)|#[a-fA-F0-9]+)/);
                
                let bWidth = parseFloat(cs.borderWidth) || 0;
                if (bWidth === 0 && pxMatches.length > 0) bWidth = Math.abs(pxMatches[pxMatches.length - 1]);
                elData.style.borderWidth = bWidth;
                elData.style.borderColor = cs.borderColor || (colorMatch ? colorMatch[1] : null);
                
                if (shapeType === 'line') {
                    const innerLine = el.querySelector('hr, .line-inner, .shape-inner') || el;
                    const lcs = window.getComputedStyle(innerLine);
                    
                    elData.style.borderColor = lcs.backgroundColor !== 'rgba(0, 0, 0, 0)' ? lcs.backgroundColor :
                                               lcs.borderTopColor !== 'rgba(0, 0, 0, 0)' ? lcs.borderTopColor :
                                               cs.backgroundColor !== 'rgba(0, 0, 0, 0)' ? cs.backgroundColor : 
                                               cs.borderColor !== 'rgba(0, 0, 0, 0)' ? cs.borderColor : "#000000";
                                               
                    elData.style.borderWidth = parseFloat(lcs.borderTopWidth) || parseFloat(lcs.height) || parseFloat(cs.borderTopWidth) || parseFloat(cs.height) || 2;
                }

                if (el.dataset.snap_l) elData.options.snap_l = el.dataset.snap_l;
                if (el.dataset.snap_r) elData.options.snap_r = el.dataset.snap_r;
            }

            // ── PHOTO ─────────────────────────────────────────────────
            if (type === 'photo') {
                const img = el.querySelector('img');
                const bgImage = cs.backgroundImage || el.style.backgroundImage;
                
                if (img && img.src) {
                    elData.src = await imageToDataUrl(img); 
                    
                    // 🚀 THE ULTIMATE PAN/ZOOM FIX: Absolute Screen Metrics
                    // Instead of trying to guess the CSS transform math, we just 
                    // measure exactly where the browser placed the image on the screen!
                    const iRect = img.getBoundingClientRect();
                    const fRect = elRect; // The photoframe's bounding box
                    
                    elData.options.photoMetrics = {
                        x: (iRect.left - fRect.left) / scaleX,
                        y: (iRect.top - fRect.top) / scaleY,
                        w: iRect.width / scaleX,
                        h: iRect.height / scaleY
                    };
                    
                } else if (bgImage && bgImage !== 'none') {
                    const match = bgImage.match(/^url\(["']?(.*?)["']?\)$/);
                    if (match && match[1]) {
                        elData.src = await imageToDataUrl({ src: match[1] });
                    }
                }

                const brStr = cs.borderRadius || el.style.borderRadius || "0";
                let br = parseFloat(brStr) || 0;
                if (brStr.includes('%')) br = (br / 100) * Math.min(w, h);
                const isCircle = br >= Math.min(w, h) / 2 - 2;

                elData.options.photoFrame = {
                    shape:  isCircle ? 'circle' : (br > 0 ? 'rounded' : 'square'),
                    radius: br,
                };

                const shadow = cs.boxShadow;
                if (shadow && shadow !== 'none') {
                    const pxMatches = [...shadow.matchAll(/([-\d.]+)px/g)].map(m => parseFloat(m[1]));
                    const colorMatch = shadow.match(/(rgba?\([^)]+\)|#[a-fA-F0-9]+)/);
                    if (pxMatches.length) elData.style.borderWidth = Math.abs(pxMatches[pxMatches.length - 1]);
                    if (colorMatch)       elData.style.borderColor = colorMatch[1];
                }
            }

            // ── IMAGE / SVG ───────────────────────────────────────────
            if (type === 'image') {
                const imgEl = el.querySelector('img');
                const svgEl = el.querySelector('svg');

                if (imgEl && imgEl.src) {
                    elData.src = await imageToDataUrl(imgEl); 
                } else if (svgEl) {
                    const csSvg = window.getComputedStyle(svgEl);
                    let exactW = parseFloat(csSvg.width);
                    let exactH = parseFloat(csSvg.height);
                    
                    if (!exactW || isNaN(exactW)) exactW = w;
                    if (!exactH || isNaN(exactH)) exactH = h;

                    // 🚀 ANTI-SHRINK FIX: 2px padding buffer
                    const padPx = 2;

                    const cx = x + w / 2;
                    const cy = y + h / 2;
                    elData.x = (cx - exactW / 2) - padPx;
                    elData.y = (cy - exactH / 2) - padPx;
                    elData.w = exactW + (padPx * 2);
                    elData.h = exactH + (padPx * 2);

                    // 🚀 Export as a pure transparent PNG using the padded math
                    elData.src = await svgElementToPngBase64(svgEl, exactW, exactH, padPx);
                } else if (el.dataset.originalSrc) {
                    elData.src = el.dataset.originalSrc;
                }
            }

            pageObj.elements.push(elData);
        }

        layout.pages.push(pageObj);
    }
    return layout;
}

  // ============================================================
  // BROWSER PRINT — Used by Standard and Browser HQ buttons
  // ============================================================
  function cleanPageForPrint(clone, mode) {
    // Strip page-level editor styles
    clone.style.outline = "none";
    clone.style.boxShadow = "none";
    clone.style.border = "none";
    clone.style.transform = "none";
    clone.style.margin = "0";
    clone.style.pageBreakAfter = "always";
    clone.style.overflow = "hidden";
    clone.style.maxHeight = "1123px";

    if (mode === 'hq') {
      clone.style.position = "relative";
      clone.style.top = "0";
      clone.style.left = "0";
      clone.style.width = "794px";
      clone.style.height = "1123px";
      clone.style.pageBreakInside = "avoid";
    }

    // 🚀 NEW: Mathematical Color Scanner for "Near-White"
    function isNearWhite(colorStr) {
      if (!colorStr) return false;
      const c = colorStr.toLowerCase().replace(/\s/g, '');
      if (c === 'white') return true;
      if (c === 'transparent' || c === 'none') return false;
      
      let r, g, b;
      if (c.startsWith('#')) {
        let hex = c.substring(1);
        if (hex.length === 3) hex = hex.split('').map(x => x + x).join('');
        if (hex.length >= 6) {
          r = parseInt(hex.substring(0, 2), 16);
          g = parseInt(hex.substring(2, 4), 16);
          b = parseInt(hex.substring(4, 6), 16);
        }
      } else if (c.startsWith('rgb')) {
        const match = c.match(/rgba?\((\d+),(\d+),(\d+)/);
        if (match) {
          r = parseInt(match[1]);
          g = parseInt(match[2]);
          b = parseInt(match[3]);
        }
      }
      
      // If Red, Green, and Blue are all above 225, it's in the white range
      if (r !== undefined && g !== undefined && b !== undefined) {
        return r > 225 && g > 225 && b > 225;
      }
      return false;
    }

    // Remove active selection highlights and SAFELY TAG NEAR-WHITE TEXT
    clone.querySelectorAll('*').forEach(el => {
      el.classList.remove("active", "multi", "editing");
      if (el.style.outline) el.style.outline = "none";

      const tColor = el.style.color || "";
      const tFill = el.getAttribute("fill") || "";
      
      // If it passes the math check, tag it
      if (isNearWhite(tColor) || isNearWhite(tFill)) {
          el.classList.add("print-white-text");
      }
    });

    // Fix anti-aliasing white lines on background shapes
    clone.querySelectorAll('.shape-el, .background-shape').forEach(el => {
      const bgColor = el.style.backgroundColor || el.style.background || el.getAttribute("fill");
      if (bgColor && bgColor !== "transparent" && bgColor !== "rgba(0, 0, 0, 0)") {
        el.style.boxShadow = `0 0 0 1px ${bgColor}`;
      }
    });
  }

  function triggerPrint() {
    // 1. Remove focus from any active elements on the live page
    if (document.activeElement) document.activeElement.blur();
    if (window.getSelection) window.getSelection().removeAllRanges();

    const printContainer = document.createElement("div");
    printContainer.id = "bulletproof-print-container";
    printContainer.style.cssText = "position: absolute; top: 0; left: 0; width: 100%; background: #fff; z-index: 999999999;";

    // 🚀 Math Scanner for White Text Illumination
    function isNearWhite(colorStr) {
      if (!colorStr) return false;
      const c = colorStr.toLowerCase().replace(/\s/g, '');
      if (c === 'white') return true;
      if (c === 'transparent' || c === 'none') return false;
      let r, g, b;
      if (c.startsWith('#')) {
        let hex = c.substring(1);
        if (hex.length === 3) hex = hex.split('').map(x => x + x).join('');
        if (hex.length >= 6) {
          r = parseInt(hex.substring(0, 2), 16);
          g = parseInt(hex.substring(2, 4), 16);
          b = parseInt(hex.substring(4, 6), 16);
        }
      } else if (c.startsWith('rgb')) {
        const match = c.match(/rgba?\((\d+),(\d+),(\d+)/);
        if (match) { r = parseInt(match[1]); g = parseInt(match[2]); b = parseInt(match[3]); }
      }
      if (r !== undefined && g !== undefined && b !== undefined) {
        return r > 225 && g > 225 && b > 225;
      }
      return false;
    }

    // 2. Clone pages and SCRUB all editor UI artifacts
    document.querySelectorAll('.a4').forEach(page => {
      const clone = page.cloneNode(true);
      
      clone.querySelectorAll('*').forEach(el => {
        // A. KILL EDITOR STATES: Remove active borders and selection classes
        el.classList.remove("active", "multi", "editing", "selected", "hover");
        if (el.style.outline) el.style.outline = "none";
        
        // B. KILL TEXT BOXES: Strip contenteditable so carets and typing behaviors disappear
        if (el.hasAttribute('contenteditable')) {
            el.removeAttribute('contenteditable');
        }

        // C. KILL DRAG HANDLES: Remove physical editor UI elements if they were cloned
        if (el.classList.contains('handle') || el.classList.contains('g-handle') || el.classList.contains('guide')) {
            el.remove();
        }

        // D. TAG WHITE TEXT: For our CSS illumination
        const tColor = el.style.color || "";
        const tFill = el.getAttribute("fill") || "";
        if (isNearWhite(tColor) || isNearWhite(tFill)) {
            el.classList.add("print-white-text");
        }
      });

      // Shape background enhancements removed.     
      printContainer.appendChild(clone);
    });

    document.body.appendChild(printContainer);

    const hideStyle = document.createElement("style");
    let styleContent = `
      body > *:not(#bulletproof-print-container) { display: none !important; }
      
      * { 
        -webkit-print-color-adjust: exact !important; 
        print-color-adjust: exact !important; 
      }

      /* 🚀 1. NATIVE BASE */
      .a4 * {
        -webkit-font-smoothing: antialiased !important;
        -moz-osx-font-smoothing: grayscale !important;
        text-rendering: optimizeLegibility !important;
        user-select: text !important;
        -webkit-user-select: text !important;
      }

      /* 🚀 2. NORMAL WHITE TEXT (Enhancements Removed) */
      .a4 .print-white-text {
          opacity: 1 !important;
      }

      /* 🚀 2.5 VECTOR GRAPHICS ENFORCEMENT */
      /* geometricPrecision keeps BOTH straight lines sharp AND rounded corners beautifully smooth */
      svg, img, hr, .shape-el, [class*="indicator"], [class*="bar"], [class*="line"], rect {
          shape-rendering: geometricPrecision !important;
          image-rendering: crisp-edges !important;
      }

      /* 🚀 3. STRICT PAGINATION LOCK (The Guillotine) */
      /* This completely stops elements from bleeding onto the next printed page */
      .a4 {
        position: relative !important;
        width: 794px !important;
        height: 1123px !important; /* Exact A4 Pixel Height */
        max-height: 1123px !important;
        overflow: hidden !important; /* Visually chops off anything crossing the line */
        
        /* Force the browser to respect the page break */
        page-break-after: always !important;
        break-after: page !important;
        page-break-inside: avoid !important;
        break-inside: avoid !important;
        
        margin: 0 auto !important;
      }



      @page { 
        size: A4 portrait; 
        margin: 0 !important; 
      }
      
      html, body { 
        background: #fff !important; 
        margin: 0 !important; 
        padding: 0 !important; 
      }
    `;
    hideStyle.innerHTML = styleContent;
    document.head.appendChild(hideStyle);

    setTimeout(() => {
      window.print();
      printContainer.remove();
      hideStyle.remove();
    }, 500);
  }


  // ============================================================
  // INIT
  // ============================================================
  function init() {
    injectUI();
  }

  window.initPrintExport = init;
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

})();