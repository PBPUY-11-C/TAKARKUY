() => {
  const parse = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const blend = (top, bottom) => { const a = top[3]; return [top[0] * a + bottom[0] * (1 - a), top[1] * a + bottom[1] * (1 - a), top[2] * a + bottom[2] * (1 - a), 1]; };
  function background(el) {
    const layers = [];
    for (let n = el; n; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.backgroundImage !== 'none' && !cs.backgroundImage.startsWith('url')) {
        const stops = [...cs.backgroundImage.matchAll(/rgba?\([^)]+\)/g)].map((m) => parse(m[0])).filter((c) => c[3] > 0.5);
        if (stops.length) { const avg = stops.reduce((acc, c) => [acc[0] + c[0] / stops.length, acc[1] + c[1] / stops.length, acc[2] + c[2] / stops.length, 1], [0, 0, 0, 1]); layers.push(avg); break; }
      }
      const c = parse(cs.backgroundColor);
      if (c && c[3] > 0) { layers.push(c); if (c[3] >= 1) break; }
      if (n.tagName === 'DIALOG' && n.open) { if (!c || c[3] === 0) layers.push([255, 255, 255, 1]); break; }
    }
    let base = [255, 255, 255, 1];
    for (let i = layers.length - 1; i >= 0; i--) base = blend(layers[i], base);
    return { color: base };
  }
  const describe = (el) => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  const out = [];
  const seen = new Set();
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || Number(cs.opacity) === 0) continue;
    const rect = el.getBoundingClientRect();
    if (!rect.width || !rect.height) continue;
    if (el.closest('dialog:not([open]), [hidden], .sr-only, [inert], .skip-link')) continue;
    const isField = ['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName) && !['checkbox', 'radio', 'hidden', 'range', 'file'].includes(el.type);
    const text = isField ? (el.value || el.placeholder || '') : [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim();
    if (!text) continue;
    const fg = parse(cs.color);
    if (!fg) continue;
    const bg = background(el);
    if (bg.gradient) continue;
    const color = fg[3] < 1 ? blend(fg, bg.color) : fg;
    const [a, b] = [lum(color), lum(bg.color)].sort((x, y) => y - x);
    const ratio = (a + 0.05) / (b + 0.05);
    const size = parseFloat(cs.fontSize), bold = Number(cs.fontWeight) >= 600;
    const need = size >= 24 || (size >= 18.6 && bold) ? 3 : 4.5;
    if (ratio < need) {
      const key = describe(el) + '|' + cs.color + '|' + bg.color.slice(0, 3).map(Math.round);
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ el: describe(el), parent: el.parentElement ? describe(el.parentElement) : '', text: text.slice(0, 40), ratio: Math.round(ratio * 100) / 100, fg: cs.color, bg: 'rgb(' + bg.color.slice(0, 3).map(Math.round).join(',') + ')' });
    }
  }
  return out;
}
