/* Ernährung - Web-App (Vanilla JS, läuft über Home-Assistant-Ingress). */
"use strict";

const S = {
  date: today(),
  view: "heute",
  status: null,
  settings: null,
  day: null,
  draft: null,      // Mahlzeit im Editor
  editMealId: null,
};

const CAT = { fruehstueck: "Frühstück", mittagessen: "Mittagessen", abendessen: "Abendessen",
  snack: "Snacks", sonstiges: "Sonstiges" };
const DAYTYPES = { ruhetag: "Ruhetag", leicht: "Leichter Tag", moderat: "Moderater Trainingstag",
  hart: "Harter Trainingstag", sehr_hart: "Sehr harter Trainingstag" };
const SRC = { bls: "BLS", off: "Produkt", ki: "KI-Schätzung", custom: "Eigenes" };
const NUT = {
  kcal: ["Kalorien", "kcal"], protein_g: ["Protein", "g"], carbs_g: ["Kohlenhydrate", "g"],
  sugar_g: ["davon Zucker", "g"], fat_g: ["Fett", "g"], satfat_g: ["davon gesättigt", "g"],
  fiber_g: ["Ballaststoffe", "g"], water_ml: ["Flüssigkeit", "ml"], sodium_mg: ["Natrium", "mg"],
  potassium_mg: ["Kalium", "mg"], magnesium_mg: ["Magnesium", "mg"], calcium_mg: ["Calcium", "mg"],
  iron_mg: ["Eisen", "mg"], zinc_mg: ["Zink", "mg"], vitd_ug: ["Vitamin D", "µg"],
  b12_ug: ["Vitamin B12", "µg"], vitc_mg: ["Vitamin C", "mg"],
};
const MICROS = ["sodium_mg", "potassium_mg", "magnesium_mg", "calcium_mg", "iron_mg", "zinc_mg",
  "vitd_ug", "b12_ug", "vitc_mg"];

/* ---------- Hilfen ---------- */
function today() { const d = new Date(); return iso(d); }
function iso(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; }
function nowTime() { const d = new Date(); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; }
function $(sel, root = document) { return root.querySelector(sel); }
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function fmt(v, digits) {
  if (v === null || v === undefined || isNaN(v)) return "–";
  const d = digits ?? (Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 0 : 1);
  return Number(v).toLocaleString("de-DE", { maximumFractionDigits: d, minimumFractionDigits: 0 });
}
function scale(per100, g) { const o = {}; for (const k in NUT) { const v = per100?.[k]; o[k] = v == null ? null : v * g / 100; } return o; }
function sumItems(items) {
  const t = {}; for (const k in NUT) t[k] = 0;
  for (const it of items) { const s = scale(it.per100, it.amount_g || 0); for (const k in NUT) t[k] += s[k] || 0; }
  return t;
}
function guessCategory() {
  const d = new Date(), h = d.getHours() + d.getMinutes() / 60;
  if (h >= 4 && h < 10.5) return "fruehstueck";
  if (h >= 10.5 && h < 14.5) return "mittagessen";
  if (h >= 17.5 && h < 21.5) return "abendessen";
  return "snack";
}
function dateLabel(ds) {
  const d = new Date(ds + "T12:00:00");
  const t = today();
  const y = new Date(); y.setDate(y.getDate() - 1);
  const prefix = ds === t ? "Heute, " : ds === iso(y) ? "Gestern, " : "";
  return prefix + d.toLocaleDateString("de-DE", { weekday: "short", day: "numeric", month: "short" });
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

let toastTimer;
function toast(msg, action) {
  const el = $("#toast");
  el.innerHTML = esc(msg) + (action ? ` <button class="linkish" style="color:inherit;text-decoration:underline">${esc(action.label)}</button>` : "");
  el.hidden = false;
  if (action) el.querySelector("button").onclick = () => { el.hidden = true; action.fn(); };
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, action ? 6000 : 2800);
}

/* ---------- Sheet ---------- */
function openSheet(html) {
  const sh = $("#sheet");
  sh.innerHTML = html;
  sh.hidden = false; $("#backdrop").hidden = false;
  document.body.style.overflow = "hidden";
  sh.querySelectorAll("[data-close]").forEach(b => b.onclick = closeSheet);
  sh.scrollTop = 0;
  return sh;
}
function closeSheet() {
  stopScan();
  $("#sheet").hidden = true; $("#backdrop").hidden = true;
  document.body.style.overflow = "";
}
$("#backdrop").onclick = closeSheet;
document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#sheet").hidden) closeSheet(); });
function head(title) { return `<div class="sheet-head"><h2>${esc(title)}</h2><button class="close" data-close aria-label="Schließen">×</button></div>`; }

/* ---------- Navigation ---------- */
document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => {
  S.view = b.dataset.view;
  document.querySelectorAll(".tabs button").forEach(x => x.setAttribute("aria-selected", x === b));
  render();
});
$("#prevDay").onclick = () => shiftDay(-1);
$("#nextDay").onclick = () => shiftDay(1);
$("#dateLabel").onclick = () => { const p = $("#datePicker"); p.value = S.date; p.hidden = false; p.showPicker ? p.showPicker() : p.click(); };
$("#datePicker").onchange = e => { if (e.target.value) { S.date = e.target.value; render(); } e.target.hidden = true; };
function shiftDay(n) { const d = new Date(S.date + "T12:00:00"); d.setDate(d.getDate() + n); S.date = iso(d); render(); }

async function render() {
  $("#dateLabel").textContent = dateLabel(S.date);
  const v = $("#view");
  try {
    if (S.view === "heute") await renderDay(v);
    else if (S.view === "woche") await renderWeek(v);
    else if (S.view === "favoriten") await renderFavorites(v);
    else await renderSettings(v);
  } catch (e) {
    v.innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
}

/* ---------- Tagesansicht ---------- */
function barHtml(key, val, target, kind) {
  const pct = target ? Math.min(100, 100 * (val || 0) / target) : 0;
  const over = kind === "max" && target && val > target;
  return `<div class="bar ${kind === "max" ? "max" : ""} ${over ? "over" : ""}"><span style="width:${pct}%;${kind !== "max" && !over ? `background:var(${colorVar(key)})` : ""}"></span></div>`;
}
function colorVar(k) {
  return { carbs_g: "--carbs", sugar_g: "--carbs", protein_g: "--protein", fat_g: "--fat", satfat_g: "--fat",
    fiber_g: "--fiber", water_ml: "--water" }[k] || "--ink";
}

async function renderDay(v) {
  const d = await api(`day?date=${S.date}`);
  S.day = d;
  const t = d.totals, g = d.targets, kind = d.target_kind || {};
  const eaten = t.kcal || 0, goal = g.kcal || 1;
  const width = Math.max(eaten, goal);
  const seg = k => Math.max(0, 100 * k / width);
  const over = eaten > goal ? 100 * (eaten - goal) / width : 0;
  const rest = goal - eaten;
  const tr = d.training || {};
  let trainingText;
  if (d.day_source === "manuell") trainingText = "Tagestyp manuell gesetzt.";
  else if (d.activities && d.activities.length) trainingText = `Garmin: ${tr.training_min} min Training, davon ${tr.endurance_min} min Ausdauer, Trainingslast ${fmt(tr.training_load)}.`;
  else if (d.date === today() && d.day_source === "garmin") trainingText = "Garmin: heute noch kein Training.";
  else if (d.estimated_targets) trainingText = "Für diesen Tag liegen keine Trainingsdaten vor.";
  else trainingText = "Keine Garmin-Daten – Tagestyp lässt sich manuell wählen.";

  const macroRows = ["protein_g", "carbs_g", "fat_g", "fiber_g", "water_ml", "sugar_g", "satfat_g"].map(k => `
    <div class="mrow"><span class="lbl">${NUT[k][0]}${kind[k] === "max" ? " <span class='muted small'>max.</span>" : ""}</span>
      ${barHtml(k, t[k], g[k], kind[k])}
      <span class="val num">${fmt(t[k])} / ${fmt(g[k])} ${NUT[k][1]}</span></div>`).join("");
  const micros = MICROS.map(k => `
    <div class="micro"><div class="row" style="justify-content:space-between"><span>${NUT[k][0]}</span>
      <span class="num muted">${fmt(t[k], 1)} / ${fmt(g[k])} ${NUT[k][1]}</span></div>${barHtml(k, t[k], g[k], kind[k])}</div>`).join("");
  const incomplete = Object.keys(d.incomplete || {}).length
    ? `<p class="muted small">Für ${Math.max(...Object.values(d.incomplete))} Position(en) fehlen einzelne Mikronährstoffwerte – die Summen sind dort Untergrenzen.</p>` : "";

  const cats = Object.entries(d.categories).map(([c, cat]) => `
    <section class="cat"><div class="cat-head"><h3>${esc(cat.label)}</h3><span class="muted num">${cat.kcal ? fmt(cat.kcal) + " kcal" : ""}</span></div>
    ${cat.meals.length ? cat.meals.map(m => `
      <button class="meal" data-meal="${m.id}">
        ${m.photo ? `<img src="api/v1/meals/${m.id}/photo" alt="" loading="lazy">` : ""}
        <span class="body"><span class="title">${esc(m.title || m.items.map(i => i.name).join(", "))}</span>
          <span class="items">${esc(m.time || "")} ${esc(m.items.map(i => `${i.name} ${fmt(i.amount_g)} g`).join(", "))}</span></span>
        <span class="kcal num">${fmt(m.totals.kcal)} kcal</span>
      </button>`).join("") : `<div class="empty">Noch nichts eingetragen.</div>`}
    </section>`).join("");

  v.innerHTML = `
    <div class="daytype"><strong>${esc(d.day_label)}</strong>
      <button id="dtBtn">Tagestyp ändern</button></div>
    <div class="muted small">${esc(trainingText)}</div>
    <div class="tank-head"><span class="big num">${fmt(eaten)}</span><span class="of num">von ${fmt(goal)} kcal</span></div>
    <div class="tank" role="img" aria-label="${fmt(eaten)} von ${fmt(goal)} Kilokalorien">
      <span class="c" style="width:${seg((t.carbs_g || 0) * 4)}%"></span>
      <span class="p" style="width:${seg((t.protein_g || 0) * 4)}%"></span>
      <span class="f" style="width:${seg((t.fat_g || 0) * 9)}%"></span>
      ${over ? `<span class="over" style="width:${over}%"></span>` : ""}
    </div>
    <div class="row" style="justify-content:space-between">
      <div class="tank-legend"><span><i style="background:var(--carbs)"></i>KH</span><span><i style="background:var(--protein)"></i>Protein</span><span><i style="background:var(--fat)"></i>Fett</span></div>
      <span class="small num ${rest < 0 ? "" : "muted"}" style="flex:none">${rest >= 0 ? `noch ${fmt(rest)} kcal` : `${fmt(-rest)} kcal über Ziel`}</span>
    </div>
    <div class="macros">${macroRows}</div>
    <h2>Mikronährstoffe</h2>
    <div class="micros">${micros}</div>
    ${incomplete}
    ${cats}
    <details class="more"><summary>Wie das Ziel zustande kommt</summary>
      <p class="small">Grundumsatz ${fmt(d.energy?.bmr)} kcal (Mifflin-St Jeor, ${fmt(d.profile?.weight_kg)} kg) × ${fmt(d.energy?.pal, 2)} Alltag
      = ${fmt(d.energy?.base)} kcal, dazu ${fmt(d.energy?.exercise)} kcal Training (Garmin, netto).
      ${d.energy?.goal_pct_applied ? `Ziel „${esc(d.energy.goal)}“: ${fmt(d.energy.goal_pct_applied)} %. ` : ""}
      Kohlenhydrate ${fmt(g.carbs_g)} g ≈ ${fmt(g.carbs_g / d.profile.weight_kg, 1)} g/kg für „${esc(d.day_label)}“, Protein ${fmt(g.protein_g / d.profile.weight_kg, 1)} g/kg.
      Mikronährstoffe: DGE-Referenzwerte. Die Werte sind Orientierung, keine medizinische Beratung.</p>
      ${d.profile_source && Object.values(d.profile_source).includes("standard") ? `<p class="small err">Körperdaten fehlen teilweise – bitte unter Einstellungen eintragen.</p>` : ""}
    </details>`;
  $("#dtBtn").onclick = () => dayTypeSheet(d);
  v.querySelectorAll("[data-meal]").forEach(b => b.onclick = () => editMeal(+b.dataset.meal));
}

function dayTypeSheet(d) {
  const sh = openSheet(head("Tagestyp") + `
    <p class="small muted">Bestimmt die Kohlenhydrat-Ziele. Normalerweise aus den Garmin-Aktivitäten des Tages.</p>
    <div class="list">${Object.entries(DAYTYPES).map(([k, l]) => `<button class="entry" data-t="${k}"><span class="n">${l}</span><span class="d">${k === d.day_type ? "aktiv" : ""}</span></button>`).join("")}
    <button class="entry" data-t=""><span class="n">Automatisch (Garmin)</span></button></div>`);
  sh.querySelectorAll("[data-t]").forEach(b => b.onclick = async () => {
    await api("settings", { method: "PUT", body: { day_type_override: b.dataset.t ? { date: S.date, type: b.dataset.t } : null } });
    closeSheet(); render();
  });
}

/* ---------- Editor ---------- */
function newDraft(method, items = [], extra = {}) {
  return Object.assign({ date: S.date, time: S.date === today() ? nowTime() : "12:00", category: guessCategory(),
    title: "", method, items, photo: null, hint: "" }, extra);
}

function openEditor() {
  const dr = S.draft;
  const editing = !!S.editMealId;
  const sh = openSheet(head(editing ? "Mahlzeit bearbeiten" : "Mahlzeit prüfen") + `
    ${dr.photo ? `<img class="photo-preview" src="${dr.photo}" alt="Foto der Mahlzeit">` : dr.photoUrl ? `<img class="photo-preview" src="${dr.photoUrl}" alt="">` : ""}
    ${dr.hint ? `<div class="hint">${esc(dr.hint)}</div>` : ""}
    <div id="items"></div>
    <button class="linkish" id="addItem">+ Lebensmittel hinzufügen</button>
    <div class="sum num" id="sum"></div>
    <label class="f">Mahlzeit</label>
    <div class="chips" id="cats">${Object.entries(CAT).map(([k, l]) => `<button class="chip" data-c="${k}" aria-pressed="${k === dr.category}">${l}</button>`).join("")}</div>
    <div class="grid2">
      <div><label class="f" for="mTitle">Titel</label><input type="text" id="mTitle" value="${esc(dr.title)}" placeholder="optional"></div>
      <div><label class="f" for="mTime">Uhrzeit</label><input type="time" id="mTime" value="${esc(dr.time)}"></div>
    </div>
    <label class="row small" style="margin-top:12px;gap:8px"><input type="checkbox" id="mFav" style="flex:none;width:auto"> Als Favorit merken</label>
    <button class="btn wide" id="save">${editing ? "Änderungen speichern" : "Speichern"}</button>
    ${editing ? `<button class="btn danger wide" id="del">Mahlzeit löschen</button>` : ""}`);
  renderItems();
  sh.querySelectorAll("#cats .chip").forEach(b => b.onclick = () => {
    dr.category = b.dataset.c; sh.querySelectorAll("#cats .chip").forEach(x => x.setAttribute("aria-pressed", x === b));
  });
  $("#mTitle").oninput = e => dr.title = e.target.value;
  $("#mTime").oninput = e => dr.time = e.target.value;
  $("#addItem").onclick = () => searchSheet(true);
  $("#save").onclick = saveDraft;
  if (editing) $("#del").onclick = async () => {
    const id = S.editMealId;
    await api(`meals/${id}`, { method: "DELETE" });
    closeSheet(); S.editMealId = null; render(); toast("Mahlzeit gelöscht");
  };
}

function renderItems() {
  const dr = S.draft, box = $("#items");
  if (!box) return;
  if (!dr.items.length) box.innerHTML = `<div class="empty">Keine Lebensmittel – füge eins hinzu.</div>`;
  else box.innerHTML = dr.items.map((it, i) => {
    const kc = (it.per100?.kcal || 0) * (it.amount_g || 0) / 100;
    const p = it.per100 || {};
    const conf = it.confidence === "niedrig" ? ", Menge unsicher" : "";
    const match = it.match_name && it.match_name !== it.name ? `${SRC[it.source] || it.source}: ${it.match_name}` : (SRC[it.source] || it.source);
    return `<div class="item" data-i="${i}">
      <div class="item-top"><span class="name"><input type="text" value="${esc(it.name)}" aria-label="Name" data-f="name"></span>
        <span class="src ${esc(it.source)}">${esc(SRC[it.source] || it.source)}</span>
        <button class="close" data-rm aria-label="Entfernen" style="width:32px;height:32px;font-size:1.2rem">×</button></div>
      <div class="amount">
        <button class="step" data-step="-" aria-label="weniger">−</button>
        <input type="number" inputmode="decimal" min="0" step="any" value="${Math.round((it.amount_g || 0) * 10) / 10}" data-f="amount" aria-label="Menge">
        <span>${it.is_liquid ? "ml" : "g"}</span>
        <button class="step" data-step="+" aria-label="mehr">+</button>
        <span class="kc num">${fmt(kc)} kcal</span>
      </div>
      <div class="meta">${esc([it.amount_text, match].filter(Boolean).join(", "))}${conf}<br>
        <span class="num">je 100 g: ${fmt(p.kcal)} kcal, ${fmt(p.protein_g)} g P, ${fmt(p.carbs_g)} g KH, ${fmt(p.fat_g)} g F</span></div>
      ${(it.candidates && it.candidates.length) || it.estimate ? `<button class="linkish" data-alt>Andere Zuordnung</button><div class="alts" hidden></div>` : `<button class="linkish" data-replace>Ersetzen</button>`}
    </div>`;
  }).join("");
  box.querySelectorAll(".item").forEach(el => {
    const i = +el.dataset.i, it = dr.items[i];
    el.querySelector("[data-f=name]").oninput = e => { it.name = e.target.value; };
    const amt = el.querySelector("[data-f=amount]");
    amt.oninput = () => { it.amount_g = parseFloat(amt.value.replace(",", ".")) || 0; updateItemKcal(el, it); updateSum(); };
    el.querySelectorAll("[data-step]").forEach(b => b.onclick = () => {
      const stepSize = it.amount_g >= 200 ? 25 : it.amount_g >= 50 ? 10 : 5;
      it.amount_g = Math.max(0, Math.round(((it.amount_g || 0) + (b.dataset.step === "+" ? stepSize : -stepSize)) / stepSize) * stepSize);
      amt.value = it.amount_g; updateItemKcal(el, it); updateSum();
    });
    el.querySelector("[data-rm]").onclick = () => { dr.items.splice(i, 1); renderItems(); };
    const alt = el.querySelector("[data-alt]");
    if (alt) alt.onclick = () => {
      const box2 = el.querySelector(".alts");
      box2.hidden = !box2.hidden;
      const opts = (it.candidates || []).map((c, j) => `<button data-c="${j}">${esc(c.name)} <span class="muted num">${fmt(c.kcal)} kcal/100 g</span></button>`);
      if (it.estimate && it.source !== "ki") opts.push(`<button data-est>KI-Schätzung verwenden <span class="muted num">${fmt(it.estimate.kcal)} kcal/100 g</span></button>`);
      opts.push(`<button data-search>In der Datenbank suchen …</button>`);
      box2.innerHTML = opts.join("");
      box2.querySelectorAll("[data-c]").forEach(b => b.onclick = () => {
        const c = it.candidates[+b.dataset.c];
        Object.assign(it, { source: c.source, ref: c.ref, food_id: null, per100: c.per100, match_name: c.name });
        renderItems(); updateSum();
      });
      const est = box2.querySelector("[data-est]");
      if (est) est.onclick = () => { Object.assign(it, { source: "ki", ref: null, food_id: null, per100: it.estimate, match_name: null }); renderItems(); updateSum(); };
      box2.querySelector("[data-search]").onclick = () => searchSheet(true, i, it.name);
    };
    const rep = el.querySelector("[data-replace]");
    if (rep) rep.onclick = () => searchSheet(true, i, it.name);
  });
  updateSum();
}
function updateItemKcal(el, it) { el.querySelector(".kc").textContent = `${fmt((it.per100?.kcal || 0) * (it.amount_g || 0) / 100)} kcal`; }
function updateSum() {
  const s = sumItems(S.draft.items), el = $("#sum");
  if (el) el.innerHTML = `<span>Summe</span><span>${fmt(s.kcal)} kcal, ${fmt(s.protein_g)} g P, ${fmt(s.carbs_g)} g KH, ${fmt(s.fat_g)} g F</span>`;
}

async function saveDraft() {
  const dr = S.draft, btn = $("#save");
  if (!dr.items.length) { toast("Mindestens ein Lebensmittel eintragen"); return; }
  btn.disabled = true;
  const body = {
    date: dr.date, time: dr.time, category: dr.category, title: dr.title || null, method: dr.method,
    items: dr.items.map(it => ({ name: it.name, amount_g: it.amount_g, amount_text: it.amount_text, source: it.source,
      ref: it.ref, food_id: it.food_id, per100: it.per100, confidence: it.confidence })),
    save_favorite: $("#mFav")?.checked, favorite_title: dr.title || null,
  };
  try {
    if (S.editMealId) {
      await api(`meals/${S.editMealId}`, { method: "PUT", body });
      if (body.save_favorite) await api("favorites", { method: "POST", body: { title: dr.title || "Favorit", category: dr.category, items: body.items } });
      toast("Gespeichert");
    } else {
      if (dr.photo && S.settings?.keep_photos !== false) body.photo = dr.photo;
      if (dr.ai) body.ai = dr.ai;
      const m = await api("meals", { method: "POST", body });
      toast(`${CAT[m.category]} gespeichert`, { label: "Rückgängig", fn: async () => { await api(`meals/${m.id}`, { method: "DELETE" }); render(); } });
    }
    S.editMealId = null; S.draft = null;
    closeSheet(); S.view = "heute"; syncTabs(); render();
  } catch (e) { toast(e.message); btn.disabled = false; }
}
function syncTabs() { document.querySelectorAll(".tabs button").forEach(x => x.setAttribute("aria-selected", x.dataset.view === S.view)); }

async function editMeal(id) {
  const m = await api(`meals/${id}`);
  S.editMealId = id;
  S.draft = { date: m.date, time: m.time || "", category: m.category, title: m.title || "", method: m.method,
    items: m.items.map(it => ({ ...it, ref: null })), photoUrl: m.photo ? `api/v1/meals/${id}/photo` : null, hint: "" };
  openEditor();
}

/* ---------- Text ---------- */
async function textSheet() {
  const sh = openSheet(head("Was hast du gegessen?") + `
    <textarea id="txt" placeholder="z. B. 2 Rühreier mit einer Scheibe Vollkornbrot und ein Kaffee mit Milch"></textarea>
    <button class="btn wide" id="go">Analysieren</button>
    <div id="out"></div>
    <h2>Häufig</h2><div class="chips" id="freq"><span class="spinner"></span></div>`);
  const ta = $("#txt"); ta.focus();
  ta.onkeydown = e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) $("#go").click(); };
  $("#go").onclick = async () => {
    const text = ta.value.trim();
    if (!text) { ta.focus(); return; }
    await runAnalyze({ text }, "text");
  };
  try {
    const f = await api("frequent");
    $("#freq").innerHTML = f.items.length ? f.items.slice(0, 12).map((it, i) => `<button class="chip" data-f="${i}">${esc(it.name)} ${fmt(it.avg_g)} g</button>`).join("")
      : `<span class="muted small">Erscheint, sobald du ein paar Mahlzeiten erfasst hast.</span>`;
    $("#freq").querySelectorAll("[data-f]").forEach(b => b.onclick = () => {
      const it = f.items[+b.dataset.f];
      S.draft = newDraft("manuell", [{ name: it.name, amount_g: it.avg_g, source: it.source, food_id: it.food_id, per100: it.per100 }]);
      S.editMealId = null; openEditor();
    });
  } catch (e) { $("#freq").innerHTML = ""; }
}

async function runAnalyze(payload, method, photo) {
  const out = $("#out") || $("#sheet");
  const btn = $("#go"); if (btn) btn.disabled = true;
  const box = document.createElement("div");
  box.className = "hint"; box.innerHTML = `<span class="spinner"></span> Wird analysiert … (meist 5–20 Sekunden)`;
  out.appendChild(box);
  try {
    const r = await api("analyze", { method: "POST", body: payload });
    S.editMealId = null;
    S.draft = newDraft(method, r.items, { title: r.title || "", hint: r.hint || "", photo: photo || null,
      category: r.category || guessCategory(),
      ai: { model: r.model, text: payload.text || null } });
    if (!r.items.length) S.draft.hint = "Keine Lebensmittel erkannt – füge sie manuell hinzu.";
    openEditor();
  } catch (e) {
    box.className = "err"; box.textContent = e.message;
    if (btn) btn.disabled = false;
  }
}

/* ---------- Foto ---------- */
function downscale(file, max = 1280, quality = 0.82) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const r = Math.min(1, max / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * r); c.height = Math.round(img.height * r);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(img.src);
      resolve({ dataUrl: c.toDataURL("image/jpeg", quality), canvas: c }); // Neu-Kodierung entfernt EXIF/GPS
    };
    img.onerror = () => reject(new Error("Bild konnte nicht gelesen werden"));
    img.src = URL.createObjectURL(file);
  });
}
$("#photoInput").onchange = async e => {
  const file = e.target.files[0]; e.target.value = "";
  if (!file) return;
  const { dataUrl } = await downscale(file);
  openSheet(head("Foto") + `<img class="photo-preview" src="${dataUrl}" alt="">
    <label class="f" for="ptxt">Ergänzung (optional)</label>
    <input type="text" id="ptxt" placeholder="z. B. mit Olivenöl, halbe Portion gegessen">
    <button class="btn wide" id="go">Analysieren</button><div id="out"></div>`);
  $("#go").onclick = () => runAnalyze({ image: dataUrl, mime: "image/jpeg", text: $("#ptxt").value }, "foto", dataUrl);
  if (S.settings?.photo_ai === false) { $("#out").innerHTML = `<div class="err">Foto-Analyse ist in den Einstellungen ausgeschaltet.</div>`; $("#go").disabled = true; }
};

/* ---------- Barcode ---------- */
let scanCtl = null;
function stopScan() { try { scanCtl && scanCtl.reset(); } catch (e) { /* egal */ } scanCtl = null; }

function barcodeSheet() {
  const live = window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.ZXing;
  openSheet(head("Barcode") + `
    ${live ? `<video class="scan" id="vid" playsinline muted></video><p class="small muted">Barcode ins Bild halten.</p>` : ""}
    <button class="btn wide ${live ? "ghost" : ""}" id="snap">Barcode fotografieren</button>
    <label class="f" for="code">Nummer eintippen</label>
    <div class="row"><input type="text" id="code" inputmode="numeric" pattern="[0-9]*" placeholder="EAN, 8 oder 13 Ziffern">
    <button class="btn" id="look" style="flex:none">Suchen</button></div>
    <div id="out"></div>`);
  $("#snap").onclick = () => $("#barcodeInput").click();
  $("#look").onclick = () => lookupBarcode($("#code").value);
  if (live) {
    try {
      const hints = new Map();
      hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, [ZXing.BarcodeFormat.EAN_13, ZXing.BarcodeFormat.EAN_8,
        ZXing.BarcodeFormat.UPC_A, ZXing.BarcodeFormat.UPC_E]);
      scanCtl = new ZXing.BrowserMultiFormatReader(hints);
      scanCtl.decodeOnceFromConstraints({ video: { facingMode: "environment" } }, "vid")
        .then(res => { stopScan(); lookupBarcode(res.getText()); })
        .catch(() => { /* abgebrochen */ });
    } catch (e) { /* Kamera nicht verfügbar - Foto-Weg bleibt */ }
  }
}
$("#barcodeInput").onchange = async e => {
  const file = e.target.files[0]; e.target.value = "";
  if (!file) return;
  const out = $("#out");
  try {
    const { canvas } = await downscale(file, 1600, 0.9);
    const code = decodeCanvas(canvas);
    if (!code) throw new Error("Kein Barcode erkannt – näher ran, gerade halten, oder Nummer eintippen.");
    $("#code").value = code;
    lookupBarcode(code);
  } catch (err) { if (out) out.innerHTML = `<div class="err">${esc(err.message)}</div>`; }
};
function decodeCanvas(canvas) {
  if (!window.ZXing) return null;
  const reader = new ZXing.MultiFormatReader();
  const hints = new Map();
  hints.set(ZXing.DecodeHintType.TRY_HARDER, true);
  hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, [ZXing.BarcodeFormat.EAN_13, ZXing.BarcodeFormat.EAN_8,
    ZXing.BarcodeFormat.UPC_A, ZXing.BarcodeFormat.UPC_E]);
  reader.setHints(hints);
  // Original und um 90° gedreht versuchen
  for (const rot of [0, 90]) {
    let c = canvas;
    if (rot) { c = document.createElement("canvas"); c.width = canvas.height; c.height = canvas.width;
      const ctx = c.getContext("2d"); ctx.translate(c.width, 0); ctx.rotate(Math.PI / 2); ctx.drawImage(canvas, 0, 0); }
    try {
      const src = new ZXing.HTMLCanvasElementLuminanceSource(c);
      const bmp = new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(src));
      return reader.decode(bmp).getText();
    } catch (e) { /* nächster Versuch */ }
  }
  return null;
}
async function lookupBarcode(code) {
  code = String(code || "").replace(/\D/g, "");
  const out = $("#out");
  if (!code) return;
  out.innerHTML = `<div class="hint"><span class="spinner"></span> Suche ${esc(code)} …</div>`;
  try {
    const f = await api("barcode", { method: "POST", body: { code } });
    const amount = f.serving_g || 100;
    S.editMealId = null;
    S.draft = newDraft("barcode", [{ name: f.name, amount_g: amount, amount_text: f.serving_label || "", source: f.source,
      food_id: f.id, per100: f.per100, is_liquid: f.is_liquid, confidence: "hoch" }]);
    openEditor();
  } catch (e) {
    out.innerHTML = `<div class="err">${esc(e.message)}</div><button class="btn ghost wide" id="newFood">Produkt selbst anlegen</button>`;
    $("#newFood").onclick = () => customFoodSheet({ barcode: code });
  }
}

/* ---------- Suche ---------- */
function searchSheet(forDraft = false, replaceIndex = null, initial = "") {
  const sh = openSheet(head(replaceIndex !== null ? "Ersetzen durch" : "Lebensmittel suchen") + `
    <input type="search" id="q" placeholder="z. B. Haferflocken, Skyr, Banane" value="${esc(initial)}" autocomplete="off">
    <div id="res" class="list"></div>
    <button class="btn ghost wide" id="newFood">Eigenes Lebensmittel anlegen</button>
    ${forDraft ? `<button class="btn ghost wide" id="back">Zurück zur Mahlzeit</button>` : ""}`);
  const q = $("#q"); q.focus();
  let timer;
  const run = async () => {
    const val = q.value.trim();
    if (val.length < 2) { $("#res").innerHTML = ""; return; }
    const r = await api(`search?q=${encodeURIComponent(val)}`);
    const rows = [
      ...r.personal.map(f => ({ name: f.name, d: `${SRC[f.source] || f.source}${f.brand ? ", " + f.brand : ""}`, kcal: f.per100.kcal,
        item: { name: f.name, amount_g: f.serving_g || 100, source: f.source, food_id: f.id, per100: f.per100, is_liquid: f.is_liquid } })),
      ...r.bls.map(b => ({ name: b.name, d: "BLS", kcal: b.per100.kcal,
        item: { name: b.name, amount_g: 100, source: "bls", ref: b.code, per100: b.per100, is_liquid: b.is_liquid } })),
    ];
    $("#res").innerHTML = rows.length ? rows.map((x, i) => `<button class="entry" data-r="${i}"><span><span class="n">${esc(x.name)}</span><br><span class="d">${esc(x.d)}</span></span><span class="num muted">${fmt(x.kcal)} kcal/100 g</span></button>`).join("")
      : `<div class="empty">Nichts gefunden. ${S.status?.bls_count ? "" : "Die BLS-Datenbank ist noch nicht geladen (Einstellungen)."}</div>`;
    $("#res").querySelectorAll("[data-r]").forEach(b => b.onclick = () => pick(rows[+b.dataset.r].item));
  };
  q.oninput = () => { clearTimeout(timer); timer = setTimeout(run, 220); };
  if (initial) run();
  const pick = item => {
    item.confidence = "hoch";
    if (forDraft && S.draft) {
      if (replaceIndex !== null) {
        const old = S.draft.items[replaceIndex];
        S.draft.items[replaceIndex] = { ...item, amount_g: old.amount_g, amount_text: old.amount_text };
      } else S.draft.items.push(item);
    } else { S.editMealId = null; S.draft = newDraft("suche", [item]); }
    openEditor();
  };
  $("#newFood").onclick = () => customFoodSheet({ name: q.value.trim() }, forDraft ? pick : null);
  if (forDraft) $("#back").onclick = openEditor;
}

function customFoodSheet(pre = {}, onCreated = null) {
  const fields = ["kcal", "protein_g", "carbs_g", "sugar_g", "fat_g", "satfat_g", "fiber_g", "sodium_mg",
    "potassium_mg", "magnesium_mg", "calcium_mg", "iron_mg", "zinc_mg", "vitd_ug", "b12_ug", "vitc_mg"];
  const sh = openSheet(head("Eigenes Lebensmittel") + `
    <label class="f" for="fn">Name</label><input type="text" id="fn" value="${esc(pre.name || "")}">
    <div class="grid2"><div><label class="f" for="fb">Marke</label><input type="text" id="fb"></div>
    <div><label class="f" for="fs">Portion (g/ml)</label><input type="number" id="fs" inputmode="decimal"></div></div>
    <p class="small muted">Nährwerte je 100 g bzw. 100 ml (von der Verpackung). Kalorien sind Pflicht.</p>
    <div class="grid2">${fields.map(k => `<div><label class="f" for="n_${k}">${NUT[k][0]} (${NUT[k][1]})</label><input type="number" step="any" inputmode="decimal" id="n_${k}"></div>`).join("")}</div>
    <label class="row small" style="margin-top:12px;gap:8px"><input type="checkbox" id="fl" style="flex:none;width:auto"> Getränk</label>
    <button class="btn wide" id="fsave">Anlegen</button>`);
  $("#fsave").onclick = async () => {
    const per100 = {};
    fields.forEach(k => { const v = $("#n_" + k).value; per100[k] = v === "" ? null : parseFloat(v.replace(",", ".")); });
    if ($("#fl").checked && per100.water_ml == null) per100.water_ml = Math.max(0, 100 - (per100.carbs_g || 0) - (per100.protein_g || 0) - (per100.fat_g || 0));
    try {
      const f = await api("foods", { method: "POST", body: { name: $("#fn").value, brand: $("#fb").value || null,
        serving_g: parseFloat($("#fs").value) || null, per100, barcode: pre.barcode || null, is_liquid: $("#fl").checked } });
      const item = { name: f.name, amount_g: f.serving_g || 100, source: f.source, food_id: f.id, per100: f.per100, is_liquid: f.is_liquid, confidence: "hoch" };
      if (onCreated) onCreated(item);
      else { S.editMealId = null; S.draft = newDraft(pre.barcode ? "barcode" : "manuell", [item]); openEditor(); }
    } catch (e) { toast(e.message); }
  };
}

/* ---------- Erfassungsleiste ---------- */
document.querySelectorAll(".capture button").forEach(b => b.onclick = async () => {
  const c = b.dataset.cap;
  if (c === "foto") $("#photoInput").click();
  else if (c === "text") textSheet();
  else if (c === "barcode") barcodeSheet();
  else if (c === "suche") searchSheet(false);
  else if (c === "wasser") {
    try {
      const m = await api("water", { method: "POST", body: { ml: 250, date: S.date } });
      toast("250 ml Wasser eingetragen", { label: "Rückgängig", fn: async () => { await api(`meals/${m.id}`, { method: "DELETE" }); render(); } });
      if (S.view === "heute") render();
    } catch (e) { toast(e.message); }
  }
});

/* ---------- Woche ---------- */
async function renderWeek(v) {
  const w = await api(`week?end=${S.date}`);
  const rows = w.days.map(d => {
    const pct = d.progress.kcal || 0;
    const wd = new Date(d.date + "T12:00:00").toLocaleDateString("de-DE", { weekday: "short", day: "numeric" });
    return `<div class="wday"><span class="small">${wd}</span>
      <div><div class="bar"><span style="width:${Math.min(100, pct)}%;background:var(${pct > 110 ? "--warn" : "--ink"})"></span></div>
      <span class="tag">${d.meals_count ? esc(d.day_label) + (d.estimated_targets ? " (ohne Trainingsdaten)" : "") : "nichts erfasst"}</span></div>
      <span class="num small" style="text-align:right">${d.meals_count ? fmt(d.totals.kcal) + " kcal" : "–"}</span></div>`;
  }).join("");
  const keys = ["kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "water_ml", ...MICROS];
  const avgTarget = k => { const ds = w.days.filter(d => d.meals_count); return ds.length ? ds.reduce((s, d) => s + (d.targets[k] || 0), 0) / ds.length : null; };
  const table = w.complete_days ? `<table class="avg"><tr><td class="muted small">Ø pro Tag</td><td class="muted small">Ist</td><td class="muted small">Ziel</td><td class="muted small">im Ziel</td></tr>
    ${keys.map(k => `<tr><td>${NUT[k][0]}</td><td class="num">${fmt(w.average[k])} ${NUT[k][1]}</td><td class="num muted">${fmt(avgTarget(k))}</td><td class="num">${w.hit_rate[k]} %</td></tr>`).join("")}</table>` : "";
  const gaps = w.gaps.length ? w.gaps.map(g => `<div class="gap"><strong>${esc(g.label)}</strong> ${g.issue === "zu_hoch" ? "über der Grenze" : "unter 70 % des Ziels"} an ${g.days} von ${g.of} Tagen</div>`).join("")
    : (w.complete_days >= 3 ? `<div class="good">Keine wiederkehrenden Lücken in den erfassten Tagen.</div>` : "");
  const f = w.fueling;
  const fuel = [];
  if (f.hard_days) fuel.push(`<div class="${f.carbs_pct_hard_days >= 90 ? "good" : "gap"}">Kohlenhydrate an harten Tagen: ${f.carbs_pct_hard_days} % des Ziels (${f.hard_days} Tag${f.hard_days > 1 ? "e" : ""})</div>`);
  if (f.protein_pct_training_days != null) fuel.push(`<div class="${f.protein_pct_training_days >= 90 ? "good" : "gap"}">Protein an Trainingstagen: ${f.protein_pct_training_days} % des Ziels</div>`);
  v.innerHTML = `<h2 style="margin-top:4px">Kalorien je Tag</h2><div class="week">${rows}</div>
    ${w.complete_days ? "" : `<p class="empty">Noch zu wenig erfasste Tage für Durchschnitte.</p>`}
    ${gaps || fuel.length ? `<h2>Auffälligkeiten</h2>${gaps}${fuel.join("")}` : ""}
    ${table ? `<h2>Durchschnitt (${w.complete_days} Tage)</h2>${table}` : ""}
    <p class="small muted">Gezählt werden Tage mit Einträgen; der heutige Tag erst ab 70 % der Ziel-Kalorien.</p>`;
}

/* ---------- Favoriten ---------- */
async function renderFavorites(v) {
  const [favs, freq] = await Promise.all([api("favorites"), api("frequent")]);
  const favHtml = favs.length ? favs.map(f => {
    const s = sumItems(f.items);
    return `<div class="item"><div class="item-top"><span class="name">${esc(f.title)}</span><span class="num muted">${fmt(s.kcal)} kcal</span></div>
      <div class="meta">${esc(f.items.map(i => `${i.name} ${fmt(i.amount_g)} g`).join(", "))}</div>
      <div class="row" style="margin-top:8px"><button class="btn" data-log="${f.id}">Eintragen</button>
      <button class="btn ghost" data-adj="${f.id}">Anpassen</button><button class="btn ghost" data-del="${f.id}" style="flex:none">Löschen</button></div></div>`;
  }).join("") : `<p class="empty">Noch keine Favoriten. Beim Speichern einer Mahlzeit „Als Favorit merken“ wählen.</p>`;
  const freqHtml = freq.meals.length ? freq.meals.map((g, i) => {
    const s = sumItems(g.meal.items);
    return `<button class="entry" data-fm="${i}"><span><span class="n">${esc(g.meal.title || g.meal.items.map(x => x.name).join(", "))}</span><br>
      <span class="d">${g.count}× in 60 Tagen</span></span><span class="num muted">${fmt(s.kcal)} kcal</span></button>`;
  }).join("") : `<p class="empty">Wiederkehrende Mahlzeiten erscheinen hier automatisch.</p>`;
  v.innerHTML = `<h2 style="margin-top:4px">Favoriten</h2>${favHtml}<h2>Häufig gegessen</h2><div class="list">${freqHtml}</div>`;
  v.querySelectorAll("[data-log]").forEach(b => b.onclick = async () => {
    const m = await api(`favorites/${b.dataset.log}/log`, { method: "POST", body: { date: S.date, category: guessCategory() } });
    toast(`${m.title} eingetragen`, { label: "Rückgängig", fn: async () => { await api(`meals/${m.id}`, { method: "DELETE" }); render(); } });
  });
  v.querySelectorAll("[data-adj]").forEach(b => b.onclick = () => {
    const f = favs.find(x => x.id === +b.dataset.adj);
    S.editMealId = null;
    S.draft = newDraft("favorit", f.items.map(i => ({ ...i })), { title: f.title, category: guessCategory() });
    openEditor();
  });
  v.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => { await api(`favorites/${b.dataset.del}`, { method: "DELETE" }); render(); });
  v.querySelectorAll("[data-fm]").forEach(b => b.onclick = () => {
    const g = freq.meals[+b.dataset.fm];
    S.editMealId = null;
    S.draft = newDraft("favorit", g.meal.items.map(i => ({ ...i })), { title: g.meal.title || "", category: guessCategory() });
    openEditor();
  });
}

/* ---------- Einstellungen ---------- */
async function renderSettings(v) {
  const [s, st] = await Promise.all([api("settings"), api("status")]);
  S.settings = s; S.status = st;
  const p = s.profile || {};
  const ov = s.target_overrides || {};
  const day = S.day || await api(`day?date=${today()}`);
  const src = day.profile_source || {};
  const gl = k => src[k] === "garmin" ? ` <span class="muted small">(Garmin: ${fmt(day.profile[k])})</span>` : "";
  v.innerHTML = `
    <h2 style="margin-top:4px">Körperdaten</h2>
    <p class="small muted">Leer lassen, um Werte aus Garmin zu übernehmen.</p>
    <div class="grid2">
      <div><label class="f" for="pw">Gewicht (kg)${gl("weight_kg")}</label><input type="number" step="0.1" id="pw" value="${p.weight_kg ?? ""}"></div>
      <div><label class="f" for="ph">Größe (cm)${gl("height_cm")}</label><input type="number" id="ph" value="${p.height_cm ?? ""}"></div>
      <div><label class="f" for="pa">Alter${gl("age")}</label><input type="number" id="pa" value="${p.age ?? ""}"></div>
      <div><label class="f" for="ps">Geschlecht</label><select id="ps"><option value="">Garmin</option>
        <option value="male" ${p.sex === "male" ? "selected" : ""}>männlich</option><option value="female" ${p.sex === "female" ? "selected" : ""}>weiblich</option></select></div>
    </div>
    <h2>Ziel</h2>
    <div class="chips" id="goal">${[["halten", "Gewicht halten"], ["abnehmen", "Abnehmen (−15 %)"], ["aufbauen", "Aufbauen (+10 %)"]].map(([k, l]) =>
      `<button class="chip" data-g="${k}" aria-pressed="${(s.goal || "halten") === k}">${l}</button>`).join("")}</div>
    <p class="small muted">Defizit bzw. Überschuss gilt voll an Ruhe- und leichten Tagen, halb an moderaten und nicht an harten Tagen.</p>
    <div class="grid2">
      <div><label class="f" for="pal">Alltagsaktivität (PAL ohne Sport)</label><select id="pal">
        ${[[1.3, "1,3 – viel Sitzen"], [1.4, "1,4 – Büro, etwas Bewegung"], [1.5, "1,5 – viel auf den Beinen"], [1.6, "1,6 – körperliche Arbeit"]].map(([x, l]) =>
          `<option value="${x}" ${(s.pal_base || 1.4) == x ? "selected" : ""}>${l}</option>`).join("")}</select></div>
      <div><label class="f" for="ppk">Protein (g je kg)</label><input type="number" step="0.1" id="ppk" value="${s.protein_g_per_kg ?? 1.8}"></div>
    </div>
    <h2>Feste Ziele (optional)</h2>
    <p class="small muted">Überschreibt das berechnete Ziel. Leer = automatisch.</p>
    <div class="grid2">${["kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "water_ml", ...MICROS].map(k =>
      `<div><label class="f" for="o_${k}">${NUT[k][0]} (${NUT[k][1]})</label><input type="number" step="any" id="o_${k}" value="${ov[k] ?? ""}" placeholder="${fmt(day.targets[k])}"></div>`).join("")}</div>
    <h2>Fotos und KI</h2>
    <label class="row small" style="gap:8px"><input type="checkbox" id="pai" style="flex:none;width:auto" ${s.photo_ai !== false ? "checked" : ""}> Fotos zur Analyse an Gemini senden</label>
    <label class="row small" style="gap:8px;margin-top:8px"><input type="checkbox" id="pkeep" style="flex:none;width:auto" ${s.keep_photos !== false ? "checked" : ""}> Fotos lokal bei der Mahlzeit speichern</label>
    <p class="small muted">KI: ${st.gemini ? `Gemini (${esc(st.gemini_model)})` : "kein API-Key – Text- und Fotoerkennung aus"}. Im kostenlosen Gemini-Kontingent darf Google Eingaben zur Verbesserung nutzen. Fotos werden vorher verkleinert, Standortdaten entfernt.</p>
    <button class="btn wide" id="ssave">Einstellungen speichern</button>
    <h2>Lebensmitteldatenbank</h2>
    <p class="small">BLS: ${st.bls_count ? `${fmt(st.bls_count)} Lebensmittel${st.bls.updated ? ", Stand " + esc(st.bls.updated) : ""}` : "nicht geladen"}. ${esc(st.bls.message || "")}</p>
    <button class="btn ghost" id="blsImp">BLS neu laden</button>
    <p class="small muted">Klappt der automatische Download nicht: Datei von blsdb.de/download nach <code>/share/ernaehrung/</code> legen und neu laden.</p>
    <h2>Daten</h2>
    <a class="btn ghost" href="api/v1/export.csv" download style="display:inline-block;text-decoration:none">Alles als CSV exportieren</a>
    <p class="small muted" style="margin-top:18px">Version ${esc(st.version)}. Nährwerte: ${esc(st.attribution)} Produktdaten: Open Food Facts (ODbL).</p>`;
  let goal = s.goal || "halten";
  v.querySelectorAll("#goal .chip").forEach(b => b.onclick = () => { goal = b.dataset.g; v.querySelectorAll("#goal .chip").forEach(x => x.setAttribute("aria-pressed", x === b)); });
  const num = id => { const x = $(id).value; return x === "" ? null : parseFloat(x.replace(",", ".")); };
  $("#ssave").onclick = async () => {
    const overrides = {};
    ["kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "water_ml", ...MICROS].forEach(k => { const x = num("#o_" + k); if (x !== null) overrides[k] = x; });
    await api("settings", { method: "PUT", body: {
      profile: { weight_kg: num("#pw"), height_cm: num("#ph"), age: num("#pa"), sex: $("#ps").value || null },
      goal, goal_adjust_pct: { halten: 0, abnehmen: -15, aufbauen: 10 }[goal], pal_base: parseFloat($("#pal").value),
      protein_g_per_kg: num("#ppk") || 1.8, target_overrides: overrides,
      photo_ai: $("#pai").checked, keep_photos: $("#pkeep").checked } });
    S.day = null; toast("Gespeichert"); renderSettings(v);
  };
  $("#blsImp").onclick = async () => { await api("bls/import", { method: "POST" }); toast("BLS wird geladen – das dauert ein bis zwei Minuten"); };
}

/* ---------- Start ---------- */
(async function init() {
  try { [S.status, S.settings] = await Promise.all([api("status"), api("settings")]); } catch (e) { /* zeigt render() */ }
  render();
  document.addEventListener("visibilitychange", () => { if (!document.hidden && $("#sheet").hidden) { if (S.date !== today() && S.view === "heute") { /* Datum behalten */ } render(); } });
})();
