/* Garmin AI Coach – Dashboard-Karten (coach-cards.js)
 * Mobile-first Karten für das Dashboard „Garmin Coach“. Keine externen Abhängigkeiten.
 * Daten: Home-Assistant-Zustände, Jinja-Makros aus custom_templates/coach_app.jinja (per render_template)
 * und Langzeitstatistik (recorder/statistics_during_period).
 * Farben: Sportarten = validierte Kategorie-Slots (blau/orange/aqua/gelb, immer mit Icon + Text),
 * Status = gut/Warnung/ernst/kritisch (immer mit Text). Hell/Dunkel getrennt gewählt.
 * HF-Zonen und Intensität teilen eine Skala: grau · blau (locker) · gelb · orange · rot.
 * 1.1.0 (16.10.2026): coach-hr und coach-lifts statt Tabellen, Schlüsselwochen in coach-phases,
 *   Tagesampel wirkt auf die Einheiten (⅓ weniger Sätze, Qualität „nicht heute“), offener Lauf wird
 *   aus der HF-Verteilung bestimmt, Vergleich Ø 7 Tage für schwankende Werte, Beschriftung neben der Kurve.
 * 1.1.1 (18.10.2026): Hinweise je Einheit kommen jetzt komplett aus coach_today() (coach_app.jinja) – die Karte
 *   rechnet nichts mehr nach. Am letzten Tag der Woche kein „nicht heute“ mehr: Was nicht mehr geht, steht unter
 *   „Fällt diese Woche aus“; Überschrift „Heute noch möglich“ statt „Diese Woche noch offen“.
 * 1.2.0 (18.10.2026): Gamification entfernt (Level/XP, Serie, Joker, Abzeichen, Meilensteine, Wochenziel).
 *   coach-week zeigt nur noch die erledigten Pflichteinheiten der Woche.
 * 1.3.0 (21.10.2026): Feedback je Einheit (x.fb aus dem Add-on, tagesform.py) direkt am erledigten Eintrag,
 *   Abschnitt „Erledigt“ (gestern + zusätzliche Einheiten von heute), „Rest der Woche“ mit allen kommenden
 *   Einheiten mit festem Tag; die Läufe ohne festen Tag stehen getrennt unter „Ohne festen Tag“.
 */
const CC_VERSION = '1.3.0';
const ICONS = {};

const E = {
  plan: 'sensor.garmin_ai_coach_garmin_plan',
  rec: 'sensor.garmin_ai_coach_garmin_tagesempfehlung',
  ready: 'sensor.garmin_ai_coach_garmin_training_readiness',
  hrv: 'sensor.garmin_ai_coach_garmin_hrv_status',
  sleep: 'sensor.garmin_ai_coach_garmin_schlafdauer',
  sleepScore: 'sensor.garmin_ai_coach_garmin_sleep_score',
  rhr: 'sensor.garmin_ai_coach_garmin_resting_hr',
  note: 'sensor.garmin_ai_coach_garmin_ai_coaching_note',
  coach: 'sensor.garmin_ai_coach_garmin_coach_status',
  sync: 'sensor.garmin_ai_coach_garmin_sync_status',
  last: 'sensor.garmin_ai_coach_garmin_last_sync',
  report: 'sensor.garmin_ai_coach_garmin_wochenreport',
  zones: 'sensor.garmin_ai_coach_garmin_herzfrequenzzonen',
  gym: 'sensor.garmin_ai_coach_garmin_gym_progression',
  strength: 'sensor.garmin_ai_coach_garmin_krafttraining_uebungen',
  kraft: 'sensor.garmin_ai_coach_garmin_kraftwerte',
};
const SPORT = {
  swim: { label: 'Schwimmen', icon: 'swim' },
  bike: { label: 'Rad', icon: 'bike' },
  run: { label: 'Laufen', icon: 'run' },
  strength: { label: 'Kraft', icon: 'weightLifter' },
  rest: { label: 'Ruhe', icon: 'sofaOutline' },
};
const SPORT_ORDER = ['swim', 'bike', 'run', 'strength'];
const PALETTE = {
  light: { swim: '#2a78d6', bike: '#eb6834', run: '#1baf7a', strength: '#eda100', good: '#0ca30c', warn: '#fab219', serious: '#ec835a', critical: '#d03b3b', goodText: '#006300', track: 'rgba(11,11,11,0.08)', grid: '#e1e0d9', band: 'rgba(12,163,12,0.10)', neutral: '#898781' },
  dark: { swim: '#3987e5', bike: '#d95926', run: '#199e70', strength: '#c98500', good: '#0ca30c', warn: '#fab219', serious: '#ec835a', critical: '#d03b3b', goodText: '#0ca30c', track: 'rgba(255,255,255,0.10)', grid: '#2c2c2a', band: 'rgba(12,163,12,0.16)', neutral: '#898781' },
};

/* ---------- Helfer ---------- */
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const kebab = (n) => n.replace(/[A-Z]/g, (m) => `-${m.toLowerCase()}`);
const icon = (name, size = 20, cls = '') => {
  const p = ICONS[name];
  if (p) return `<svg class="ic ${cls}" viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true"><path d="${p}"/></svg>`;
  return `<ha-icon class="ic ${cls}" icon="mdi:${kebab(name)}" style="--mdc-icon-size:${size}px;--icon-primary-color:currentColor;width:${size}px;height:${size}px"></ha-icon>`;
};
const num = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : null; };
const fmtNum = (v, d = 0) => (v == null ? '–' : Number(v).toLocaleString('de-DE', { minimumFractionDigits: d, maximumFractionDigits: d }));
const fmtMMSS = (s) => { if (s == null) return '–'; const t = Math.round(s); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`; };
const fmtVal = (v, fmt, d) => (fmt === 'mmss' ? fmtMMSS(v) : fmtNum(v, d ?? 0));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const ddmm = (d) => `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.`;
const mondayOf = (d) => { const x = new Date(d); x.setHours(0, 0, 0, 0); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x; };

const BASE_CSS = `
:host { display: block; }
ha-card { overflow: hidden; }
.card { padding: 16px; color: var(--primary-text-color); font-size: 14px; line-height: 1.4; }
.ic { fill: currentColor; flex: none; display: block; line-height: 0; }
.ic.inl { display: inline-block; vertical-align: -2px; width: 14px; height: 14px; }
.eyebrow { font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--secondary-text-color); }
.muted { color: var(--secondary-text-color); }
.small { font-size: 12px; }
.row { display: flex; align-items: center; gap: 10px; }
.between { justify-content: space-between; }
.chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 9px; border-radius: 999px; font-size: 12px; font-weight: 500; background: var(--cc-track); color: var(--primary-text-color); white-space: nowrap; }
.chip .ic { width: 14px; height: 14px; }
.pill { display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px 5px 8px; border-radius: 999px; font-weight: 600; font-size: 14px; }
.dot { width: 10px; height: 10px; border-radius: 50%; flex: none; }
.big { font-size: 30px; font-weight: 650; letter-spacing: -.02em; line-height: 1.05; }
.hr { height: 1px; background: var(--divider-color, var(--cc-track)); margin: 12px 0; }
button.link { all: unset; cursor: pointer; color: var(--primary-color); font-size: 13px; font-weight: 500; }
.tap { cursor: pointer; -webkit-tap-highlight-color: transparent; }
.bar { position: relative; height: 8px; border-radius: 999px; background: var(--cc-track); overflow: hidden; }
.bar > i { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 999px; }
.marker { position: absolute; top: -3px; bottom: -3px; width: 2px; background: var(--primary-text-color); opacity: .55; border-radius: 1px; }
.details { margin-top: 6px; font-size: 13px; color: var(--secondary-text-color); }
.sport-ic { width: 32px; height: 32px; border-radius: 10px; display: grid; place-items: center; flex: none; color: #fff; }
.sport-ic .ic { width: 18px; height: 18px; }
.ok { color: var(--cc-goodText); }
`;

class CoachBase extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._open = new Set();
    this._tpl = {};
    this._tplUnsub = {};
    this._sig = '';
    this._data = {};
  }
  setConfig(config) { this._config = config || {}; this._sig = ''; if (this._hass) this._schedule(); }
  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    if (first) this._subscribeTemplates();
    const sig = this._signature();
    if (sig !== this._sig) { this._sig = sig; this._onChange(); this._schedule(); }
  }
  get hass() { return this._hass; }
  connectedCallback() { if (this._hass) { this._subscribeTemplates(); this._schedule(); } }
  disconnectedCallback() { for (const k of Object.keys(this._tplUnsub)) { const u = this._tplUnsub[k]; Promise.resolve(u).then((f) => f && f()).catch(() => {}); } this._tplUnsub = {}; }
  getCardSize() { return 4; }
  getGridOptions() { return { columns: 12, min_columns: 6, rows: 'auto' }; }
  _entities() { return []; }
  _templates() { return {}; }
  _onChange() {}
  _signature() {
    const s = this._hass?.states || {};
    return this._entities().map((id) => { const o = s[id]; return o ? `${o.state}|${o.last_updated}` : '-'; }).join('#') + `#${this._hass?.themes?.darkMode ? 1 : 0}`;
  }
  _subscribeTemplates() {
    const tpls = this._templates();
    for (const [k, t] of Object.entries(tpls)) {
      if (this._tplUnsub[k] || !this._hass?.connection) continue;
      this._tplUnsub[k] = this._hass.connection.subscribeMessage((msg) => {
        if (msg && 'result' in msg) {
          let v = msg.result;
          if (typeof v === 'string') { try { v = JSON.parse(v); } catch (e) { /* Text bleibt Text */ } }
          this._tpl[k] = v; this._schedule();
        }
      }, { type: 'render_template', template: t, strict: false, report_errors: false }).catch(() => { delete this._tplUnsub[k]; });
    }
  }
  _st(id) { return this._hass?.states?.[id]; }
  _num(id) { return num(this._st(id)?.state); }
  _attr(id, a) { return this._st(id)?.attributes?.[a]; }
  _dark() { return !!this._hass?.themes?.darkMode; }
  _c() { return this._dark() ? PALETTE.dark : PALETTE.light; }
  _vars() { const c = this._c(); return `--cc-track:${c.track};--cc-goodText:${c.goodText};`; }
  _schedule() { if (this._raf) return; this._raf = requestAnimationFrame(() => { this._raf = null; this._paint(); }); }
  _paint() {
    if (!this._hass) return;
    let body = '';
    try { body = this._render(); } catch (e) { body = `<div class="card muted small">Karte konnte nicht dargestellt werden: ${esc(e.message)}</div>`; console.error('coach-cards', e); }
    this.shadowRoot.innerHTML = `<style>${BASE_CSS}${this._css ? this._css() : ''}</style><ha-card style="${this._vars()}">${body}</ha-card>`;
    this._bind();
    if (this._after) this._after();
  }
  _bind() {
    this.shadowRoot.querySelectorAll('[data-nav]').forEach((el) => el.addEventListener('click', (ev) => { ev.stopPropagation(); this._navigate(el.dataset.nav); }));
    this.shadowRoot.querySelectorAll('[data-more]').forEach((el) => el.addEventListener('click', (ev) => { ev.stopPropagation(); this._moreInfo(el.dataset.more); }));
    this.shadowRoot.querySelectorAll('[data-toggle]').forEach((el) => el.addEventListener('click', (ev) => { ev.stopPropagation(); const k = el.dataset.toggle; if (this._open.has(k)) this._open.delete(k); else this._open.add(k); this._paint(); }));
    this.shadowRoot.querySelectorAll('[data-sync]').forEach((el) => el.addEventListener('click', (ev) => { ev.stopPropagation(); this._sync(el); }));
  }
  _navigate(path) { history.pushState(null, '', path); window.dispatchEvent(new CustomEvent('location-changed', { detail: { replace: false } })); }
  _moreInfo(entityId) { this.dispatchEvent(new CustomEvent('hass-more-info', { detail: { entityId }, bubbles: true, composed: true })); }
  _sync(el) {
    const lbl = el && el.querySelector('.lbl');
    if (!this._armed) { // zweimal tippen statt Dialog: der Button umgeht die 15-min-Sperre des Add-ons
      this._armed = true; if (lbl) lbl.textContent = 'Nochmal tippen';
      clearTimeout(this._armT); this._armT = setTimeout(() => { this._armed = false; this._paint(); }, 4000); return;
    }
    this._armed = false; clearTimeout(this._armT);
    this._hass.callService('button', 'press', {}, { entity_id: 'button.garmin_ai_coach_garmin_jetzt_synchronisieren' });
    if (el) { el.classList.add('busy'); if (lbl) lbl.textContent = 'Läuft …'; }
  }
  _ring(pct, color, size = 64, stroke = 7, inner = '') {
    const r = (size - stroke) / 2; const c = 2 * Math.PI * r; const p = clamp(pct, 0, 100);
    return `<div class="ring" style="width:${size}px;height:${size}px;position:relative;flex:none">
      <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="transform:rotate(-90deg)">
        <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--cc-track)" stroke-width="${stroke}"/>
        ${p > 0 ? `<circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${color}" stroke-width="${stroke}" stroke-linecap="round" stroke-dasharray="${(c * p) / 100} ${c}"/>` : ''}
      </svg><div style="position:absolute;inset:0;display:grid;place-items:center;text-align:center">${inner}</div></div>`;
  }
  _sportIc(s, size = 32) { const c = this._c(); const k = SPORT[s] ? s : 'rest'; const bg = c[k] || c.neutral; return `<span class="sport-ic" style="background:${bg};width:${size}px;height:${size}px">${icon(SPORT[k].icon, Math.round(size * 0.56))}</span>`; }
  _statusColor(kind) { return this._c()[kind] || this._c().neutral; }
}

/* ================= Hero: Heute ================= */
class CoachHero extends CoachBase {
  _entities() { return [E.rec, E.ready, E.hrv, E.sleep, E.sleepScore, E.rhr, E.note, E.coach, E.plan, E.sync, E.last, E.report]; }
  _templates() { return { today: "{% from 'coach_app.jinja' import coach_today %}{{ coach_today() }}" }; }
  _css() {
    return `.top{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;flex-wrap:wrap}
    .vitals{display:flex;gap:14px;align-items:center;margin-top:14px}
    .vlist{flex:1;min-width:0;display:grid;gap:8px}
    .v{display:flex;align-items:center;gap:8px;min-width:0}
    .v .ic{width:18px;height:18px;color:var(--secondary-text-color)}
    .v b{font-size:15px;font-weight:600}
    .v span.s{font-size:12px;color:var(--secondary-text-color);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .item{display:flex;gap:12px;align-items:flex-start;padding:10px 0}
    .item + .item{border-top:1px solid var(--divider-color,var(--cc-track))}
    .item .t{font-weight:600;font-size:15px}
    .item .c{font-size:13px;color:var(--secondary-text-color)}
    .state{margin-left:auto;flex:none;width:22px;height:22px;border-radius:50%;border:2px solid var(--cc-track);display:grid;place-items:center}
    .state.done{background:var(--cc-goodText);border-color:var(--cc-goodText);color:#fff}
    .state.done .ic{width:14px;height:14px}
    .advice{margin-top:10px;padding:10px 12px;border-radius:12px;font-size:13px}
    .note{display:flex;gap:10px;align-items:flex-start;font-size:13px}
    .note .ic{width:18px;height:18px;color:var(--secondary-text-color);margin-top:1px}
    .warnline{margin-top:8px;font-size:12px;color:#d03b3b}
    .clamp{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
    .fb{margin-top:4px;font-size:13px;line-height:1.35;color:var(--primary-text-color);display:flex;gap:6px;align-items:flex-start}
    .fb .ic{width:14px;height:14px;margin-top:2px;color:var(--secondary-text-color)}
    .day{display:inline-block;min-width:34px;font-size:11px;font-weight:600;color:var(--secondary-text-color);text-transform:uppercase;letter-spacing:.04em}
    .item.compact{padding:7px 0}
    .item.compact .sport-ic{width:26px!important;height:26px!important;border-radius:8px}
    .item.compact .t{font-size:14px}`;
  }
  _render() {
    const t = this._tpl.today || {};
    const c = this._c();
    const lvl = t.lvl || this._attr(E.rec, 'level') || '';
    const lvlMap = { normal: ['good', 'Normal trainieren'], locker: ['warn', 'Locker / verkürzt'], pause: ['critical', 'Pause / Erholung'] };
    const [lvlKind, lvlDefault] = lvlMap[lvl] || ['neutral', 'Noch keine Tagesempfehlung'];
    const label = t.label || this._st(E.rec)?.state || lvlDefault;
    const reasons = (t.reasons || this._attr(E.rec, 'reasons') || []).join(' · ');
    const tint = lvlKind === 'neutral' ? c.track : `${c[lvlKind]}22`;

    const ready = this._num(E.ready);
    const rLevel = (this._attr(E.ready, 'level') || '').toUpperCase();
    const rMap = { PRIME: ['good', 'Top'], HIGH: ['good', 'Hoch'], MODERATE: ['warn', 'Mittel'], LOW: ['serious', 'Niedrig'], POOR: ['critical', 'Sehr niedrig'] };
    const [rKind, rLabel] = rMap[rLevel] || [ready == null ? 'neutral' : ready >= 75 ? 'good' : ready >= 50 ? 'warn' : ready >= 25 ? 'serious' : 'critical', ''];

    const hrvRaw = (this._attr(E.hrv, 'raw') || '').toUpperCase();
    const hrvAvg = this._attr(E.hrv, 'weekly_avg');
    const base = this._attr(E.hrv, 'baseline') || {};
    const hrvKind = { BALANCED: 'good', UNBALANCED: 'warn', LOW: 'serious', POOR: 'critical' }[hrvRaw] || 'neutral';
    const hrvRange = base.balancedLow && base.balancedUpper ? `Normal ${base.balancedLow}–${base.balancedUpper}` : '';
    const sleepH = this._num(E.sleep); const sleepS = this._num(E.sleepScore);
    const sleepKind = sleepS == null ? 'neutral' : sleepS >= 80 ? 'good' : sleepS >= 60 ? 'warn' : 'serious';
    const rhr = this._num(E.rhr);
    const rhrAvg = num(this._attr(E.report, 'resting_hr_avg'));
    const rhrKind = rhr == null || rhrAvg == null ? 'neutral' : rhr - rhrAvg <= 2 ? 'good' : rhr - rhrAvg <= 5 ? 'warn' : 'serious';

    this._lvl = lvl;
    const items = (t.items || []).map((x, i) => this._item(x, `i${i}`)).join('');
    const open = (t.open || []).map((x, i) => this._item(x, `o${i}`, true)).join('');
    const week = (t.week || []).map((x, i) => this._item(x, `w${i}`, true, true)).join('');
    const done = (t.done || []).map((x, i) => this._item({ ...x, ok: true, c: x.w }, `d${i}`, false, true)).join('');
    const skip = (t.skip || []).map((x, i) => this._item(x, `s${i}`, true)).join('');

    const noteSt = this._st(E.note);
    const noteLines = String(noteSt?.attributes?.full_text || '').split('\n').map((s) => s.replace(/^[-•]\s*/, '').trim()).filter(Boolean);
    const coachBad = this._st(E.coach) && !['ok', 'unknown', 'unavailable'].includes(this._st(E.coach).state);
    const syncBad = this._st(E.sync)?.state === 'error';
    const lastSync = this._st(E.last)?.state; const age = lastSync ? (Date.now() - new Date(lastSync).getTime()) / 36e5 : null;

    const nt = t.next_test; const ntDays = nt ? Math.round((new Date(nt.w) - mondayOf(new Date())) / 864e5) : null;

    return `<div class="card">
      <div class="top">
        <div>
          <div class="eyebrow">${esc(t.wd || '')} ${esc(t.date || '')}${t.ph ? ` · ${esc(t.ph)}` : ''}${t.wi ? ` · Woche ${t.wi}/${t.wn}` : ''}</div>
        </div>
        <div class="row" style="gap:6px;flex-wrap:wrap">
          ${t.dm >= 0 ? `<span class="chip tap" title="Tage bis zum Marathon" data-nav="/garmin-coach/marathon">${icon('run', 14)}${t.dm} Tage</span>` : ''}
          ${t.dr >= 0 ? `<span class="chip tap" title="Tage bis zum Ironman 70.3" data-nav="/garmin-coach/saison">${icon('flagCheckered', 14)}${t.dr} Tage</span>` : ''}
        </div>
      </div>
      <div style="margin-top:10px"><span class="pill" style="background:${tint}"><span class="dot" style="background:${lvlKind === 'neutral' ? c.neutral : c[lvlKind]}"></span>${esc(label)}</span></div>
      ${(lvl === 'locker' || lvl === 'pause') && t.advice ? `<div style="margin-top:8px;font-size:14px">${esc(t.advice)}</div>` : ''}
      ${reasons ? `<div class="small muted" style="margin-top:4px">${icon('informationOutline', 14, 'inl')} ${esc(reasons)}</div>` : ''}
      <div class="vitals tap" data-nav="/garmin-coach/home">
        ${this._ring(ready ?? 0, rKind === 'neutral' ? c.neutral : c[rKind], 88, 9, `<div><div style="font-size:24px;font-weight:650;line-height:1">${ready ?? '–'}</div><div class="small muted" style="line-height:1.2">Readiness${rLabel ? `<br>${rLabel}` : ''}</div></div>`)}
        <div class="vlist">
          <div class="v">${icon('heartFlash')}<span class="dot" style="background:${hrvKind === 'neutral' ? c.neutral : c[hrvKind]}"></span><b>${hrvAvg ?? '–'}</b><span class="small muted">ms HRV</span><span class="s">${esc(hrvRange)}</span></div>
          <div class="v">${icon('sleep')}<span class="dot" style="background:${sleepKind === 'neutral' ? c.neutral : c[sleepKind]}"></span><b>${sleepH == null ? '–' : fmtNum(sleepH, 1)}</b><span class="small muted">h Schlaf</span><span class="s">${sleepS == null ? '' : `Score ${sleepS}`}</span></div>
          <div class="v">${icon('heartPulse')}<span class="dot" style="background:${rhrKind === 'neutral' ? c.neutral : c[rhrKind]}"></span><b>${rhr == null ? '–' : fmtNum(rhr)}</b><span class="small muted">bpm Ruhepuls</span><span class="s">${rhrAvg == null ? '' : `Ø ${fmtNum(rhrAvg)}`}</span></div>
        </div>
      </div>
      <div class="hr"></div>
      <div class="eyebrow">Heute</div>
      ${items || `<div class="small muted" style="padding:8px 0">Kein fester Termin – Zeit für eine offene Einheit oder Erholung.</div>`}
      ${done ? `<div class="eyebrow" style="margin-top:10px">Erledigt</div>${done}` : ''}
      ${week ? `<div class="eyebrow" style="margin-top:10px">Rest der Woche</div>${week}` : ''}
      ${open ? `<div class="eyebrow" style="margin-top:10px">${t.dl > 0 ? 'Noch offen · ohne festen Tag' : 'Heute noch möglich'}</div>${open}` : ''}
      ${skip ? `<div class="eyebrow" style="margin-top:10px">Fällt diese Woche aus</div>${skip}` : ''}
      ${t.hint ? `<div class="small muted">${icon('informationOutline', 14, 'inl')} ${esc(t.hint)}</div>` : ''}
      ${noteLines.length ? `<div class="hr"></div><div class="note tap" data-toggle="note">${icon('robotOutline')}<div style="flex:1"><div class="${this._open.has('note') ? '' : 'clamp'}">${esc(noteLines[0])}</div>${this._open.has('note') && noteLines.length > 1 ? noteLines.slice(1).map((l) => `<div style="margin-top:6px">${esc(l)}</div>`).join('') : ''}${noteLines.length > 1 ? `<div><button class="link">${this._open.has('note') ? 'weniger' : 'mehr'}</button></div>` : ''}</div></div>` : ''}
      ${coachBad ? `<div class="warnline">KI-Coach ${esc(this._st(E.coach).state)} – Tagesnotiz kommt aus den Regeln.</div>` : ''}
      ${syncBad || (age != null && age > 14) ? `<div class="warnline">Letzter Garmin-Sync ${syncBad ? 'fehlgeschlagen' : `vor ${Math.round(age)} h`}.</div>` : ''}
      ${nt && ntDays != null && ntDays <= 21 ? `<div class="small muted" style="margin-top:10px">${icon('target', 14, 'inl')} Nächster Test: ${esc(nt.f)} (ab ${ddmm(new Date(nt.w))})</div>` : ''}
    </div>`;
  }
  _item(x, key, open = false, compact = false) {
    const isOpen = this._open.has(key);
    const has = !!x.d;
    const c = this._c();
    // Hinweis-Chip kommt fertig aus coach_today() (x.a) – Wochentag, Ampel und Art der Einheit sind dort berücksichtigt
    const adapt = x.a
      ? `<span class="chip" style="margin-left:6px;background:${this._lvl === 'pause' ? c.critical : c.warn}26;font-size:11px;padding:1px 7px">${esc(x.a)}</span>` : '';
    return `<div class="item ${has ? 'tap' : ''} ${compact ? 'compact' : ''}" ${has ? `data-toggle="${key}"` : ''}>
      ${this._sportIc(x.s, compact ? 26 : 32)}
      <div style="flex:1;min-width:0">
        <div class="t">${x.day ? `<span class="day">${esc(x.day)}</span>` : ''}${esc(x.t)}${adapt}</div>
        ${x.c ? `<div class="c">${esc(x.c)}</div>` : ''}
        ${x.fb ? `<div class="fb">${icon('commentTextOutline', 14)}<span>${esc(x.fb)}</span></div>` : ''}
        ${isOpen && has ? `<div class="details">${esc(x.d).replace(/ · /g, '<br>')}</div>` : ''}
      </div>
      ${open ? (has ? `<span class="muted" style="margin-left:auto">${icon(isOpen ? 'chevronDown' : 'chevronRight', 18)}</span>` : '') : `<span class="state ${x.ok ? 'done' : ''}">${x.ok ? icon('check', 14) : ''}</span>`}
    </div>`;
  }
}

/* ================= Woche: Ringe ================= */
class CoachWeek extends CoachBase {
  _entities() { return [E.plan]; }
  _templates() { return this._config?.mode === 'full' ? { week: "{% from 'coach_app.jinja' import coach_week %}{{ coach_week() }}" } : {}; }
  _css() {
    return `.rings{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:14px}
    .rc{display:flex;flex-direction:column;align-items:center;gap:6px;text-align:center}
    .rc .lab{font-size:12px;color:var(--secondary-text-color)}
    .rc .val{font-size:14px;font-weight:600}
    .row2{display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-top:1px solid var(--divider-color,var(--cc-track))}
    .row2 .t{font-weight:600}
    .pips{display:flex;gap:4px;margin-left:auto;flex:none;padding-top:4px}
    .pips i{width:10px;height:10px;border-radius:50%;background:var(--cc-track)}`;
  }
  _render() {
    const c = this._c();
    const tg = this._attr(E.plan, 'targets') || [];
    const pdate = this._attr(E.plan, 'date');
    const sameWeek = pdate && mondayOf(new Date(pdate)).getTime() === mondayOf(new Date()).getTime();
    const by = {}; tg.forEach((t) => { by[t.key] = t; });
    let d = 0, n = 0;
    SPORT_ORDER.forEach((k) => { const t = by[k]; if (!t) return; const mn = +t.min || 0; if (mn > 0) { d += Math.min(sameWeek ? +t.done || 0 : 0, mn); n += mn; } });
    const pct = n ? Math.round((d / n) * 100) : null;
    if (pct == null) return `<div class="card"><div class="eyebrow">Diese Woche</div><div class="small muted" style="margin-top:6px">Noch kein Wochenplan vom Add-on – erscheint nach dem nächsten Sync.</div></div>`;
    const left = 6 - ((new Date().getDay() + 6) % 7);
    const kind = pct >= 100 ? 'good' : 'neutral';
    const full = this._config?.mode === 'full';
    const w = this._tpl.week || {};

    const rings = SPORT_ORDER.filter((k) => by[k] && (+by[k].min || +by[k].max)).map((k) => {
      const t = by[k]; const done = sameWeek ? +t.done || 0 : 0; const mn = +t.min || 0; const mx = +t.max || mn;
      const p = mn ? (Math.min(done, mn) / mn) * 100 : (done ? 100 : 0);
      const complete = mn && done >= mn;
      return `<div class="rc">${this._ring(p, c[k], 62, 7, `<span style="color:${complete ? c.goodText : 'var(--primary-text-color)'}">${complete ? icon('check', 22) : icon(SPORT[k].icon, 22)}</span>`)}
        <div class="val">${done}/${mn}</div><div class="lab">${SPORT[k].label}</div></div>`;
    }).join('');

    const header = `<div class="row between">
        <div><div class="eyebrow">Diese Woche${w.range ? ` · ${esc(w.range)}` : ''}</div>
          <div class="row" style="gap:8px;margin-top:4px"><span class="big" style="color:${kind === 'good' ? c.goodText : 'inherit'}">${pct} %</span>
          <span class="small muted">${pct >= 100 ? 'Woche komplett' : `${d} von ${n} Einheiten`}</span></div></div>
        <div class="small muted" style="text-align:right">${left > 0 ? `noch ${left} ${left === 1 ? 'Tag' : 'Tage'}` : 'letzter Tag'}</div>
      </div>
      <div class="bar" style="margin-top:10px"><i style="width:${clamp(pct, 0, 100)}%;background:${pct >= 100 ? c.good : c.swim}"></i></div>`;

    let body = `<div class="rings">${rings}</div>`;
    if (full && w.ok) {
      body += `<div style="margin-top:12px">${SPORT_ORDER.filter((k) => by[k]).map((k) => {
        const r = (w.rows || {})[k] || {}; const t = by[k]; const done = sameWeek ? +t.done || 0 : 0; const mn = +t.min || 0; const mx = Math.max(+t.max || 0, mn);
        const key = `w_${k}`; const isOpen = this._open.has(key);
        const pips = Array.from({ length: mx }, (_, i) => `<i style="${i < done ? `background:${c[k]}` : ''}${i >= mn ? ';opacity:.5' : ''}"></i>`).join('');
        return `<div class="row2 tap" data-toggle="${key}">${this._sportIc(k, 30)}<div style="flex:1;min-width:0"><div class="t">${SPORT[k].label}</div><div class="small muted">${esc(r.c || '')}</div>${isOpen && r.d ? `<div class="details">${esc(r.d).replace(/ · /g, '<br>')}</div>` : ''}</div><div class="pips">${pips}</div></div>`;
      }).join('')}</div>`;
      if (w.prio) body += `<div class="small muted" style="margin-top:8px"><b>Wenn die Woche eng wird:</b> ${esc(w.prio)}</div>`;
      if (w.next) {
        const nx = w.next;
        body += `<div class="hr"></div><div class="eyebrow">Nächste Woche ab ${esc(nx.w)}${nx.new_phase ? ` · neue Phase: ${esc(nx.ph)}` : ''}</div>
          ${nx.f ? `<div style="margin-top:4px;font-weight:600">${esc(nx.f)}</div>` : ''}
          <div class="small muted" style="margin-top:4px">${[['swim', nx.swim], ['bike', nx.bike], ['run', nx.run]].filter((x) => x[1]).map(([k, v]) => `${SPORT[k].label}: ${esc(v)}`).join(' · ')}</div>`;
      }
    } else if (!full) {
      body += `<div class="small muted" style="margin-top:10px;text-align:center">Details und Plan im Reiter „Woche“</div>`;
    }
    return `<div class="card ${full ? '' : 'tap'}" ${full ? '' : 'data-nav="/garmin-coach/woche"'}>${header}${body}</div>`;
  }
}

/* ================= Trend (Statistik-Sparkline / Wochenbalken) ================= */
class CoachTrend extends CoachBase {
  _entities() { const cfg = this._config || {}; return [cfg.entity, ...(cfg.band?.entity ? [cfg.band.entity] : [])].filter(Boolean); }
  _templates() { return this._config?.subtitle_template ? { sub: this._config.subtitle_template } : {}; }
  _onChange() { this._load(); }
  getCardSize() { return 3; }
  _css() { return `.chart{position:relative;margin-top:10px;touch-action:pan-y}
    .chart svg{display:block;width:100%;overflow:visible}
    .ylab{position:absolute;left:0;width:34px;text-align:right;font-size:11px;line-height:1;color:var(--secondary-text-color);transform:translateY(-50%)}
    .plot{position:absolute;left:40px;right:4px;top:0;bottom:0}
    .xlab{display:flex;justify-content:space-between;font-size:11px;color:var(--secondary-text-color);margin-top:4px}
    .tip{position:absolute;top:-6px;transform:translate(-50%,-100%);background:var(--primary-text-color);color:var(--ha-card-background,var(--card-background-color,#fff));font-size:12px;padding:3px 8px;border-radius:6px;white-space:nowrap;pointer-events:none}
    .cross{position:absolute;top:0;bottom:0;width:1px;background:var(--secondary-text-color);opacity:.5;pointer-events:none}
    .bars{display:flex;align-items:flex-end;justify-content:space-between;gap:2px;position:relative}
    .bars .b{flex:1;max-width:22px;border-radius:4px 4px 1px 1px;min-height:2px}
    .delta{font-size:12px;font-weight:600;padding:2px 8px;border-radius:999px}
    .compact .big{font-size:22px}.compact{padding:12px}`; }
  async _load() {
    const cfg = this._config || {}; if (!cfg.entity || !this._hass) return;
    const now = Date.now(); if (this._loading || (this._loadedAt && now - this._loadedAt < 120000 && this._pts)) return;
    this._loading = true;
    try {
      const days = cfg.days || 56;
      const start = new Date(now - days * 864e5).toISOString(); const end = new Date(now).toISOString();
      let pts = [];
      if (cfg.aggregate === 'week') {
        const r = await this._hass.callWS({ type: 'recorder/statistics_during_period', start_time: start, end_time: end, statistic_ids: [cfg.entity], period: 'hour', types: ['max'] });
        const rows = r[cfg.entity] || []; const map = new Map();
        for (const x of rows) {
          const t = new Date(typeof x.start === 'number' ? x.start : Date.parse(x.start));
          const k = mondayOf(new Date(t.getTime() - 7 * 36e5)).getTime(); // Mo 00–07 Uhr gehört noch zur Vorwoche (Sync um 6 Uhr setzt zurück)
          if (x.max != null) map.set(k, Math.max(map.get(k) ?? -Infinity, x.max));
        }
        const first = map.size ? Math.min(...map.keys()) : mondayOf(new Date(now)).getTime(); const lastW = mondayOf(new Date(now)).getTime();
        for (let w = first; w <= lastW; w += 7 * 864e5) { const k = mondayOf(new Date(w + 12 * 36e5)).getTime(); if (!map.has(k)) map.set(k, 0); }
        pts = [...map.entries()].sort((a, b) => a[0] - b[0]).filter(([t]) => t >= first).map(([t, v]) => ({ t, v }));
      } else {
        const stat = cfg.stat || 'mean';
        try {
          const r = await this._hass.callWS({ type: 'recorder/statistics_during_period', start_time: start, end_time: end, statistic_ids: [cfg.entity], period: cfg.period || 'day', types: [stat] });
          pts = (r[cfg.entity] || []).filter((x) => x[stat] != null).map((x) => ({ t: typeof x.start === 'number' ? x.start : Date.parse(x.start), v: x[stat] }));
        } catch (e) { pts = []; }
        if (!pts.length) {
          const h = await this._hass.callWS({ type: 'history/history_during_period', start_time: start, end_time: end, entity_ids: [cfg.entity], minimal_response: true, no_attributes: true, significant_changes_only: false });
          const rows = h[cfg.entity] || []; const byDay = new Map();
          for (const x of rows) { const v = num(x.s); const ts = (x.lu ?? x.lc) * 1000; if (v == null || !ts) continue; const d = new Date(ts); d.setHours(0, 0, 0, 0); byDay.set(d.getTime(), v); }
          pts = [...byDay.entries()].sort((a, b) => a[0] - b[0]).map(([t, v]) => ({ t, v }));
        }
      }
      this._pts = pts; this._loadedAt = Date.now();
    } catch (e) { this._err = e.message || String(e); }
    this._loading = false; this._paint();
  }
  _render() {
    const cfg = this._config || {}; const c = this._c();
    const st = this._st(cfg.entity);
    const unit = cfg.unit ?? st?.attributes?.unit_of_measurement ?? '';
    const d = cfg.decimals ?? 0; const fmt = cfg.format;
    const cur = cfg.aggregate === 'week' ? (this._pts?.length ? this._pts[this._pts.length - 1].v : num(st?.state)) : num(st?.state);
    const color = c[cfg.color] || cfg.color || c.swim;
    const pts = this._pts || [];
    let delta = '';
    if (cfg.compare !== false && pts.length > 2 && cfg.aggregate !== 'week') {
      // 'avg': Ø der letzten 7 Tage gegen Ø davor – für Werte, die täglich schwanken (Readiness, Schlaf,
      // Ruhepuls). Ein Vergleich erster gegen letzter Tag wäre dort reiner Zufall.
      let diff = null; let label = '';
      if (cfg.compare === 'avg') {
        const cut = Date.now() - 7 * 864e5; const mean = (a) => a.reduce((s2, p) => s2 + p.v, 0) / a.length;
        const recent = pts.filter((p) => p.t >= cut); const before = pts.filter((p) => p.t < cut);
        if (recent.length >= 3 && before.length >= 5) { diff = mean(recent) - mean(before); label = `Ø 7 Tage ${fmtVal(mean(recent), fmt, d)} ggü. davor`; }
      } else {
        diff = (cur ?? pts[pts.length - 1].v) - pts[0].v; label = `seit ${ddmm(new Date(pts[0].t))}`;
      }
      const shown = diff == null ? 0 : (fmt === 'mmss' ? Math.round(diff) : Number(diff.toFixed(d)));
      if (diff != null && Math.abs(shown) > 1e-9) {
        const better = cfg.invert ? diff < 0 : diff > 0; const neutral = cfg.neutral_delta;
        const col = neutral ? 'var(--secondary-text-color)' : better ? c.goodText : c.serious;
        const txt = fmt === 'mmss' ? `${diff > 0 ? '+' : '−'}${Math.abs(shown)} s` : `${diff > 0 ? '+' : '−'}${fmtNum(Math.abs(diff), d)}`;
        delta = `<span class="delta" style="color:${col};background:var(--cc-track)">${icon(diff > 0 ? 'trendingUp' : 'trendingDown', 14, 'inl')} ${txt} <span class="muted" style="font-weight:400">${label}</span></span>`;
      }
    }
    const sub = this._tpl.sub;
    const flat = pts.length >= 2 && cfg.chart !== 'bar' && Math.max(...pts.map((p) => p.v)) - Math.min(...pts.map((p) => p.v)) < 1e-9;
    const chart = flat ? `<div class="small muted" style="margin-top:8px">Unverändert seit ${ddmm(new Date(pts[0].t))}${cfg.flat_hint ? ` – ${esc(cfg.flat_hint)}.` : ''}</div>` : pts.length >= 2 ? (cfg.chart === 'bar' ? this._bars(pts, color, cfg) : this._line(pts, color, cfg)) : `<div class="small muted" style="margin-top:10px">${this._err ? `Verlauf nicht ladbar (${esc(this._err)}).` : this._loadedAt ? 'Noch zu wenig Verlauf – die Kurve füllt sich mit jedem Sync.' : 'Lade Verlauf …'}</div>`;
    return `<div class="card ${cfg.nav ? 'tap' : ''} ${cfg.compact ? 'compact' : ''}" ${cfg.nav ? `data-nav="${esc(cfg.nav)}"` : ''}>
      <div class="row between" style="align-items:flex-start"><div class="eyebrow">${esc(cfg.title || st?.attributes?.friendly_name || '')}</div>${cfg.info ? `<span class="small muted">${esc(cfg.info)}</span>` : ''}</div>
      <div class="row" style="gap:10px;margin-top:4px;flex-wrap:wrap;align-items:baseline">
        <span class="big">${fmtVal(cur, fmt, d)}</span><span class="muted">${esc(unit)}</span>${delta}
      </div>
      ${typeof sub === 'string' && sub.trim() ? `<div class="small muted" style="margin-top:4px">${esc(sub.trim())}</div>` : ''}
      ${chart}
    </div>`;
  }
  _range(pts, cfg) {
    let lo = Math.min(...pts.map((p) => p.v)); let hi = Math.max(...pts.map((p) => p.v));
    const band = this._band(cfg);
    if (band) { lo = Math.min(lo, band[0]); hi = Math.max(hi, band[1]); }
    if (cfg.min != null) lo = Math.min(lo, cfg.min); if (cfg.max != null) hi = Math.max(hi, cfg.max);
    if (hi - lo < 1e-9) { hi += 1; lo -= 1; }
    const pad = (hi - lo) * 0.12; return [lo - pad, hi + pad];
  }
  _band(cfg) {
    const b = cfg.band; if (!b) return null;
    if (b.entity) { const st = this._st(b.entity); const src = b.path ? b.path.reduce((o, k) => (o ? o[k] : undefined), st?.attributes) : st?.attributes; const lo = num(src?.[b.low]); const hi = num(src?.[b.high]); return lo != null && hi != null ? [lo, hi] : null; }
    return b.low != null && b.high != null ? [b.low, b.high] : null;
  }
  _line(pts, color, cfg) {
    const W = 320, H = cfg.height || (cfg.compact ? 54 : 90); const [lo, hi] = this._range(pts, cfg);
    const t0 = pts[0].t, t1 = pts[pts.length - 1].t || t0 + 1;
    const X = (t) => ((t - t0) / Math.max(t1 - t0, 1)) * W; const Y = (v) => H - ((v - lo) / (hi - lo)) * H;
    const path = pts.map((p, i) => `${i ? 'L' : 'M'}${X(p.t).toFixed(1)},${Y(p.v).toFixed(1)}`).join('');
    const area = `${path}L${W},${H}L0,${H}Z`;
    const band = this._band(cfg);
    const bandRect = band ? `<rect x="0" y="${Y(band[1])}" width="${W}" height="${Math.max(Y(band[0]) - Y(band[1]), 1)}" fill="${this._c().band}"/>` : '';
    const minV = Math.min(...pts.map((p) => p.v)); const maxV = Math.max(...pts.map((p) => p.v));
    const d = cfg.decimals ?? 0; const fmt = cfg.format;
    const last = pts[pts.length - 1];
    this._chartState = { pts, X, Y, W, H, fmt, d, unit: cfg.unit ?? '' };
    return `<div class="chart" style="height:${H}px"><div class="plot">
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="height:${H}px">
        ${bandRect}
        <line x1="0" x2="${W}" y1="${Y(maxV)}" y2="${Y(maxV)}" stroke="var(--divider-color,#8884)" stroke-width="1" vector-effect="non-scaling-stroke"/>
        <line x1="0" x2="${W}" y1="${Y(minV)}" y2="${Y(minV)}" stroke="var(--divider-color,#8884)" stroke-width="1" vector-effect="non-scaling-stroke"/>
        <path d="${area}" fill="${color}" opacity=".10"/>
        <path d="${path}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>
      </svg>
      <span style="position:absolute;left:calc(${(X(last.t) / W) * 100}% - 4px);top:${Y(last.v) - 4}px;width:8px;height:8px;border-radius:50%;background:${color};box-shadow:0 0 0 2px var(--ha-card-background,var(--card-background-color,#fff))"></span></div>
      <span class="ylab" style="top:${(Y(maxV) / H) * 100}%">${fmtVal(maxV, fmt, d)}</span>
      ${Math.abs(maxV - minV) > 1e-9 ? `<span class="ylab" style="top:${(Y(minV) / H) * 100}%">${fmtVal(minV, fmt, d)}</span>` : ''}
    </div>
    <div class="xlab" style="margin-left:40px"><span>${ddmm(new Date(t0))}</span>${band && !cfg.compact ? `<span>Normalbereich ${fmtVal(band[0], fmt, d)}–${fmtVal(band[1], fmt, d)}</span>` : ''}<span>heute</span></div>`;
  }
  _bars(pts, color, cfg) {
    const H = cfg.height || 80; const max = Math.max(...pts.map((p) => p.v), cfg.max ?? 0) || 1; const d = cfg.decimals ?? 0;
    const lastIdx = pts.length - 1;
    this._chartState = { bars: true, pts, d, unit: cfg.unit ?? '' };
    return `<div class="chart"><div class="bars" style="height:${H}px">${pts.map((p, i) => `<div class="b" data-i="${i}" style="height:${Math.max((p.v / max) * 100, 2)}%;background:${color};${i === lastIdx ? 'opacity:.55' : ''}"></div>`).join('')}</div></div>
      <div class="xlab"><span>KW ab ${ddmm(new Date(pts[0].t))}</span><span>Ø ${fmtNum(pts.slice(0, -1).reduce((s, p) => s + p.v, 0) / Math.max(pts.length - 1, 1), d)} · max ${fmtNum(max, d)}</span><span>diese Woche</span></div>`;
  }
  _after() {
    const ch = this.shadowRoot.querySelector('.chart'); const s = this._chartState; if (!ch || !s) return;
    const host = ch.querySelector('.plot') || ch;
    const show = (clientX) => {
      const r = host.getBoundingClientRect(); const fx = clamp((clientX - r.left) / r.width, 0, 1);
      let i = Math.round(fx * (s.pts.length - 1));
      if (!s.bars) { const tt = s.pts[0].t + fx * (s.pts[s.pts.length - 1].t - s.pts[0].t); let best = 0; s.pts.forEach((p, k) => { if (Math.abs(p.t - tt) < Math.abs(s.pts[best].t - tt)) best = k; }); i = best; }
      const p = s.pts[i]; const xPct = s.bars ? ((i + 0.5) / s.pts.length) * 100 : (s.X(p.t) / s.W) * 100;
      let tip = ch.querySelector('.tip'); let cr = ch.querySelector('.cross');
      if (!tip) { tip = document.createElement('div'); tip.className = 'tip'; host.appendChild(tip); cr = document.createElement('div'); cr.className = 'cross'; host.appendChild(cr); }
      tip.style.left = `${clamp(xPct, 12, 88)}%`; cr.style.left = `${xPct}%`;
      const label = s.bars ? `KW ab ${ddmm(new Date(p.t))}` : ddmm(new Date(p.t));
      tip.textContent = `${label}: ${fmtVal(p.v, s.fmt, s.d)} ${s.unit}`.trim();
    };
    const hide = () => { ch.querySelectorAll('.tip,.cross').forEach((e) => e.remove()); };
    ch.addEventListener('pointermove', (e) => show(e.clientX));
    ch.addEventListener('pointerdown', (e) => show(e.clientX));
    ch.addEventListener('pointerleave', hide);
  }
}

/* ================= Intensitätsverteilung ================= */
class CoachZones extends CoachBase {
  _entities() { return [E.report, E.zones]; }
  _css() { return `.stack{display:flex;height:14px;border-radius:999px;overflow:hidden;gap:2px;position:relative}
    .stack i{display:block;height:100%}
    .lg{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--secondary-text-color);margin-top:6px}
    .lg span{display:inline-flex;align-items:center;gap:5px}
    .lg i{width:10px;height:10px;border-radius:3px;display:inline-block}`; }
  _render() {
    const c = this._c(); const cols = [HR_COLORS[1], HR_COLORS[2], HR_COLORS[4]]; // locker = blau wie Z2, mittel = gelb wie Z3, hart = rot
    const rep = this._st(E.report)?.attributes || {};
    const avg = this._attr(E.zones, 'distribution_avg') || {};
    const rows = [];
    if (rep.zone_total_min) rows.push({ t: `Diese Woche · ${rep.zone_total_min} min`, v: [rep.zone_low_pct, rep.zone_mid_pct, rep.zone_high_pct], note: 'Zeit in den Zonen der Uhr' });
    for (const [k, lab] of [['run', 'Laufen'], ['bike', 'Rad']]) { const r = avg[k]; if (r && r.minutes) rows.push({ t: `${lab}, 4 Wochen · ${r.minutes} min`, v: [r.easy_pct, r.mid_pct, r.hard_pct], note: 'nach Coach-Zonen' }); }
    if (!rows.length) return `<div class="card"><div class="eyebrow">Intensität</div><div class="small muted" style="margin-top:6px">Noch keine Ausdauereinheit mit Herzfrequenz-Zonen.</div></div>`;
    const weeks = this._config?.weeks ? ((this._attr(E.zones, 'distribution') || {}).per_week || []) : [];
    return `<div class="card"><div class="row between"><div class="eyebrow">Intensität</div><span class="small muted">Ziel ≈ 80 % locker</span></div>
      ${rows.map((r) => { const v = r.v.map((x) => +x || 0); const easy = v[0]; return `<div style="margin-top:12px"><div class="row between small"><span>${esc(r.t)}</span><b style="color:${easy >= 75 ? c.goodText : 'inherit'}">${easy} % locker</b></div>
        <div style="position:relative;margin-top:6px"><div class="stack">${v.map((x, i) => (x > 0 ? `<i style="width:${x}%;background:${cols[i]}"></i>` : '')).join('')}</div><span class="marker" style="left:80%;top:-4px;bottom:-4px"></span></div></div>`; }).join('')}
      <div class="lg"><span><i style="background:${cols[0]}"></i>locker Z1–2</span><span><i style="background:${cols[1]}"></i>mittel Z3</span><span><i style="background:${cols[2]}"></i>hart Z4–5</span><span>│ = 80 %</span></div>
      ${weeks.length ? `<div class="eyebrow" style="margin-top:14px">Wochen im Vergleich · Uhr-Zonen</div>${weeks.slice(0, 6).map((w) => { const parts = [['run', 'Lauf'], ['bike', 'Rad']].filter(([k]) => w[k]); return `<div style="margin-top:8px"><div class="small muted">ab ${ddmm(new Date(w.week_start))}</div>${parts.map(([k, lab]) => { const r = w[k]; const v = [r.easy_pct, r.mid_pct, r.hard_pct].map((x) => +x || 0); return `<div class="row" style="gap:8px;margin-top:3px"><span class="small" style="width:30px">${lab}</span><div class="stack" style="flex:1;height:10px">${v.map((x, i) => (x > 0 ? `<i style="width:${x}%;background:${cols[i]}"></i>` : '')).join('')}</div><span class="small muted" style="width:62px;text-align:right">${r.minutes} min</span></div>`; }).join('')}</div>`; }).join('')}` : ''}
      <div class="small muted" style="margin-top:6px">Richtwert (Seiler; Muñoz 2014): rund 80 % der Ausdauerzeit locker. Zu viel Mittelbereich kostet Erholung, ohne mehr zu bringen. Die Uhr misst in % der HFmax und rechnet lockere Läufe oft schon als Z3.</div></div>`;
  }
}

/* ================= Gym ================= */
class CoachGym extends CoachBase {
  _entities() { return [E.gym, E.strength, E.plan, E.rec, E.kraft]; }
  _css() { return `.ex{display:flex;gap:10px;align-items:flex-start;padding:10px 0;border-top:1px solid var(--divider-color,var(--cc-track))}
    .ex:first-of-type{border-top:0}
    .ex .n{font-weight:600}
    .tag{font-size:12px;font-weight:600;padding:3px 9px;border-radius:999px;white-space:nowrap;flex:none}
    .mg{display:grid;grid-template-columns:76px 1fr 28px;gap:8px;align-items:center;margin-top:8px;font-size:13px}
    .mg .bar{height:10px}
    .band{position:absolute;top:0;bottom:0;background:${'rgba(12,163,12,.18)'}}`; }
  _render() { return this._config?.mode === 'volume' ? this._volume() : this._progression(); }
  _progression() {
    const c = this._c();
    const ex = this._attr(E.gym, 'exercises') || [];
    if (!ex.length) return `<div class="card"><div class="eyebrow">Gewichts-Progression</div><div class="small muted" style="margin-top:6px">Noch keine Einheiten mit Gewicht im Verlauf.</div></div>`;
    const order = { 'erhöhen': 0, 'prüfen': 1, 'wiedereinstieg': 2, 'aufbauen': 3, basis: 4, ohne_gewicht: 5 };
    const st = { 'erhöhen': [c.good, '#fff'], 'prüfen': [c.serious, '#fff'], wiedereinstieg: [c.warn, '#1a1a19'], aufbauen: ['var(--cc-track)', 'var(--primary-text-color)'], basis: ['var(--cc-track)', 'var(--secondary-text-color)'], ohne_gewicht: ['var(--cc-track)', 'var(--secondary-text-color)'] };
    const kg = (x) => `${String(Math.round(x * 100) / 100).replace('.', ',')} kg`;
    const sorted = [...ex].sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9));
    const up = sorted.filter((e) => e.status === 'erhöhen');
    const rec = this._attr(E.rec, 'level');
    return `<div class="card">
      <div class="row between"><div class="eyebrow">Gewichts-Progression</div><span class="small muted">Doppelprogression</span></div>
      ${up.length ? (rec && rec !== 'normal' ? `<div class="small muted" style="margin-top:6px">${icon('informationOutline', 14, 'inl')} Erholung heute eingeschränkt – Steigerung erst bei guter Tagesform.</div>` : '') : `<div class="small muted" style="margin-top:6px">Gerade keine Übung an der Obergrenze – Gewichte halten, Wiederholungen steigern.</div>`}
      <div style="margin-top:6px">${(() => {
        const act = sorted.filter((e) => ['erhöhen', 'prüfen', 'wiedereinstieg'].includes(e.status));
        const rest = sorted.filter((e) => !act.includes(e));
        const restOpen = this._open.has('rest');
        const row = (e, i) => {
        const [bg, fg] = st[e.status] || st.basis; const key = `g${e.id || i}`; const isOpen = this._open.has(key);
        const tagTxt = e.status === 'erhöhen' ? `↑ ${kg(e.next_weight)}` : e.status === 'prüfen' ? 'prüfen' : e.status === 'wiedereinstieg' ? 'Wiedereinstieg' : '';
        const m = /noch (\d+) Wdh/.exec(e.detail || ''); const quiet = e.status === 'aufbauen' ? (m ? `noch ${m[1]} Wdh.` : 'Wdh. steigern') : (tagTxt ? '' : 'zu wenig Daten');
        return `<div class="ex tap" data-toggle="${key}"><div style="flex:1;min-width:0"><div class="n">${esc(e.name)}${e.assumed ? ' <span class="small muted">(angenommen)</span>' : ''}</div>
          <div class="small muted">${e.weight ? kg(e.weight) : 'Körpergewicht'} × ${(e.reps || []).join('/')} · Ziel ${esc(e.target)} · ${e.last_date ? ddmm(new Date(e.last_date)) : ''}</div>
          ${isOpen ? `<div class="details">${esc(e.detail || e.headline || '')}</div>` : ''}</div>
          ${tagTxt ? `<span class="tag" style="background:${bg};color:${fg}">${tagTxt}</span>` : `<span class="small muted" style="flex:none;padding-top:2px">${quiet}</span>`}</div>`;
        };
        return act.map(row).join('') + (rest.length ? `<div class="ex tap" data-toggle="rest"><div style="flex:1"><div class="n">${rest.length} weitere ${rest.length === 1 ? 'Übung' : 'Übungen'}</div><div class="small muted">Gewicht halten, Wiederholungen bis zur Obergrenze steigern</div></div><span class="muted">${icon(restOpen ? 'chevronDown' : 'chevronRight', 18)}</span></div>${restOpen ? rest.map(row).join('') : ''}` : '');
      })()}</div>
      <div class="small muted" style="margin-top:8px">Regel: alle Arbeitssätze an der Obergrenze → +2,5–5 % und wieder unten im Bereich anfangen (ACSM 2009). Antippen für Details.</div>
    </div>`;
  }
  _volume() {
    const c = this._c();
    const since = new Date(); since.setDate(since.getDate() - 6); const sinceIso = since.toISOString().slice(0, 10);
    const sessions = (this._attr(E.strength, 'sessions') || []).filter((s) => s.date >= sinceIso);
    const groups = ['Brust', 'Rücken', 'Schultern', 'Bizeps', 'Trizeps', 'Beine', 'Rumpf']; const cnt = Object.fromEntries(groups.map((g) => [g, 0])); let unk = 0;
    for (const s of sessions) for (const ex of s.exercises || []) { const sets = ex.sets || []; const n = ex.id === 'plank' ? sets.length : sets.filter((x) => x.reps).length; if (!n || ex.id === 'unbekannt' || ex.exercise === 'Unknown') { unk += sets.length; continue; } if (ex.group in cnt) cnt[ex.group] += n; }
    const tg = (this._attr(E.plan, 'targets') || []).find((t) => t.key === 'strength') || {};
    const prog = this._attr(E.gym, 'exercises') || [];
    const legRx = /bein|wade|knie|squat|ausfall|kreuzheb|hip thrust|glute/i;
    const legs = [...prog.filter((e) => e.group === 'Beine').map((e) => e.last_date), ...(this._attr(E.kraft, 'exercises') || []).filter((e) => legRx.test(e.exercise || '')).map((e) => e.last_date)].filter(Boolean).sort();
    const legAge = legs.length ? Math.round((Date.now() - new Date(legs[legs.length - 1])) / 864e5) : null;
    const max = 14;
    return `<div class="card"><div class="row between"><div class="eyebrow">Sätze je Muskel · 7 Tage</div><span class="small muted" style="white-space:nowrap">${tg.done ?? 0}/${tg.min ?? 4} diese Woche</span></div>
      ${legAge == null || legAge > 10 ? `<div style="margin-top:8px;padding:8px 10px;border-radius:10px;background:${c.warn}26;font-size:13px">${icon('alertCircleOutline', 14, 'inl')} <b>Beine ${legAge == null ? 'bisher nicht erfasst' : `zuletzt vor ${legAge} Tagen`}.</b> Für Lauf- und Radökonomie zählt Beintraining am meisten – Di oder Do einplanen.</div>` : ''}
      ${groups.map((g) => { const n = cnt[g]; const col = n === 0 ? c.serious : n >= 5 ? c.good : c.warn; return `<div class="mg"><span>${g}</span><div class="bar" style="position:relative"><span class="band" style="left:${(5 / max) * 100}%;width:${(4 / max) * 100}%"></span><i style="width:${clamp((n / max) * 100, n ? 4 : 0, 100)}%;background:${col}"></i></div><b style="text-align:right">${n}</b></div>`; }).join('')}
      <div class="small muted" style="margin-top:8px">Grün = 5–9 Sätze pro Woche: solider Kraftaufbau neben dem Ausdauertraining. Mehr Sätze bringen mehr, aber mit abnehmendem Ertrag – bei der Kraft flacht es früh ab (Schoenfeld 2017, Pelland 2025).${unk ? ` ${unk} ${unk === 1 ? 'Satz' : 'Sätze'} ohne Übungszuordnung.` : ''}</div></div>`;
  }
}

/* ================= Saison-Zeitstrahl ================= */
class CoachPhases extends CoachBase {
  _entities() { return [E.plan]; }
  _templates() { return { keys: "{# key_weeks #}{% from 'coach_plan.jinja' import coach_plan %}{% set p = coach_plan() | from_json %}{% set mon = (now().date() - timedelta(days=now().weekday())).isoformat() %}{% set ns = namespace(l=[]) %}{% for x in p.weeks if x.w >= mon and x.f %}{% set ns.l = ns.l + [{'w': x.w, 'f': x.f}] %}{% endfor %}{{ ns.l | to_json }}" }; }
  _css() { return `.tl{display:flex;height:12px;border-radius:999px;overflow:hidden;gap:2px;margin-top:12px;position:relative}
    .tl i{display:block;height:100%}
    .now{position:absolute;top:-5px;bottom:-5px;width:3px;border-radius:2px;background:var(--primary-text-color)}
    .ph{display:grid;grid-template-columns:12px 1fr auto;gap:8px;align-items:center;font-size:13px;padding:6px 0;border-top:1px solid var(--divider-color,var(--cc-track))}
    .ph i{width:10px;height:10px;border-radius:3px}`; }
  _render() {
    const c = this._c(); const ph = this._attr(E.plan, 'phases') || [];
    if (!ph.length) return `<div class="card muted">Keine Phasen verfügbar.</div>`;
    const cols = { Grundlage: this._dark() ? '#9ec5f4' : '#5598e7', 'Marathon-Aufbau': c.run, 'Marathon-Taper': c.run, Regeneration: c.neutral, '70.3-Aufbau': c.bike, '70.3-Peak': c.bike, '70.3-Taper': c.bike };
    const t0 = new Date(ph[0].start).getTime(); const t1 = new Date(ph[ph.length - 1].end).getTime() + 864e5; const span = t1 - t0;
    const nowPct = clamp(((Date.now() - t0) / span) * 100, 0, 100);
    const cur = ph.find((p) => p.current) || ph[0];
    const weeksLeft = Math.max(0, Math.ceil((new Date(cur.end).getTime() + 864e5 - Date.now()) / (7 * 864e5)));
    const m = this._attr(E.plan, 'days_to_marathon'); const r = this._attr(E.plan, 'days_to_race');
    return `<div class="card">
      <div class="eyebrow">Saison 2026/27</div>
      <div class="row" style="gap:16px;margin-top:6px;flex-wrap:wrap">
        <div><div class="big">${m ?? '–'}</div><div class="small muted">Tage bis Marathon 02.05.</div></div>
        <div><div class="big">${r ?? '–'}</div><div class="small muted">Tage bis 70.3 am 29.08.</div></div>
      </div>
      <div class="tl">${ph.map((p) => { const w = ((new Date(p.end).getTime() + 864e5 - new Date(p.start).getTime()) / span) * 100; return `<i title="${esc(p.name)}" style="width:${w}%;background:${cols[p.name] || c.neutral};${p.current ? '' : 'opacity:.45'}"></i>`; }).join('')}<span class="now" style="left:calc(${nowPct}% - 1px)"></span></div>
      <div style="margin-top:12px;font-weight:600">${esc(cur.name)} · noch ${weeksLeft} ${weeksLeft === 1 ? 'Woche' : 'Wochen'}</div>
      <div class="small muted">${esc(cur.focus || '')}</div>
      ${(() => { const kw = Array.isArray(this._tpl.keys) ? this._tpl.keys : []; if (!kw.length) return ''; const all = this._open.has('keys'); const list = all ? kw : kw.slice(0, 5);
        return `<div class="hr"></div><div class="eyebrow">Schlüsselwochen</div>${list.map((x) => `<div class="ph" style="grid-template-columns:52px 1fr"><span class="muted">${mondayOf(new Date(x.w)).getTime() === mondayOf(new Date()).getTime() ? 'jetzt' : ddmm(new Date(x.w))}</span><span>${/test/i.test(x.f) ? `${icon('target', 14, 'inl')} ` : ''}${esc(x.f)}</span></div>`).join('')}${kw.length > 5 ? `<button class="link" data-toggle="keys" style="margin-top:6px">${all ? 'weniger' : `alle ${kw.length} anzeigen`}</button>` : ''}`; })()}
      <div class="row between tap" data-toggle="phases" style="margin-top:10px"><span class="small muted">Alle ${ph.length} Phasen</span><span class="muted">${icon(this._open.has('phases') ? 'chevronDown' : 'chevronRight', 18)}</span></div>
      ${this._open.has('phases') ? `<div style="margin-top:6px">${ph.map((p) => `<div class="ph" style="${p.current ? 'font-weight:600' : ''}"><i style="background:${cols[p.name] || c.neutral}"></i><span>${esc(p.name)}</span><span class="muted">${ddmm(new Date(p.start))}–${ddmm(new Date(p.end))}</span></div>`).join('')}</div>` : ''}
    </div>`;
  }
}

/* ================= Kraftwerte kompakt (ersetzt je eine Trendkarte pro Übung) ================= */
class CoachLifts extends CoachBase {
  _entities() { return (this._config?.items || []).map((x) => x.entity); }
  _onChange() { this._load(); }
  async _load() {
    const ids = this._entities(); if (!ids.length || !this._hass) return;
    const now = Date.now(); if (this._loading || (this._loadedAt && now - this._loadedAt < 300000)) return;
    this._loading = true;
    try {
      const days = this._config.days || 180;
      const r = await this._hass.callWS({ type: 'recorder/statistics_during_period', start_time: new Date(now - days * 864e5).toISOString(), end_time: new Date(now).toISOString(), statistic_ids: ids, period: 'day', types: ['max'] });
      this._series = {};
      for (const id of ids) this._series[id] = (r[id] || []).filter((x) => x.max != null).map((x) => ({ t: typeof x.start === 'number' ? x.start : Date.parse(x.start), v: x.max }));
      this._loadedAt = Date.now();
    } catch (e) { this._err = e.message || String(e); }
    this._loading = false; this._paint();
  }
  _css() { return `.lr{display:grid;grid-template-columns:minmax(0,1fr) auto 56px 52px;gap:10px;align-items:center;padding:9px 0;border-top:1px solid var(--divider-color,var(--cc-track))}
    .lr:first-child{border-top:0}.lr .v{font-weight:650;font-size:16px;white-space:nowrap}.lr .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .spark{width:56px;height:22px;display:block;overflow:visible}`; }
  _render() {
    const c = this._c(); const cfg = this._config || {}; const rows = []; const missing = [];
    for (const it of cfg.items || []) {
      const v = this._num(it.entity); if (v == null) { missing.push(it.name); continue; }
      const s = (this._series || {})[it.entity] || [];
      const ref = s.find((p) => p.t >= Date.now() - 31 * 864e5) || s[0];
      const diff = ref && s.length >= 2 ? v - ref.v : null;
      const lo = Math.min(...s.map((p) => p.v), v); const hi = Math.max(...s.map((p) => p.v), v);
      const spark = s.length >= 2 && hi - lo > 1e-9 ? (() => { const t0 = s[0].t; const t1 = s[s.length - 1].t || t0 + 1; const X = (t) => ((t - t0) / Math.max(t1 - t0, 1)) * 56; const Y = (y) => 20 - ((y - lo) / (hi - lo)) * 18; return `<svg class="spark" viewBox="0 0 56 22"><path d="${s.map((p, i) => `${i ? 'L' : 'M'}${X(p.t).toFixed(1)},${Y(p.v).toFixed(1)}`).join('')}" fill="none" stroke="${c.strength}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/></svg>`; })() : '<span></span>';
      const dTxt = diff == null ? '<span class="muted">neu</span>' : Math.abs(diff) < 0.05 ? '<span class="muted">±0</span>' : `<span style="color:${diff > 0 ? c.goodText : c.serious};font-weight:600">${diff > 0 ? '+' : '−'}${fmtNum(Math.abs(diff), 1)}</span>`;
      rows.push(`<div class="lr tap" data-more="${esc(it.entity)}"><span class="nm">${esc(it.name)}</span><span class="v">${fmtNum(v, 1)} <span class="small muted" style="font-weight:400">kg</span></span>${spark}<span class="small" style="text-align:right">${dTxt}</span></div>`);
    }
    return `<div class="card"><div class="row between"><div class="eyebrow">Kraftwerte · e1RM</div><span class="small muted">Δ 4 Wochen</span></div>
      <div style="margin-top:4px">${rows.join('') || '<div class="small muted">Noch keine Werte.</div>'}</div>
      ${missing.length ? `<div class="small muted" style="margin-top:6px">${esc(missing.join(', '))}: erscheint, sobald Sätze mit Gewicht erfasst sind.</div>` : ''}
      <div class="small muted" style="margin-top:6px">e1RM = geschätztes Maximalgewicht aus deinen Sätzen (Epley). Antippen zeigt den Verlauf.</div></div>`;
  }
}

/* ================= Herzfrequenzzonen (ersetzt fünf Tabellen) ================= */
const HR_COLORS = ['#9e9e9e', '#2a78d6', '#eda100', '#eb6834', '#d03b3b']; // grau · blau (locker) · gelb · orange · rot – wie die Intensitätskarte
class CoachHr extends CoachBase {
  _entities() { return [E.zones]; }
  _css() { return `.band{display:flex;gap:2px;height:12px;border-radius:999px;overflow:hidden;margin-top:10px}
    .band i{flex:1;display:block}
    .lbl{display:grid;grid-template-columns:repeat(5,1fr);gap:2px;margin-top:4px;font-size:11px;text-align:center;color:var(--secondary-text-color);line-height:1.25}
    .lbl b{display:block;color:var(--primary-text-color);font-size:12px}
    .sp{padding:12px 0;border-top:1px solid var(--divider-color,var(--cc-track))}.sp:first-of-type{border-top:0;padding-top:4px}
    .note{margin-top:10px;padding:8px 10px;border-radius:10px;font-size:13px}`; }
  _five(zones) {
    // Z5a–c zu einer Zone zusammenfassen: auf dem Handy bleiben 5 lesbare Felder
    const z = zones || []; const z5 = z.filter((x) => String(x.zone).startsWith('Z5'));
    const base = z.filter((x) => !String(x.zone).startsWith('Z5')).slice(0, 4);
    if (z5.length) base.push({ zone: 'Z5', use: 'Schwelle+', low: z5[0].low, high: z5[z5.length - 1].high });
    return base;
  }
  _band(zs) {
    const rng = (x) => (x.low == null ? `bis ${x.high}` : x.zone === 'Z5' ? `ab ${x.low}` : `${x.low}–${x.high}`);
    return `<div class="band">${zs.map((x, i) => `<i style="background:${HR_COLORS[i]}"></i>`).join('')}</div>
      <div class="lbl">${zs.map((x) => `<span><b>${esc(x.zone)}</b>${rng(x)}</span>`).join('')}</div>`;
  }
  _render() {
    const c = this._c(); const a = this._st(E.zones)?.attributes || {};
    const coach = a.coach || {}; const hm = a.hrmax || {};
    if (!coach.run && !coach.bike) return `<div class="card"><div class="eyebrow">Herzfrequenz-Zonen</div><div class="small muted" style="margin-top:6px">Noch keine Zonen berechnet – erscheint nach dem nächsten Sync.</div></div>`;
    const sports = [['run', 'Laufen'], ['bike', 'Rad']].filter(([k]) => coach[k]);
    const block = ([k, lab]) => {
      const z = coach[k]; const zs = this._five(z.zones); const easyTop = (zs[1] || {}).high;
      return `<div class="sp"><div class="row" style="gap:10px">${this._sportIc(k, 30)}<div style="flex:1;min-width:0"><div style="font-weight:600">${lab}</div><div class="small muted">${esc(z.source || '')}</div></div>
        <div style="text-align:right"><div style="font-size:20px;font-weight:650;line-height:1.1">${z.lthr ?? '–'}</div><div class="small muted">bpm Schwelle</div></div></div>
        ${this._band(zs)}
        ${easyTop ? `<div class="small" style="margin-top:8px"><b>Locker (Z1–2):</b> bis ${easyTop} bpm</div>` : ''}</div>`;
    };
    const notes = [];
    if (coach.bike?.approx) notes.push([c.warn, `Rad-Zonen sind eine Näherung aus dem Laufwert. Ein 30-min-Test auf dem Rad (Ø-HF der letzten 20 min) macht sie genau – Wert unter Einstellungen eintragen.`]);
    if (hm.used && hm.observed_confirmed && hm.used - hm.observed_confirmed > 3 && !hm.override) notes.push([c.track, `HFmax ${hm.used} laut Uhr, gemessen bisher höchstens ${hm.observed_confirmed}. Für die Coach-Zonen egal (sie hängen an der Schwelle), die Uhr-Zonen liegen dadurch eventuell zu hoch.`]);
    const g = (a.garmin || [])[0];
    const more = this._open.has('more');
    const z5 = (coach.run?.zones || []).filter((x) => String(x.zone).startsWith('Z5'));
    return `<div class="card">
      <div class="row between"><div class="eyebrow">Herzfrequenz-Zonen</div><span class="small muted">${a.updated ? `aktualisiert ${ddmm(new Date(a.updated))}` : ''}</span></div>
      <div style="margin-top:8px">${sports.map(block).join('')}</div>
      ${notes.map(([bg, t]) => `<div class="note" style="background:${bg === c.track ? 'var(--cc-track)' : `${bg}26`}">${icon('informationOutline', 14, 'inl')} ${esc(t)}</div>`).join('')}
      <div class="row between tap" data-toggle="more" style="margin-top:12px"><span class="small muted">Z5 genauer · Zonen auf der Uhr</span><span class="muted">${icon(more ? 'chevronDown' : 'chevronRight', 18)}</span></div>
      ${more ? `<div class="details" style="line-height:1.55">
        ${z5.length ? `<b>Laufen Z5:</b> ${z5.map((x) => `${esc(x.use)} ${x.low}–${x.high}`).join(' · ')}<br>` : ''}
        ${g ? `<div style="margin-top:8px"><b>Uhr-Zonen (${g.method === 'HR_MAX' ? '% HFmax' : esc(g.method)}, HFmax ${g.max_hr})</b></div>${this._band((g.zones || []).map((x) => ({ zone: `Z${x.n}`, low: x.low, high: x.high })))}
        <div style="margin-top:6px">Die Uhr rechnet in % der HFmax – deren Z2 liegt deutlich tiefer als Z2 nach Schwelle. Für lockere Einheiten gilt die Coach-Zone oben. Zonen der Uhr ändern: Garmin Connect › Benutzereinstellungen › Herzfrequenzzonen.</div>` : ''}
        <div style="margin-top:6px">Zonen nach Friel in % der Schwellen-HF (LTHR). Sie werden bei jedem Sync neu berechnet; eigene Testwerte haben Vorrang.</div></div>` : ''}
      <div class="row between tap" data-nav="/garmin-coach/einstellungen" style="margin-top:10px"><span class="small" style="color:var(--primary-color)">Eigene Werte eintragen</span><span class="muted">${icon('chevronRight', 18)}</span></div>
    </div>`;
  }
}

/* ================= Navigation ================= */
class CoachNav extends CoachBase {
  _entities() { return [E.last, E.sync]; }
  _css() { return `.nav{display:grid;grid-template-columns:repeat(var(--n),1fr);gap:6px;padding:10px}
    .nb{display:flex;flex-direction:column;align-items:center;gap:4px;padding:10px 4px;border-radius:12px;font-size:12px;cursor:pointer;color:var(--primary-text-color);-webkit-tap-highlight-color:transparent}
    .nb:active{background:var(--cc-track)}
    .nb .ic{width:22px;height:22px;color:var(--primary-color)}
    .busy .ic{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}`; }
  _render() {
    const items = this._config?.items || [];
    const last = this._st(E.last)?.state; const age = last ? (Date.now() - new Date(last).getTime()) / 6e4 : null;
    const ago = age == null ? '' : age < 60 ? `vor ${Math.round(age)} min` : `vor ${Math.round(age / 60)} h`;
    return `<div class="nav" style="--n:${items.length}">${items.map((it) => it.action === 'sync'
      ? `<div class="nb" data-sync="1">${icon('refresh')}<span class="lbl">${esc(it.label || 'Sync')}</span><span class="muted" style="font-size:10px">${ago}</span></div>`
      : `<div class="nb" data-nav="${esc(it.path)}">${icon(it.icon || 'chevronRight')}<span>${esc(it.label)}</span></div>`).join('')}</div>`;
  }
}

/* ================= Kennzahlen-Raster ================= */
class CoachMetrics extends CoachBase {
  _entities() { return (this._config?.items || []).map((x) => x.entity); }
  _css() { return `.mgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(100px,1fr));gap:8px;margin-top:8px}
    .m{background:var(--cc-track);border-radius:12px;padding:10px;cursor:pointer}
    .m b{display:block;font-size:20px;font-weight:650;line-height:1.15}
    .m.txt{grid-column:span 2}.m.txt b{font-size:16px;overflow-wrap:anywhere}
    .m span{font-size:11px;color:var(--secondary-text-color)}`; }
  _render() {
    const cfg = this._config || {};
    const tiles = (cfg.items || []).map((x) => { const st = this._st(x.entity); if (!st || ['unknown', 'unavailable'].includes(st.state)) return ''; const v = num(st.state); const val = v == null ? esc(st.state) : fmtVal(v, x.format, x.decimals ?? 0); const unit = x.unit ?? st.attributes?.unit_of_measurement ?? ''; const short = unit.length <= 4; return `<div class="m ${v == null ? 'txt' : ''}" data-more="${esc(x.entity)}"><b>${val}${short && unit ? `<span style="font-size:12px;font-weight:400;color:var(--secondary-text-color)"> ${esc(unit)}</span>` : ''}</b><span>${esc(x.name)}${!short && unit ? ` · ${esc(unit)}` : ''}</span></div>`; }).join('');
    return `<div class="card">${cfg.title ? `<div class="eyebrow">${esc(cfg.title)}</div>` : ''}<div class="mgrid">${tiles}</div>${cfg.note ? `<div class="small muted" style="margin-top:8px">${esc(cfg.note)}</div>` : ''}</div>`;
  }
}

const defs = [
  ['coach-hero', CoachHero, 'Coach: Heute'],
  ['coach-week', CoachWeek, 'Coach: Woche'],
  ['coach-trend', CoachTrend, 'Coach: Trend'],
  ['coach-zones', CoachZones, 'Coach: Intensität'],
  ['coach-gym', CoachGym, 'Coach: Gym'],
  ['coach-phases', CoachPhases, 'Coach: Saison'],
  ['coach-nav', CoachNav, 'Coach: Navigation'],
  ['coach-metrics', CoachMetrics, 'Coach: Kennzahlen'],
  ['coach-lifts', CoachLifts, 'Coach: Kraftwerte'],
  ['coach-hr', CoachHr, 'Coach: Herzfrequenzzonen'],
];
window.customCards = window.customCards || [];
for (const [tag, cls, name] of defs) {
  if (!customElements.get(tag)) customElements.define(tag, cls);
  if (!window.customCards.find((x) => x.type === tag)) window.customCards.push({ type: tag, name, description: 'Garmin AI Coach' });
}
console.info(`%c COACH-CARDS %c ${CC_VERSION} `, 'background:#2a78d6;color:#fff;border-radius:3px 0 0 3px', 'background:#1baf7a;color:#fff;border-radius:0 3px 3px 0');

