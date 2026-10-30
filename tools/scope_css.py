"""Ubah takarkuy-modul4-lengkap.css menjadi CSS yang hanya berlaku di Modul 4 (konten .book-shell + #cooking-dialog)."""
import re, sys
SRC, ADAPTER, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
SC = ':is(.book-shell, #cooking-dialog)'
css = open(SRC, encoding='utf-8').read()
css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)

def parse(s):
    """-> list of (prelude, body|None). body is str for leaf blocks."""
    out, i, n = [], 0, len(s)
    while i < n:
        while i < n and s[i] in ' \t\r\n': i += 1
        if i >= n: break
        j = i; depth = 0
        while j < n and s[j] not in '{;': j += 1
        prelude = s[i:j].strip()
        if j < n and s[j] == ';': out.append((prelude, None)); i = j + 1; continue
        k = j + 1; depth = 1
        while k < n and depth:
            if s[k] == '{': depth += 1
            elif s[k] == '}': depth -= 1
            k += 1
        out.append((prelude, s[j+1:k-1])); i = k
    return out

def split_sel(sel):
    parts, d, cur = [], 0, ''
    for ch in sel:
        if ch in '([': d += 1
        if ch in ')]': d -= 1
        if ch == ',' and d == 0: parts.append(cur); cur = ''
        else: cur += ch
    return [p.strip() for p in parts + [cur] if p.strip()]

DROP = re.compile(r'\.(site-header|nav\b|nav__|theme-toggle|switch|user\b|user__|logout|skip-link|icon--sun|icon--moon)|body\.has-modal|is-theme-switching|^html\b')
THEME = re.compile(r'^\[data-theme="(dark|light)"\]')
def map_sel(s):
    if DROP.search(s): return []
    if s.startswith('::view-transition'): return [s]
    m = THEME.match(s)
    if m:
        rest = s[m.end():].strip()
        if not rest: return [f'[data-theme="{m.group(1)}"] .book-shell', f'[data-theme="{m.group(1)}"] #cooking-dialog']
        return [f'[data-theme="{m.group(1)}"] ' + x for x in map_sel(rest)]
    if s in (':root', 'body'): return ['.book-shell', '#cooking-dialog']
    if s.startswith('.modal__'): return ['#cooking-dialog ' + s]
    if s.startswith('.modal'): return ['#cooking-dialog' + s]
    return [f'{SC} {s}']

KEYFRAMES = sorted(set(re.findall(r'@keyframes\s+([\w-]+)', css)), key=len, reverse=True)
def ren_anim(body):
    def fix(m):
        val = m.group(2)
        for k in KEYFRAMES: val = re.sub(rf'(?<![\w-]){re.escape(k)}(?![\w-])', 'm4-' + k, val)
        return m.group(1) + val
    return re.sub(r'(animation(?:-name)?\s*:)([^;}]*)', fix, body)

def emit(items, ind=''):
    out = []
    for pre, body in items:
        if body is None: out.append(f'{ind}{pre};'); continue
        if pre.startswith('@keyframes'):
            name = pre.split()[1]; out.append(f'{ind}@keyframes m4-{name} {{{body.strip()}}}'); continue
        if pre.startswith('@media') and 'prefers-color-scheme' in pre: continue   # tema ikut aplikasi, bukan sistem
        if pre.startswith('@view-transition'): out.append(f'{ind}{pre} {{{body.strip()}}}'); continue
        if pre.startswith('@'):
            inner = emit(parse(body), ind + '  ')
            if inner.strip(): out.append(f'{ind}{pre} {{\n{inner}\n{ind}}}')
            continue
        sels = [x for s in split_sel(pre) for x in map_sel(s)]
        if not sels: continue
        out.append(f'{ind}{", ".join(sels)} {{ {ren_anim(body).strip()} }}')
    return '\n'.join(out)

body = emit(parse(css))
adapter = open(ADAPTER, encoding='utf-8').read().replace('&SC', SC)
head = """/*
 * TAKARKUY · Modul 4 (Recipe Book) · CSS tampilan Figma
 * DIBUAT OTOMATIS oleh alat/scope_css.py dari takarkuy-modul4-lengkap.css + modul4-adapter.css.
 * Ubah sumbernya lalu jalankan ulang; jangan sunting bagian I–III langsung.
 *
 * Lingkup: setiap selector diawali :is(.book-shell, #cooking-dialog), jadi header bersama
 * (partials/app_header.html), Planner, dan Pantry tidak tersentuh. Keyframes diberi awalan m4-.
 * Dihapus dari sumber: header/nav/switch tema/skip-link (milik base.css), aturan html/body global,
 * dan @media (prefers-color-scheme) karena tema mengikuti aplikasi ([data-theme] pada leluhur).
 */
"""
with open(OUT, 'w', encoding='utf-8', newline='\n') as output:
    output.write(head + '\n/* ===== BAGIAN I–III · dari takarkuy-modul4-lengkap.css (terlingkup) ===== */\n' + body +
                  '\n\n/* ===== BAGIAN IV · ADAPTER untuk markup & JavaScript Recipe Book ===== */\n' + adapter)
with open(OUT, encoding='utf-8') as generated_file:
    generated = '\n'.join(line.rstrip() for line in generated_file.read().splitlines()) + '\n'
with open(OUT, 'w', encoding='utf-8', newline='\n') as generated_file:
    generated_file.write(generated)
print('keyframes:', len(KEYFRAMES), 'output bytes:', len(generated.encode('utf-8')))
