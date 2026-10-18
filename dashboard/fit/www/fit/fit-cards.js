/* Fit Coach – Dashboard-Karten (fit-cards.js)
 * Mobile-first Karten für das Dashboard „Fit“. Keine externen Abhängigkeiten.
 * Daten: Sensoren der App „Fit Coach“ (sensor.fit_coach_*), Eingaben über deren
 * number-/select-/button-Entitäten. Gestaltung wie coach-cards.js (Garmin AI Coach):
 * Kategorie-Farben validiert (Gewicht blau, Essen orange, Laufen aqua, Gym gelb –
 * immer mit Icon + Text), Status = gut/Warnung/ernst/kritisch (immer mit Text),
 * Hell/Dunkel getrennt gewählt.
 * 0.1.0 (18.10.2026): erste Fassung.
 */
const FC_VERSION = '0.1.0';
const P = 'sensor.fit_coach_';
const E = {
  status: `${P}status`, heute: `${P}heute`, woche: `${P}woche`, tipp: `${P}tipp`, weight: `${P}abnahme`,
  food: `${P}ernaehrung`, run: `${P}laufen`, gym: `${P}gym`, badges: `${P}erfolge`, plan: `${P}plan`,
  serie: `${P}serie`, last: `${P}letzter_sync`,
  nWeight: 'number.fit_coach_gewicht_eintragen', nGoal: 'number.fit_coach_zielgewicht',
  nKg: 'number.fit_coach_rekord_kg', nReps: 'number.fit_coach_rekord_wdh', sEx: 'select.fit_coach_uebung',
  bSync: 'button.fit_coach_sync', bRec: 'button.fit_coach_rekord_speichern', bRecUndo: 'button.fit_coach_rekord_rueckgaengig',
  bWeightUndo: 'button.fit_coach_gewicht_rueckgaengig',
};
const PALETTE = {
  light: { weight: '#2a78d6', food: '#eb6834', run: '#1baf7a', gym: '#eda100', habit: '#6250d6', good: '#0ca30c', warn: '#fab219', serious: '#ec835a', critical: '#d03b3b', goodText: '#006300', warnText: '#8a5a00', track: 'rgba(11,11,11,0.08)', grid: '#e1e0d9', neutral: '#898781' },
  dark: { weight: '#3987e5', food: '#d95926', run: '#199e70', gym: '#c98500', habit: '#9085e9', good: '#0ca30c', warn: '#fab219', serious: '#ec835a', critical: '#d03b3b', goodText: '#3fbf3f', warnText: '#f0b13a', track: 'rgba(255,255,255,0.10)', grid: '#2c2c2a', neutral: '#898781' },
};
const WD = ['Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag'];
const MON = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];

/* ---------- Helfer ---------- */
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const kebab = (n) => n.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`);
const icon = (name, size = 20, cls = '') => `<ha-icon class="ic ${cls}" icon="mdi:${name.includes('-') ? name : kebab(name)}" style="--mdc-icon-size:${size}px;width:${size}px;height:${size}px"></ha-icon>`;
const num = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : null; };
const fmt = (v, d = 0) => (v == null || !Number.isFinite(+v) ? '–' : Number(v).toLocaleString('de-DE', { minimumFractionDigits: d, maximumFractionDigits: d }));
const signed = (v, d = 1, unit = '') => (v == null ? '–' : `${v > 0 ? '+' : v < 0 ? '−' : '±'}${fmt(Math.abs(v), d)}${unit ? ` ${unit}` : ''}`);
const pace = (s) => { if (s == null) return '–'; const t = Math.round(s); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`; };
const dur = (s) => { if (s == null) return '–'; const t = Math.round(s); const h = Math.floor(t / 3600); const m = Math.floor((t % 3600) / 60); const x = t % 60; return h ? `${h}:${String(m).padStart(2, '0')}:${String(x).padStart(2, '0')}` : `${m}:${String(x).padStart(2, '0')}`; };
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const pd = (s) => { if (!s) return null; const [y, m, d] = String(s).slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d); };
const ddmm = (s) => { const d = typeof s === 'string' ? pd(s) : s; return d ? `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.` : '–'; };
const dayLabel = (s) => { const d = pd(s); if (!d) return '–'; const t = new Date(); t.setHours(0, 0, 0, 0); const diff = Math.round((t - d) / 864e5); if (diff === 0) return 'heute'; if (diff === 1) return 'gestern'; if (diff < 7 && diff > 0) return WD[d.getDay()]; return ddmm(d); };
const localIso = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const monthYear = (s) => { const d = pd(s); return d ? `${MON[d.getMonth()]} ${d.getFullYear()}` : ''; };

const BASE_CSS = `
:host { display: block; }
ha-card { overflow: hidden; }
.card { padding: 16px; color: var(--primary-text-color); font-size: 14px; line-height: 1.4; }
.ic { flex: none; display: inline-flex; color: inherit; }
.eyebrow { font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--secondary-text-color); }
.muted { color: var(--secondary-text-color); }
.small { font-size: 12px; }
.row { display: flex; align-items: center; gap: 10px; }
.between { justify-content: space-between; }
.wrap { flex-wrap: wrap; }
.chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 9px; border-radius: 999px; font-size: 12px; font-weight: 500; background: var(--fc-track); color: var(--primary-text-color); white-space: nowrap; }
.pill { display: inline-flex; align-items: center; gap: 6px; padding: 4px 11px 4px 8px; border-radius: 999px; font-weight: 600; font-size: 13px; background: var(--fc-track); }
.dot { width: 10px; height: 10px; border-radius: 50%; flex: none; display: inline-block; }
.big { font-size: 30px; font-weight: 650; letter-spacing: -.02em; line-height: 1.05; }
.mid { font-size: 20px; font-weight: 650; letter-spacing: -.01em; line-height: 1.1; }
.hr { height: 1px; background: var(--divider-color, var(--fc-track)); margin: 14px 0; }
.bar { position: relative; height: 8px; border-radius: 999px; background: var(--fc-track); overflow: hidden; }
.bar > i { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 999px; }
.bar .mk { position: absolute; top: -2px; bottom: -2px; width: 2px; background: var(--primary-text-color); opacity: .55; border-radius: 1px; }
.tap { cursor: pointer; -webkit-tap-highlight-color: transparent; }
button.btn { all: unset; box-sizing: border-box; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 9px 14px; border-radius: 10px; font-weight: 600; font-size: 14px; background: var(--primary-color); color: var(--text-primary-color, #fff); }
button.btn.sec { background: var(--fc-track); color: var(--primary-text-color); }
button.btn.busy { opacity: .6; pointer-events: none; }
button.link { all: unset; cursor: pointer; color: var(--primary-color); font-size: 13px; font-weight: 500; }
input.in, select.in { box-sizing: border-box; height: 40px; padding: 0 10px; border-radius: 10px; border: 1px solid var(--divider-color, #8884); background: var(--card-background-color, transparent); color: var(--primary-text-color); font-size: 16px; min-width: 0; }
.sic { width: 32px; height: 32px; border-radius: 10px; display: grid; place-items: center; flex: none; color: #fff; }
.item { display: flex; gap: 12px; align-items: flex-start; padding: 10px 0; }
.item + .item { border-top: 1px solid var(--divider-color, var(--fc-track)); }
.item .t { font-weight: 600; }
.item .c { font-size: 13px; color: var(--secondary-text-color); }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.tile { background: var(--fc-track); border-radius: 12px; padding: 10px 12px; min-width: 0; }
.tile .v { font-size: 18px; font-weight: 650; }
.tile .l { font-size: 12px; color: var(--secondary-text-color); }
.warnline { margin-top: 8px; font-size: 13px; }
.chart { position: relative; margin-top: 10px; touch-action: pan-y; user-select: none; -webkit-user-select: none; }
.chart svg { display: block; width: 100%; overflow: visible; }
.ylab { position: absolute; left: 0; width: 34px; text-align: right; font-size: 11px; line-height: 1; color: var(--secondary-text-color); transform: translateY(-50%); font-variant-numeric: tabular-nums; }
.plot { position: absolute; left: 40px; right: 8px; top: 0; bottom: 0; }
.xlab { display: flex; justify-content: space-between; font-size: 11px; color: var(--secondary-text-color); margin-top: 4px; }
.tip { position: absolute; top: -8px; transform: translate(-50%, -100%); background: var(--primary-text-color); color: var(--card-background-color, #fff); font-size: 12px; padding: 4px 8px; border-radius: 6px; white-space: nowrap; pointer-events: none; z-index: 2; }
.tip b { font-weight: 650; }
.cross { position: absolute; top: 0; bottom: 0; width: 1px; background: var(--secondary-text-color); opacity: .5; pointer-events: none; }
.bars { display: flex; align-items: flex-end; gap: 2px; height: 100%; }
.bars .b { flex: 1; max-width: 24px; border-radius: 4px 4px 0 0; min-height: 2px; margin: 0 auto; }
.bars .b.hov { filter: brightness(1.15); }
.seg { display: inline-flex; background: var(--fc-track); border-radius: 999px; padding: 2px; gap: 2px; }
.seg button { all: unset; cursor: pointer; padding: 3px 10px; border-radius: 999px; font-size: 12px; color: var(--secondary-text-color); }
.seg button.on { background: var(--card-background-color, #fff); color: var(--primary-text-color); font-weight: 600; }
.ok { color: var(--fc-goodText); }
.wtx { color: var(--fc-warnText); }
.clamp2 { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
a.src { color: var(--secondary-text-color); font-size: 11px; text-decoration: underline; text-underline-offset: 2px; }
`;

/* ---------- Basisklasse ---------- */
class FitBase extends HTMLElement {
  constructor() { super(); this.attachShadow({ mode: 'open' }); this._open = new Set(); this._sig = ''; this._ui = {}; this._charts = {}; }
  setConfig(config) { this._config = config || {}; this._sig = ''; if (this._hass) this._schedule(); }
  set hass(h) {
    this._hass = h;
    const sig = this._signature();
    if (sig !== this._sig) { this._sig = sig; this._schedule(); }
  }
  get hass() { return this._hass; }
  connectedCallback() { if (this._hass) this._schedule(); }
  getCardSize() { return 4; }
  getGridOptions() { return { columns: 12, min_columns: 6, rows: 'auto' }; }
  _entities() { return [E.status]; }
  _signature() {
    const s = this._hass?.states || {};
    return this._entities().map((id) => { const o = s[id]; return o ? `${o.state}|${o.last_updated}` : '-'; }).join('#') + `#${this._hass?.themes?.darkMode ? 1 : 0}`;
  }
  _st(id) { return this._hass?.states?.[id]; }
  _num(id) { return num(this._st(id)?.state); }
  _a(id) { return this._st(id)?.attributes || {}; }
  _dark() { return !!this._hass?.themes?.darkMode; }
  _c() { return this._dark() ? PALETTE.dark : PALETTE.light; }
  _vars() { const c = this._c(); return `--fc-track:${c.track};--fc-goodText:${c.goodText};--fc-warnText:${c.warnText};`; }
  _schedule() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => { this._raf = null; if (this._editing) { this._pending = true; return; } this._paint(); });
  }
  _paint() {
    if (!this._hass) return;
    let body = '';
    this._charts = {};
    if (!this._installed() && !this.constructor.showsSetup) { this.style.display = 'none'; this.shadowRoot.innerHTML = ''; return; }
    this.style.display = '';
    try { body = this._installed() ? this._render() : this._notInstalled(); } catch (e) { body = `<div class="card muted small">Karte konnte nicht dargestellt werden: ${esc(e.message)}</div>`; console.error('fit-cards', e); }
    this.shadowRoot.innerHTML = `<style>${BASE_CSS}${this._css ? this._css() : ''}</style><ha-card style="${this._vars()}">${body}</ha-card>`;
    this._bind();
    this._bindCharts();
  }
  _installed() { return !!this._st(E.status); }
  _notInstalled() {
    return `<div class="card"><div class="eyebrow">Fit Coach</div>
      <div style="margin-top:6px;font-weight:600">Die App ist noch nicht installiert.</div>
      <div class="small muted" style="margin-top:4px">Einstellungen › Apps › App-Store › „Fit Coach“ installieren und starten. Danach in der Seitenleiste „Fit Coach“ öffnen und bei Garmin anmelden.</div></div>`;
  }
  _panelUrl() {
    const panels = this._hass?.panels || {};
    const p = Object.values(panels).find((x) => /fit_coach$/.test(x?.config?.ingress || '') || x?.title === 'Fit Coach');
    return p ? `/${p.url_path}` : (this._config?.panel || '/app/1c76c417_fit_coach');
  }
  _bind() {
    const root = this.shadowRoot;
    root.querySelectorAll('[data-nav]').forEach((el) => el.addEventListener('click', (ev) => { ev.stopPropagation(); const v = el.dataset.nav; this._navigate(v === 'panel' ? this._panelUrl() : /^(\/|https?:)/.test(v) ? v : `/${location.pathname.split('/')[1]}/${v}`); }));
    root.querySelectorAll('[data-more]').forEach((el) => el.addEventListener('click', (ev) => { ev.stopPropagation(); this.dispatchEvent(new CustomEvent('hass-more-info', { detail: { entityId: el.dataset.more }, bubbles: true, composed: true })); }));
    root.querySelectorAll('[data-toggle]').forEach((el) => el.addEventListener('click', (ev) => { ev.stopPropagation(); const k = el.dataset.toggle; if (this._open.has(k)) this._open.delete(k); else this._open.add(k); this._paint(); }));
    root.querySelectorAll('[data-ui]').forEach((el) => el.addEventListener('click', (ev) => { ev.stopPropagation(); const [k, v] = el.dataset.ui.split('='); this._ui[k] = v; this._paint(); }));
    root.querySelectorAll('input.in, select.in').forEach((el) => {
      el.addEventListener('focus', () => { this._editing = true; });
      el.addEventListener('blur', () => { setTimeout(() => { if (!root.activeElement || !root.activeElement.matches?.('input.in, select.in')) { this._editing = false; if (this._pending) { this._pending = false; this._paint(); } } }, 150); });
      el.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') { const b = root.querySelector(`[data-submit="${el.dataset.form}"]`); if (b) b.click(); } });
    });
    if (this._bindExtra) this._bindExtra(root);
  }
  _navigate(path) { if (/^https?:/.test(path)) { window.open(path, '_blank'); return; } history.pushState(null, '', path); window.dispatchEvent(new CustomEvent('location-changed', { detail: { replace: false } })); }
  _call(domain, service, data) { return this._hass.callService(domain, service, data).catch((e) => { this._err = e.message || String(e); this._paint(); }); }
  _press(entity) { return this._call('button', 'press', { entity_id: entity }); }
  _setNum(entity, value) { return this._call('number', 'set_value', { entity_id: entity, value }); }
  _ring(pct, color, size = 72, stroke = 8, inner = '') {
    const r = (size - stroke) / 2; const c = 2 * Math.PI * r; const p = clamp(pct, 0, 100);
    return `<div style="width:${size}px;height:${size}px;position:relative;flex:none">
      <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="transform:rotate(-90deg)" aria-hidden="true">
        <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--fc-track)" stroke-width="${stroke}"/>
        ${p > 0 ? `<circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${color}" stroke-width="${stroke}" stroke-linecap="round" stroke-dasharray="${(c * p) / 100} ${c}"/>` : ''}
      </svg><div style="position:absolute;inset:0;display:grid;place-items:center;text-align:center">${inner}</div></div>`;
  }
  _sic(kind, ic, size = 32) { return `<span class="sic" style="background:${this._c()[kind] || this._c().neutral};width:${size}px;height:${size}px">${icon(ic, Math.round(size * 0.56))}</span>`; }
  _status(kind, label) { const c = this._c(); return `<span class="pill"><span class="dot" style="background:${c[kind] || c.neutral}"></span>${esc(label)}</span>`; }

  /* ---------- Diagramme ---------- */
  // Linie (2px) mit Fläche (10 %), optional Rohwerte als Punkte, Ziel-Linie, invertierte Achse.
  _line(id, o) {
    const pts = o.pts.filter((p) => p.v != null);
    if (pts.length < 2) return `<div class="small muted" style="margin-top:8px">${esc(o.empty || 'Noch zu wenig Verlauf – die Kurve füllt sich mit jedem Sync.')}</div>`;
    const W = 320; const H = o.height || 110;
    const vals = pts.map((p) => p.v).concat((o.raw || []).map((p) => p.v)).concat(o.goal != null ? [o.goal] : []);
    let lo = Math.min(...vals); let hi = Math.max(...vals); if (hi - lo < 1e-9) { hi += 1; lo -= 1; }
    const pad = (hi - lo) * 0.1; lo -= pad; hi += pad;
    const t0 = pts[0].t; const t1 = Math.max(pts[pts.length - 1].t, ...(o.raw || []).map((p) => p.t)) || t0 + 1;
    const X = (t) => ((t - t0) / Math.max(t1 - t0, 1)) * W;
    const Y = (v) => (o.invert ? ((v - lo) / (hi - lo)) * H : H - ((v - lo) / (hi - lo)) * H);
    const path = pts.map((p, i) => `${i ? 'L' : 'M'}${X(p.t).toFixed(1)},${Y(p.v).toFixed(1)}`).join('');
    const area = o.invert ? '' : `<path d="${path}L${X(pts[pts.length - 1].t).toFixed(1)},${H}L${X(pts[0].t).toFixed(1)},${H}Z" fill="${o.color}" opacity=".10"/>`;
    const raw = (o.raw || []).map((p) => `<circle cx="${X(p.t).toFixed(1)}" cy="${Y(p.v).toFixed(1)}" r="2.2" fill="${o.color}" opacity=".45" vector-effect="non-scaling-stroke"/>`).join('');
    const goal = o.goal != null ? `<line x1="0" x2="${W}" y1="${Y(o.goal)}" y2="${Y(o.goal)}" stroke="var(--primary-text-color)" stroke-opacity=".45" stroke-width="1" vector-effect="non-scaling-stroke"/>` : '';
    const minV = Math.min(...pts.map((p) => p.v)); const maxV = Math.max(...pts.map((p) => p.v));
    const last = pts[pts.length - 1];
    const f = o.fmt || ((v) => fmt(v, 1));
    const topV = o.invert ? minV : maxV; const botV = o.invert ? maxV : minV;
    this._charts[id] = { kind: 'line', pts: o.hover || pts, X, W, tip: o.tip };
    return `<div class="chart" data-chart="${id}" style="height:${H}px"><div class="plot">
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="height:${H}px" aria-hidden="true">
        <line x1="0" x2="${W}" y1="${Y(topV)}" y2="${Y(topV)}" stroke="var(--divider-color,#8884)" stroke-width="1" vector-effect="non-scaling-stroke"/>
        <line x1="0" x2="${W}" y1="${Y(botV)}" y2="${Y(botV)}" stroke="var(--divider-color,#8884)" stroke-width="1" vector-effect="non-scaling-stroke"/>
        ${goal}${area}${raw}
        <path d="${path}" fill="none" stroke="${o.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>
      </svg>
      <span style="position:absolute;left:calc(${(X(last.t) / W) * 100}% - 5px);top:${Y(last.v) - 5}px;width:10px;height:10px;border-radius:50%;background:${o.color};box-shadow:0 0 0 2px var(--ha-card-background,var(--card-background-color,#fff))"></span>
      ${o.goal != null ? `<span class="small muted" style="position:absolute;right:2px;top:${Y(o.goal) - 16}px">${esc(o.goalLabel || 'Ziel')}</span>` : ''}
      </div>
      <span class="ylab" style="top:${(Y(topV) / H) * 100}%">${f(topV)}</span>
      ${Math.abs(maxV - minV) > 1e-9 ? `<span class="ylab" style="top:${(Y(botV) / H) * 100}%">${f(botV)}</span>` : ''}
    </div><div class="xlab" style="margin-left:40px"><span>${ddmm(new Date(t0))}</span>${o.mid ? `<span>${esc(o.mid)}</span>` : ''}<span>${esc(o.endLabel || 'heute')}</span></div>`;
  }
  // Säulen (≤ 24 px, 4 px runde Kappe, 2 px Lücke), optional Ziel-Linie.
  _bars(id, o) {
    const items = o.items; if (!items.length) return '';
    const H = o.height || 90;
    const max = Math.max(...items.map((x) => x.v || 0), o.goal || 0) * 1.08 || 1;
    this._charts[id] = { kind: 'bars', items, tip: o.tip };
    const goal = o.goal ? `<div style="position:absolute;left:0;right:0;bottom:${(o.goal / max) * 100}%;border-top:1px solid var(--primary-text-color);opacity:.45;pointer-events:none"></div><span class="small muted" style="position:absolute;right:0;bottom:calc(${(o.goal / max) * 100}% + 2px)">${esc(o.goalLabel || 'Ziel')}</span>` : '';
    return `<div class="chart" data-chart="${id}" style="height:${H}px"><div style="position:absolute;inset:0">${goal}
      <div class="bars">${items.map((x, i) => `<div class="b" data-i="${i}" style="height:${Math.max(((x.v || 0) / max) * 100, x.v ? 3 : 1.5)}%;background:${x.color || o.color};${x.muted ? 'opacity:.4;' : ''}"></div>`).join('')}</div></div></div>
      <div class="xlab"><span>${esc(o.first || '')}</span>${o.mid ? `<span>${esc(o.mid)}</span>` : ''}<span>${esc(o.last || '')}</span></div>`;
  }
  _bindCharts() {
    this.shadowRoot.querySelectorAll('.chart[data-chart]').forEach((el) => {
      const ch = this._charts[el.dataset.chart]; if (!ch) return;
      const host = el.querySelector('.plot') || el;
      let tip = null; let cross = null;
      const clear = () => { tip?.remove(); cross?.remove(); tip = cross = null; el.querySelectorAll('.b.hov').forEach((b) => b.classList.remove('hov')); };
      const show = (clientX) => {
        const r = host.getBoundingClientRect(); const x = clamp(clientX - r.left, 0, r.width);
        let idx; let px;
        if (ch.kind === 'line') {
          const tx = (x / r.width) * ch.W; let best = 0; let bd = Infinity;
          ch.pts.forEach((p, i) => { const d = Math.abs(ch.X(p.t) - tx); if (d < bd) { bd = d; best = i; } });
          idx = best; px = (ch.X(ch.pts[best].t) / ch.W) * r.width;
        } else {
          const bs = [...el.querySelectorAll('.b')]; let best = 0; let bd = Infinity;
          bs.forEach((b, i) => { const br = b.getBoundingClientRect(); const c = br.left + br.width / 2 - r.left; const d = Math.abs(c - x); if (d < bd) { bd = d; best = i; } });
          idx = best; const br = bs[best].getBoundingClientRect(); px = br.left + br.width / 2 - r.left;
          bs.forEach((b, i) => b.classList.toggle('hov', i === best));
        }
        const item = ch.kind === 'line' ? ch.pts[idx] : ch.items[idx];
        if (!tip) { tip = document.createElement('div'); tip.className = 'tip'; host.appendChild(tip); }
        if (ch.kind === 'line' && !cross) { cross = document.createElement('div'); cross.className = 'cross'; host.appendChild(cross); }
        const parts = ch.tip ? ch.tip(item) : [String(item.v)];
        tip.textContent = '';
        parts.forEach((p, i) => { const s = document.createElement(i === 0 ? 'b' : 'span'); s.textContent = (i ? ' · ' : '') + p; tip.appendChild(s); });
        const tw = tip.offsetWidth || 80;
        tip.style.left = `${clamp(px, tw / 2, r.width - tw / 2)}px`;
        if (cross) cross.style.left = `${px}px`;
      };
      el.addEventListener('pointermove', (ev) => show(ev.clientX));
      el.addEventListener('pointerdown', (ev) => show(ev.clientX));
      el.addEventListener('pointerleave', clear);
    });
  }
}

/* ================= Heute ================= */
class FitHero extends FitBase {
  static get showsSetup() { return true; }
  _entities() { return [E.status, E.heute, E.woche, E.tipp, E.weight, E.run, E.serie, E.badges, E.nWeight]; }
  _css() {
    return `.rings{display:grid;grid-template-columns:repeat(auto-fit,minmax(88px,1fr));gap:8px;margin-top:14px}
    .rc{display:flex;flex-direction:column;align-items:center;gap:6px;text-align:center;min-width:0}
    .rc .lab{font-size:12px;color:var(--secondary-text-color)}
    .rc .val{font-size:15px;font-weight:650;line-height:1.1}
    .rc .sub{font-size:11px;color:var(--secondary-text-color);line-height:1.2}
    .tipbox{display:flex;gap:10px;align-items:flex-start;padding:8px 0}
    .tipbox + .tipbox{border-top:1px solid var(--divider-color,var(--fc-track))}
    .wform{display:flex;gap:8px;margin-top:10px}.wform input{flex:1;width:0}`;
  }
  _render() {
    const c = this._c(); const st = this._st(E.status); const sa = st.attributes || {};
    const h = this._a(E.heute); const wk = (this._a(E.woche).current) || {};
    const w = this._a(E.weight); const run = this._a(E.run); const tips = this._a(E.tipp).tips || [];
    const now = new Date(); const name = (this._hass.user?.name || '').split(' ')[0];
    const hour = now.getHours(); const hi = hour < 11 ? 'Guten Morgen' : hour < 18 ? 'Hallo' : 'Guten Abend';
    const streak = this._num(E.serie) || 0;
    const head = `<div class="row between" style="align-items:flex-start">
        <div><div class="eyebrow">${WD[now.getDay()]}, ${now.getDate()}. ${MON[now.getMonth()]}</div>
        <div class="mid" style="margin-top:4px">${hi}${name ? ` ${esc(name)}` : ''}</div></div>
        <div class="row" style="gap:6px">${streak > 0 ? `<span class="chip tap" data-nav="${esc(this._config.badges_path || 'erfolge')}" title="Wochen in Folge geschafft">${icon('fire', 14)}${streak} ${streak === 1 ? 'Woche' : 'Wochen'}</span>` : ''}</div></div>`;
    const conn = sa.garmin?.connected || sa.yazio?.connected;
    if (!conn) {
      return `<div class="card">${head}
        <div style="margin-top:14px;font-weight:600">Einmal anmelden – dann läuft alles automatisch.</div>
        <div class="small muted" style="margin-top:4px">In der Seitenleiste „Fit Coach“ öffnen, mit dem Garmin-Konto anmelden (bei Zwei-Faktor kommt danach der Code) und optional Yazio verbinden. Der erste Abruf holt die letzten Wochen nach.</div>
        <div style="margin-top:12px"><button class="btn" data-nav="panel">${icon('login', 18)}Jetzt anmelden</button></div></div>`;
    }
    // Ringe
    const rings = [];
    const am = wk.active_min; if (am != null) rings.push({ p: (am / 150) * 100, col: c.run, val: `${fmt(am)} min`, lab: 'Bewegung', sub: 'Woche · Ziel 150', ok: am >= 150, ic: 'heart-pulse' });
    if (h.steps != null) rings.push({ p: h.step_goal ? (h.steps / h.step_goal) * 100 : 0, col: c.weight, val: fmt(h.steps), lab: 'Schritte', sub: h.step_goal ? `Ziel ${fmt(h.step_goal)}` : '', ok: h.step_goal && h.steps >= h.step_goal, ic: 'walk' });
    if (h.kcal != null && h.kcal_goal) {
      const rem = h.kcal_remaining; rings.push({ p: (h.kcal / h.kcal_goal) * 100, col: c.food, val: fmt(h.kcal), lab: 'kcal gegessen', sub: rem >= 0 ? `noch ${fmt(rem)}` : `${fmt(-rem)} über Ziel`, ok: false, ic: 'food-apple-outline' });
    }
    const ringHtml = rings.length ? `<div class="rings tap" data-nav="${esc(this._config.week_path || 'woche')}">${rings.map((r) => `<div class="rc">${this._ring(r.p, r.col, 72, 8, `<span style="color:${r.ok ? c.goodText : 'var(--secondary-text-color)'}">${icon(r.ok ? 'check' : r.ic, 22)}</span>`)}<div class="val">${esc(r.val)}</div><div class="lab">${esc(r.lab)}</div><div class="sub">${esc(r.sub)}</div></div>`).join('')}</div>` : '';
    // Gewicht
    let weightHtml = '';
    if (w.has_data) {
      const d7 = w.change_7d; const good = d7 != null && d7 < 0;
      weightHtml = `<div class="hr"></div><div class="row between tap" data-nav="${esc(this._config.weight_path || 'gewicht')}">
        <div class="row">${this._sic('weight', 'scale-bathroom')}<div><div style="font-weight:600">${fmt(w.trend, 1)} kg <span class="small muted" style="font-weight:400">Trend</span></div>
        <div class="small muted">${d7 != null ? `<span class="${good ? 'ok' : ''}">${signed(d7, 1, 'kg')}</span> in 7 Tagen` : 'Trend ab 2 Wochen Messungen'}${w.goal ? ` · Ziel ${fmt(w.goal, 1)} kg` : ''}</div></div></div>
        ${w.tempo?.kind === 'warn' ? this._status('warn', 'zu schnell') : ''}</div>`;
    }
    const weighed = h.weighed_today;
    const entry = `<div class="small muted" style="margin-top:${w.has_data ? 8 : 0}px">${weighed ? `${icon('check', 14)} Heute gewogen: ${fmt(h.weight_last, 1)} kg` : 'Heute schon gewogen? (morgens, nach dem Toilettengang)'}</div>
      ${weighed ? '' : `<div class="wform"><input class="in" data-form="w" id="w" type="number" inputmode="decimal" step="0.1" min="30" max="250" placeholder="kg, z. B. ${w.trend ? fmt(w.trend, 1) : '70,0'}"><button class="btn" data-submit="w">Speichern</button></div>`}`;
    if (!w.has_data) weightHtml = `<div class="hr"></div>`;
    // Nächstes Workout
    const nx = run.next || h.next;
    const nextHtml = nx ? `<div class="hr"></div><div class="eyebrow">Nächster Lauf</div>
      <div class="item">${this._sic('run', 'run')}<div style="flex:1;min-width:0"><div class="t">${esc(nx.title)}</div>
      <div class="c">${nx.source === 'garmin' ? `Garmin-Plan · ${esc(dayLabel(nx.date))}` : esc(nx.detail || '')}</div></div></div>` : '';
    // Tipps
    const tipHtml = tips.length ? `<div class="hr"></div><div class="eyebrow">Für dich</div>${tips.map((t) => `<div class="tipbox">
      <span style="color:${t.kind === 'warn' ? c.warnText : 'var(--secondary-text-color)'};margin-top:1px">${icon(t.kind === 'warn' ? 'alert-circle-outline' : t.cat === 'lob' ? 'star-outline' : 'lightbulb-on-outline', 18)}</span>
      <div style="flex:1;min-width:0"><div style="font-weight:600">${esc(t.title)}</div><div class="small muted">${esc(t.text)}</div>
      ${t.url ? `<a class="src" href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.source)}</a>` : ''}</div></div>`).join('')}` : '';
    const warn = st.state === 'neu anmelden' ? `<div class="warnline wtx tap" data-nav="panel">${icon('alert', 14)} Anmeldung abgelaufen – bitte in „Fit Coach“ neu anmelden.</div>`
      : st.state === 'fehler' ? `<div class="warnline wtx">${icon('alert', 14)} Letzter Abruf fehlgeschlagen – nächster Versuch automatisch.</div>` : '';
    return `<div class="card">${head}${ringHtml}${weightHtml}${entry}${nextHtml}${tipHtml}${warn}${this._err ? `<div class="warnline wtx">${esc(this._err)}</div>` : ''}</div>`;
  }
  _bindExtra(root) {
    const b = root.querySelector('[data-submit="w"]'); if (!b) return;
    b.addEventListener('click', (ev) => {
      ev.stopPropagation(); const v = num(String(root.getElementById('w').value).replace(',', '.'));
      if (v == null || v < 30 || v > 250) { this._err = 'Bitte ein Gewicht zwischen 30 und 250 kg eingeben.'; this._editing = false; this._paint(); return; }
      this._err = null; this._editing = false; b.classList.add('busy'); this._setNum(E.nWeight, v);
    });
  }
}

/* ================= Woche ================= */
class FitWeek extends FitBase {
  _entities() { return [E.status, E.woche, E.serie]; }
  _css() { return `.pips{display:flex;gap:5px;margin-left:auto;flex:none}.pips i{width:12px;height:12px;border-radius:50%;background:var(--fc-track)}
    .hist{display:grid;grid-template-columns:repeat(8,1fr);gap:4px;margin-top:8px;text-align:center}
    .hist .d{height:26px;border-radius:8px;display:grid;place-items:center}`; }
  _render() {
    const c = this._c(); const a = this._a(E.woche); const w = a.current || {};
    if (!w.w) return `<div class="card"><div class="eyebrow">Diese Woche</div><div class="small muted" style="margin-top:6px">Erscheint nach dem ersten Abruf.</div></div>`;
    const pips = (done, target, col) => `<div class="pips">${Array.from({ length: Math.max(target, done) }, (_, i) => `<i style="${i < done ? `background:${col}` : ''}${i >= target ? ';opacity:.55' : ''}"></i>`).join('')}</div>`;
    const rows = [];
    if (w.run_target) rows.push(`<div class="item">${this._sic('run', 'run')}<div style="flex:1"><div class="t">Läufe</div><div class="c">${w.runs} von ${w.run_target}${w.runs >= w.run_target ? ' · geschafft' : ''}</div></div>${pips(w.runs, w.run_target, c.run)}</div>`);
    if (w.gym_target) rows.push(`<div class="item">${this._sic('gym', 'dumbbell')}<div style="flex:1"><div class="t">Gym</div><div class="c">${w.gym} von ${w.gym_target}${w.gym >= w.gym_target ? ' · geschafft' : ''}</div></div>${pips(w.gym, w.gym_target, c.gym)}</div>`);
    rows.push(`<div class="item">${this._sic('neutral', 'heart-pulse')}<div style="flex:1;min-width:0"><div class="row between"><div class="t">Bewegung</div><div class="small muted">${fmt(w.active_min)} / 150 min</div></div>
      <div class="bar" style="margin-top:6px"><i style="width:${clamp((w.active_min / 150) * 100, 0, 100)}%;background:${w.active_min >= 150 ? c.good : c.run}"></i></div>
      <div class="c" style="margin-top:4px">${w.active_src === 'garmin' ? 'Garmin-Intensitätsminuten (intensiv zählt doppelt)' : 'aus den Aktivitäten'} · WHO: 150–300 min/Woche</div></div></div>`);
    if (w.steps_avg) rows.push(`<div class="item">${this._sic('weight', 'walk')}<div style="flex:1"><div class="t">Schritte</div><div class="c">Ø ${fmt(w.steps_avg)} pro Tag${w.step_goal ? ` · Ziel ${fmt(w.step_goal)}` : ''}</div></div></div>`);
    const hist = (a.history || []).slice(-8);
    const histHtml = hist.length ? `<div class="hr"></div><div class="row between"><div class="eyebrow">Letzte Wochen</div><span class="small muted">${icon('fire', 14)} Serie ${a.streak || 0}</span></div>
      <div class="hist">${hist.map((h) => `<div><div class="d" style="background:${h.ok ? `${c.good}26` : 'var(--fc-track)'};${h.current && !h.ok ? 'outline:1px dashed var(--secondary-text-color);outline-offset:-1px' : ''}">${h.ok ? `<span class="ok">${icon('check', 16)}</span>` : ''}</div><div class="small muted" style="margin-top:2px">${pd(h.w).getDate()}.${pd(h.w).getMonth() + 1}.</div></div>`).join('')}</div>
      <div class="small muted" style="margin-top:6px">Eine Woche zählt, wenn das Wochenziel <b>oder</b> 150 Minuten Bewegung erreicht sind.</div>` : '';
    return `<div class="card"><div class="row between"><div><div class="eyebrow">Diese Woche</div>
      <div class="row" style="gap:8px;margin-top:4px"><span class="big" style="${w.ok ? `color:${c.goodText}` : ''}">${w.pct} %</span><span class="small muted">${w.workouts_ok ? 'Wochenziel geschafft' : w.move_ok ? '150 Minuten erreicht' : 'vom Wochenziel'}</span></div></div>
      <div class="small muted" style="text-align:right">${w.days_left > 0 ? `noch ${w.days_left} ${w.days_left === 1 ? 'Tag' : 'Tage'}` : 'letzter Tag'}</div></div>
      <div style="margin-top:6px">${rows.join('')}</div>${histHtml}</div>`;
  }
}

/* ================= Gewicht ================= */
class FitWeight extends FitBase {
  _entities() { return [E.status, E.weight, E.nWeight, E.nGoal]; }
  _render() {
    const c = this._c(); const w = this._a(E.weight);
    const entry = `<div class="hr"></div><div class="eyebrow">Gewicht eintragen</div>
      <div class="row" style="margin-top:8px"><input class="in" data-form="w" id="w" type="number" inputmode="decimal" step="0.1" min="30" max="250" placeholder="kg" style="flex:1;width:0"><button class="btn" data-submit="w">Speichern</button></div>
      <div class="small muted" style="margin-top:6px">Wiegt dich eine Garmin-Waage oder trägst du in Yazio ein, kommt das Gewicht automatisch. Eigene Eingaben gehen vor.${(w.series || []).some((p) => p.s === 'm' && p.d === localIso()) ? ' <button class="link" data-undo="1">Heutige Eingabe löschen</button>' : ''}</div>`;
    if (!w.has_data) {
      return `<div class="card"><div class="eyebrow">Gewicht</div><div style="margin-top:6px;font-weight:600">Noch keine Messung</div>
        <div class="small muted" style="margin-top:4px">Ab der ersten Messung erscheint hier der Verlauf, ab 5 Messungen in 2 Wochen auch das Tempo.</div>${entry}</div>`;
    }
    const range = this._ui.range || '90';
    const all = (w.series || []).map((p) => ({ t: pd(p.d).getTime(), v: p.t, raw: p.w, s: p.s, d: p.d }));
    const cut = range === 'all' ? 0 : Date.now() - (+range) * 864e5;
    const pts = all.filter((p) => p.t >= cut);
    const src = { m: 'Dashboard', g: 'Garmin', y: 'Yazio' };
    const chart = this._line('w', {
      pts, raw: pts.map((p) => ({ t: p.t, v: p.raw })), hover: pts, color: c.weight, goal: w.goal && w.goal >= Math.min(...pts.map((p) => p.v)) - 3 ? w.goal : null,
      goalLabel: w.goal ? `Ziel ${fmt(w.goal, 1)}` : '', height: 120, fmt: (v) => fmt(v, 1),
      tip: (p) => [`${fmt(p.v, 1)} kg Trend`, `${fmt(p.raw, 1)} kg gewogen`, `${dayLabel(p.d)} (${src[p.s] || ''})`],
    });
    const t = w.tempo || {};
    const kind = t.kind === 'good' ? 'good' : t.kind === 'warn' ? 'warn' : 'neutral';
    const d7 = w.change_7d; const d30 = w.change_30d;
    const prog = w.goal && w.progress_pct != null ? `<div class="hr"></div><div class="row between small"><span class="muted">Start ${fmt(w.start_kg, 1)} kg · ${ddmm(w.start_date)}</span><span class="muted">Ziel ${fmt(w.goal, 1)} kg${w.goal_source && w.goal_source !== 'Dashboard' ? ` (${esc(w.goal_source)})` : ''}</span></div>
      <div class="bar" style="margin-top:6px;height:10px"><i style="width:${w.progress_pct}%;background:${c.weight}"></i></div>
      <div class="row between" style="margin-top:6px"><span style="font-weight:600">${w.progress_pct} % geschafft</span><span class="small muted">${w.goal_reached ? 'Ziel erreicht 🎉' : `noch ${fmt(w.remaining, 1)} kg`}</span></div>
      ${w.eta && !w.goal_reached ? `<div class="small muted" style="margin-top:4px">${icon('calendar-flag', 14)} Bei aktuellem Tempo etwa ${esc(monthYear(w.eta))} – grobe Hochrechnung, die Abnahme wird zum Ende hin meist langsamer.</div>` : ''}` : (!w.goal ? `<div class="small muted" style="margin-top:10px">Kein Zielgewicht gesetzt – in Yazio, Garmin oder unter Einstellungen eintragen.</div>` : '');
    return `<div class="card"><div class="row between" style="align-items:flex-start"><div class="eyebrow">Gewicht · Trend</div>
      <div class="seg">${[['30', '30 T'], ['90', '90 T'], ['all', 'Alles']].map(([k, l]) => `<button class="${range === k ? 'on' : ''}" data-ui="range=${k}">${l}</button>`).join('')}</div></div>
      <div class="row wrap" style="gap:10px;margin-top:6px;align-items:baseline"><span class="big">${fmt(w.trend, 1)}</span><span class="muted">kg</span>
      ${d7 != null ? `<span class="chip"><span class="${d7 < 0 ? 'ok' : ''}" style="font-weight:600">${signed(d7, 1, 'kg')}</span> <span class="muted">7 Tage</span></span>` : ''}
      ${d30 != null ? `<span class="chip"><span class="${d30 < 0 ? 'ok' : ''}" style="font-weight:600">${signed(d30, 1, 'kg')}</span> <span class="muted">30 Tage</span></span>` : ''}</div>
      <div style="margin-top:10px">${this._status(kind, t.label || '')}</div>
      ${t.text ? `<div class="small muted" style="margin-top:6px">${esc(t.text)}</div>` : ''}
      ${chart}
      <div class="small muted" style="margin-top:6px">Linie = geglätteter Trend, Punkte = gewogene Werte. Tageswerte schwanken um 1–2 kg (Wasser, Salz, Zyklus) – der Trend zeigt die echte Richtung.</div>
      ${prog}
      <div class="grid2" style="margin-top:12px">
        <div class="tile"><div class="v">${w.rate_kg_week != null ? `${signed(w.rate_kg_week, 2)}` : '–'}</div><div class="l">kg pro Woche${w.rate_pct_week != null ? ` (${signed(w.rate_pct_week, 1)} %)` : ''}</div></div>
        <div class="tile"><div class="v">${w.weighins_7d ?? 0}×</div><div class="l">gewogen in 7 Tagen${w.weighin_streak > 1 ? ` · ${w.weighin_streak} Tage in Folge` : ''}</div></div>
      </div>
      <div class="small muted" style="margin-top:8px">Letzte Messung: ${fmt(w.last_kg, 1)} kg, ${esc(dayLabel(w.last_date))} (${esc(w.last_source || '')})</div>
      ${entry}${this._err ? `<div class="warnline wtx">${esc(this._err)}</div>` : ''}</div>`;
  }
  _bindExtra(root) {
    const b = root.querySelector('[data-submit="w"]');
    if (b) b.addEventListener('click', (ev) => {
      ev.stopPropagation(); const v = num(String(root.getElementById('w').value).replace(',', '.'));
      if (v == null || v < 30 || v > 250) { this._err = 'Bitte ein Gewicht zwischen 30 und 250 kg eingeben.'; this._editing = false; this._paint(); return; }
      this._err = null; this._editing = false; b.classList.add('busy'); this._setNum(E.nWeight, v);
    });
    const u = root.querySelector('[data-undo]');
    if (u) u.addEventListener('click', (ev) => { ev.stopPropagation(); this._press(E.bWeightUndo); });
  }
}

/* ================= Ernährung ================= */
class FitFood extends FitBase {
  _entities() { return [E.status, E.food]; }
  _render() {
    const c = this._c(); const n = this._a(E.food); const yz = this._a(E.status).yazio || {};
    if (!n.has_data) {
      return `<div class="card"><div class="eyebrow">Essen · Yazio</div><div style="margin-top:6px;font-weight:600">${yz.connected ? 'Noch keine Einträge abgerufen' : 'Yazio ist nicht verbunden'}</div>
        <div class="small muted" style="margin-top:4px">${yz.connected ? 'Erscheint nach dem nächsten Abruf.' : 'Optional: In „Fit Coach“ mit E-Mail und Yazio-Passwort verbinden. Dann erscheinen hier Kalorien, Eiweiß und der geschätzte echte Verbrauch.'}</div>
        ${yz.connected ? '' : `<div style="margin-top:10px"><button class="btn sec" data-nav="panel">${icon('link-variant', 18)}Yazio verbinden</button></div>`}</div>`;
    }
    const t = n.today || {};
    const pct = t.goal ? (t.kcal / t.goal) * 100 : 0;
    const macro = (label, v, goal, col) => `<div style="margin-top:8px"><div class="row between small"><span>${label}</span><span class="muted">${fmt(v)}${goal ? ` / ${fmt(goal)}` : ''} g</span></div>
      <div class="bar" style="margin-top:4px"><i style="width:${goal ? clamp((v / goal) * 100, 0, 100) : 0}%;background:${col}"></i></div></div>`;
    const ring = this._ring(pct, c.food, 92, 9, `<div><div style="font-size:20px;font-weight:650;line-height:1">${fmt(t.kcal)}</div><div class="small muted">von ${fmt(t.goal)}</div></div>`);
    const rem = t.remaining;
    const series = (n.series || []).slice(-14);
    const today = localIso();
    const bars = this._bars('k', {
      items: series.map((s) => ({ v: s.k, muted: !s.c || s.d === today, d: s.d, g: s.g, p: s.p, c: s.c })), color: c.food, goal: n.avg7_goal || t.goal, height: 90,
      first: ddmm(series[0]?.d), last: 'heute', mid: 'helle Säulen = unvollständig/heute',
      tip: (x) => [`${fmt(x.v)} kcal`, `${fmt(x.p)} g Eiweiß`, `${dayLabel(x.d)}${x.c ? '' : ' (unvollständig)'}`],
    });
    const pt = n.protein_target;
    const diff = n.avg7_diff;
    const ex = n.expenditure || {};
    const hints = (n.hints || []).map((h) => `<div class="warnline ${h.kind === 'warn' ? 'wtx' : 'muted'}">${icon(h.kind === 'warn' ? 'alert-circle-outline' : 'information-outline', 14)} ${esc(h.text)}</div>`).join('');
    return `<div class="card"><div class="eyebrow">Essen heute · Yazio</div>
      <div class="row" style="gap:16px;margin-top:10px;align-items:center">${ring}<div style="flex:1;min-width:0">
        <div style="font-weight:600">${rem == null ? '' : rem >= 0 ? `Noch ${fmt(rem)} kcal` : `${fmt(-rem)} kcal über Ziel`}</div>
        <div class="small muted">${t.adds_activity ? `Ziel inkl. ${fmt(t.activity_kcal)} kcal Bewegung` : 'Ziel aus Yazio'} · ${t.meals || 0} Mahlzeiten</div>
        ${macro('Eiweiß', t.protein, t.protein_goal, c.food)}${macro('Kohlenhydrate', t.carbs, t.carbs_goal, c.neutral)}${macro('Fett', t.fat, t.fat_goal, c.neutral)}</div></div>
      ${t.water_goal ? `<div class="row between small" style="margin-top:10px"><span>${icon('cup-water', 14)} Wasser</span><span class="muted">${fmt((t.water_ml || 0) / 1000, 1)} / ${fmt(t.water_goal / 1000, 1)} l</span></div>` : ''}
      <div class="hr"></div><div class="row between"><div class="eyebrow">Letzte 14 Tage</div><span class="small muted">${n.logged7}/7 Tage erfasst</span></div>
      ${bars}
      <div class="grid2" style="margin-top:12px">
        <div class="tile"><div class="v">${fmt(n.avg7_kcal)}</div><div class="l">Ø kcal pro Tag (7 Tage)${diff != null ? ` · ${diff === 0 ? 'genau im Ziel' : `${fmt(Math.abs(diff))} ${diff < 0 ? 'unter' : 'über'} Ziel`}` : ''}</div></div>
        <div class="tile"><div class="v">${fmt(n.avg7_protein)} g</div><div class="l">Ø Eiweiß${pt ? ` · Richtwert ${pt.low}–${pt.high} g` : ''}</div></div>
      </div>
      ${ex.ok ? `<div class="hr"></div><div class="row" style="align-items:flex-start">${icon('fire', 20)}<div style="flex:1"><div style="font-weight:600">Echter Verbrauch ≈ ${fmt(ex.kcal)} kcal/Tag</div>
        <div class="small muted">Geschätzt aus ${ex.complete_days} erfassten Tagen und deinem Gewichtstrend (${signed(ex.trend_change, 1, 'kg')} in ${ex.days} Tagen) · Verlässlichkeit ${esc(ex.confidence)}${n.garmin_total_kcal ? ` · Garmin schätzt heute ${fmt(n.garmin_total_kcal)} kcal` : ''}.</div></div></div>`
        : `<div class="small muted" style="margin-top:10px">${icon('fire', 14)} Der echte Verbrauch wird geschätzt, sobald ${ex.need || 10} Tage vollständig erfasst sind (bisher ${ex.complete_days || 0}).</div>`}
      ${hints}</div>`;
  }
}

/* ================= Laufen ================= */
class FitRun extends FitBase {
  _entities() { return [E.status, E.run]; }
  _render() {
    const c = this._c(); const r = this._a(E.run);
    if (!r.has_data) {
      return `<div class="card"><div class="eyebrow">Laufen</div><div style="margin-top:6px;font-weight:600">Noch kein Lauf</div>
        <div class="small muted" style="margin-top:4px">Einfach auf der Uhr „Laufen“ starten. Tipp für den Anfang: 20–30 Minuten abwechselnd 1–2 min locker laufen und gehen – so locker, dass Reden geht. Garmin Coach (kostenlos in Garmin Connect › Training) erstellt einen Plan, der hier automatisch angezeigt wird.</div></div>`;
    }
    const p = r.pace || {};
    const delta = p.easy_pace_delta;
    const nx = r.next;
    const pips = Array.from({ length: Math.max(r.target_per_week || 0, r.week_runs) }, (_, i) => `<i style="display:inline-block;width:12px;height:12px;border-radius:50%;background:${i < r.week_runs ? c.run : 'var(--fc-track)'}"></i>`).join('');
    const pacePts = (p.points || []).map((x) => ({ t: pd(x.d).getTime(), v: x.p, d: x.d, e: x.e }));
    const paceChart = this._line('p', { pts: pacePts, color: c.run, invert: true, height: 90, fmt: pace, empty: 'Die Kurve erscheint ab zwei lockeren Läufen (≥ 70 % Zeit in Zone 1–2).',
      tip: (x) => [`${pace(x.v)} /km`, x.e ? `${fmt(x.e, 2)} m/Schlag` : '', dayLabel(x.d)].filter(Boolean), endLabel: 'letzter Lauf' });
    const weeks = r.weeks || [];
    const kmBars = this._bars('km', { items: weeks.map((w, i) => ({ v: w.km, w: w.w, n: w.n, min: w.min, muted: i === weeks.length - 1 })), color: c.run, height: 70,
      first: `ab ${ddmm(weeks[0]?.w)}`, last: 'diese Woche (läuft)', tip: (x) => [`${fmt(x.v, 1)} km`, `${x.n} ${x.n === 1 ? 'Lauf' : 'Läufe'}`, `${x.min} min`, `Woche ab ${ddmm(x.w)}`] });
    const prs = r.prs || [];
    const prTile = (pr) => `<div class="tile"><div class="v">${pr.kind === 'time' ? dur(pr.value) : `${fmt(pr.value / 1000, 1)} km`}</div><div class="l">${esc(pr.label)}${pr.estimated ? ' (Ø-Tempo)' : ''} · ${ddmm(pr.date)}</div></div>`;
    const pr = r.predictions || {};
    const predHist = (r.prediction_history || []).map((x) => ({ t: pd(x.d).getTime(), v: x.s, d: x.d }));
    const predChart = predHist.length >= 3 ? this._line('pr', { pts: predHist, color: c.run, invert: true, height: 60, fmt: dur, tip: (x) => [dur(x.v), dayLabel(x.d)] }) : '';
    const easy = r.easy_share_14d;
    const hints = (r.hints || []).map((h) => `<div class="warnline ${h.kind === 'warn' ? 'wtx' : 'muted'}">${icon(h.kind === 'warn' ? 'alert-circle-outline' : 'information-outline', 14)} ${esc(h.text)}</div>`).join('');
    const listOpen = this._open.has('runs');
    const recent = (r.recent || []).slice(0, listOpen ? 15 : 4).map((x) => `<div class="item"><div style="flex:1;min-width:0"><div class="t">${fmt(x.km, 2)} km · ${pace(x.pace)} /km</div>
      <div class="c">${esc(dayLabel(x.date))} · ${dur(x.sec)}${x.hr ? ` · Ø ${x.hr} bpm` : ''}${x.easy != null ? ` · ${Math.round(x.easy * 100)} % locker` : ''}</div></div></div>`).join('');
    return `<div class="card"><div class="row between"><div class="eyebrow">Laufen · diese Woche</div><div class="row" style="gap:4px">${pips}</div></div>
      <div class="row" style="gap:10px;margin-top:4px;align-items:baseline"><span class="big">${r.week_runs}</span><span class="muted">${r.week_runs === 1 ? 'Lauf' : 'Läufe'} · ${fmt(r.week_km, 1)} km</span></div>
      ${nx ? `<div class="item" style="margin-top:6px">${this._sic('run', nx.source === 'garmin' ? 'calendar-check' : 'run')}<div style="flex:1;min-width:0"><div class="t">${esc(nx.title)}</div><div class="c">${nx.source === 'garmin' ? `Aus deinem Garmin-Plan · ${esc(dayLabel(nx.date))}` : esc(nx.detail || '')}</div></div></div>` : ''}
      ${hints}
      <div class="hr"></div><div class="eyebrow">Lockere Pace</div>
      <div class="row wrap" style="gap:10px;margin-top:4px;align-items:baseline"><span class="big">${pace(p.easy_pace)}</span><span class="muted">/km</span>
        ${delta != null ? `<span class="chip"><span class="${delta < 0 ? 'ok' : ''}" style="font-weight:600">${delta < 0 ? `${Math.abs(delta)} s schneller` : delta > 0 ? `${delta} s langsamer` : 'gleich'}</span> <span class="muted">als vor 4 Wochen</span></span>` : ''}</div>
      <div class="small muted" style="margin-top:4px">Median der lockeren Läufe der letzten 4 Wochen${p.m_per_beat ? ` · ${fmt(p.m_per_beat, 2)} m pro Herzschlag${p.m_per_beat_before ? ` (vorher ${fmt(p.m_per_beat_before, 2)})` : ''}` : ''}. Schneller wird man vor allem durch viel lockeres Laufen.</div>
      ${paceChart}
      ${easy != null ? `<div style="margin-top:12px"><div class="row between small"><span>Locker gelaufen (14 Tage, Zone 1–2)</span><span class="muted">${easy} % · Ziel ≈ 80 %</span></div>
        <div class="bar" style="margin-top:4px"><i style="width:${easy}%;background:${c.run}"></i><span class="mk" style="left:calc(80% - 1px)"></span></div></div>` : ''}
      <div class="hr"></div><div class="eyebrow">Bestzeiten</div>
      <div class="grid2" style="margin-top:8px">${prs.length ? prs.map(prTile).join('') : '<div class="small muted">Erscheinen nach den ersten Läufen.</div>'}</div>
      ${pr['5k'] || r.vo2max ? `<div class="hr"></div><div class="row between"><div class="eyebrow">Garmin-Prognose</div>${r.vo2max ? `<span class="small muted">VO2max ${fmt(r.vo2max, 1)}</span>` : ''}</div>
        <div class="grid2" style="margin-top:8px">${pr['5k'] ? `<div class="tile"><div class="v">${dur(pr['5k'])}</div><div class="l">5 km</div></div>` : ''}${pr['10k'] ? `<div class="tile"><div class="v">${dur(pr['10k'])}</div><div class="l">10 km</div></div>` : ''}</div>
        ${predChart}<div class="small muted" style="margin-top:4px">Schätzung der Uhr aus VO2max und Training – kein Muss, eher ein Fitness-Thermometer.</div>` : ''}
      <div class="hr"></div><div class="row between"><div class="eyebrow">Kilometer pro Woche</div><span class="small muted">gesamt ${fmt(r.total_km, 0)} km · ${r.total_runs} Läufe</span></div>
      ${kmBars}
      <div class="hr"></div><div class="eyebrow">Letzte Läufe</div>${recent}
      ${(r.recent || []).length > 4 ? `<button class="link" data-toggle="runs">${listOpen ? 'weniger' : 'alle anzeigen'}</button>` : ''}</div>`;
  }
}

/* ================= Gym ================= */
class FitGym extends FitBase {
  _entities() { return [E.status, E.gym, E.sEx, E.nKg, E.nReps]; }
  _render() {
    const c = this._c(); const g = this._a(E.gym);
    const st = { erhöhen: ['good', 'steigern'], aufbauen: ['neutral', 'dranbleiben'], basis: ['neutral', 'Startwert'], wiedereinstieg: ['warn', 'Wiedereinstieg'], prüfen: ['serious', 'prüfen'] };
    const recs = (g.records || []);
    const showAll = this._open.has('recs');
    const recHtml = recs.length ? recs.slice(0, showAll ? 40 : 6).map((r) => `<div class="item">${this._sic('gym', 'dumbbell', 30)}<div style="flex:1;min-width:0">
      <div class="row between"><div class="t">${esc(r.name)}</div>${r.new ? `<span class="chip" style="background:${c.good}26">${icon('star', 12)}neu</span>` : ''}</div>
      <div class="c">${r.kg > 0 ? `${fmt(r.kg, 1)} kg × ${r.reps}` : `${r.reps} Wdh. (Körpergewicht)`}${r.e1rm ? ` · e1RM ${fmt(r.e1rm, 1)} kg` : ''}${r.gain_pct ? ` · <span class="ok">+${r.gain_pct} %</span>` : ''}</div>
      <div class="c">${esc(dayLabel(r.date))}${r.source === 'manuell' ? ' · selbst eingetragen' : ''}${r.improvements ? ` · ${r.improvements}× verbessert` : ''}</div></div></div>`).join('')
      : '<div class="small muted" style="padding:8px 0">Noch keine Rekorde. Krafttraining auf der Uhr aufzeichnen (Übungen mit Gewicht in Garmin Connect ergänzen) oder unten selbst eintragen.</div>';
    const prog = (g.progression || []).filter((p) => p.status !== 'basis').slice(0, 5).map((p) => {
      const [k, l] = st[p.status] || ['neutral', p.status];
      return `<div class="item"><div style="flex:1;min-width:0"><div class="row between wrap"><div class="t">${esc(p.name)}</div>${this._status(k, l)}</div><div class="c" style="margin-top:2px">${esc(p.headline)}</div>
        ${this._open.has(`p_${p.id}`) ? `<div class="c" style="margin-top:4px">${esc(p.detail)}</div>` : `<button class="link" data-toggle="p_${p.id}">warum?</button>`}</div></div>`;
    }).join('');
    const ex = this._st(E.sEx); const opts = ex?.attributes?.options || [];
    const kg = this._num(E.nKg); const reps = this._num(E.nReps);
    const form = ex ? `<div class="hr"></div><div class="eyebrow">Rekord selbst eintragen</div>
      <select class="in" id="ex" data-form="r" style="width:100%;margin-top:8px">${opts.map((o) => `<option ${o === ex.state ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>
      <div class="row" style="margin-top:8px"><input class="in" id="kg" data-form="r" type="number" inputmode="decimal" step="0.5" min="0" value="${kg ?? ''}" style="flex:1;width:0" aria-label="Gewicht in kg"><span class="muted">kg ×</span>
      <input class="in" id="reps" data-form="r" type="number" inputmode="numeric" step="1" min="1" max="50" value="${reps ?? ''}" style="width:64px" aria-label="Wiederholungen"><span class="muted">Wdh.</span></div>
      <div class="row" style="margin-top:8px;gap:8px"><button class="btn" data-submit="r">${icon('content-save-outline', 18)}Speichern</button>${g.manual_count ? '<button class="btn sec" data-undo-rec="1">Letzten löschen</button>' : ''}</div>
      <div class="small muted" style="margin-top:6px">Bester Satz zählt. 0 kg = Körpergewicht (dann zählen die Wiederholungen).</div>` : '';
    const ls = g.last_session;
    return `<div class="card"><div class="row between"><div class="eyebrow">Gym</div><span class="small muted">${g.sessions_week || 0}/${g.target_per_week || 0} diese Woche · ${g.sessions_month || 0} im Monat</span></div>
      ${ls ? `<div class="small muted" style="margin-top:4px">Letztes Training ${esc(dayLabel(ls.date))} · ${ls.min} min</div>` : ''}
      <div class="eyebrow" style="margin-top:12px">Deine Rekorde</div>${recHtml}
      ${recs.length > 6 ? `<button class="link" data-toggle="recs">${showAll ? 'weniger' : `alle ${recs.length} anzeigen`}</button>` : ''}
      ${prog ? `<div class="hr"></div><div class="eyebrow">Nächstes Mal</div>${prog}` : ''}
      ${g.missing_sets_hint ? '<div class="warnline muted">Für Rekorde braucht Garmin die Übungen mit Gewicht – in Garmin Connect › Aktivität › Übungen bearbeiten.</div>' : ''}
      ${form}
      <div class="small muted" style="margin-top:10px">e1RM = geschätztes Maximum für eine Wiederholung (Epley, nur bis 12 Wdh.) – zum Vergleichen mit dir selbst, kein Test nötig. Krafttraining hilft beim Abnehmen, die Muskeln zu erhalten.</div>
      ${this._err ? `<div class="warnline wtx">${esc(this._err)}</div>` : ''}</div>`;
  }
  _bindExtra(root) {
    const b = root.querySelector('[data-submit="r"]');
    if (b) b.addEventListener('click', async (ev) => {
      ev.stopPropagation();
      const ex = root.getElementById('ex').value; const kg = num(String(root.getElementById('kg').value).replace(',', '.')); const reps = num(root.getElementById('reps').value);
      if (kg == null || kg < 0 || reps == null || reps < 1) { this._err = 'Bitte Gewicht (0 = Körpergewicht) und Wiederholungen eintragen.'; this._editing = false; this._paint(); return; }
      this._err = null; this._editing = false; b.classList.add('busy');
      await this._call('select', 'select_option', { entity_id: E.sEx, option: ex });
      await this._setNum(E.nKg, kg); await this._setNum(E.nReps, Math.round(reps));
      setTimeout(() => this._press(E.bRec), 400);
    });
    const u = root.querySelector('[data-undo-rec]');
    if (u) u.addEventListener('click', (ev) => { ev.stopPropagation(); this._press(E.bRecUndo); });
  }
}

/* ================= Erfolge ================= */
class FitBadges extends FitBase {
  _entities() { return [E.status, E.badges]; }
  _css() { return `.bgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(96px,1fr));gap:8px;margin-top:8px}
    .bd{border-radius:14px;padding:10px 8px;text-align:center;background:var(--fc-track);min-width:0}
    .bd .bi{width:40px;height:40px;border-radius:50%;display:grid;place-items:center;margin:0 auto 6px}
    .bd .bt{font-size:12px;font-weight:600;line-height:1.2}.bd .bs{font-size:11px;color:var(--secondary-text-color);margin-top:2px}`; }
  _badge(b) {
    const c = this._c(); const col = { Laufen: c.run, Gym: c.gym, Gewicht: c.weight, Gewohnheiten: c.food, Konstanz: c.habit }[b.group] || c.neutral;
    const got = !!b.earned;
    return `<div class="bd" title="${esc(b.desc)}" style="${got ? '' : 'opacity:.75'}"><div class="bi" style="background:${got ? col : 'transparent'};color:${got ? '#fff' : 'var(--secondary-text-color)'};${got ? '' : 'border:2px dashed var(--divider-color,#8886)'}">${icon(b.icon, 22)}</div>
      <div class="bt">${esc(b.title)}</div><div class="bs">${got ? ddmm(b.earned) : `${Math.round((b.progress || 0) * 100)} %`}</div>
      ${got ? '' : `<div class="bar" style="height:4px;margin-top:5px"><i style="width:${Math.round((b.progress || 0) * 100)}%;background:${col}"></i></div>`}</div>`;
  }
  _render() {
    const a = this._a(E.badges); const all = a.badges || [];
    if (!all.length) return `<div class="card"><div class="eyebrow">Erfolge</div><div class="small muted" style="margin-top:6px">Erscheinen nach dem ersten Abruf.</div></div>`;
    if (this._config.mode !== 'full') {
      const latest = (a.latest || []).slice(0, 3); const next = (a.next || []).slice(0, 3);
      return `<div class="card tap" data-nav="${esc(this._config.nav || 'erfolge')}"><div class="row between"><div class="eyebrow">Erfolge</div><span class="small muted">${a.earned}/${a.total}</span></div>
        ${latest.length ? `<div class="small muted" style="margin-top:8px">Zuletzt</div><div class="bgrid">${latest.map((b) => this._badge(b)).join('')}</div>` : ''}
        ${next.length ? `<div class="small muted" style="margin-top:10px">Als Nächstes</div><div class="bgrid">${next.map((b) => this._badge(b)).join('')}</div>` : ''}</div>`;
    }
    const groups = ['Laufen', 'Gym', 'Gewicht', 'Gewohnheiten', 'Konstanz'];
    return `<div class="card"><div class="row between"><div class="eyebrow">Erfolge</div><span class="small muted">${a.earned} von ${a.total}</span></div>
      <div class="bar" style="margin-top:8px"><i style="width:${(a.earned / Math.max(a.total, 1)) * 100}%;background:${this._c().good}"></i></div>
      ${groups.map((g) => { const bs = all.filter((b) => b.group === g); if (!bs.length) return ''; bs.sort((x, y) => (y.earned ? 1 : 0) - (x.earned ? 1 : 0) || (y.progress - x.progress)); return `<div class="eyebrow" style="margin-top:14px">${g}</div><div class="bgrid">${bs.map((b) => this._badge(b)).join('')}</div>`; }).join('')}
      <div class="small muted" style="margin-top:12px">Einmal verdient bleibt verdient. Die Serie zählt Wochen, keine Tage – Ruhetage gehören zum Training.</div></div>`;
  }
}

/* ================= Status / Verbindung ================= */
class FitStatus extends FitBase {
  static get showsSetup() { return true; }
  _entities() { return [E.status, E.last]; }
  _render() {
    const c = this._c(); const st = this._st(E.status); const a = st.attributes || {};
    const g = a.garmin || {}; const y = a.yazio || {};
    const line = (label, x, ic) => {
      const [k, t] = !x.connected ? ['neutral', 'nicht verbunden'] : x.needs_login ? ['critical', 'neu anmelden'] : x.last_error ? ['warn', 'Hinweis'] : ['good', 'verbunden'];
      return `<div class="item">${this._sic('neutral', ic)}<div style="flex:1;min-width:0"><div class="row between wrap"><div class="t">${label}</div>${this._status(k, t)}</div>
        <div class="c">${x.last_sync ? `Letzter Abruf ${esc(dayLabel(x.last_sync.slice(0, 10)))} ${esc(x.last_sync.slice(11, 16))}` : x.connected ? 'Abruf läuft gleich' : label === 'Yazio' ? 'optional' : 'In „Fit Coach“ anmelden'}</div>
        ${x.last_error ? `<div class="c clamp2">${esc(x.last_error)}</div>` : ''}</div></div>`;
    };
    const running = st.state === 'synchronisiert';
    return `<div class="card"><div class="eyebrow">Verbindungen</div>${line('Garmin', g, 'watch')}${line('Yazio', y, 'food-apple-outline')}
      <div class="small muted" style="margin-top:6px">Automatischer Abruf um ${(a.sync_hours || []).map((h) => `${h}`).join(', ')} Uhr${a.next_sync ? ` · nächster ${esc(dayLabel(a.next_sync.slice(0, 10)))} ${esc(a.next_sync.slice(11, 16))}` : ''}</div>
      <div class="row wrap" style="gap:8px;margin-top:12px"><button class="btn ${running ? 'busy' : ''}" data-sync="1">${icon('sync', 18)}<span class="lbl">${running ? 'Läuft …' : 'Jetzt abrufen'}</span></button>
      <button class="btn sec" data-nav="panel">${icon('account-key-outline', 18)}Anmeldung verwalten</button></div>
      <div class="small muted" style="margin-top:8px">Version ${esc(a.version || '–')} · Karten ${FC_VERSION}</div></div>`;
  }
  _bindExtra(root) {
    const b = root.querySelector('[data-sync]');
    if (b) b.addEventListener('click', (ev) => { ev.stopPropagation(); b.classList.add('busy'); const l = b.querySelector('.lbl'); if (l) l.textContent = 'Läuft …'; this._press(E.bSync); });
  }
}

window.customCards = window.customCards || [];
[['fit-hero', FitHero, 'Fit: Heute'], ['fit-week', FitWeek, 'Fit: Woche'], ['fit-weight', FitWeight, 'Fit: Gewicht'],
  ['fit-food', FitFood, 'Fit: Essen'], ['fit-run', FitRun, 'Fit: Laufen'], ['fit-gym', FitGym, 'Fit: Gym'],
  ['fit-badges', FitBadges, 'Fit: Erfolge'], ['fit-status', FitStatus, 'Fit: Verbindung']].forEach(([tag, cls, name]) => {
  if (!customElements.get(tag)) customElements.define(tag, cls);
  if (!window.customCards.find((x) => x.type === tag)) window.customCards.push({ type: tag, name, description: 'Fit Coach' });
});
console.info(`%c FIT-CARDS %c ${FC_VERSION} `, 'background:#1baf7a;color:#fff;border-radius:3px 0 0 3px', 'background:#444;color:#fff;border-radius:0 3px 3px 0');
