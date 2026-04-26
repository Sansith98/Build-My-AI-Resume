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

    <button id="mainExportBtn" title="Download Resume as PDF">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
        <polyline points="7 10 12 15 17 10"></polyline>
        <line x1="12" y1="15" x2="12" y2="3"></line>
      </svg>
      Download PDF
    </button>
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
            <div class="export-opt-desc">High-fidelity vector rendering perfectly optimized for printing and ATS software. Delivers the sharpest text and graphics.</div>
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
      triggerPlaywrightExport();
    });

    stdBtn.addEventListener("click", () => {
      hideModal();
      triggerPrint('standard');
    });
  }


  // ============================================================
  // PLAYWRIGHT EXPORT
  // Collects full page HTML (with styles + fonts), saves it to
  // the server via /api/save_export, then redirects to
  // /export/hq-pdf/<eid> for server-side PDF generation.
  // ============================================================
  async function triggerPlaywrightExport() {
    // Points to the new main button on the toolbar instead of the old deleted one
    const btn = document.getElementById("mainExportBtn");
    const originalHTML = btn.innerHTML;

    // 1. Show loading state
    btn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            style="animation: spin 1s linear infinite;">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"></path>
        </svg>
        Generating...`;
    btn.style.opacity = "0.7";
    btn.style.pointerEvents = "none";

    // Inject spin animation if not already present
    if (!document.getElementById("pw-spin-style")) {
      const spinStyle = document.createElement("style");
      spinStyle.id = "pw-spin-style";
      spinStyle.innerHTML = `@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`;
      document.head.appendChild(spinStyle);
    }

    try {
      // 2. Grab ALL resume page elements (not just the first!)
      const pageEls = document.querySelectorAll(PAGE_SELECTOR);
      if (!pageEls.length) {
        alert("Resume page not found! Make sure your resume is loaded.");
        return;
      }

      // 3. Collect ALL <style> tags from the page
      //    (This includes your template CSS, studio CSS, everything)
      const styleTags = Array.from(document.querySelectorAll("style"))
        .map(s => s.outerHTML)
        .join("\n");

      // 4. Collect ALL <link rel="stylesheet"> tags AND inline the font CSS
      //    so Playwright has one less network hop to make for fonts
      const linkEls = Array.from(document.querySelectorAll('link[rel="stylesheet"]'));
      
      const inlinedFontStyles = await Promise.all(
        linkEls.map(async (link) => {
          try {
            // Fix Google Fonts URLs to always include weight 800
            let href = link.href;
            if (href.includes('fonts.googleapis.com') && href.includes('Inter') && !href.includes('800')) {
              href = href.replace(/wght@([^&"]+)/, (match, weights) => {
                const list = weights.split(';').filter(w => w);
                if (!list.includes('800')) list.push('800');
                return 'wght@' + list.sort((a,b) => a-b).join(';');
              });
            }
            const resp = await fetch(href);
            const css = await resp.text();
            return `<style>\n/* Inlined from ${href} */\n${css}\n</style>`;
          } catch (err) {
            return link.outerHTML; // fallback to standard link tag if fetch fails
          }
        })
      );
      const linkTags = inlinedFontStyles.join("\n");

      
// 5. Clean ALL page clones — strip editor UI artifacts from each
      const allPagesHTML = Array.from(pageEls).map((pageEl) => {
        const clone = pageEl.cloneNode(true);

        // 🚀 THE GLOBAL ENHANCER: Mathematically boosts contrast for Text, Shapes, and SVGs safely
        const targetSelector = 'p, span, h1, h2, h3, h4, h5, h6, li, a, text, tspan, .text-el, .shape-el, .background-shape, div, svg, path, rect, circle, polygon, line';
        const liveEls = pageEl.querySelectorAll(targetSelector);
        const cloneEls = clone.querySelectorAll(targetSelector);

        for (let i = 0; i < liveEls.length; i++) {
          const liveEl = liveEls[i];
          const cloneEl = cloneEls[i];

          const computed = window.getComputedStyle(liveEl);
          
          const processColor = (rgbStr, property, isTextNode) => {
            if (!rgbStr || rgbStr === 'none' || !rgbStr.startsWith('rgb') || rgbStr === 'rgba(0, 0, 0, 0)') return;
            const match = rgbStr.match(/\d+/g);
            if (!match || match.length < 3) return;
            let [r, g, b] = match.map(Number);

            // 1. IS IT WHITE TEXT? Use paint-order stroke trick for PDF presence without blur
            if (isTextNode && r > 200 && g > 200 && b > 200) {
                if (property === 'fill' || property === 'stroke') {
                    cloneEl.style.setProperty('fill', 'rgb(255, 255, 255)', 'important');
                    cloneEl.style.setProperty('stroke', 'rgb(255, 255, 255)', 'important');
                    cloneEl.style.setProperty('stroke-width', '0.35px', 'important');
                    cloneEl.style.setProperty('stroke-linejoin', 'round', 'important');
                    cloneEl.style.setProperty('stroke-opacity', '0.55', 'important');
                    cloneEl.style.setProperty('paint-order', 'stroke fill', 'important');
                } else if (property === 'color') {
                    cloneEl.style.setProperty('color', 'rgb(255, 255, 255)', 'important');
                    cloneEl.style.setProperty('-webkit-text-stroke', '0.35px rgba(255, 255, 255, 0.55)', 'important');
                    // NO text-shadow — it blurs the glyph edge in Playwright PDF output
                }
                return;
            }

            // 2. NON-WHITE TEXT: minimal colour boost, preserve natural weight
            if (isTextNode) {
                const avg = (r + g + b) / 3;
                r = Math.round(avg + (r - avg) * 1.03);
                g = Math.round(avg + (g - avg) * 1.03);
                b = Math.round(avg + (b - avg) * 1.03);
                r = Math.min(255, Math.max(0, Math.round(r * 0.99)));
                g = Math.min(255, Math.max(0, Math.round(g * 0.99)));
                b = Math.min(255, Math.max(0, Math.round(b * 0.99)));
                if (property === 'color') {
                    cloneEl.style.setProperty('color', `rgb(${r}, ${g}, ${b})`, 'important');
                } else if (property === 'fill') {
                    cloneEl.style.setProperty('fill', `rgb(${r}, ${g}, ${b})`, 'important');
                }
                return;
            }

            // 3. SHAPES & BACKGROUNDS ONLY: Enhance Saturation & Density
            // (Skip pure white backgrounds so we don't accidentally darken the paper)
            if (r > 245 && g > 245 && b > 245) return;

            // Boost Saturation by 8% for richer colors (Blues get bluer, Reds get redder)
            const avg = (r + g + b) / 3;
            r = avg + (r - avg) * 1.08;
            g = avg + (g - avg) * 1.08;
            b = avg + (b - avg) * 1.08;

            // Darken by 4% to increase "ink density" (ensures text NEVER fades, shapes get punchy)
            r = Math.min(255, Math.max(0, Math.floor(r * 0.96)));
            g = Math.min(255, Math.max(0, Math.floor(g * 0.96)));
            b = Math.min(255, Math.max(0, Math.floor(b * 0.96)));

            cloneEl.style.setProperty(property, `rgb(${r}, ${g}, ${b})`, 'important');
          };

          const tagName = liveEl.tagName.toUpperCase();
          const isTextNode = ['P', 'SPAN', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'LI', 'A', 'TEXT', 'TSPAN'].includes(tagName) || liveEl.classList.contains('text-el');

          // Apply math securely to every vector element
          processColor(computed.color, 'color', isTextNode);
          processColor(computed.backgroundColor, 'background-color', false);
          processColor(computed.fill, 'fill', isTextNode);
          processColor(computed.stroke, 'stroke', isTextNode);
        }

        // Clean up UI artifacts from the clone + force subpixel rendering on all text
        clone.querySelectorAll('*').forEach(el => {
          el.classList.remove("active", "multi", "editing");
          if (el.style.outline) el.style.outline = "none";
          if (el.style.boxShadow && el.style.boxShadow.includes("rgb(59")) {
            el.style.boxShadow = "none";
          }
          // Force subpixel font rendering inline — overrides any stylesheet antialiased setting
          el.style.setProperty('-webkit-font-smoothing', 'subpixel-antialiased', 'important');
          el.style.setProperty('-moz-osx-font-smoothing', 'auto', 'important');
        });
        clone.querySelectorAll('.handle, .g-handle, #multiBox, #marquee, .guide').forEach(el => el.remove());
        return clone.outerHTML;
      }).join("\n");

      // 6. Build a complete self-contained HTML document
      //    Playwright receives this and renders it exactly as seen on screen
      const fullHTML = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  ${linkTags}
  ${styleTags}
  <style>
    /* Playwright render overrides */
    @page { size: 794px 1123px; margin: 0 !important; }
    html, body {
      margin: 0 !important;
      padding: 0 !important;
      background: #fff !important;
      width: 794px !important;
    }
    /* 
      THE BLUR FIX:
      #pages-export wraps all .a4 divs exactly as #pages does in the studio.
      This gives .a4 divs the same offset parent context they had in the editor,
      so position:absolute children land on exact integer pixels — no blur.
    */
    #pages-export {
      position: relative !important;
      width: 794px !important;
      margin: 0 !important;
      padding: 0 !important;
      background: #fff !important;
    }
    .a4 {
      position: relative !important;
      top: 0 !important;
      left: 0 !important;
      width: 794px !important;
      height: 1123px !important;
      margin: 0 !important;
      box-shadow: none !important;
      outline: none !important;
      border: none !important;
      overflow: hidden !important;
      page-break-after: always !important;
      break-after: page !important;
      transform: none !important;
    }
    * {
      -webkit-print-color-adjust: exact !important;
      print-color-adjust: exact !important;
      -webkit-font-smoothing: subpixel-antialiased !important;
      -moz-osx-font-smoothing: auto !important;
      text-rendering: geometricPrecision !important;
      font-kerning: normal !important;
    }
    svg text, svg tspan {
      paint-order: stroke fill !important;
    }
    

    img {
      image-rendering: high-quality !important;
      image-rendering: -webkit-optimize-contrast !important;
      filter: contrast(1.04) saturate(1.05) !important;
    }
  </style>
</head>
<body style="margin:0; padding:0; background:#fff;">
  <div id="pages-export">
    ${allPagesHTML}
  </div>
</body>
</html>`;

      // 7. Save the HTML to the server — get back a real eid
      const res = await fetch("/api/save_export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ html: fullHTML, slug: "resume" })
      });

      if (!res.ok) {
        alert("Server error while preparing export. Please try again.");
        return;
      }

      const result = await res.json();
      if (!result.ok || !result.eid) {
        alert("Failed to prepare export. Please try again.");
        return;
      }

      // 8. Redirect to Playwright PDF route — download starts automatically
      window.location.href = `/export/hq-pdf/${result.eid}`;

    } catch (err) {
      console.error("Playwright export error:", err);
      alert("Export failed: " + err.message);

    } finally {
      // Reset button after a delay (in case redirect is slow)
      setTimeout(() => {
        btn.innerHTML = originalHTML;
        btn.style.opacity = "1";
        btn.style.pointerEvents = "auto";
      }, 4000);
    }
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

    // Remove active selection highlights
    clone.querySelectorAll('*').forEach(el => {
      el.classList.remove("active");
      if (el.style.outline) el.style.outline = "none";
    });

    // Fix anti-aliasing white lines on background shapes
    clone.querySelectorAll('.shape-el, .background-shape').forEach(el => {
      const bgColor = el.style.backgroundColor || el.style.background || el.getAttribute("fill");
      if (bgColor && bgColor !== "transparent" && bgColor !== "rgba(0, 0, 0, 0)") {
        el.style.boxShadow = `0 0 0 1px ${bgColor}`;
      }
    });
  }

  function triggerPrint(mode) {
    if (document.activeElement) document.activeElement.blur();
    if (window.getSelection) window.getSelection().removeAllRanges();

    const printContainer = document.createElement("div");
    printContainer.id = "bulletproof-print-container";

    if (mode === 'hq') {
      printContainer.style.cssText = "position: absolute; top: 0; left: 0; margin: 0; padding: 0; width: 794px; background: #fff; z-index: 999999999;";
    } else {
      printContainer.style.cssText = "position: absolute; top: 0; left: 0; width: 100%; background: #fff; z-index: 999999999;";
    }

    document.querySelectorAll(PAGE_SELECTOR).forEach(page => {
      const clone = page.cloneNode(true);
      cleanPageForPrint(clone, mode);
      printContainer.appendChild(clone);
    });

    document.body.appendChild(printContainer);

    const hideStyle = document.createElement("style");
    let styleContent = `
      body > *:not(#bulletproof-print-container) { display: none !important; }
      * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
    `;

    if (mode === 'hq') {
      styleContent += `
        @page { size: 794px 1123px; margin: 0 !important; }
        html, body { background: #fff !important; margin: 0 !important; padding: 0 !important; width: 794px !important; }
        * { -webkit-font-smoothing: antialiased !important; -moz-osx-font-smoothing: grayscale !important; text-rendering: optimizeLegibility !important; }
        img { image-rendering: high-quality !important; image-rendering: -webkit-optimize-contrast !important; }
        .a4, .a4 * { zoom: 1 !important; filter: none !important; }
      `;
    } else {
      styleContent += `
        @page { size: A4 portrait; margin: 0 !important; }
        html, body { background: #fff !important; margin: 0 !important; padding: 0 !important; }
        .a4 { overflow: hidden !important; max-height: 1123px !important; }
      `;
    }

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