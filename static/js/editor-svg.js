async function loadGeneratedSvgPages({ theme, data }) {
  try {
    const res = await fetch('/generate_resume_svg', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme, data })
    });
    const json = await res.json();
    if (!json.ok) {
      console.error(json);
      alert(json.error || 'SVG generation failed');
      return;
    }
    const wrap = document.querySelector('#pages-wrap');
    wrap.innerHTML = '';
    (json.pages || []).forEach(svgStr => {
      const page = document.createElement('div');
      page.className = 'a4';
      page.innerHTML = svgStr; // inline SVG string
      wrap.appendChild(page);
    });
  } catch (e) {
    console.error(e);
    alert('Preview request failed');
  }
}
