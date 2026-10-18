/* Fit Coach – Daisy (fit-daisy.js)
 * Tamagotchi-Karte: Daisy, die Hündin, reagiert auf Janas Fortschritt und motiviert –
 * trainerhaft, aber lieb und mit Humor. Gezeichnet als SVG nach Daisys Fotos (keine Bilddateien).
 * Liest nur die vorhandenen sensor.fit_coach_*-Werte, braucht keine Helfer. Streicheln und Leckerli werden pro Gerät im Browser gemerkt.
 * Gesundheits-Leitplanken: Daisy lobt nie Hungern oder schnelles Abnehmen, schimpft nie
 * wegen Gewicht oder Essen und erinnert bei sehr wenig Essen ans Essen.
 * 0.1.0 (18.10.2026): erste Fassung (Fotos).
 * 0.2.0 (18.10.2026): Daisy als animierte Zeichnung statt Fotos (Schwanzwedeln, Blinzeln, Hecheln, Ohren, Atmen).
 */
const DAISY_VERSION = '0.2.0';
const P = 'sensor.fit_coach_';
const E = { status: `${P}status`, heute: `${P}heute`, woche: `${P}woche`, weight: `${P}abnahme`, food: `${P}ernaehrung`, run: `${P}laufen`, gym: `${P}gym`, badges: `${P}erfolge`, serie: `${P}serie` };
const PAL = {
  light: { run: '#1baf7a', weight: '#2a78d6', habit: '#6250d6', food: '#eb6834', good: '#0ca30c', warn: '#fab219', goodText: '#006300', track: 'rgba(11,11,11,0.08)', bubble: '#f3f1ec', heart: '#e0457b' },
  dark: { run: '#199e70', weight: '#3987e5', habit: '#9085e9', food: '#d95926', good: '#0ca30c', warn: '#fab219', goodText: '#3fbf3f', track: 'rgba(255,255,255,0.10)', bubble: '#2a2a28', heart: '#f06a96' },
};
const LEVELS = ['Welpe', 'Schnüffel-Azubi', 'Leinen-Profi', 'Gassi-Champion', 'Park-Legende', 'Rudelchefin', 'Daisys Heldin'];

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const num = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : null; };
const fmt = (v, d = 0) => (v == null || !Number.isFinite(+v) ? '–' : Number(v).toLocaleString('de-DE', { minimumFractionDigits: d, maximumFractionDigits: d }));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const icon = (n, s = 18) => `<ha-icon icon="mdi:${n}" style="--mdc-icon-size:${s}px;width:${s}px;height:${s}px;display:inline-flex;flex:none"></ha-icon>`;
const iso = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const pd = (s) => { if (!s) return null; const [y, m, d] = String(s).slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d); };
const daysSince = (s) => { const d = pd(s); if (!d) return null; const t = new Date(); t.setHours(0, 0, 0, 0); return Math.round((t - d) / 864e5); };
const monday = () => { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return iso(d); };
const pick = (arr, seed) => arr[Math.abs(seed) % arr.length];
const hash = (s) => { let h = 0; for (const ch of s) h = (h * 31 + ch.charCodeAt(0)) | 0; return h; };
const store = {
  get(k, d) { try { const v = localStorage.getItem(`fit-daisy:${k}`); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(`fit-daisy:${k}`, JSON.stringify(v)); } catch (e) { /* privat/gesperrt: dann eben nur für jetzt */ } },
};

/* ---------- Daisy als animierte Zeichnung (SVG) ----------
 * Nach den Fotos: struppiges goldenes Fell, helle Schnauze und Bart, Schlappohren mit dunkleren Spitzen, hellblaues Blümchen-Halstuch, graues Halsband. */
const COL = { fur: '#dba864', furHi: '#ecc78c', furDk: '#b8803f', ear: '#a96f34', cream: '#f5e2bb', nose: '#2b2220', eye: '#2a1f1a', tongue: '#e86f84', tongueDk: '#c9536a', bandana: '#a9cfee', bandanaDk: '#86b4dc', collar: '#7f95a6', blush: '#f19aa6' };

// Struppiger Umriss: Ellipse mit Fell-Zacken (deterministisch).
function fuzz(cx, cy, rx, ry, n = 22, amp = 0.09, rot = 0) {
  const pts = [];
  for (let i = 0; i < n; i += 1) {
    const a = (i / n) * Math.PI * 2 + rot;
    const k = 1 + (i % 2 ? amp : -amp * 0.35) + (i % 3 === 0 ? amp * 0.3 : 0);
    pts.push([cx + Math.cos(a) * rx * k, cy + Math.sin(a) * ry * k]);
  }
  let d = '';
  for (let i = 0; i < n; i += 1) {
    const p = pts[i]; const q = pts[(i + 1) % n];
    const mid = [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
    d += i === 0 ? `M${mid[0].toFixed(1)},${mid[1].toFixed(1)}` : '';
    const nx = pts[(i + 1) % n]; const nn = pts[(i + 2) % n];
    const m2 = [(nx[0] + nn[0]) / 2, (nx[1] + nn[1]) / 2];
    d += `Q${nx[0].toFixed(1)},${nx[1].toFixed(1)} ${m2[0].toFixed(1)},${m2[1].toFixed(1)}`;
  }
  return `${d}Z`;
}

const eyes = (kind, x1, x2, y, sad) => {
  const brow = (x, s) => `<path d="M${x - 7},${y - 11 + (sad ? s * 3 : 0)} Q${x},${y - 15 - (sad ? 0 : 1)} ${x + 7},${y - 11 - (sad ? s * 3 : 0)}" stroke="${COL.furDk}" stroke-width="4.2" fill="none" stroke-linecap="round" stroke-dasharray="3 1.5"/>`;
  const one = (x) => {
    if (kind === 'closed') return `<path d="M${x - 6},${y} Q${x},${y + 4} ${x + 6},${y}" stroke="${COL.eye}" stroke-width="2.6" fill="none" stroke-linecap="round"/>`;
    if (kind === 'happy') return `<path d="M${x - 6},${y + 2} Q${x},${y - 5} ${x + 6},${y + 2}" stroke="${COL.eye}" stroke-width="2.8" fill="none" stroke-linecap="round"/>`;
    if (kind === 'half') return `<g><ellipse cx="${x}" cy="${y + 1}" rx="5.5" ry="4" fill="${COL.eye}"/><path d="M${x - 7},${y - 1} L${x + 7},${y - 1}" stroke="${COL.fur}" stroke-width="4"/><circle cx="${x + 2}" cy="${y + 1}" r="1.3" fill="#fff"/></g>`;
    return `<g class="d-blink" style="transform-origin:${x}px ${y}px"><ellipse cx="${x}" cy="${y}" rx="6" ry="7" fill="${COL.eye}"/><circle cx="${x + 2.2}" cy="${y - 2.6}" r="2.2" fill="#fff"/><circle cx="${x - 2}" cy="${y + 2.5}" r="1" fill="#fff" opacity=".7"/></g>`;
  };
  return `${brow(x1, 1)}${brow(x2, -1)}${one(x1)}${one(x2)}`;
};

const flowers = (pts) => pts.map(([x, y, c]) => `<g transform="translate(${x},${y})"><circle r="2.6" fill="${c}"/><circle r="1" fill="#fff6c2"/></g>`).join('');

function sitting(o) {
  const tongue = o.tongue ? `<g class="d-pant" style="transform-origin:100px 109px"><path d="M93,109 Q93,128 100,129 Q107,128 107,109 Z" fill="${COL.tongue}"/><path d="M100,112 L100,124" stroke="${COL.tongueDk}" stroke-width="1.4" stroke-linecap="round"/></g>` : '';
  return `
  <g class="d-tail" style="transform-origin:136px 160px"><path d="M134,162 C156,156 166,136 160,116" stroke="${COL.fur}" stroke-width="13" fill="none" stroke-linecap="round"/><path d="${fuzz(160, 113, 9, 9, 12, 0.18)}" fill="${COL.fur}"/></g>
  <g class="d-body">
    <ellipse cx="64" cy="180" rx="19" ry="10" fill="${COL.furDk}"/><ellipse cx="136" cy="180" rx="19" ry="10" fill="${COL.furDk}"/>
    <path d="${fuzz(100, 152, 44, 36, 26, 0.07)}" fill="${COL.fur}"/>
    <ellipse cx="100" cy="156" rx="22" ry="25" fill="${COL.furHi}"/>
    <rect x="78" y="150" width="19" height="36" rx="9.5" fill="${COL.fur}"/><rect x="103" y="150" width="19" height="36" rx="9.5" fill="${COL.fur}"/>
    <ellipse cx="87.5" cy="186" rx="12" ry="7" fill="${COL.cream}"/><ellipse cx="112.5" cy="186" rx="12" ry="7" fill="${COL.cream}"/>
    <path d="M84,183 v5 M91,183 v5 M109,183 v5 M116,183 v5" stroke="${COL.furDk}" stroke-width="1.4" stroke-linecap="round"/>
    <path d="M64,118 Q100,128 136,118 L104,158 Q100,162 96,158 Z" fill="${COL.bandana}"/>
    <path d="M64,118 Q100,128 136,118 Q100,134 64,118 Z" fill="${COL.bandanaDk}"/>
    ${flowers([[84, 130, '#ec8fb0'], [112, 132, '#f0b84a'], [98, 142, '#ec8fb0'], [122, 125, '#9b7fd6'], [76, 122, '#f0b84a'], [104, 151, '#9b7fd6']])}
  </g>
  <g class="d-head" style="transform-origin:100px 118px">
    <g class="d-ear-l" style="transform-origin:66px 62px"><path d="M70,56 Q46,58 44,90 Q44,108 56,110 Q68,104 70,84 Z" fill="${COL.ear}"/><path d="M50,100 l-3,8 m7,-6 l0,9" stroke="${COL.ear}" stroke-width="3" stroke-linecap="round"/></g>
    <g class="d-ear-r" style="transform-origin:134px 62px"><path d="M130,56 Q154,58 156,90 Q156,108 144,110 Q132,104 130,84 Z" fill="${COL.ear}"/><path d="M150,100 l3,8 m-7,-6 l0,9" stroke="${COL.ear}" stroke-width="3" stroke-linecap="round"/></g>
    <path d="${fuzz(100, 82, 41, 37, 30, 0.08)}" fill="${COL.fur}"/>
    <path d="M86,48 l4,-9 l3,8 l4,-10 l3,9 l4,-8 l2,9" stroke="${COL.fur}" stroke-width="5" stroke-linejoin="round" fill="none"/>
    <ellipse cx="100" cy="72" rx="9" ry="16" fill="${COL.furHi}"/>
    <path d="${fuzz(100, 104, 25, 17, 20, 0.08)}" fill="${COL.cream}"/>
    <circle cx="70" cy="100" r="6" fill="${COL.blush}" opacity=".35"/><circle cx="130" cy="100" r="6" fill="${COL.blush}" opacity=".35"/>
    ${eyes(o.eyes, 82, 118, 82, o.sad)}
    <path d="M100,101 L100,107 M100,107 Q93,111 88,107 M100,107 Q107,111 112,107" stroke="${COL.nose}" stroke-width="2.2" fill="none" stroke-linecap="round"/>
    <path d="M91,94 Q100,89 109,94 Q108,101 100,103 Q92,101 91,94 Z" fill="${COL.nose}"/>
    <ellipse cx="96" cy="94" rx="3" ry="1.6" fill="#fff" opacity=".45"/>
    <path d="M82,114 l-3,7 l6,-3 l1,7 l5,-5 l3,6 l3,-6 l3,6 l3,-6 l3,5 l5,-5 l1,7 l6,-3 l-3,-7" fill="${COL.cream}" stroke="${COL.cream}" stroke-width="2" stroke-linejoin="round"/>
    <path d="M60,86 l-7,3 l6,3 l-6,5 l8,0 M140,86 l7,3 l-6,3 l6,5 l-8,0" stroke="${COL.fur}" stroke-width="4" fill="${COL.fur}" stroke-linejoin="round"/>
    ${tongue}
  </g>`;
}

function lying(o) {
  const eye = o.eyes === 'open' ? `<g class="d-blink" style="transform-origin:150px 132px"><ellipse cx="150" cy="132" rx="5" ry="6" fill="${COL.eye}"/><circle cx="152" cy="130" r="1.8" fill="#fff"/></g>`
    : o.eyes === 'half' ? `<g><ellipse cx="150" cy="133" rx="5" ry="3.6" fill="${COL.eye}"/><path d="M144,131 L156,131" stroke="${COL.fur}" stroke-width="3.5"/></g>`
      : o.eyes === 'happy' ? `<path d="M144,134 Q150,128 156,134" stroke="${COL.eye}" stroke-width="2.6" fill="none" stroke-linecap="round"/>`
        : `<path d="M144,132 Q150,137 156,132" stroke="${COL.eye}" stroke-width="2.6" fill="none" stroke-linecap="round"/>`;
  const brow = o.sad ? `<path d="M142,122 Q148,118 157,122" stroke="${COL.furDk}" stroke-width="3" fill="none" stroke-linecap="round"/>` : `<path d="M143,121 Q150,117 157,120" stroke="${COL.furDk}" stroke-width="3" fill="none" stroke-linecap="round"/>`;
  const tongue = o.tongue ? `<g class="d-pant" style="transform-origin:172px 157px"><path d="M168,156 Q167,170 173,171 Q179,170 177,156 Z" fill="${COL.tongue}"/></g>` : '';
  return `
  <g class="d-tail" style="transform-origin:46px 150px"><path d="M48,152 C30,150 22,134 32,122" stroke="${COL.fur}" stroke-width="12" fill="none" stroke-linecap="round"/><path d="${fuzz(32, 119, 8, 8, 12, 0.18)}" fill="${COL.fur}"/></g>
  <g class="d-breathe" style="transform-origin:100px 176px">
    <path d="${fuzz(96, 152, 56, 25, 30, 0.06)}" fill="${COL.fur}"/>
    <path d="${fuzz(70, 162, 24, 14, 16, 0.07)}" fill="${COL.furDk}"/>
    <ellipse cx="54" cy="174" rx="15" ry="6" fill="${COL.cream}"/>
    <ellipse cx="96" cy="160" rx="34" ry="10" fill="${COL.furHi}" opacity=".7"/>
  </g>
  <ellipse cx="148" cy="174" rx="22" ry="7" fill="${COL.cream}"/><ellipse cx="166" cy="178" rx="18" ry="6" fill="${COL.cream}"/>
  <path d="M160,175 v5 M166,175 v5 M172,175 v5" stroke="${COL.furDk}" stroke-width="1.3" stroke-linecap="round"/>
  <g class="d-head-lie" style="transform-origin:140px 165px">
    <path d="${fuzz(146, 138, 35, 31, 28, 0.09)}" fill="${COL.fur}"/>
    <path d="M118,140 Q130,132 126,164" stroke="${COL.collar}" stroke-width="6" fill="none" stroke-linecap="round"/>
    <path d="${fuzz(170, 150, 19, 13, 18, 0.08)}" fill="${COL.cream}"/>
    <g class="d-ear-l" style="transform-origin:136px 120px"><path d="M140,116 Q120,114 116,140 Q116,156 126,158 Q136,150 140,134 Z" fill="${COL.ear}"/></g>
    ${brow}${eye}
    <path d="M183,142 Q190,143 190,149 Q186,154 181,151 Q178,146 183,142 Z" fill="${COL.nose}"/>
    <path d="M158,160 l2,6 l3,-4 l2,6 l3,-5 l3,5 l2,-5 l3,4 l1,-6" fill="${COL.cream}" stroke="${COL.cream}" stroke-width="2" stroke-linejoin="round"/>
    <path d="M181,152 Q178,157 170,156" stroke="${COL.nose}" stroke-width="2" fill="none" stroke-linecap="round"/>
    ${tongue}
    <circle cx="160" cy="152" r="5" fill="${COL.blush}" opacity=".35"/>
  </g>`;
}

const DAISY_CSS = `
.daisy{width:100%;height:100%;display:block;overflow:visible}
.daisy .d-blink{animation:d-blink 4.5s infinite;transform-box:view-box}
.daisy .d-tail{animation:d-wag var(--wag,1.1s) ease-in-out infinite;transform-box:view-box}
.daisy.w-none .d-tail{animation:d-wag 5s ease-in-out infinite}
.daisy .d-pant{animation:d-pant .45s ease-in-out infinite;transform-box:view-box}
.daisy .d-ear-l{animation:d-ear 3.2s ease-in-out infinite;transform-box:view-box}
.daisy .d-ear-r{animation:d-ear 3.2s ease-in-out infinite reverse;transform-box:view-box}
.daisy .d-head{animation:d-tilt 5s ease-in-out infinite;transform-box:view-box}
.daisy .d-breathe,.daisy .d-head-lie{animation:d-breathe 3.6s ease-in-out infinite;transform-box:view-box}
.daisy.jump .d-all{animation:d-jump 1s ease-in-out infinite;transform-box:view-box;transform-origin:100px 190px}
.daisy.tilt .d-head{animation:d-tilt2 4s ease-in-out infinite}
@keyframes d-blink{0%,92%,100%{transform:scaleY(1)}95%{transform:scaleY(.1)}}
@keyframes d-wag{0%,100%{transform:rotate(-14deg)}50%{transform:rotate(14deg)}}
@keyframes d-pant{0%,100%{transform:scaleY(1)}50%{transform:scaleY(1.13)}}
@keyframes d-ear{0%,100%{transform:rotate(0)}50%{transform:rotate(4deg)}}
@keyframes d-tilt{0%,100%{transform:rotate(0)}50%{transform:rotate(-3deg)}}
@keyframes d-tilt2{0%,100%{transform:rotate(-9deg)}50%{transform:rotate(-6deg)}}
@keyframes d-breathe{0%,100%{transform:scale(1)}50%{transform:scale(1.025,1.04)}}
@keyframes d-jump{0%,100%{transform:translateY(0) scale(1)}30%{transform:translateY(-14px) scale(1.02,.99)}55%{transform:translateY(0) scale(1.04,.95)}70%{transform:scale(1)}}
@media (prefers-reduced-motion:reduce){.daisy *{animation:none!important}}`;

// o: { pose: 'sit'|'lie', eyes: 'open'|'closed'|'happy'|'half', tongue, wag: 'fast'|'slow'|'none', sad, jump, tilt }
function daisySvg(o) {
  const wag = o.wag === 'fast' ? '.42s' : o.wag === 'slow' ? '1.4s' : o.wag === 'mid' ? '.8s' : '5s';
  const cls = ['daisy', o.wag === 'none' ? 'w-none' : '', o.jump ? 'jump' : '', o.tilt ? 'tilt' : ''].join(' ');
  return `<svg class="${cls}" style="--wag:${wag}" viewBox="${o.pose === 'lie' ? '2 26 196 196' : '20 30 170 170'}" role="img" aria-label="Daisy"><ellipse cx="100" cy="${o.pose === 'lie' ? 171 : 190}" rx="${o.pose === 'lie' ? 84 : 58}" ry="6" fill="#000" opacity=".08"/><g class="d-all">${o.pose === 'lie' ? `<g transform="translate(-14,-34) scale(1.14)">${lying(o)}</g>` : sitting(o)}</g></svg>`;
}

/* Stimmungen: Zeichnung, Name, Farbe */
const MOODS = {
  door: { art: { pose: 'sit', eyes: 'open', wag: 'slow', tilt: true }, label: 'wartet an der Tür', col: 'habit' },
  sleep: { art: { pose: 'lie', eyes: 'closed', wag: 'none' }, label: 'schläft', col: 'habit', zzz: true },
  proud: { art: { pose: 'lie', eyes: 'happy', tongue: true, wag: 'slow' }, label: 'platt & stolz', col: 'good', zzz: true },
  party: { art: { pose: 'sit', eyes: 'happy', tongue: true, wag: 'fast', jump: true }, label: 'überglücklich', col: 'good' },
  happy: { art: { pose: 'sit', eyes: 'open', tongue: true, wag: 'mid' }, label: 'zufrieden', col: 'run' },
  rest: { art: { pose: 'lie', eyes: 'half', wag: 'slow' }, label: 'Ruhetag', col: 'weight' },
  ready: { art: { pose: 'sit', eyes: 'open', tongue: true, wag: 'fast', tilt: true }, label: 'will raus', col: 'run' },
  bored: { art: { pose: 'lie', eyes: 'open', sad: true, wag: 'none' }, label: 'langweilt sich', col: 'food' },
  miss: { art: { pose: 'lie', eyes: 'open', sad: true, wag: 'none' }, label: 'vermisst dich', col: 'heart', grey: true },
};
// Reaktion beim Streicheln / Leckerli: kurz aufspringen, Augen zu vor Freude, wild wedeln.
const REACT = { pose: 'sit', eyes: 'happy', tongue: true, wag: 'fast', jump: true };

class FitDaisy extends HTMLElement {
  constructor() { super(); this.attachShadow({ mode: 'open' }); this._sig = ''; this._tap = 0; this._fx = ''; this._say = null; }
  setConfig(c) { this._config = c || {}; this._sig = ''; if (this._hass) this._paint(); }
  set hass(h) {
    this._hass = h;
    const s = h.states || {};
    const sig = Object.values(E).map((id) => s[id]?.last_updated || '-').join('|') + (h.themes?.darkMode ? 'd' : 'l') + new Date().getHours();
    if (sig !== this._sig) { this._sig = sig; this._paint(); }
  }
  getCardSize() { return 5; }
  getGridOptions() { return { columns: 12, min_columns: 6, rows: 'auto' }; }
  static getStubConfig() { return { name: 'Jana' }; }

  _a(id) { return this._hass?.states?.[id]?.attributes || {}; }
  _c() { return this._hass?.themes?.darkMode ? PAL.dark : PAL.light; }
  _name() { return this._config?.name || (this._hass?.user?.name || '').split(' ')[0] || 'du'; }

  /* ---------- Lage auswerten ---------- */
  _model() {
    const now = new Date(); const hour = now.getHours(); const today = iso(now);
    const stE = this._hass.states[E.status];
    const st = stE?.attributes || {};
    const installed = !!stE; const conn = !!(st.garmin?.connected || st.yazio?.connected);
    const h = this._a(E.heute); const wk = this._a(E.woche).current || {};
    const r = this._a(E.run); const g = this._a(E.gym); const w = this._a(E.weight); const b = this._a(E.badges);
    const streak = num(this._hass.states[E.serie]?.state) || 0;
    const lastRun = (r.recent || [])[0]?.date || null; const lastGym = g.last_session?.date || null;
    const last = [lastRun, lastGym].filter(Boolean).sort().pop() || null;
    const since = daysSince(last);
    const gymToday = lastGym === today; const ranToday = !!h.ran_today || lastRun === today;
    const activeToday = ranToday || gymToday || (h.intensity_min || 0) >= 20;
    const stepsPct = h.steps != null && h.step_goal ? h.steps / h.step_goal : null;

    // Bedürfnisse 0–100
    const recency = since == null ? 15 : since <= 0 ? 100 : since === 1 ? 70 : since === 2 ? 45 : since === 3 ? 25 : 10;
    const walk = activeToday ? 100 : Math.round(Math.max(recency, stepsPct != null ? Math.min(stepsPct, 1) * 90 : 0));
    const train = wk.w ? clamp(wk.pct || 0, 0, 100) : null;
    const ci = [];
    if (w.has_data) { const d = daysSince(w.last_date); ci.push(h.weighed_today ? 1 : d === 1 ? 0.6 : d != null && d <= 3 ? 0.3 : 0); }
    if (h.yazio) ci.push(h.kcal > 0 ? 1 : 0);
    const checkin = ci.length ? Math.round((ci.reduce((x, y) => x + y, 0) / ci.length) * 100) : null;
    const parts = [[walk, 0.4], [train, 0.4], [checkin, 0.2]].filter(([v]) => v != null);
    const overall = parts.length ? Math.round(parts.reduce((s, [v, k]) => s + v * k, 0) / parts.reduce((s, [, k]) => s + k, 0)) : 0;

    const newBadge = (b.latest || []).find((x) => x.earned && daysSince(x.earned) <= 2);
    const newRec = (g.records || []).find((x) => x.new && daysSince(x.date) <= 2);
    const weekDone = !!(wk.ok && wk.current);

    let mood;
    if (!installed || !conn) mood = 'door';
    else if (hour >= 22 || hour < 6) mood = activeToday ? 'proud' : 'sleep';
    else if (ranToday || gymToday) mood = 'proud';
    else if (weekDone || newBadge || newRec) mood = 'party';
    else if (since === 1 && (train ?? 0) >= 50 && hour < 17) mood = 'rest';
    else if (overall >= 70) mood = 'happy';
    else if (since != null && since >= 3) mood = 'miss';
    else if (overall < 40) mood = 'bored';
    else mood = 'ready';

    // XP & Level: Team Daisy & Jana
    const xp = (r.total_runs || 0) * 10 + Math.round(r.total_km || 0) + (b.earned || 0) * 20 + streak * 15 + (g.sessions_month || 0) * 5;
    const lvl = Math.floor(Math.sqrt(xp / 25)) + 1;
    const lo = 25 * (lvl - 1) ** 2; const hi = 25 * lvl ** 2;

    // Leckerli: verdient fürs Training dieser Woche
    const week = monday();
    const earned = (wk.current ? (wk.runs || 0) + (wk.gym || 0) : 0) + (weekDone ? 2 : 0) + (newBadge ? 1 : 0) + (h.weighed_today ? 1 : 0);
    const given = store.get(`treats:${week}`, 0);
    return { now, hour, today, installed, conn, st, h, wk, r, g, w, b, streak, since, ranToday, gymToday, activeToday, stepsPct, walk, train, checkin, overall, mood, newBadge, newRec, weekDone, xp, lvl, lo, hi, week, treats: Math.max(0, earned - given) };
  }

  /* ---------- Was Daisy sagt (wichtigstes zuerst) ---------- */
  _lines(m) {
    const n = esc(this._name()); const out = [];
    const { h, wk, r, w, hour } = m;
    const seed = hash(m.today);
    if (!m.installed) return ['Wuff! Ich sitze schon an der Tür. Sobald der Fit Coach installiert ist, geht\'s los – ich hab die Leine im Maul.'];
    if (!m.conn) return [`Hey ${n}! Einmal bei Garmin anmelden, dann sehe ich, was du so treibst. Danach heißt es: Training rein, Leckerli raus.`, 'Ich warte. Geduldig. Also … relativ geduldig. *wedelt*'];
    // Fürsorge vor Druck: sehr wenig gegessen am Abend
    if (h.yazio && h.kcal > 0 && h.kcal < 1200 && hour >= 18) out.push(`Du hast heute erst ${fmt(h.kcal)} kcal gegessen. Selbst ich weiß: ohne Futter keine Power. Iss noch was Ordentliches, ${n}!`);
    if (w.tempo?.kind === 'warn') out.push('Du nimmst gerade sehr schnell ab. Klingt toll, kostet aber Muskeln – iss lieber etwas mehr. Sagt die Trainerin. Also ich.');
    if (m.mood === 'sleep') out.push(pick([`Pssst … ich schlafe. Mach du das am besten auch, ${n} – guter Schlaf hilft beim Abnehmen mehr als jede Extrarunde.`, 'Zzz … ich träume von Eichhörnchen. Und von deinem nächsten Lauf. Gute Nacht!'], seed));
    // Feiern
    if (m.ranToday) out.push(pick([`Lauf erledigt! Ich bin platt und du bist eine Maschine, ${n}.`, 'Gelaufen! Ich lieg jetzt flach – nicht weil ich müde bin, sondern aus Respekt.', 'Wuff! Training abgehakt. Jetzt: trinken, dehnen, angeben.'], seed));
    else if (m.gymToday) out.push(pick(['Gym erledigt! Die Hanteln haben Angst vor dir. Ich übrigens auch, ein bisschen.', `Krafttraining heute – stark, ${n}! Muskeln sind beim Abnehmen dein bestes Team. Nach mir.`], seed));
    if (m.newRec) out.push(`Neuer Rekord bei ${esc(m.newRec.name)}! Ich würde ja klatschen, aber: Pfoten.`);
    if (m.newBadge) out.push(`Neues Abzeichen: „${esc(m.newBadge.title)}“! Hab es im Garten vergraben, damit es keiner klaut.`);
    if (m.weekDone) out.push(pick([`Wochenziel geschafft! Hiermit ernenne ich dich offiziell zum besten Frauchen der Welt.`, 'Woche: erledigt. Ich mach einen Freudentanz. Mit Zunge.'], seed));
    // Stimmung
    if (m.mood === 'rest') out.push(pick(['Ruhetag ist auch Training. Ich zeig dir, wie das geht: hinlegen, seufzen, fertig.', 'Gestern trainiert, heute Pause – genau richtig. Muskeln wachsen beim Faulenzen. Mein Lieblingsfakt.'], seed));
    if (m.mood === 'miss') out.push(pick([`Ich liege seit ${m.since} Tagen auf dem Sofa. Das Sofa ist toll, aber du fehlst mir draußen. 15 Minuten reichen schon!`, `${m.since} Tage ohne Training. Kein Drama – aber ich hab die Leine gefunden. Zufällig. Heute?`], seed));
    if (m.mood === 'bored') out.push(pick(['Mir ist langweilig. Wie wär\'s mit einer lockeren Runde? So locker, dass du dabei mit mir quatschen kannst.', 'Ich hab alle Socken gezählt. Jetzt bist du dran: Schuhe an, 20 Minuten raus!'], seed));
    // Plan & Woche
    const nx = r.next;
    if (nx && !m.activeToday && nx.date === m.today) out.push(`Heute steht „${esc(nx.title)}“ an. Ich hab die Leine schon im Maul. Nur so als Info.`);
    else if (nx && !m.activeToday && nx.date && daysSince(nx.date) === -1) out.push(`Morgen: „${esc(nx.title)}“. Leg schon mal die Laufschuhe raus – ich bewache sie.`);
    if (wk.current && !wk.ok && wk.run_target) {
      const left = Math.max(0, wk.run_target - (wk.runs || 0));
      if (left > 0 && wk.days_left <= 3) out.push(`Noch ${wk.days_left === 0 ? 'heute' : `${wk.days_left} ${wk.days_left === 1 ? 'Tag' : 'Tage'}`}, noch ${left} ${left === 1 ? 'Lauf' : 'Läufe'} bis zum Wochenziel. Ich glaub an dich. Und an Leckerli.`);
    }
    if (h.step_goal && h.steps != null && hour >= 15 && h.steps < h.step_goal && h.step_goal - h.steps <= 3000) out.push(`Nur noch ${fmt(h.step_goal - h.steps)} Schritte bis zum Tagesziel. Kleine Runde um den Block? Ich komm mit!`);
    // Fortschritt
    const pd7 = r.pace?.easy_pace_delta;
    if (pd7 != null && pd7 < 0) out.push(`Deine lockere Pace ist ${Math.abs(pd7)} Sekunden schneller als vor 4 Wochen. Ich hab's an der Leine gemerkt.`);
    if (w.has_data && w.change_7d != null && w.change_7d < 0 && w.tempo?.kind !== 'warn') out.push(`${fmt(Math.abs(w.change_7d), 1)} kg runter im Trend. Langsam und stetig – so wie ich, wenn's was zu schnüffeln gibt.`);
    if (w.has_data && w.change_7d != null && w.change_7d > 0.2) out.push('Die Waage zickt? Egal. Tageswerte sind viel Wasser – der Trend zählt, und wir bleiben dran. Wuff.');
    if (w.goal_reached) out.push('Zielgewicht erreicht! Ich bin so stolz, ich hab vor Freude die Couch angeknabbert. (Ein bisschen.)');
    if (h.yazio && h.kcal_remaining != null && h.kcal_remaining < -150 && hour >= 19) out.push('Mehr gegessen als geplant? Passiert. Ein Tag ist ein Tag – morgen geht\'s ganz normal weiter. Ich ess auch mal Socken.');
    // Lob & Laune
    if (m.streak >= 2) out.push(`${m.streak} Wochen am Stück dabei! Ich hab extra meinen Schwanz aufgewärmt.`);
    if (m.mood === 'ready') out.push(pick([`Ich bin bereit, wenn du's bist, ${n}! Heute ein bisschen Bewegung, und ich wedle den ganzen Abend.`, 'Trainerin Daisy sagt: Lieber locker und oft als hart und selten. Und jetzt: Leine!'], seed));
    if (m.mood === 'happy') out.push(pick(['Läuft bei uns! Ich bin zufrieden. Und ein bisschen hungrig. Aber vor allem zufrieden.', `Gute Woche bis jetzt, ${n}. Weiter so – und denk an genug Wasser. Ich hab meins schon umgeschüttet.`], seed));
    if (!h.weighed_today && m.w.has_data && hour >= 6 && hour < 11 && m.mood !== 'sleep') out.push('Morgen-Check-in? Ich hol schon mal die Waage. Kein Stress, wenn nicht – der Trend verzeiht.');
    out.push(pick(['Fun Fact: Ich laufe auf vier Beinen und finde dich trotzdem schneller. *stolz*', 'Ein guter Lauf fühlt sich an wie Wedeln mit dem ganzen Körper.', 'Wenn du mal nicht willst: Schuhe anziehen reicht. Den Rest mach ich mit Hundeblick.'], seed));
    return [...new Set(out)];
  }

  _mission(m) {
    const { h, r, wk } = m;
    if (!m.conn) return null;
    const nx = r.next;
    if (nx && nx.date === m.today) return { text: esc(nx.title), done: m.ranToday, ic: 'run' };
    if (nx && m.hour >= 21 && nx.date && daysSince(nx.date) === -1) return { text: esc(nx.title), done: false, ic: 'run' };
    if (m.since === 1 && (m.train ?? 0) >= 50 && !m.activeToday) return { text: 'Ruhetag: Spaziergang & dehnen', done: m.stepsPct != null && m.stepsPct >= 0.6, ic: 'walk' };
    if (wk.current && wk.run_target && (wk.runs || 0) < wk.run_target && !m.activeToday) return { text: '20–30 min locker laufen (so, dass Reden geht)', done: false, ic: 'run' };
    if (h.step_goal) return { text: `${fmt(h.step_goal)} Schritte`, done: h.steps >= h.step_goal, ic: 'walk', sub: `${fmt(h.steps)} bisher` };
    return { text: '30 min Bewegung', done: m.activeToday, ic: 'heart-pulse' };
  }

  /* ---------- Darstellung ---------- */
  _css(c) {
    return `:host{display:block}ha-card{overflow:hidden}
    .card{padding:16px;color:var(--primary-text-color);font-size:14px;line-height:1.4}
    .eyebrow{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--secondary-text-color)}
    .muted{color:var(--secondary-text-color)}.small{font-size:12px}
    .row{display:flex;align-items:center;gap:10px}.between{justify-content:space-between}
    .top{display:flex;gap:14px;align-items:flex-start;margin-top:10px}
    .pet{position:relative;width:118px;height:118px;flex:none;cursor:pointer;-webkit-tap-highlight-color:transparent}
    .pet .ring{position:absolute;inset:0;border-radius:50%;padding:4px;background:conic-gradient(var(--mc) calc(var(--p)*1%),${c.track} 0)}
    .pet .art{position:absolute;inset:5px;border-radius:50%;overflow:hidden;background:var(--card-background-color,#fff);border:3px solid var(--card-background-color,#fff);box-sizing:border-box}
    .pet .art svg{position:absolute;inset:0;width:100%;height:100%}
    .pet.grey .art svg{filter:grayscale(.45) brightness(.97)}
    .zzz{position:absolute;right:-2px;top:2px;font-weight:700;color:var(--secondary-text-color);pointer-events:none}
    .zzz span{position:absolute;animation:zz 3s ease-in infinite;opacity:0}
    .zzz span:nth-child(2){animation-delay:1s;font-size:15px}.zzz span:nth-child(3){animation-delay:2s;font-size:19px}
    @keyframes zz{0%{opacity:0;transform:translate(0,0)}20%{opacity:.9}100%{opacity:0;transform:translate(14px,-26px)}}
    .mood{position:absolute;left:50%;bottom:-8px;transform:translateX(-50%);white-space:nowrap;font-size:11px;font-weight:600;padding:2px 8px;border-radius:999px;background:var(--mc);color:#fff;box-shadow:0 1px 3px rgba(0,0,0,.2)}
    .fx{position:absolute;inset:0;pointer-events:none}
    .fx i{position:absolute;left:50%;top:45%;color:${c.heart};animation:float 1.4s ease-out forwards;opacity:0}
    @keyframes float{0%{opacity:0;transform:translate(-50%,0) scale(.6)}15%{opacity:1}100%{opacity:0;transform:translate(calc(-50% + var(--dx)),-70px) scale(1.15)}}
    .bubble{position:relative;flex:1;min-width:0;background:${c.bubble};border-radius:14px;padding:10px 12px;cursor:pointer;-webkit-tap-highlight-color:transparent}
    .bubble:before{content:"";position:absolute;left:-7px;top:22px;border:8px solid transparent;border-right-color:${c.bubble};border-left:0}
    .bubble .who{font-weight:650;font-size:13px}.bubble .txt{margin-top:2px}
    .bubble .more{margin-top:6px;font-size:11px;color:var(--secondary-text-color)}
    .needs{display:grid;gap:8px;margin-top:18px}
    .need{display:grid;grid-template-columns:22px 92px 1fr 40px;align-items:center;gap:8px;font-size:13px}
    .need .ic{color:var(--secondary-text-color);display:flex}
    .need .v{text-align:right;font-variant-numeric:tabular-nums;color:var(--secondary-text-color);font-size:12px}
    .bar{position:relative;height:8px;border-radius:999px;background:${c.track};overflow:hidden}
    .bar>i{position:absolute;left:0;top:0;bottom:0;border-radius:999px;transition:width .6s}
    .mission{display:flex;gap:10px;align-items:center;margin-top:14px;padding:10px 12px;border-radius:12px;background:${c.track}}
    .mission .chk{width:24px;height:24px;border-radius:50%;display:grid;place-items:center;flex:none;border:2px solid var(--secondary-text-color);color:#fff}
    .mission .chk.on{background:${c.good};border-color:${c.good}}
    .acts{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
    button.btn{all:unset;box-sizing:border-box;cursor:pointer;display:inline-flex;align-items:center;gap:6px;padding:8px 13px;border-radius:999px;font-weight:600;font-size:13px;background:${c.track};color:var(--primary-text-color);-webkit-tap-highlight-color:transparent}
    button.btn:active{transform:scale(.96)}button.btn.dim{opacity:.55}
    .lvl{display:flex;align-items:center;gap:8px;margin-top:14px}
    .lvl .bar{flex:1;height:5px}
    @media (prefers-reduced-motion:reduce){.zzz span,.fx i{animation:none!important}.zzz span{opacity:.7}}
    ${DAISY_CSS}`;
  }

  _paint() {
    if (!this._hass) return;
    let html;
    try { html = this._render(); } catch (e) { console.error('fit-daisy', e); html = `<div class="card small muted">Daisy hat sich versteckt: ${esc(e.message)}</div>`; }
    this.shadowRoot.innerHTML = `<style>${this._css(this._c())}</style><ha-card>${html}</ha-card>`;
    this._bind();
  }

  _render() {
    const c = this._c(); const m = this._model(); this._m = m;
    const mo = MOODS[m.mood]; const mc = c[mo.col] || c.run;
    const lines = this._lines(m);
    const say = this._say || lines[this._tap % lines.length];
    const need = (ic, label, v, col) => (v == null ? '' : `<div class="need"><span class="ic">${icon(ic, 18)}</span><span>${label}</span><div class="bar"><i style="width:${v}%;background:${v >= 70 ? col : v >= 35 ? c.warn : c.food}"></i></div><span class="v">${v} %</span></div>`);
    let mis = this._mission(m); let misHead = 'Daisys Auftrag für heute';
    if (mis && !mis.done && m.hour >= 21) { if (mis.ic === 'walk') mis = null; else misHead = 'Daisys Plan für morgen'; }
    const lvlName = LEVELS[Math.min(m.lvl - 1, LEVELS.length - 1)];
    const lvlPct = clamp(((m.xp - m.lo) / Math.max(m.hi - m.lo, 1)) * 100, 0, 100);
    const ring = m.conn ? m.overall : 0;
    return `<div class="card">
      <div class="row between"><div class="eyebrow">${icon('paw', 14)} Daisy · deine Trainerin</div>${m.conn ? `<span class="small muted">Level ${m.lvl}</span>` : ''}</div>
      <div class="top">
        <div class="pet ${mo.grey && !this._react ? 'grey' : ''}" data-act="pet" role="button" aria-label="Daisy streicheln" style="--mc:${mc};--p:${ring}">
          <div class="ring"></div><div class="art">${daisySvg(this._react ? REACT : mo.art)}</div>
          ${mo.zzz && !this._react ? '<div class="zzz"><span>z</span><span>z</span><span>Z</span></div>' : ''}
          <span class="mood">${esc(mo.label)}</span><div class="fx">${this._fx}</div>
        </div>
        <div class="bubble" data-act="next" role="button" aria-label="Was sagt Daisy noch?">
          <div class="who">Daisy</div><div class="txt">${say}</div>
          ${lines.length > 1 && !this._say ? `<div class="more">${this._tap % lines.length + 1}/${lines.length} · tippen für mehr</div>` : ''}
        </div>
      </div>
      ${m.conn ? `<div class="needs">
        ${need('dog-side', 'Auslauf', m.walk, c.run)}
        ${need('flag-checkered', 'Wochenziel', m.train, c.habit)}
        ${need('clipboard-check-outline', 'Check-in', m.checkin, c.weight)}
      </div>` : ''}
      ${mis ? `<div class="mission"><span class="chk ${mis.done ? 'on' : ''}">${mis.done ? icon('check', 16) : ''}</span><div style="flex:1;min-width:0">
        <div class="small muted">${misHead}</div><div style="font-weight:600">${mis.text}</div>${mis.sub && !mis.done ? `<div class="small muted">${esc(mis.sub)}</div>` : ''}</div>${icon(mis.ic, 22)}</div>` : ''}
      <div class="acts">
        <button class="btn" data-act="pet">${icon('hand-heart-outline', 18)}Streicheln</button>
        ${m.conn ? `<button class="btn ${m.treats ? '' : 'dim'}" data-act="treat">${icon('bone', 18)}Leckerli${m.treats ? ` (${m.treats})` : ''}</button>` : ''}
      </div>
      ${m.conn ? `<div class="lvl"><span class="small" style="font-weight:600">${esc(lvlName)}</span><div class="bar"><i style="width:${lvlPct}%;background:${c.habit}"></i></div><span class="small muted">${fmt(m.xp)} XP</span></div>
      <div class="small muted" style="margin-top:4px">Team Daisy & ${esc(this._name())}: XP gibt's für Läufe, Kilometer, Gym, Abzeichen und Wochenserien.</div>` : ''}
    </div>`;
  }

  _hearts(n = 5, ic = 'heart') {
    return Array.from({ length: n }, (_, i) => `<i style="--dx:${(i - (n - 1) / 2) * 16}px;animation-delay:${i * 0.12}s">${icon(ic, 18 + (i % 2) * 6)}</i>`).join('');
  }

  _bind() {
    const root = this.shadowRoot;
    root.querySelectorAll('[data-act]').forEach((el) => el.addEventListener('click', (ev) => {
      ev.stopPropagation(); const act = el.dataset.act; const m = this._m; const n = esc(this._name());
      clearTimeout(this._t);
      if (act === 'next') { this._say = null; this._tap += 1; this._fx = ''; this._react = false; }
      if (act === 'pet') {
        const k = `pets:${m.today}`; const cnt = store.get(k, 0) + 1; store.set(k, cnt);
        this._fx = this._hearts(); this._react = true;
        this._say = cnt >= 6 ? pick([`Okay, okay, genug gekuschelt – jetzt Schuhe an, ${n}!`, 'Noch mehr Streicheln gibt\'s nach dem Training. Trainerregeln. *wedelt trotzdem*'], cnt)
          : pick(['*wedelt mit dem ganzen Hintern*', 'Mehr! Hinterm Ohr! Jaaa, genau da.', `Ich hab dich auch lieb, ${n}. Und jetzt motivier ich dich weiter.`, '*Pfote auf deine Hand* – Das heißt: Wir schaffen das.', '*rollt sich auf den Rücken* Bauch bitte. Dann Lauf.'], cnt + hash(m.today));
      }
      if (act === 'treat') {
        if (m.treats > 0) {
          store.set(`treats:${m.week}`, store.get(`treats:${m.week}`, 0) + 1);
          this._fx = this._hearts(4, 'bone'); this._react = true;
          this._say = pick(['Mmmh! Verdient ist verdient. Du übrigens auch – trink was!', '*schnapp* Danke! Für jedes Training gibt\'s eins. Ich zähl mit.', 'Lecker! Weißt du, was auch lecker ist? Dein nächster Lauf. Okay, nicht lecker. Aber gut.'], m.treats + hash(m.week));
        } else {
          this._fx = '';
          this._say = pick(['Keine Leckerli mehr in der Dose. Die gibt\'s fürs Training – erst Gassi, dann Snack. Trainerregeln.', 'Netter Versuch! *Hundeblick* Ein Lauf oder eine Gym-Einheit und die Dose ist wieder voll.'], hash(m.today) + this._tap);
        }
      }
      this._paint();
      this._t = setTimeout(() => { this._fx = ''; if (this._react) { this._react = false; this._paint(); } else { const fx = this.shadowRoot.querySelector('.fx'); if (fx) fx.innerHTML = ''; } }, 2200);
    }));
  }
}

if (!customElements.get('fit-daisy')) customElements.define('fit-daisy', FitDaisy);
window.customCards = window.customCards || [];
if (!window.customCards.find((x) => x.type === 'fit-daisy')) window.customCards.push({ type: 'fit-daisy', name: 'Fit: Daisy', description: 'Daisy motiviert – Tamagotchi für den Fit Coach' });
console.info(`%c FIT-DAISY %c ${DAISY_VERSION} `, 'background:#e0457b;color:#fff;border-radius:3px 0 0 3px', 'background:#444;color:#fff;border-radius:0 3px 3px 0');
