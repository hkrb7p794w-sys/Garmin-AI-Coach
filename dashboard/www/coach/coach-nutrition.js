/* Garmin AI Coach – Karte „Ernährung“ (coach-nutrition.js)
 * Ergänzt coach-cards.js um custom:coach-nutrition und nutzt dessen Basisklasse (Stil, Ring, Navigation).
 * Daten: sensor.ernaehrung_tag / sensor.ernaehrung_woche aus dem Add-on „Ernährung“.
 * Antippen öffnet die Ernährungs-App (Seitenleisten-Panel, sonst Ingress-Seite).
 * 1.0.0 (23.10.2026)
 * Optionen: max_recs (Standard 2), max_week (Standard 2).
 */
const CN_VERSION = '1.0.0';
const NUT_SLUG = '1c76c417_ernaehrung';
const ENT = { day: 'sensor.ernaehrung_tag', week: 'sensor.ernaehrung_woche' };
const NUT_COL = { light: { protein_g: '#2a78d6', carbs_g: '#eda100', fat_g: '#eb6834', water_ml: '#3987e5' },
  dark: { protein_g: '#3987e5', carbs_g: '#c98500', fat_g: '#d95926', water_ml: '#6aa3f0' } };
const NUT_LBL = { protein_g: ['Protein', 'g'], carbs_g: ['Kohlenhydrate', 'g'], fat_g: ['Fett', 'g'], water_ml: ['Flüssigkeit', 'ml'] };
const REC_IC = { timing: ['lightning-bolt', 'strength'], essen: ['silverware-fork-knife', 'run'], wie: ['dumbbell', 'swim'],
  hinweis: ['alert-circle-outline', 'serious'], lob: ['thumb-up-outline', 'good'], dge: ['leaf', 'run'],
  naehrstoff: ['nutrition', 'swim'], training: ['run', 'bike'], info: ['information-outline', 'neutral'] };
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (v) => (v == null ? '–' : Number(v).toLocaleString('de-DE', { maximumFractionDigits: 0 }));
const ic = (name, size = 18, extra = '') => `<ha-icon icon="mdi:${name}" style="--mdc-icon-size:${size}px;width:${size}px;height:${size}px;${extra}"></ha-icon>`;

(async () => {
  await customElements.whenDefined('coach-hero');
  const Base = Object.getPrototypeOf(customElements.get('coach-hero'));
  class CoachNutrition extends Base {
    _entities() { return [ENT.day, ENT.week]; }
    _css() {
      return `.mlist{flex:1;min-width:0;display:grid;gap:8px}
      .ml{font-size:13px;display:flex;align-items:baseline;gap:6px}.ml b{font-size:15px;font-weight:600}
      .ml .t{margin-left:auto;font-size:12px;color:var(--secondary-text-color)}
      .item{display:flex;gap:12px;align-items:flex-start;padding:9px 0}.item + .item{border-top:1px solid var(--divider-color,var(--cc-track))}
      .item .t{font-weight:600;font-size:14px}.item .c{font-size:13px;color:var(--secondary-text-color)}
      .open{display:flex;justify-content:space-between;align-items:center;margin-top:12px;color:var(--primary-color);font-weight:500;font-size:13px}`;
    }
    _path() { return this._hass?.panels?.[NUT_SLUG] ? `/${NUT_SLUG}` : `/hassio/ingress/${NUT_SLUG}`; }
    _render() {
      const st = this._st(ENT.day);
      if (!st || ['unknown', 'unavailable'].includes(st.state)) {
        return `<div class="card"><div class="eyebrow">Ernährung</div><div class="small muted" style="margin-top:6px">Noch keine Daten – Add-on „Ernährung“ starten.</div></div>`;
      }
      const a = st.attributes || {}, t = a.totals || {}, g = a.targets || {}, c = this._c();
      const col = this._dark() ? NUT_COL.dark : NUT_COL.light;
      const kcal = t.kcal || 0, goal = g.kcal || 1, pct = (100 * kcal) / goal, rest = Math.round(goal - kcal);
      const rows = ['protein_g', 'carbs_g', 'fat_g', 'water_ml'].map((k) => {
        const p = g[k] ? Math.max(0, Math.min(100, (100 * (t[k] || 0)) / g[k])) : 0;
        return `<div><div class="ml"><span class="dot" style="background:${col[k]}"></span><b>${fmt(t[k])}</b><span class="muted">${NUT_LBL[k][1]} ${NUT_LBL[k][0]}</span><span class="t">von ${fmt(g[k])}</span></div>
          <div class="bar" style="margin-top:3px"><i style="width:${p}%;background:${col[k]}"></i></div></div>`;
      }).join('');
      const recs = (a.recommendations || []).slice(0, this._config?.max_recs ?? 2);
      const weekRecs = (this._attr(ENT.week, 'recommendations') || []).filter((r) => !['lob', 'info'].includes(r.type))
        .slice(0, this._config?.max_week ?? 2);
      const item = (r) => {
        const [name, kind] = REC_IC[r.type] || REC_IC.info;
        return `<div class="item"><span class="sport-ic" style="background:${c[kind] || c.neutral}">${ic(name)}</span><div style="flex:1;min-width:0">
          <div class="t">${esc(r.title)}</div><div class="c">${esc((r.foods || []).length ? r.foods.join(' · ') : r.text)}</div></div></div>`;
      };
      const kind = !a.meals_count ? 'neutral' : rest >= -0.1 * goal ? 'good' : 'warn';
      const pill = !a.meals_count ? 'Noch nichts erfasst' : rest >= 0 ? `Noch ${fmt(rest)} kcal` : `${fmt(-rest)} kcal über Ziel`;
      return `<div class="card tap" data-nav="${this._path()}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
          <div class="eyebrow">Ernährung · ${esc(a.day_label || '')}</div>
          <span class="chip">${ic('dumbbell', 14)}${a.protein_meals ?? 0}/3 Protein</span></div>
        <div style="margin-top:10px"><span class="pill" style="background:${kind === 'neutral' ? c.track : `${c[kind]}22`}"><span class="dot" style="background:${c[kind] || c.neutral}"></span>${esc(pill)}</span></div>
        <div class="row" style="gap:14px;margin-top:12px">
          ${this._ring(pct, pct > 110 ? c.warn : 'var(--primary-color)', 88, 9, `<div><div style="font-size:20px;font-weight:650;line-height:1">${fmt(kcal)}</div><div class="small muted" style="line-height:1.2">von ${fmt(goal)}<br>kcal</div></div>`)}
          <div class="mlist">${rows}</div></div>
        ${recs.length ? `<div class="hr"></div><div class="eyebrow">Heute</div>${recs.map(item).join('')}` : ''}
        ${weekRecs.length ? `<div class="hr"></div><div class="eyebrow">Diese Woche</div>${weekRecs.map(item).join('')}` : ''}
        <div class="open"><span>${ic('silverware-fork-knife', 16, 'vertical-align:-3px;margin-right:4px')}Mahlzeit erfassen</span>${ic('chevron-right', 18)}</div>
      </div>`;
    }
  }
  if (!customElements.get('coach-nutrition')) customElements.define('coach-nutrition', CoachNutrition);
  window.customCards = window.customCards || [];
  if (!window.customCards.find((x) => x.type === 'coach-nutrition')) window.customCards.push({ type: 'coach-nutrition', name: 'Coach: Ernährung', description: 'Garmin AI Coach' });
  console.info(`%c COACH-NUTRITION %c ${CN_VERSION} `, 'background:#0F766E;color:#fff;border-radius:3px 0 0 3px', 'background:#eda100;color:#fff;border-radius:0 3px 3px 0');
})();
