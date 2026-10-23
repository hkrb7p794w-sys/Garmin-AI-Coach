/* Ernährung – Web-App im Design des Garmin-AI-Coach-Dashboards.
   Läuft über Home-Assistant-Ingress; Farben/Schrift kommen aus dem aktiven HA-Theme.
   Fotos existieren nur im Arbeitsspeicher dieser Seite und werden nach der Analyse verworfen. */
"use strict";

const S = { date: today(), view: "heute", status: null, settings: null, day: null, draft: null, editMealId: null,
  photo: null, photoTaken: null };

const CAT = { fruehstueck: "Frühstück", mittagessen: "Mittagessen", abendessen: "Abendessen", snack: "Snacks",
  sonstiges: "Sonstiges" };
const DAYTYPES = { ruhetag: "Ruhetag", leicht: "Leichter Tag", moderat: "Moderater Trainingstag",
  hart: "Harter Trainingstag", sehr_hart: "Sehr harter Trainingstag" };
const SRC = { bls: ["BLS", "--c-fiber"], off: ["Produkt", "--c-protein"], ki: ["KI-Schätzung", "--cc-serious"],
  custom: ["Eigenes", "--c-carbs"] };
const NUT = {
  kcal: ["Kalorien", "kcal"], protein_g: ["Protein", "g"], carbs_g: ["Kohlenhydrate", "g"], sugar_g: ["Zucker", "g"],
  fat_g: ["Fett", "g"], satfat_g: ["Gesättigte Fettsäuren", "g"], fiber_g: ["Ballaststoffe", "g"],
  water_ml: ["Flüssigkeit", "ml"], sodium_mg: ["Natrium", "mg"], potassium_mg: ["Kalium", "mg"],
  magnesium_mg: ["Magnesium", "mg"], calcium_mg: ["Calcium", "mg"], iron_mg: ["Eisen", "mg"], zinc_mg: ["Zink", "mg"],
  vitd_ug: ["Vitamin D", "µg"], b12_ug: ["Vitamin B12", "µg"], vitc_mg: ["Vitamin C", "mg"],
  iodine_ug: ["Jod", "µg"], omega3_mg: ["Omega-3 (EPA+DHA)", "mg"],
};
const MACROS = [["protein_g", "--c-protein"], ["carbs_g", "--c-carbs"], ["fat_g", "--c-fat"], ["fiber_g", "--c-fiber"],
  ["water_ml", "--c-water"]];
const MICROS = ["iron_mg", "zinc_mg", "magnesium_mg", "calcium_mg", "potassium_mg", "iodine_ug", "omega3_mg", "vitd_ug",
  "b12_ug", "vitc_mg", "sodium_mg"];
const REC_COLORS = { timing: "--c-carbs", essen: "--primary-color", wie: "--c-protein", hinweis: "--cc-serious",
  lob: "--cc-good", dge: "--c-fiber", naehrstoff: "--c-protein", training: "--c-fat", info: "--cc-neutral" };

/* ---------- Helfer ---------- */
function today() { return iso(new Date()); }
function iso(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; }
function nowTime() { const d = new Date(); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; }
function $(sel, root = document) { return root.querySelector(sel); }
function $$(sel, root = document) { return [...root.querySelectorAll(sel)]; }
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function fmt(v, d) {
  if (v === null || v === undefined || isNaN(v)) return "–";
  const dd = d ?? (Math.abs(v) >= 10 ? 0 : 1);
  return Number(v).toLocaleString("de-DE", { maximumFractionDigits: dd, minimumFractionDigits: 0 });
}
function icon(name, size = 20, cls = "") {
  const p = (window.ICONS || {})[name];
  return p ? `<svg class="ic ${cls}" viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true"><path d="${p}"/></svg>` : "";
}
function cssv(name) { return `var(${name})`; }
function scale(per100, g) { const o = {}; for (const k in NUT) { const v = per100?.[k]; o[k] = v == null ? null : v * g / 100; } return o; }
function sumItems(items) { const t = {}; for (const k in NUT) t[k] = 0; for (const it of items) { const s = scale(it.per100, it.amount_g || 0); for (const k in NUT) t[k] += s[k] || 0; } return t; }
function categoryAt(hhmm) {
  const [hh, mm] = String(hhmm || nowTime()).split(":").map(Number); const h = hh + (mm || 0) / 60;
  if (h >= 4 && h < 10.5) return "fruehstueck"; if (h >= 10.5 && h < 14.5) return "mittagessen";
  if (h >= 17.5 && h < 21.5) return "abendessen"; return "snack";
}
function dateLabel(ds) {
  const d = new Date(ds + "T12:00:00"); const y = new Date(); y.setDate(y.getDate() - 1);
  const pre = ds === today() ? "Heute, " : ds === iso(y) ? "Gestern, " : "";
  return pre + d.toLocaleDateString("de-DE", { weekday: "short", day: "numeric", month: "short" });
}
function yesterdayOf(ds) { const d = new Date(ds + "T12:00:00"); d.setDate(d.getDate() - 1); return iso(d); }
function ring(pct, color, size = 88, stroke = 9, inner = "") {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r, p = Math.max(0, Math.min(100, pct));
  return `<div class="ring" style="width:${size}px;height:${size}px"><svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--cc-track)" stroke-width="${stroke}"/>
    ${p > 0 ? `<circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${color}" stroke-width="${stroke}" stroke-linecap="round" stroke-dasharray="${(c * p) / 100} ${c}"/>` : ""}
    </svg><div class="in">${inner}</div></div>`;
}
function bar(pct, color, marker) {
  return `<div class="bar"><i style="width:${Math.max(0, Math.min(100, pct || 0))}%;background:${color}"></i>${marker != null ? `<span class="marker" style="left:${Math.min(100, marker)}%"></span>` : ""}</div>`;
}

async function api(path, opts = {}) {
  const init = { method: opts.method || "GET", headers: {} };
  if (opts.body !== undefined) { init.body = JSON.stringify(opts.body); init.headers["Content-Type"] = "application/json"; }
  const r = await fetch("api/v1/" + path, init);
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error((data && data.error) || `Fehler ${r.status}`);
  return data;
}

/* ---------- Theme aus Home Assistant übernehmen ---------- */
const THEME_VARS = ["--primary-color", "--accent-color", "--primary-background-color", "--card-background-color",
  "--ha-card-background", "--primary-text-color", "--secondary-text-color", "--divider-color",
  "--ha-card-border-radius", "--ha-card-box-shadow", "--ha-font-family-body"];
function applyTheme() {
  const root = document.documentElement;
  let dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  try {
    const pd = window.parent && window.parent !== window ? window.parent.document : null;
    if (pd) {
      const cs = getComputedStyle(pd.documentElement);
      for (const v of THEME_VARS) {
        const val = cs.getPropertyValue(v).trim();
        if (val) root.style.setProperty(v === "--ha-card-background" ? "--card-background-color" : v, val);
      }
      const bg = cs.getPropertyValue("--primary-background-color").trim();
      const m = bg.match(/^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i);
      if (m) dark = (parseInt(m[1], 16) * 299 + parseInt(m[2], 16) * 587 + parseInt(m[3], 16) * 114) / 1000 < 128;
    }
  } catch (e) { /* außerhalb von HA: eigene Werte */ }
  root.classList.toggle("dark", !!dark);
}

let toastTimer;
function toast(msg, action) {
  const el = $("#toast");
  el.innerHTML = esc(msg) + (action ? `<button>${esc(action.label)}</button>` : "");
  el.hidden = false;
  if (action) el.querySelector("button").onclick = () => { el.hidden = true; action.fn(); };
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, action ? 6000 : 2800);
}

/* ---------- Sheet ---------- */
function openSheet(html) {
  const sh = $("#sheet"); sh.innerHTML = html; sh.hidden = false; $("#backdrop").hidden = false;
  document.body.style.overflow = "hidden"; $$("[data-close]", sh).forEach((b) => (b.onclick = closeSheet)); sh.scrollTop = 0;
  return sh;
}
function closeSheet() {
  stopScan(); S.photo = null; // Foto verwerfen
  $("#sheet").hidden = true; $("#backdrop").hidden = true; document.body.style.overflow = "";
}
$("#backdrop").onclick = closeSheet;
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#sheet").hidden) closeSheet(); });
function head(title) { return `<div class="sheet-head"><h2>${esc(title)}</h2><button class="iconbtn" data-close aria-label="Schließen">${icon("close", 22)}</button></div>`; }

/* ---------- Navigation ---------- */
const NAV = { heute: ["homeVariant", "Heute"], woche: ["calendarWeek", "Woche"], favoriten: ["starOutline", "Favoriten"],
  einstellungen: ["cog", "Einstellungen"] };
$$(".nav .nb").forEach((b) => { const [ic, l] = NAV[b.dataset.view]; b.innerHTML = `${icon(ic)}<span>${l}</span>`;
  b.onclick = () => { S.view = b.dataset.view; syncTabs(); render(); }; });
function syncTabs() { $$(".nav .nb").forEach((x) => x.setAttribute("aria-selected", x.dataset.view === S.view)); }
$("#prevDay").innerHTML = icon("chevronLeft", 24); $("#nextDay").innerHTML = icon("chevronRight", 24);
$("#prevDay").onclick = () => shiftDay(-1); $("#nextDay").onclick = () => shiftDay(1);
$("#dateLabel").onclick = () => { const p = $("#datePicker"); p.value = S.date; if (p.showPicker) p.showPicker(); else p.click(); };
$("#datePicker").onchange = (e) => { if (e.target.value) { S.date = e.target.value; render(); } };
function shiftDay(n) { const d = new Date(S.date + "T12:00:00"); d.setDate(d.getDate() + n); S.date = iso(d); render(); }

async function render() {
  $("#dateLabel").textContent = dateLabel(S.date);
  const v = $("#view");
  try {
    if (S.view === "heute") await renderDay(v);
    else if (S.view === "woche") await renderWeek(v);
    else if (S.view === "favoriten") await renderFavorites(v);
    else await renderSettings(v);
  } catch (e) { v.innerHTML = `<div class="card"><div class="err">${esc(e.message)}</div></div>`; }
}

/* ---------- Heute ---------- */
async function renderDay(v) {
  const d = await api(`day?date=${S.date}`); S.day = d;
  const t = d.totals, g = d.targets, kind = d.target_kind || {};
  const eaten = t.kcal || 0, goal = g.kcal || 1, pct = 100 * eaten / goal, rest = goal - eaten;
  const tr = d.training || {};
  const src = { geplant: "nach Wochenplan", manuell: "manuell", garmin: "Garmin" }[d.day_source] || "";
  const kcalColor = pct > 110 ? cssv("--cc-warn") : cssv("--primary-color");
  const isToday = d.date === today();
  const pillText = !d.meals_count ? "Noch nichts erfasst" : rest >= 0 ? `Noch ${fmt(rest)} kcal` : `${fmt(-rest)} kcal über dem Ziel`;
  const pillDot = !d.meals_count ? "--cc-neutral" : rest >= -0.1 * goal ? "--cc-good" : "--cc-warn";

  const macros = MACROS.map(([k, col]) => {
    const p = g[k] ? 100 * (t[k] || 0) / g[k] : 0;
    return `<div class="v"><div class="lab"><span class="dot" style="background:var(${col})"></span><b class="num">${fmt(t[k])}</b>
      <span class="muted">${NUT[k][1]} ${NUT[k][0]}</span><span class="t num">von ${fmt(g[k])}</span></div>${bar(p, `var(${col})`)}</div>`;
  }).join("");
  const microItem = (k) => {
    const p = g[k] ? 100 * (t[k] || 0) / g[k] : 0; const over = kind[k] === "max" && p > 100;
    const col = over ? "--cc-critical" : kind[k] === "max" || kind[k] === "ref" ? "--cc-neutral" : p >= 90 ? "--cc-good" : "--primary-color";
    return `<div class="micro"><div class="lab"><span>${NUT[k][0]}${kind[k] === "max" ? " (max.)" : ""}</span><span class="num">${fmt(t[k], 1)} / ${fmt(g[k])} ${NUT[k][1]}</span></div>${bar(p, `var(${col})`)}</div>`;
  };
  const incomplete = Object.keys(d.incomplete || {}).length
    ? `<div class="small muted" style="margin-top:8px">${icon("informationOutline", 14, "inl")} Bei ${Math.max(...Object.values(d.incomplete))} Position(en) fehlen einzelne Mikronährstoffe – die Summen sind dort Untergrenzen.</div>` : "";

  const hero = `<section class="card">
    <div class="top"><div class="eyebrow">${esc(d.day_label)}${src ? ` · ${esc(src)}` : ""}</div>
      <div class="row wrap" style="gap:6px">
        ${tr.training_min ? `<span class="chip">${icon("dumbbell", 14)}${tr.training_min} min Training</span>` : ""}
        <button class="chip" id="dtBtn">${icon("swapHorizontal", 14)}Tagestyp</button></div></div>
    <div style="margin-top:10px"><span class="pill" style="background:color-mix(in srgb, var(${pillDot}) 14%, transparent)"><span class="dot" style="background:var(${pillDot})"></span>${esc(pillText)}</span></div>
    ${d.day_source === "geplant" && d.plan_text ? `<div class="small muted" style="margin-top:6px">${icon("informationOutline", 14, "inl")} Noch kein Training aufgezeichnet – Ziel nach Plan: ${esc(d.plan_text)}</div>` : ""}
    <div class="vitals">
      ${ring(pct, kcalColor, 96, 9, `<div><div class="num" style="font-size:22px;font-weight:650;line-height:1">${fmt(eaten)}</div><div class="small muted" style="line-height:1.25">von ${fmt(goal)}<br>kcal</div></div>`)}
      <div class="vlist">${macros}</div>
    </div>
    <div class="small muted" style="margin-top:10px">${icon("dumbbell", 14, "inl")} Proteinreiche Mahlzeiten (≥ ${fmt(d.protein_meal_min_g)} g): <b style="color:var(--primary-text-color)">${d.protein_meals}</b> von 3–4</div>
    <div class="hr"></div>
    <button class="toggle" data-tg="micros"><span class="eyebrow">Mikronährstoffe & Grenzen</span>${icon(S.openMicros ? "chevronDown" : "chevronRight", 18)}</button>
    ${S.openMicros ? `<div class="micros">${MICROS.map(microItem).join("")}${["sugar_g", "satfat_g"].map(microItem).join("")}</div>${incomplete}` : ""}
    <div class="hr"></div>
    <button class="toggle" data-tg="why"><span class="eyebrow">Wie das Ziel zustande kommt</span>${icon(S.openWhy ? "chevronDown" : "chevronRight", 18)}</button>
    ${S.openWhy ? `<div class="details">Grundumsatz ${fmt(d.energy?.bmr)} kcal (Mifflin-St Jeor, ${fmt(d.profile?.weight_kg, 1)} kg${d.profile_source?.weight_kg ? ` aus ${esc(d.profile_source.weight_kg)}` : ""}) × ${fmt(d.energy?.pal, 2)} Alltag
      = ${fmt(d.energy?.base)} kcal, dazu ${fmt(d.energy?.exercise)} kcal Training (Garmin, netto).
      ${d.energy?.goal_pct_applied ? `Ziel „${esc(d.energy.goal)}“: ${fmt(d.energy.goal_pct_applied)} %. ` : ""}
      ${d.energy?.ea_floor ? "Untergrenze Energieverfügbarkeit (30 kcal je kg fettfreie Masse) greift. " : ""}
      ${d.energy?.garmin_total_kcal ? `Zum Vergleich: Garmin schätzt bisher ${fmt(d.energy.garmin_total_kcal)} kcal Gesamtumsatz. ` : ""}
      Kohlenhydrate ${fmt(g.carbs_g / d.profile.weight_kg, 1)} g/kg für „${esc(d.day_label)}“, Protein ${fmt(d.protein_g_per_kg, 1)} g/kg.
      Mikronährstoffe: DGE-Referenzwerte (Jod 150 µg seit 2025), Omega-3: EFSA. Orientierung, keine medizinische Beratung.</div>` : ""}
  </section>`;

  const recs = d.recommendations || [];
  const recCard = recs.length ? `<section class="card"><div class="eyebrow">${isToday ? "Empfehlungen für heute" : "Rückblick"}</div>
    ${recs.map((r, i) => recItem(r, i)).join("")}</section>` : "";

  const yest = yesterdayOf(S.date);
  const meals = `<section class="card">${Object.entries(d.categories).map(([c, cat]) => `
      <div class="catrow"><span class="eyebrow">${esc(cat.label)}${cat.kcal ? ` · ${fmt(cat.kcal)} kcal` : ""}</span>
        <span class="cat-actions">${!cat.meals.length && c !== "sonstiges" ? `<button class="link" data-copycat="${c}">wie gestern</button>` : ""}<button class="link" data-add="${c}" aria-label="${esc(cat.label)} hinzufügen">${icon("plus", 18)}</button></span></div>
      ${cat.meals.length ? cat.meals.map((m) => `<button class="item" data-meal="${m.id}">
        <span style="flex:1;min-width:0"><span class="t clamp">${esc(m.title || m.items.map((i) => i.name).join(", "))}</span>
        <span class="c clamp">${esc(m.time || "")} · ${esc(m.items.map((i) => `${i.name} ${fmt(i.amount_g)} ${i.is_liquid ? "ml" : "g"}`).join(", "))}</span></span>
        <span class="k num">${fmt(m.totals.kcal)} kcal</span></button>`).join("") : `<div class="empty">Noch nichts eingetragen.</div>`}`).join("")}
    </section>`;

  v.innerHTML = hero + recCard + meals;
  $("#dtBtn").onclick = () => dayTypeSheet(d);
  $$("[data-tg]", v).forEach((b) => (b.onclick = () => { const k = b.dataset.tg; if (k === "micros") S.openMicros = !S.openMicros; else S.openWhy = !S.openWhy; renderDay(v); }));
  $$("[data-meal]", v).forEach((b) => (b.onclick = () => editMeal(+b.dataset.meal)));
  $$("[data-add]", v).forEach((b) => (b.onclick = () => searchSheet(false, null, "", b.dataset.add)));
  $$("[data-copycat]", v).forEach((b) => (b.onclick = async () => {
    try {
      const out = await api("copy_category", { method: "POST", body: { from: yest, to: S.date, category: b.dataset.copycat } });
      toast(`${out.length} Eintrag/Einträge von gestern übernommen`, { label: "Rückgängig", fn: async () => { for (const m of out) await api(`meals/${m.id}`, { method: "DELETE" }); render(); } });
      render();
    } catch (e) { toast(e.message); }
  }));
  bindRecs(v, recs);
}

function recItem(r, i) {
  const col = REC_COLORS[r.type] || "--primary-color";
  return `<div class="item"><span class="sport-ic" style="background:var(${col})">${icon(r.icon || "lightbulbOnOutline", 18)}</span>
    <div style="flex:1;min-width:0"><div class="t">${esc(r.title)}</div><div class="c">${esc(r.text)}</div>
    ${(r.foods || []).length ? `<div class="foods">${r.foods.map((f, j) => `<button class="food" data-rec="${i}:${j}" title="Eintragen">${icon("plus", 14)}<span><b>${esc(f.name)}</b> · ${esc(f.portion)} · ${fmt(f.kcal)} kcal${f.highlight ? ` · ${esc(f.highlight)}` : f.protein_g >= 8 ? ` · ${fmt(f.protein_g)} g P` : f.carbs_g >= 15 ? ` · ${fmt(f.carbs_g)} g KH` : ""}</span></button>`).join("")}</div>` : ""}
    ${r.source ? `<div class="src">Quelle: ${esc(r.source)}</div>` : ""}</div></div>`;
}
function bindRecs(root, recs) {
  $$("[data-rec]", root).forEach((b) => (b.onclick = () => {
    const [i, j] = b.dataset.rec.split(":").map(Number); const f = recs[i].foods[j];
    S.editMealId = null;
    S.draft = newDraft("empfehlung", [{ name: f.name, amount_g: f.grams, amount_text: f.portion, source: "bls", ref: f.bls_code,
      per100: f.per100, is_liquid: f.is_liquid, confidence: "hoch", match_name: f.bls_name }]);
    openEditor();
  }));
}

function dayTypeSheet(d) {
  const sh = openSheet(head("Tagestyp") + `<p class="small muted">Bestimmt das Kohlenhydrat-Ziel. Normalerweise aus Garmin bzw. dem Wochenplan.</p>
    <div class="list">${Object.entries(DAYTYPES).map(([k, l]) => `<button class="entry" data-t="${k}"><span class="n">${l}</span><span class="d">${k === d.day_type ? "aktiv" : ""}</span></button>`).join("")}
    <button class="entry" data-t=""><span class="n">Automatisch</span><span class="d">Garmin / Plan</span></button></div>`);
  $$("[data-t]", sh).forEach((b) => (b.onclick = async () => {
    await api("settings", { method: "PUT", body: { day_type_override: b.dataset.t ? { date: S.date, type: b.dataset.t } : null } });
    closeSheet(); render();
  }));
}

/* ---------- Editor ---------- */
function newDraft(method, items = [], extra = {}) {
  const time = S.date === today() ? nowTime() : "12:00";
  return Object.assign({ date: S.date, time, category: categoryAt(time), title: "", method, items, hint: "" }, extra);
}

function openEditor() {
  const dr = S.draft, editing = !!S.editMealId;
  const sh = openSheet(head(editing ? "Mahlzeit bearbeiten" : "Mahlzeit prüfen") + `
    ${S.photo && !editing ? `<img class="photo-preview" src="${S.photo}" alt="Foto (wird nicht gespeichert)">` : ""}
    ${dr.hint ? `<div class="hint">${esc(dr.hint)}</div>` : ""}
    <div id="items"></div>
    <div class="row" style="margin-top:6px"><button class="link" id="addItem">${icon("plus", 14, "inl")} Lebensmittel hinzufügen</button></div>
    <div class="sum num" id="sum"></div>
    <label class="f">Mahlzeit</label>
    <div class="row wrap" id="cats" style="gap:6px">${Object.entries(CAT).map(([k, l]) => `<button class="chip" data-c="${k}" aria-pressed="${k === dr.category}">${l}</button>`).join("")}</div>
    <div class="grid2">
      <div><label class="f" for="mDate">Datum</label><input type="date" id="mDate" value="${esc(dr.date)}"></div>
      <div><label class="f" for="mTime">Uhrzeit</label><input type="time" id="mTime" value="${esc(dr.time)}"></div>
    </div>
    <label class="f" for="mTitle">Titel (optional)</label><input type="text" id="mTitle" value="${esc(dr.title)}">
    <label class="check"><input type="checkbox" id="mFav"> Als Favorit/Rezept merken</label>
    <div id="favOpts" hidden class="grid2"><div><label class="f" for="mServ">Ergibt Portionen</label><input type="number" id="mServ" min="1" step="1" value="1"></div></div>
    <button class="btn wide" id="save">${editing ? "Änderungen speichern" : "Speichern"}</button>
    ${editing ? `<div class="grid2"><button class="btn ghost wide" id="again">${icon("contentCopy", 16, "inl")} Heute nochmal</button><button class="btn danger wide" id="del">Löschen</button></div>` : ""}`);
  renderItems();
  $$("#cats .chip", sh).forEach((b) => (b.onclick = () => { dr.category = b.dataset.c; $$("#cats .chip", sh).forEach((x) => x.setAttribute("aria-pressed", x === b)); }));
  $("#mTitle").oninput = (e) => (dr.title = e.target.value);
  $("#mTime").oninput = (e) => (dr.time = e.target.value);
  $("#mDate").oninput = (e) => (dr.date = e.target.value);
  $("#mFav").onchange = (e) => ($("#favOpts").hidden = !e.target.checked);
  $("#addItem").onclick = () => searchSheet(true);
  $("#save").onclick = saveDraft;
  if (editing) {
    $("#del").onclick = async () => { await api(`meals/${S.editMealId}`, { method: "DELETE" }); S.editMealId = null; closeSheet(); render(); toast("Mahlzeit gelöscht"); };
    $("#again").onclick = async () => { const m = await api(`meals/${S.editMealId}/copy`, { method: "POST", body: {} }); closeSheet(); S.date = m.date; render();
      toast(`${CAT[m.category]} nochmal eingetragen`, { label: "Rückgängig", fn: async () => { await api(`meals/${m.id}`, { method: "DELETE" }); render(); } }); };
  }
}

function renderItems() {
  const dr = S.draft, box = $("#items"); if (!box) return;
  if (!dr.items.length) { box.innerHTML = `<div class="empty">Keine Lebensmittel – füge eins hinzu.</div>`; updateSum(); return; }
  box.innerHTML = dr.items.map((it, i) => {
    const p = it.per100 || {}, [sl, sc] = SRC[it.source] || [it.source, "--cc-neutral"];
    const match = it.match_name && it.match_name !== it.name ? `${sl}: ${it.match_name}` : sl;
    return `<div class="pos" data-i="${i}">
      <div class="pos-top"><input type="text" value="${esc(it.name)}" aria-label="Name" data-f="name">
        <span class="tag" style="background:color-mix(in srgb, var(${sc}) 18%, transparent)">${esc(sl)}</span>
        <button class="step" data-rm aria-label="Entfernen" style="width:30px;height:30px">${icon("close", 16)}</button></div>
      <div class="amount">
        <button class="step" data-step="-" aria-label="weniger">${icon("minus", 18)}</button>
        <input type="number" inputmode="decimal" min="0" step="any" value="${Math.round((it.amount_g || 0) * 10) / 10}" data-f="amount" aria-label="Menge">
        <span class="muted">${it.is_liquid ? "ml" : "g"}</span>
        <button class="step" data-step="+" aria-label="mehr">${icon("plus", 18)}</button>
        <span class="kc num">${fmt((p.kcal || 0) * (it.amount_g || 0) / 100)} kcal</span></div>
      <div class="units" data-units></div>
      <div class="details">${esc([it.amount_text, match].filter(Boolean).join(" · "))}${it.confidence === "niedrig" ? " · Menge unsicher" : ""}<br>
        <span class="num">je 100 g: ${fmt(p.kcal)} kcal · ${fmt(p.protein_g)} g P · ${fmt(p.carbs_g)} g KH · ${fmt(p.fat_g)} g F</span></div>
      <button class="link" data-alt style="margin-top:4px">${(it.candidates && it.candidates.length) || it.estimate ? "Andere Zuordnung" : "Ersetzen"}</button><div class="alts" hidden></div>
    </div>`;
  }).join("");
  $$(".pos", box).forEach((el) => {
    const i = +el.dataset.i, it = dr.items[i];
    $("[data-f=name]", el).oninput = (e) => (it.name = e.target.value);
    const amt = $("[data-f=amount]", el);
    const setAmt = (g) => { it.amount_g = Math.max(0, g); amt.value = Math.round(it.amount_g * 10) / 10; $(".kc", el).textContent = `${fmt((it.per100?.kcal || 0) * it.amount_g / 100)} kcal`; updateSum(); };
    amt.oninput = () => setAmt(parseFloat(amt.value.replace(",", ".")) || 0);
    $$("[data-step]", el).forEach((b) => (b.onclick = () => { const st = it.amount_g >= 200 ? 25 : it.amount_g >= 50 ? 10 : 5;
      setAmt(Math.round(((it.amount_g || 0) + (b.dataset.step === "+" ? st : -st)) / st) * st); }));
    $("[data-rm]", el).onclick = () => { dr.items.splice(i, 1); renderItems(); };
    api(`portions?name=${encodeURIComponent(it.name)}&serving_g=${it.serving_g || ""}`).then((units) => {
      $("[data-units]", el).innerHTML = units.map((u) => `<button class="chip" data-g="${u.grams}">${esc(u.label)} · ${u.grams} ${it.is_liquid ? "ml" : "g"}</button>`).join("");
      $$("[data-g]", el).forEach((b) => (b.onclick = () => { setAmt(+b.dataset.g); it.amount_text = b.textContent.split(" · ")[0]; }));
    }).catch(() => {});
    $("[data-alt]", el).onclick = () => {
      const box2 = $(".alts", el); box2.hidden = !box2.hidden;
      const opts = (it.candidates || []).map((c, j) => `<button data-c="${j}">${esc(c.name)} <span class="muted num">${fmt(c.kcal)} kcal/100 g</span></button>`);
      if (it.estimate && it.source !== "ki") opts.push(`<button data-est>KI-Schätzung verwenden <span class="muted num">${fmt(it.estimate.kcal)} kcal/100 g</span></button>`);
      opts.push(`<button data-search>In der Datenbank suchen …</button>`);
      box2.innerHTML = opts.join("");
      $$("[data-c]", box2).forEach((b) => (b.onclick = () => { const c = it.candidates[+b.dataset.c];
        Object.assign(it, { source: c.source, ref: c.ref, food_id: null, per100: c.per100, match_name: c.name }); renderItems(); }));
      const est = $("[data-est]", box2);
      if (est) est.onclick = () => { Object.assign(it, { source: "ki", ref: null, food_id: null, per100: it.estimate, match_name: null }); renderItems(); };
      $("[data-search]", box2).onclick = () => searchSheet(true, i, it.name);
    };
  });
  updateSum();
}
function updateSum() {
  const s = sumItems(S.draft.items), el = $("#sum");
  if (el) el.innerHTML = `<span>Summe</span><span>${fmt(s.kcal)} kcal · ${fmt(s.protein_g)} g P · ${fmt(s.carbs_g)} g KH · ${fmt(s.fat_g)} g F</span>`;
}

async function saveDraft() {
  const dr = S.draft, btn = $("#save");
  if (!dr.items.length) { toast("Mindestens ein Lebensmittel eintragen"); return; }
  btn.disabled = true;
  const items = dr.items.map((it) => ({ name: it.name, amount_g: it.amount_g, amount_text: it.amount_text, source: it.source,
    ref: it.ref, food_id: it.food_id, per100: it.per100, confidence: it.confidence, ai_group: it.ai_group, food_group: it.food_group }));
  const body = { date: dr.date, time: dr.time, category: dr.category, title: dr.title || null, method: dr.method, items, ai: dr.ai };
  const fav = $("#mFav")?.checked, servings = parseFloat($("#mServ")?.value) || 1;
  try {
    let m;
    if (S.editMealId) { m = await api(`meals/${S.editMealId}`, { method: "PUT", body }); toast("Gespeichert"); }
    else {
      m = await api("meals", { method: "POST", body });
      toast(`${CAT[m.category]} gespeichert`, { label: "Rückgängig", fn: async () => { await api(`meals/${m.id}`, { method: "DELETE" }); render(); } });
    }
    if (fav) await api("favorites", { method: "POST", body: { title: dr.title || m.title || "Favorit", category: dr.category, items, servings } });
    S.editMealId = null; S.draft = null; closeSheet(); S.date = m.date; S.view = "heute"; syncTabs(); render();
  } catch (e) { toast(e.message); btn.disabled = false; }
}

async function editMeal(id) {
  const m = await api(`meals/${id}`); S.editMealId = id;
  S.draft = { date: m.date, time: m.time || "", category: m.category, title: m.title || "", method: m.method,
    items: m.items.map((it) => ({ ...it, ref: null })), hint: "" };
  openEditor();
}

/* ---------- Text ---------- */
async function textSheet() {
  openSheet(head("Was hast du gegessen?") + `
    <textarea id="txt" placeholder="z. B. 2 Rühreier mit einer Scheibe Vollkornbrot und ein Kaffee mit Milch"></textarea>
    <button class="btn wide" id="go">Analysieren</button><div id="out"></div>
    <div class="eyebrow" style="margin-top:16px">Häufig</div><div class="row wrap" id="freq" style="gap:6px;margin-top:6px"><span class="spinner"></span></div>`);
  const ta = $("#txt"); ta.focus();
  ta.onkeydown = (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) $("#go").click(); };
  $("#go").onclick = () => { const text = ta.value.trim(); if (!text) { ta.focus(); return; } runAnalyze({ text }, "text"); };
  try {
    const f = await api("frequent");
    $("#freq").innerHTML = f.items.length ? f.items.slice(0, 12).map((it, i) => `<button class="chip" data-f="${i}">${esc(it.name)} · ${fmt(it.avg_g)} g</button>`).join("")
      : `<span class="small muted">Erscheint, sobald ein paar Mahlzeiten erfasst sind.</span>`;
    $$("[data-f]", $("#freq")).forEach((b) => (b.onclick = () => { const it = f.items[+b.dataset.f];
      S.editMealId = null; S.draft = newDraft("manuell", [{ name: it.name, amount_g: it.avg_g, source: it.source, food_id: it.food_id, per100: it.per100 }]); openEditor(); }));
  } catch (e) { $("#freq").innerHTML = ""; }
}

async function runAnalyze(payload, method) {
  const out = $("#out"), btn = $("#go"); if (btn) btn.disabled = true;
  const box = document.createElement("div"); box.className = "note"; box.innerHTML = `<span class="spinner"></span> Wird analysiert … (meist 5–20 Sekunden)`; out.appendChild(box);
  try {
    const r = await api("analyze", { method: "POST", body: payload });
    payload.image = null; // Bild nicht länger als nötig halten
    S.editMealId = null;
    const taken = method === "foto" ? S.photoTaken : null;
    S.draft = newDraft(method, r.items, { title: r.title || "", hint: r.hint || "", ai: { model: r.model, text: payload.text || null } });
    if (taken) { S.draft.date = taken.date; S.draft.time = taken.time; }
    S.draft.category = r.category || categoryAt(S.draft.time);
    if (!r.items.length) S.draft.hint = "Keine Lebensmittel erkannt – füge sie manuell hinzu.";
    openEditor();
  } catch (e) { box.className = "err"; box.textContent = e.message; if (btn) btn.disabled = false; }
}

/* ---------- Foto (nur im Speicher) ---------- */
function downscale(file, max = 1280, quality = 0.82) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => { const r = Math.min(1, max / Math.max(img.width, img.height)); const c = document.createElement("canvas");
      c.width = Math.round(img.width * r); c.height = Math.round(img.height * r); c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(img.src); resolve({ dataUrl: c.toDataURL("image/jpeg", quality), canvas: c }); }; // Neu-Kodierung entfernt EXIF/GPS
    img.onerror = () => reject(new Error("Bild konnte nicht gelesen werden"));
    img.src = URL.createObjectURL(file);
  });
}
async function photoTakenAt(file) { /* EXIF DateTimeOriginal lesen (nur Datum/Uhrzeit, sonst nichts) */
  try {
    const buf = new DataView(await file.slice(0, 256 * 1024).arrayBuffer()); if (buf.getUint16(0) !== 0xFFD8) return null;
    let off = 2;
    while (off + 4 < buf.byteLength) {
      const marker = buf.getUint16(off), len = buf.getUint16(off + 2);
      if (marker === 0xFFE1 && buf.getUint32(off + 4) === 0x45786966) {
        const tiff = off + 10, le = buf.getUint16(tiff) === 0x4949, u16 = (o) => buf.getUint16(o, le), u32 = (o) => buf.getUint32(o, le);
        const find = (ifd, tag) => { const n = u16(ifd); for (let i = 0; i < n; i++) { const e = ifd + 2 + i * 12; if (u16(e) === tag) return e; } return null; };
        const ex = find(tiff + u32(tiff + 4), 0x8769); if (!ex) return null;
        const dto = find(tiff + u32(ex + 8), 0x9003); if (!dto) return null;
        const at = tiff + u32(dto + 8); let s = ""; for (let i = 0; i < 19; i++) s += String.fromCharCode(buf.getUint8(at + i));
        const m = s.match(/^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2})/); return m ? { date: `${m[1]}-${m[2]}-${m[3]}`, time: `${m[4]}:${m[5]}` } : null;
      }
      if ((marker & 0xFF00) !== 0xFF00) return null; off += 2 + len;
    }
  } catch (e) { /* kein EXIF */ }
  return null;
}
$("#photoInput").onchange = async (e) => {
  const file = e.target.files[0]; e.target.value = ""; if (!file) return;
  const taken = await photoTakenAt(file);
  const { dataUrl } = await downscale(file);
  const age = taken ? (Date.now() - new Date(`${taken.date}T${taken.time}:00`).getTime()) / 60000 : 0;
  S.photoTaken = taken && age > 20 ? taken : null; S.photo = dataUrl;
  openSheet(head("Foto") + `<img class="photo-preview" src="${dataUrl}" alt="">
    <div class="small muted" style="margin-top:6px">${icon("informationOutline", 14, "inl")} Das Foto wird nur für die Analyse verwendet und nicht gespeichert (${esc(S.status?.ai_label || "KI")}).</div>
    ${S.photoTaken ? `<div class="note">Aufgenommen ${esc(dateLabel(S.photoTaken.date))}, ${esc(S.photoTaken.time)} Uhr – die Mahlzeit wird dort eingetragen.</div>` : ""}
    <label class="f" for="ptxt">Ergänzung (optional)</label><input type="text" id="ptxt" placeholder="z. B. mit Olivenöl, halbe Portion gegessen">
    <button class="btn wide" id="go">Analysieren</button><div id="out"></div>`);
  $("#go").onclick = () => runAnalyze({ image: S.photo, mime: "image/jpeg", text: $("#ptxt").value }, "foto");
  if (S.settings?.photo_ai === false) { $("#out").innerHTML = `<div class="err">Foto-Analyse ist in den Einstellungen ausgeschaltet.</div>`; $("#go").disabled = true; }
};

/* ---------- Barcode ---------- */
let scanCtl = null;
function stopScan() { try { if (scanCtl) scanCtl.reset(); } catch (e) { /* egal */ } scanCtl = null; }
const BC_FORMATS = () => [ZXing.BarcodeFormat.EAN_13, ZXing.BarcodeFormat.EAN_8, ZXing.BarcodeFormat.UPC_A, ZXing.BarcodeFormat.UPC_E];
function barcodeSheet() {
  const live = window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.ZXing;
  openSheet(head("Barcode") + `
    ${live ? `<video class="scan" id="vid" playsinline muted></video><div class="small muted" style="margin-top:4px">Barcode ins Bild halten.</div>` : ""}
    <button class="btn wide ${live ? "ghost" : ""}" id="snap">${icon("cameraOutline", 16, "inl")} Barcode fotografieren / aus Fotos</button>
    <label class="f" for="code">Nummer eintippen</label>
    <div class="row"><input type="text" id="code" inputmode="numeric" placeholder="EAN, 8 oder 13 Ziffern"><button class="btn" id="look">Suchen</button></div>
    <div id="out"></div>`);
  $("#snap").onclick = () => $("#barcodeInput").click();
  $("#look").onclick = () => lookupBarcode($("#code").value);
  if (live) {
    try {
      const hints = new Map(); hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, BC_FORMATS());
      scanCtl = new ZXing.BrowserMultiFormatReader(hints);
      scanCtl.decodeOnceFromConstraints({ video: { facingMode: "environment" } }, "vid").then((res) => { stopScan(); lookupBarcode(res.getText()); }).catch(() => {});
    } catch (e) { /* Kamera nicht verfügbar */ }
  }
}
$("#barcodeInput").onchange = async (e) => {
  const file = e.target.files[0]; e.target.value = ""; if (!file) return;
  try {
    const { canvas } = await downscale(file, 1600, 0.9); const code = decodeCanvas(canvas);
    if (!code) throw new Error("Kein Barcode erkannt – näher ran, gerade halten oder Nummer eintippen.");
    $("#code").value = code; lookupBarcode(code);
  } catch (err) { const out = $("#out"); if (out) out.innerHTML = `<div class="err">${esc(err.message)}</div>`; }
};
function decodeCanvas(canvas) {
  if (!window.ZXing) return null;
  const reader = new ZXing.MultiFormatReader(), hints = new Map();
  hints.set(ZXing.DecodeHintType.TRY_HARDER, true); hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, BC_FORMATS()); reader.setHints(hints);
  for (const rot of [0, 90]) {
    let c = canvas;
    if (rot) { c = document.createElement("canvas"); c.width = canvas.height; c.height = canvas.width; const ctx = c.getContext("2d"); ctx.translate(c.width, 0); ctx.rotate(Math.PI / 2); ctx.drawImage(canvas, 0, 0); }
    try { return reader.decode(new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(new ZXing.HTMLCanvasElementLuminanceSource(c)))).getText(); } catch (e) { /* weiter */ }
  }
  return null;
}
async function lookupBarcode(code) {
  code = String(code || "").replace(/\D/g, ""); const out = $("#out"); if (!code) return;
  out.innerHTML = `<div class="note"><span class="spinner"></span> Suche ${esc(code)} …</div>`;
  try {
    const f = await api("barcode", { method: "POST", body: { code } });
    S.editMealId = null;
    S.draft = newDraft("barcode", [{ name: f.name, amount_g: f.serving_g || 100, serving_g: f.serving_g, amount_text: f.serving_label || "", source: f.source,
      food_id: f.id, per100: f.per100, is_liquid: f.is_liquid, confidence: "hoch" }]);
    openEditor();
  } catch (e) {
    out.innerHTML = `<div class="err">${esc(e.message)}</div><button class="btn ghost wide" id="newFood">Produkt selbst anlegen</button>`;
    $("#newFood").onclick = () => customFoodSheet({ barcode: code });
  }
}

/* ---------- Suche ---------- */
function searchSheet(forDraft = false, replaceIndex = null, initial = "", category = null) {
  openSheet(head(replaceIndex !== null ? "Ersetzen durch" : category ? `${CAT[category]}: hinzufügen` : "Lebensmittel suchen") + `
    <input type="search" id="q" placeholder="z. B. Haferflocken, Skyr, Banane" value="${esc(initial)}" autocomplete="off">
    <div id="res" class="list"></div>
    <div class="grid2"><button class="btn ghost wide" id="prod">${icon("barcodeScan", 16, "inl")} Markenprodukte</button>
      <button class="btn ghost wide" id="quick">${icon("fire", 16, "inl")} Nur Kalorien</button></div>
    <button class="btn ghost wide" id="newFood">${icon("plus", 16, "inl")} Eigenes Lebensmittel anlegen</button>
    ${forDraft ? `<button class="btn ghost wide" id="back">Zurück zur Mahlzeit</button>` : ""}`);
  const q = $("#q"); q.focus();
  let timer;
  const pick = (item) => {
    item.confidence = "hoch";
    if (forDraft && S.draft) {
      if (replaceIndex !== null) { const old = S.draft.items[replaceIndex]; S.draft.items[replaceIndex] = { ...item, amount_g: old.amount_g, amount_text: old.amount_text }; }
      else S.draft.items.push(item);
    } else { S.editMealId = null; S.draft = newDraft("suche", [item]); if (category) S.draft.category = category; }
    openEditor();
  };
  const show = (rows, emptyText) => {
    $("#res").innerHTML = rows.length ? rows.map((x, i) => `<button class="entry" data-r="${i}"><span><span class="n">${esc(x.name)}</span><br><span class="d">${esc(x.d)}</span></span><span class="num">${fmt(x.kcal)} kcal/100 g</span></button>`).join("")
      : `<div class="empty">${esc(emptyText)}</div>`;
    $$("[data-r]", $("#res")).forEach((b) => (b.onclick = () => pick(rows[+b.dataset.r].item)));
  };
  const run = async () => {
    const val = q.value.trim();
    if (val.length < 2) { // zuletzt/häufig gegessen
      const f = await api("frequent");
      show(f.items.slice(0, 15).map((it) => ({ name: it.name, d: `zuletzt Ø ${fmt(it.avg_g)} g`, kcal: it.per100.kcal,
        item: { name: it.name, amount_g: it.avg_g, source: it.source, food_id: it.food_id, per100: it.per100 } })), "Tippe, um zu suchen.");
      return;
    }
    const r = await api(`search?q=${encodeURIComponent(val)}`);
    show([...r.personal.map((f) => ({ name: f.name, d: `${(SRC[f.source] || [f.source])[0]}${f.brand ? `, ${f.brand}` : ""}`, kcal: f.per100.kcal,
      item: { name: f.name, amount_g: f.serving_g || 100, serving_g: f.serving_g, source: f.source, food_id: f.id, per100: f.per100, is_liquid: f.is_liquid } })),
    ...r.bls.map((b) => ({ name: b.name, d: "BLS", kcal: b.per100.kcal, item: { name: b.name, amount_g: 100, source: "bls", ref: b.code, per100: b.per100, is_liquid: b.is_liquid } }))],
    "Nichts gefunden – probiere „Markenprodukte“ oder lege es selbst an.");
  };
  q.oninput = () => { clearTimeout(timer); timer = setTimeout(run, 220); };
  run();
  $("#prod").onclick = async () => {
    const val = q.value.trim(); if (val.length < 3) { toast("Mindestens 3 Zeichen für die Produktsuche"); return; }
    $("#res").innerHTML = `<div class="note"><span class="spinner"></span> Suche in Open Food Facts …</div>`;
    try {
      const ps = await api(`products?q=${encodeURIComponent(val)}`);
      show(ps.map((p) => ({ name: p.name, d: [p.brand, p.quantity, "Open Food Facts"].filter(Boolean).join(" · "), kcal: p.per100.kcal,
        item: { name: p.brand && !p.name.includes(p.brand) ? `${p.name} (${p.brand})` : p.name, amount_g: p.serving_g || 100, serving_g: p.serving_g,
          source: "off", ref: p.barcode, barcode: p.barcode, per100: p.per100, is_liquid: p.is_liquid } })), "Keine Produkte mit Nährwerten gefunden.");
    } catch (e) { $("#res").innerHTML = `<div class="err">${esc(e.message)}</div>`; }
  };
  $("#quick").onclick = () => quickSheet(category);
  $("#newFood").onclick = () => customFoodSheet({ name: q.value.trim() }, forDraft ? pick : null);
  if (forDraft) $("#back").onclick = openEditor;
}

function quickSheet(category) {
  openSheet(head("Schnelleintrag") + `<p class="small muted">Wenn es schnell gehen muss: nur Kalorien, Makros optional.</p>
    <label class="f" for="qn">Bezeichnung</label><input type="text" id="qn" placeholder="z. B. Kantinenessen">
    <div class="grid2"><div><label class="f" for="qk">Kalorien</label><input type="number" id="qk" inputmode="decimal"></div>
      <div><label class="f" for="qp">Protein (g)</label><input type="number" id="qp" inputmode="decimal"></div>
      <div><label class="f" for="qc">Kohlenhydrate (g)</label><input type="number" id="qc" inputmode="decimal"></div>
      <div><label class="f" for="qf">Fett (g)</label><input type="number" id="qf" inputmode="decimal"></div></div>
    <button class="btn wide" id="qs">Eintragen</button>`);
  $("#qs").onclick = async () => {
    try {
      await api("quick", { method: "POST", body: { name: $("#qn").value, kcal: $("#qk").value, protein_g: $("#qp").value, carbs_g: $("#qc").value,
        fat_g: $("#qf").value, date: S.date, category: category || undefined } });
      closeSheet(); render(); toast("Eingetragen");
    } catch (e) { toast(e.message); }
  };
}

function customFoodSheet(pre = {}, onCreated = null) {
  const fields = ["kcal", "protein_g", "carbs_g", "sugar_g", "fat_g", "satfat_g", "fiber_g", "sodium_mg", "potassium_mg", "magnesium_mg",
    "calcium_mg", "iron_mg", "zinc_mg", "iodine_ug", "vitd_ug", "b12_ug", "vitc_mg"];
  openSheet(head("Eigenes Lebensmittel") + `
    <label class="f" for="fn">Name</label><input type="text" id="fn" value="${esc(pre.name || "")}">
    <div class="grid2"><div><label class="f" for="fb">Marke</label><input type="text" id="fb"></div>
    <div><label class="f" for="fs">Portion (g/ml)</label><input type="number" id="fs" inputmode="decimal"></div></div>
    <p class="small muted">Nährwerte je 100 g bzw. 100 ml (Verpackung). Kalorien sind Pflicht.</p>
    <div class="grid2">${fields.map((k) => `<div><label class="f" for="n_${k}">${NUT[k][0]} (${NUT[k][1]})</label><input type="number" step="any" inputmode="decimal" id="n_${k}"></div>`).join("")}</div>
    <label class="check"><input type="checkbox" id="fl"> Getränk</label>
    <button class="btn wide" id="fsave">Anlegen</button>`);
  $("#fsave").onclick = async () => {
    const per100 = {}; fields.forEach((k) => { const v = $("#n_" + k).value; per100[k] = v === "" ? null : parseFloat(v.replace(",", ".")); });
    if ($("#fl").checked && per100.water_ml == null) per100.water_ml = Math.max(0, 100 - (per100.carbs_g || 0) - (per100.protein_g || 0) - (per100.fat_g || 0));
    try {
      const f = await api("foods", { method: "POST", body: { name: $("#fn").value, brand: $("#fb").value || null, serving_g: parseFloat($("#fs").value) || null,
        per100, barcode: pre.barcode || null, is_liquid: $("#fl").checked } });
      const item = { name: f.name, amount_g: f.serving_g || 100, serving_g: f.serving_g, source: f.source, food_id: f.id, per100: f.per100, is_liquid: f.is_liquid, confidence: "hoch" };
      if (onCreated) onCreated(item); else { S.editMealId = null; S.draft = newDraft(pre.barcode ? "barcode" : "manuell", [item]); openEditor(); }
    } catch (e) { toast(e.message); }
  };
}

/* ---------- Erfassungsleiste ---------- */
const CAPS = { foto: ["cameraOutline", "Foto"], text: ["pencilOutline", "Text"], barcode: ["barcodeScan", "Barcode"],
  suche: ["magnify", "Suchen"], wasser: ["cupWater", "+250 ml"] };
$$(".capture .nb").forEach((b) => { const [ic, l] = CAPS[b.dataset.cap]; b.innerHTML = `${icon(ic)}<span>${l}</span>`;
  b.onclick = async () => {
    const c = b.dataset.cap;
    if (c === "foto") $("#photoInput").click();
    else if (c === "text") textSheet();
    else if (c === "barcode") barcodeSheet();
    else if (c === "suche") searchSheet(false);
    else if (c === "wasser") {
      try { const m = await api("water", { method: "POST", body: { ml: 250, date: S.date } });
        toast("250 ml Wasser eingetragen", { label: "Rückgängig", fn: async () => { await api(`meals/${m.id}`, { method: "DELETE" }); render(); } });
        if (S.view === "heute") render(); } catch (e) { toast(e.message); }
    }
  }; });

/* ---------- Woche ---------- */
async function renderWeek(v) {
  const w = await api(`week?end=${S.date}`);
  const days = w.days.map((d) => {
    const pct = d.progress.kcal || 0; const wd = new Date(d.date + "T12:00:00").toLocaleDateString("de-DE", { weekday: "short", day: "numeric" });
    return `<div class="wday"><span class="small">${esc(wd)}</span><div>${bar(pct, pct > 110 ? "var(--cc-warn)" : "var(--primary-color)", 100 * 100 / Math.max(100, pct))}
      <div class="lbl">${d.meals_count ? esc(d.day_label) + (d.estimated_targets ? " (ohne Trainingsdaten)" : "") : "nichts erfasst"}</div></div>
      <span class="num small" style="text-align:right">${d.meals_count ? `${fmt(d.totals.kcal)} kcal` : "–"}</span></div>`;
  }).join("");
  const recs = w.recommendations || [];
  const fg = w.food_groups || { grams: {} }, n = Math.max(1, w.complete_days || 0), gr = fg.grams || {};
  const grp = (label, val, target, unit, note) => `<div class="grp"><span>${esc(label)}</span><span class="num muted">${esc(val)} / ${esc(target)} ${esc(unit)}</span>
    ${bar(100 * (parseFloat(String(val).replace(",", ".")) || 0) / target, "var(--c-fiber)")}${note ? `<span class="small muted" style="grid-column:1/-1">${esc(note)}</span>` : ""}</div>`;
  const grains = (gr.vollkorn || 0) + (gr.getreide || 0);
  const groupsCard = w.complete_days ? `<section class="card"><div class="eyebrow">Lebensmittelgruppen (DGE) · ${w.complete_days} Tage</div>
    ${grp("Fischmahlzeiten", fg.fish_meals, 2, "", `davon fettreich: ${fg.fatty_fish_meals} (Ziel 1–2 pro Woche, eine fettreich)`)}
    ${grp("Hülsenfrüchte", fg.legume_meals, 1, "Mahlzeiten", "mindestens 1 pro Woche")}
    ${grp("Obst & Gemüse", fmt(((gr.obst || 0) + (gr.gemuese || 0)) / n), 550, "g/Tag", "5 Portionen à 110 g")}
    ${grp("Nüsse & Samen", fmt((gr.nuesse || 0) / n), 25, "g/Tag", "eine Handvoll")}
    ${grains ? grp("Vollkornanteil", fmt(100 * (gr.vollkorn || 0) / grains), 100, "%", "Getreideprodukte möglichst als Vollkorn") : ""}
    ${(gr.fleisch || 0) ? grp("Fleisch & Wurst", fmt(gr.fleisch || 0), 300, "g/Woche", "Obergrenze 300 g") : ""}
    <div class="src">Quelle: DGE „Gut essen und trinken“ 2024 · Zuordnung über BLS-Gruppen bzw. KI</div></section>` : "";
  const keys = ["kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "water_ml", ...MICROS];
  const avgT = (k) => { const ds = w.days.filter((d) => d.meals_count); return ds.length ? ds.reduce((s, d) => s + (d.targets[k] || 0), 0) / ds.length : null; };
  const table = w.complete_days ? `<section class="card"><div class="eyebrow">Durchschnitt pro Tag</div><table class="avg">
    <tr><td class="muted small">Nährstoff</td><td class="muted small">Ist</td><td class="muted small">Ziel</td><td class="muted small">im Ziel</td></tr>
    ${keys.map((k) => `<tr><td>${NUT[k][0]}</td><td class="num">${fmt(w.average[k])} ${NUT[k][1]}</td><td class="num muted">${fmt(avgT(k))}</td><td class="num">${w.hit_rate[k] ?? "–"} %</td></tr>`).join("")}</table></section>` : "";
  const eb = w.energy_balance || {};
  const ebCard = `<section class="card"><div class="eyebrow">Energiebilanz (Schätzung)</div>
    ${eb.ready ? `<div class="row between" style="margin-top:8px"><span>Geschätzter Verbrauch</span><b class="num">${fmt(eb.estimated_expenditure)} kcal</b></div>
      <div class="row between"><span class="muted">Ø Zufuhr · Ø Ziel</span><span class="num muted">${fmt(eb.avg_intake)} · ${fmt(eb.avg_target)} kcal</span></div>
      <div class="row between"><span class="muted">Gewichtstrend</span><span class="num muted">${eb.weight_change_kg_per_week > 0 ? "+" : ""}${fmt(eb.weight_change_kg_per_week, 2)} kg/Woche</span></div>
      ${eb.text ? `<div class="note">${esc(eb.text)}</div>` : ""}` : `<div class="small muted" style="margin-top:6px">${esc(eb.text || "")} Bisher: ${eb.days_logged || 0} Tage, ${eb.weights || 0} Gewichtswerte.</div>`}</section>`;
  v.innerHTML = `<section class="card"><div class="eyebrow">Kalorien je Tag</div><div style="margin-top:8px">${days}</div>
      <div class="small muted" style="margin-top:6px">Ausgewertet werden vollständig erfasste Tage; heute erst ab 70 % des Ziels.</div></section>
    ${recs.length ? `<section class="card"><div class="eyebrow">Was sich lohnt</div>${recs.map((r, i) => recItem(r, i)).join("")}</section>` : ""}
    ${groupsCard}${table}${ebCard}`;
  bindRecs(v, recs);
}

/* ---------- Favoriten ---------- */
async function renderFavorites(v) {
  const [favs, freq] = await Promise.all([api("favorites"), api("frequent")]);
  const favHtml = favs.length ? favs.map((f) => { const s = sumItems(f.items), sv = f.servings || 1;
    return `<div class="item"><span class="sport-ic" style="background:var(--accent-color)">${icon("starOutline", 18)}</span><div style="flex:1;min-width:0">
      <div class="row between"><span class="t">${esc(f.title)}</span><span class="num muted">${fmt(s.kcal / sv)} kcal${sv > 1 ? " / Portion" : ""}</span></div>
      <div class="c clamp">${sv > 1 ? `Rezept, ${fmt(sv)} Portionen · ` : ""}${esc(f.items.map((i) => `${i.name} ${fmt(i.amount_g)} g`).join(", "))}</div>
      <div class="row wrap" style="gap:6px;margin-top:8px"><button class="chip" data-log="${f.id}">${icon("plus", 14)}Eintragen</button>
      <button class="chip" data-adj="${f.id}">${icon("pencilOutline", 14)}Anpassen</button><button class="chip" data-del="${f.id}">${icon("deleteOutline", 14)}Löschen</button></div></div></div>`; }).join("")
    : `<div class="empty">Noch keine Favoriten. Beim Speichern „Als Favorit/Rezept merken“ wählen.</div>`;
  const freqHtml = freq.meals.length ? freq.meals.map((g, i) => `<button class="entry" data-fm="${i}"><span><span class="n">${esc(g.meal.title || g.meal.items.map((x) => x.name).join(", "))}</span><br>
      <span class="d">${g.count}× in 60 Tagen</span></span><span class="num">${fmt(sumItems(g.meal.items).kcal)} kcal</span></button>`).join("")
    : `<div class="empty">Wiederkehrende Mahlzeiten erscheinen hier automatisch.</div>`;
  v.innerHTML = `<section class="card"><div class="eyebrow">Favoriten & Rezepte</div>${favHtml}</section>
    <section class="card"><div class="eyebrow">Häufig gegessen</div><div class="list">${freqHtml}</div></section>`;
  $$("[data-log]", v).forEach((b) => (b.onclick = async () => {
    const m = await api(`favorites/${b.dataset.log}/log`, { method: "POST", body: { date: S.date, category: categoryAt(nowTime()) } });
    toast(`${m.title} eingetragen`, { label: "Rückgängig", fn: async () => { await api(`meals/${m.id}`, { method: "DELETE" }); render(); } });
  }));
  $$("[data-adj]", v).forEach((b) => (b.onclick = () => { const f = favs.find((x) => x.id === +b.dataset.adj), sv = f.servings || 1;
    S.editMealId = null; S.draft = newDraft("favorit", f.items.map((i) => ({ ...i, amount_g: i.amount_g / sv })), { title: f.title }); openEditor(); }));
  $$("[data-del]", v).forEach((b) => (b.onclick = async () => { await api(`favorites/${b.dataset.del}`, { method: "DELETE" }); render(); }));
  $$("[data-fm]", v).forEach((b) => (b.onclick = () => { const g = freq.meals[+b.dataset.fm];
    S.editMealId = null; S.draft = newDraft("favorit", g.meal.items.map((i) => ({ ...i })), { title: g.meal.title || "" }); openEditor(); }));
}

/* ---------- Einstellungen ---------- */
async function renderSettings(v) {
  const [s, st, ws] = await Promise.all([api("settings"), api("status"), api("weight_sensors").catch(() => [])]);
  S.settings = s; S.status = st;
  const p = s.profile || {}, ov = s.target_overrides || {};
  const day = S.day || (await api(`day?date=${today()}`)), src = day.profile_source || {};
  const gl = (k) => src[k] && src[k] !== "einstellung" && src[k] !== "standard" ? ` (${esc(src[k])}: ${fmt(day.profile[k], 1)})` : "";
  v.innerHTML = `
  <section class="card"><div class="eyebrow">Körperdaten</div>
    <div class="small muted" style="margin-top:4px">Leer lassen = aus Garmin bzw. Waage.</div>
    <label class="f" for="pwe">Gewicht von Sensor</label>
    <select id="pwe"><option value="">Garmin-Profil</option>${ws.map((x) => `<option value="${esc(x.entity_id)}" ${s.weight_entity === x.entity_id ? "selected" : ""}>${esc(x.name)}${x.value != null ? ` (${fmt(x.value, 1)} kg)` : ""}</option>`).join("")}</select>
    <div class="grid2">
      <div><label class="f" for="pw">Gewicht fest (kg)${gl("weight_kg")}</label><input type="number" step="0.1" id="pw" value="${p.weight_kg ?? ""}"></div>
      <div><label class="f" for="ph">Größe (cm)${gl("height_cm")}</label><input type="number" id="ph" value="${p.height_cm ?? ""}"></div>
      <div><label class="f" for="pa">Alter${gl("age")}</label><input type="number" id="pa" value="${p.age ?? ""}"></div>
      <div><label class="f" for="ps">Geschlecht</label><select id="ps"><option value="">aus Garmin</option>
        <option value="male" ${p.sex === "male" ? "selected" : ""}>männlich</option><option value="female" ${p.sex === "female" ? "selected" : ""}>weiblich</option></select></div>
      <div><label class="f" for="pbf">Körperfett (%)</label><input type="number" step="0.5" id="pbf" value="${s.body_fat_pct ?? ""}" placeholder="Schätzung ${fmt(day.energy?.body_fat_pct)}"></div>
      <div><label class="f" for="pal">Alltag ohne Sport</label><select id="pal">${[[1.3, "1,3 – viel Sitzen"], [1.4, "1,4 – Büro + etwas Bewegung"], [1.5, "1,5 – viel auf den Beinen"], [1.6, "1,6 – körperliche Arbeit"]]
        .map(([x, l]) => `<option value="${x}" ${(s.pal_base || 1.4) == x ? "selected" : ""}>${l}</option>`).join("")}</select></div>
    </div></section>
  <section class="card"><div class="eyebrow">Ernährung & Ziel</div>
    <label class="f">Ernährungsweise (für Vorschläge und KI)</label>
    <div class="row wrap" id="diet" style="gap:6px">${Object.entries(st.diets || {}).map(([k, l]) => `<button class="chip" data-d="${k}" aria-pressed="${s.diet === k}">${esc(l)}</button>`).join("")}</div>
    <label class="f">Ziel</label>
    <div class="row wrap" id="goal" style="gap:6px">${[["halten", "Gewicht halten"], ["abnehmen", "Abnehmen (−15 %)"], ["aufbauen", "Aufbauen (+10 %)"]]
      .map(([k, l]) => `<button class="chip" data-g="${k}" aria-pressed="${(s.goal || "halten") === k}">${l}</button>`).join("")}</div>
    <div class="small muted" style="margin-top:6px">Defizit/Überschuss gilt voll an Ruhe- und leichten Tagen, halb an moderaten, nicht an harten Tagen. Protein je Ziel 1,8 / 2,2 / 2,0 g/kg; nie unter 30 kcal je kg fettfreie Masse.</div>
    <div class="grid2"><div><label class="f" for="ppk">Protein g/kg (leer = nach Ziel)</label><input type="number" step="0.1" id="ppk" value="${s.protein_g_per_kg ?? ""}" placeholder="${fmt(day.protein_g_per_kg, 1)}"></div></div>
    <button class="toggle" id="ovTg" style="margin-top:12px"><span class="eyebrow">Feste Ziele (optional)</span>${icon("chevronRight", 18)}</button>
    <div id="ov" hidden><div class="grid2">${["kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "water_ml", ...MICROS].map((k) => `<div><label class="f" for="o_${k}">${NUT[k][0]} (${NUT[k][1]})</label><input type="number" step="any" id="o_${k}" value="${ov[k] ?? ""}" placeholder="${fmt(day.targets[k])}"></div>`).join("")}</div></div>
    <button class="btn wide" id="ssave">Speichern</button></section>
  <section class="card"><div class="eyebrow">Fotos & KI</div>
    <div class="note">${icon("informationOutline", 14, "inl")} Fotos werden <b>nie gespeichert</b> – weder hier noch im Browser. Sie existieren nur für die Analyse im Arbeitsspeicher.
      Analyse durch: <b>${esc(st.ai_label)}</b>. ${st.ai_provider === "gemini" ? "Dafür verlässt das Foto das Heimnetz; im kostenlosen Gemini-Kontingent darf Google Eingaben zur Verbesserung nutzen. Vollständig im Heimnetz: in der Add-on-Konfiguration „ki_anbieter: lokal“ mit eigenem KI-Server (z. B. Ollama auf einem PC)." : "Alles bleibt im Heimnetz."}</div>
    <label class="check"><input type="checkbox" id="pai" ${s.photo_ai !== false ? "checked" : ""}> Foto-Analyse erlauben</label></section>
  <section class="card"><div class="eyebrow">Lebensmitteldatenbank</div>
    <div class="small" style="margin-top:6px">BLS 4.0: ${st.bls_count ? `${fmt(st.bls_count)} Lebensmittel${st.bls.updated ? `, Stand ${esc(st.bls.updated)}` : ""}` : "nicht geladen"}. ${esc(st.bls.message || "")}</div>
    <button class="btn ghost wide" id="blsImp">BLS neu laden</button></section>
  <section class="card"><div class="eyebrow">Daten</div>
    <a class="btn ghost wide" href="api/v1/export.csv" download style="display:block;text-align:center;text-decoration:none">Alles als CSV exportieren</a>
    <button class="btn danger wide" id="wipe">Alle Daten löschen</button>
    <div class="src" style="margin-top:10px">Version ${esc(st.version)} · Nährwerte: ${esc(st.attribution)} · Produkte: Open Food Facts (ODbL) · Icons: Material Design Icons</div></section>`;
  let goal = s.goal || "halten", diet = s.diet || "pescetarisch";
  $$("#goal .chip", v).forEach((b) => (b.onclick = () => { goal = b.dataset.g; $$("#goal .chip", v).forEach((x) => x.setAttribute("aria-pressed", x === b)); }));
  $$("#diet .chip", v).forEach((b) => (b.onclick = () => { diet = b.dataset.d; $$("#diet .chip", v).forEach((x) => x.setAttribute("aria-pressed", x === b)); }));
  $("#ovTg").onclick = () => { $("#ov").hidden = !$("#ov").hidden; };
  const num = (id) => { const x = $(id).value; return x === "" ? null : parseFloat(x.replace(",", ".")); };
  const save = async () => {
    const overrides = {}; ["kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "water_ml", ...MICROS].forEach((k) => { const x = num("#o_" + k); if (x !== null) overrides[k] = x; });
    await api("settings", { method: "PUT", body: { profile: { weight_kg: num("#pw"), height_cm: num("#ph"), age: num("#pa"), sex: $("#ps").value || null },
      weight_entity: $("#pwe").value || null, goal, goal_adjust_pct: { halten: 0, abnehmen: -15, aufbauen: 10 }[goal], diet,
      pal_base: parseFloat($("#pal").value), protein_g_per_kg: num("#ppk"), body_fat_pct: num("#pbf"), target_overrides: overrides, photo_ai: $("#pai").checked } });
    S.day = null; toast("Gespeichert"); renderSettings(v);
  };
  $("#ssave").onclick = save; $("#pai").onchange = save;
  $("#blsImp").onclick = async () => { await api("bls/import", { method: "POST" }); toast("BLS wird geladen – ein bis zwei Minuten"); };
  $("#wipe").onclick = () => {
    const sh = openSheet(head("Alle Daten löschen?") + `<p>Mahlzeiten, eigene Lebensmittel, Favoriten und Einstellungen werden endgültig gelöscht. Vorher am besten als CSV exportieren.</p>
      <label class="f" for="wc">Zum Bestätigen LÖSCHEN eintippen</label><input type="text" id="wc" autocomplete="off"><button class="btn danger wide" id="wgo">Endgültig löschen</button>`);
    $("#wgo", sh).onclick = async () => { try { await api("data", { method: "DELETE", body: { confirm: $("#wc").value.trim() } }); closeSheet(); S.day = null; toast("Alle Daten gelöscht"); render(); } catch (e) { toast(e.message); } };
  };
}

/* ---------- Start ---------- */
(async function init() {
  applyTheme();
  try { const pd = window.parent.document; new MutationObserver(applyTheme).observe(pd.documentElement, { attributes: true, attributeFilter: ["style", "class"] }); } catch (e) { /* außerhalb von HA */ }
  if (window.matchMedia) window.matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", applyTheme);
  try { [S.status, S.settings] = await Promise.all([api("status"), api("settings")]); } catch (e) { /* render zeigt Fehler */ }
  render();
  document.addEventListener("visibilitychange", () => { if (!document.hidden && $("#sheet").hidden) render(); });
})();
