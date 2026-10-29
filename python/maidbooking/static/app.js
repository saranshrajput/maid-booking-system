"use strict";

/* ===================== constants ===================== */

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]; // index = weekday number the API uses (0 = Monday)
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const SERVICES = ["CLEANING", "COOKING", "DISHWASHING", "LAUNDRY", "BABYSITTING"];
const SERVICE_TITLES = { CLEANING: "Home cleaning", COOKING: "Cooking", DISHWASHING: "Dishwashing", LAUNDRY: "Laundry", BABYSITTING: "Babysitting" };
const GENDERS = ["FEMALE", "MALE", "OTHER"];
const DURATIONS = [30, 60, 90, 120, 180, 240];
const MAX_RANGE_DAYS = 14;
const METHODS = {
  CARD: { label: "Card", placeholder: "4111111111111111", hint: "12 to 19 digit card number" },
  UPI: { label: "UPI", placeholder: "asha@upi", hint: "UPI id, for example name@bank" },
  WALLET: { label: "Wallet", placeholder: "wallet-123", hint: "Wallet id" },
};
const SAMPLE_MAIDS = [
  { name: "Asha Rao", locality: "Koramangala", gender: "FEMALE", rating: 4.8, hourlyRates: { CLEANING: 250, COOKING: 300 },
    skills: ["deep-cleaning", "north-indian"], days: [0, 1, 2, 3, 4, 5], start: "08:00", end: "18:00" },
  { name: "Ravi Kumar", locality: "Koramangala", gender: "MALE", rating: 4.2, hourlyRates: { CLEANING: 180, DISHWASHING: 120 },
    skills: ["utensils"], days: [0, 1, 2, 3, 4], start: "09:00", end: "17:00" },
  { name: "Meena Iyer", locality: "Indiranagar", gender: "FEMALE", rating: 4.6, hourlyRates: { COOKING: 350, BABYSITTING: 280, LAUNDRY: 150 },
    skills: ["south-indian", "infant-care"], days: [1, 2, 3, 4, 5, 6], start: "10:00", end: "20:00" },
];

const SVG = {
  CLEANING: '<svg viewBox="0 0 48 48"><path d="M30 6l12 12"/><path d="M36 12L19 29"/><path d="M13 25l10 10-13 6z"/></svg>',
  COOKING: '<svg viewBox="0 0 48 48"><path d="M9 22h30v12a6 6 0 0 1-6 6H15a6 6 0 0 1-6-6z"/><path d="M5 22h38"/><path d="M18 15c0-3 3-3 3-7M28 15c0-3 3-3 3-7"/></svg>',
  DISHWASHING: '<svg viewBox="0 0 48 48"><circle cx="24" cy="27" r="14"/><circle cx="24" cy="27" r="7"/><path d="M8 9l4 4M40 9l-4 4M24 5v4"/></svg>',
  LAUNDRY: '<svg viewBox="0 0 48 48"><path d="M17 7L5 15l6 7 5-3v22h16V19l5 3 6-7-12-8c-1 4-4 6-7 6s-6-2-7-6z"/></svg>',
  BABYSITTING: '<svg viewBox="0 0 48 48"><circle cx="24" cy="27" r="13"/><circle cx="13" cy="12" r="5"/><circle cx="35" cy="12" r="5"/><path d="M19 25v1M29 25v1M20 32c2 2 6 2 8 0"/></svg>',
  BOLT: '<svg viewBox="0 0 48 48"><path d="M27 4L10 27h12l-3 17 19-25H26z"/></svg>',
  CAL: '<svg viewBox="0 0 48 48"><rect x="7" y="10" width="34" height="31" rx="5"/><path d="M7 20h34M16 5v9M32 5v9"/></svg>',
  CALS: '<svg viewBox="0 0 48 48"><rect x="7" y="10" width="34" height="31" rx="5"/><path d="M7 20h34M16 5v9M32 5v9M15 28h4M22 28h4M29 28h4M15 34h4M22 34h4"/></svg>',
  PIN: '<svg viewBox="0 0 24 24"><path d="M12 21s7-6.2 7-11a7 7 0 0 0-14 0c0 4.8 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/></svg>',
  BACK: '<svg viewBox="0 0 24 24"><path d="M15 5l-7 7 7 7"/></svg>',
};
function icon(markup) { const t = document.createElement("template"); t.innerHTML = markup; return t.content.firstElementChild; }

const state = {
  customer: "", area: "", serverMs: Date.now(), fetchedAt: Date.now(),
  maids: new Map(), localities: [], flow: null, timers: [],
};

/* ===================== helpers ===================== */

function el(tag, props, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, value);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

const label = (s) => s.charAt(0) + s.slice(1).toLowerCase().replace(/_/g, " ");
const money = (n) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Math.round(Number(n)));
const moneyExact = (n) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2 }).format(Number(n));
const pad = (n) => String(n).padStart(2, "0");
const toISO = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const addDays = (d, n) => { const x = new Date(d.getFullYear(), d.getMonth(), d.getDate()); x.setDate(x.getDate() + n); return x; };
const wdIndex = (d) => (d.getDay() + 6) % 7;

// The API sends naive local date-times ("2030-01-08T10:00:00"); build the Date from parts so no timezone shift happens.
function parseLocal(iso) {
  const [d, t = "00:00:00"] = iso.split("T");
  const [y, m, day] = d.split("-").map(Number);
  const [hh, mm, ss = 0] = t.split(":").map(Number);
  return new Date(y, m - 1, day, hh, mm, Math.floor(ss));
}
const parseDay = (iso) => parseLocal(iso + "T00:00:00");
const fmtClock = (d) => `${d.getHours() % 12 || 12}:${pad(d.getMinutes())} ${d.getHours() >= 12 ? "pm" : "am"}`;
const fmtHHMM = (s) => fmtClock(parseLocal(`2000-01-01T${s}:00`));
const fmtDay = (d) => `${d.getDate()} ${MONTHS[d.getMonth()]}`;
const fmtLongDay = (d) => `${DAYS[wdIndex(d)]}, ${fmtDay(d)} ${d.getFullYear()}`;
const minutesBetween = (a, b) => Math.round((b - a) / 60000);

// The server's wall clock (business timezone), kept in step with the browser's timer.
const serverNow = () => new Date(state.serverMs + (Date.now() - state.fetchedAt));
const serverToday = () => toISO(serverNow());
async function syncClock() {
  const meta = await api("/api/meta");
  state.serverMs = parseLocal(meta.now).getTime();
  state.fetchedAt = Date.now();
}

const newKey = () => (window.crypto && crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2));

class ApiError extends Error {
  constructor(message, code, status) { super(message); this.code = code; this.status = status; }
}
async function api(path, { method = "GET", body, headers = {}, withTotal = false } = {}) {
  const res = await fetch(path, {
    method,
    headers: { ...(body ? { "Content-Type": "application/json" } : {}), ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* empty body */ }
  if (!res.ok) throw new ApiError((data && data.message) || `Request failed (${res.status})`, data && data.code, res.status);
  return withTotal ? { items: data, total: Number(res.headers.get("X-Total-Count") ?? data.length) } : data;
}

function toast(message, kind) {
  const t = el("div", { class: "toast" + (kind === "err" ? " err" : "") }, message);
  const box = document.getElementById("toasts");
  while (box.children.length >= 3) box.firstChild.remove();
  box.append(t);
  setTimeout(() => t.remove(), kind === "err" ? 6000 : 3500);
}

async function getMaid(id) {
  if (!state.maids.has(id)) state.maids.set(id, await api(`/api/maids/${id}`));
  return state.maids.get(id);
}
function remember(maids) { maids.forEach((m) => state.maids.set(m.id, m)); }
const localities = () => state.localities;
async function refreshLocalities() {
  state.localities = await api("/api/localities");
}

function field(labelText, input, hint) {
  return el("label", { class: "field" }, el("span", null, labelText), input, hint ? el("span", { class: "hint" }, hint) : null);
}
function select(id, options, value) {
  return el("select", { id }, options.map(([v, text]) => el("option", { value: v, selected: v === value }, text)));
}
function topbar(title, { back, right } = {}) {
  return el("div", { class: "topbar" },
    back ? el("button", { class: "back", type: "button", "aria-label": "Back", onclick: back }, icon(SVG.BACK)) : null,
    el("div", { class: "title" }, title), right || null);
}
const areaLabel = () => state.area || "All areas";

function armedButton(text, armedText, action, extra) {
  const btn = el("button", { class: `btn small danger ${extra || ""}`, type: "button" }, text);
  let timer = null;
  btn.addEventListener("click", (e) => {
    e.preventDefault(); e.stopPropagation();
    if (!btn.classList.contains("armed")) {
      btn.classList.add("armed"); btn.textContent = armedText;
      timer = setTimeout(() => { btn.classList.remove("armed"); btn.textContent = text; }, 4000);
      return;
    }
    clearTimeout(timer);
    btn.disabled = true;
    action();
  });
  return btn;
}

/* ===================== derived booking state ===================== */

// The API only knows pending / confirmed / cancelled; what is upcoming, running or finished depends on the clock.
function occState(o, now) {
  if (o.status === "CANCELLED") return "cancelled";
  if (o.status === "PENDING_PAYMENT") return "pending";
  const start = parseLocal(o.start), end = parseLocal(o.end);
  if (end <= now) return "completed";
  if (start <= now) return "inprogress";
  return "upcoming";
}
const STATE_LABEL = { upcoming: "Upcoming", completed: "Completed", inprogress: "In progress", cancelled: "Cancelled", pending: "Awaiting payment" };
const pill = (s) => el("span", { class: `pill ${s}` }, STATE_LABEL[s]);

function bookingState(b, now) {
  const states = b.occurrences.map((o) => occState(o, now));
  for (const s of ["inprogress", "pending", "upcoming", "completed"]) if (states.includes(s)) return s;
  return "cancelled";
}
function bookingKind(b) {
  if (b.bookingType !== "RECURRING") return "single";
  const days = b.occurrences.map((o) => toISO(parseLocal(o.start))).sort();
  const consecutive = days.every((d, i) => i === 0 || (parseDay(d) - parseDay(days[i - 1])) / 864e5 === 1);
  return days.length > 1 && consecutive ? "multiple" : "recurring";
}
const sortedOccs = (b) => [...b.occurrences].sort((x, y) => parseLocal(x.start) - parseLocal(y.start));
const activeTotal = (b) => b.occurrences.filter((o) => o.status !== "CANCELLED").reduce((s, o) => s + Number(o.price), 0);

/* ===================== routing ===================== */

const routes = { home: renderHome, details: renderDetails, maids: renderMaids, bookings: renderBookings, booking: renderBookingDetails, account: renderAccount, partner: renderPartner };
const TAB_SCREENS = new Set(["home", "bookings", "account"]);

function clearTimers() { state.timers.forEach(clearInterval); state.timers = []; }

async function route(opts = {}) {
  clearTimers();
  const [name, a, b] = (location.hash || "#/home").replace(/^#\/?/, "").split("/");
  const screen = routes[name] ? name : "home";
  const view = document.getElementById("view");
  view.replaceChildren();
  const tab = TAB_SCREENS.has(screen) ? screen : null;
  document.getElementById("tabbar").classList.toggle("hidden", !tab);
  document.querySelectorAll("#tabbar a").forEach((x) => { if (x.dataset.tab === tab) x.setAttribute("aria-current", "page"); else x.removeAttribute("aria-current"); });
  window.scrollTo(0, 0);
  try { await routes[screen](view, a, b, opts); } catch (err) {
    view.replaceChildren(topbar("Something went wrong"), el("div", { class: "empty" }, el("h3", null, "We could not load this screen"), el("p", null, err.message),
      el("a", { class: "btn primary", href: "#/home" }, "Back to home")));
  }
}
const go = (hash) => { location.hash = hash; };

/* ===================== dialog (bottom sheet) ===================== */

const dlg = document.getElementById("dlg");
document.getElementById("dlg-close").addEventListener("click", () => dlg.close());
dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
dlg.addEventListener("close", () => { if (/^#\/(booking|bookings)/.test(location.hash)) route(); });
function showSheet(title, ...content) {
  document.getElementById("dlg-title").textContent = title;
  document.getElementById("dlg-body").replaceChildren(...content);
  if (!dlg.open) dlg.showModal();
}

function openAreaSheet() {
  const apply = (area) => {
    state.area = area;
    try { localStorage.setItem("mb.area", area); } catch (e) { /* storage unavailable */ }
    dlg.close(); route({ keep: true });
  };
  const input = el("input", { id: "area-input", type: "text", list: "area-list", placeholder: "Type an area", autocomplete: "off", value: state.area });
  const places = localities();
  showSheet("Choose your area",
    el("div", { class: "stack" },
      places.length ? el("div", { class: "locs" }, places.map((p) => el("button", { class: "chip", type: "button", "data-area": p, "aria-pressed": String(p === state.area), onclick: () => apply(p) }, p)))
        : el("p", { class: "sub" }, "No maids have been added yet. Add some from the Account tab."),
      field("Or type an area", input), el("datalist", { id: "area-list" }, places.map((p) => el("option", { value: p }))),
      el("div", { class: "row2" },
        el("button", { class: "btn", type: "button", id: "area-all", onclick: () => apply("") }, "All areas"),
        el("button", { class: "btn primary", type: "button", id: "area-apply", onclick: () => apply(input.value.trim()) }, "Use this area"))));
}

/* ===================== home ===================== */

async function renderHome(view) {
  const tiles = el("div", { class: "tiles", id: "tiles" }, SERVICES.map((s) => tile(s, null)));
  view.append(
    el("div", { class: "hero" },
      el("button", { class: "area-btn", type: "button", id: "area-btn", onclick: openAreaSheet }, icon(SVG.PIN), `Home | ${areaLabel()}`),
      el("h1", null, "A trusted maid, whenever you need one"),
      el("p", null, "Book instantly, for a day, for a week or on repeat.")),
    el("div", { class: "sheet-top" }, el("div", { class: "section" }, el("h2", null, "What service do you need?")), tiles));
  const [summary] = await Promise.all([api(servicesSummaryUrl()), refreshLocalities()]);
  tiles.replaceChildren(...SERVICES.map((s) => tile(s, summary[s] || { maids: 0 })));
  view.append(el("a", { class: "promo", href: "#/details/CLEANING/now", id: "promo" },
    el("div", null, el("b", null, "Need help right now?"), el("span", null, "Book a maid who is free this minute")),
    el("span", { class: "go" }, "Book now")));
  if (!state.localities.length) {
    view.append(el("div", { class: "card" }, el("h3", null, "No maids yet"), el("p", { class: "sub" }, "Load three sample maids to try the whole booking flow."),
      el("div", { class: "actions" }, el("button", { class: "btn primary", type: "button", id: "seed-btn", onclick: seedMaids }, "Load sample maids"))));
  } else if (!state.area) {
    view.append(el("div", { class: "card" }, el("div", { class: "note" }, "Pick your area to see only the maids who serve it."),
      el("div", { class: "actions" }, el("button", { class: "btn primary", type: "button", id: "choose-area", onclick: openAreaSheet }, "Choose area"))));
  }
}

const servicesSummaryUrl = () => `/api/services/summary${state.area ? `?locality=${encodeURIComponent(state.area)}` : ""}`;

// entry is { maids, minHourlyRate } from the summary endpoint, or null while it loads.
function tile(service, entry) {
  const loaded = entry !== null;
  const available = !loaded || entry.maids > 0;
  const sub = !loaded ? "" : entry.maids
    ? `from ${money(entry.minHourlyRate)}/hour · ${entry.maids} ${entry.maids === 1 ? "maid" : "maids"}` : "Not available in this area";
  return el(available ? "a" : "div", { class: "tile", href: available ? `#/details/${service}` : null, "aria-disabled": available ? null : "true", "data-service": service },
    el("div", { class: "ico" }, icon(SVG[service])), el("b", null, SERVICE_TITLES[service]), el("small", null, sub));
}

async function seedMaids() {
  const btn = document.getElementById("seed-btn");
  if (btn) btn.disabled = true;
  try {
    for (const s of SAMPLE_MAIDS) {
      await api("/api/maids", { method: "POST", body: {
        name: s.name, locality: s.locality, gender: s.gender, rating: s.rating, hourlyRates: s.hourlyRates, skills: s.skills,
        availability: s.days.map((day) => ({ day, start: s.start, end: s.end })) } });
    }
    toast("Added 3 sample maids");
    await refreshLocalities();
    route();
  } catch (err) {
    toast(err.message, "err");
    if (btn) btn.disabled = false;
  }
}

/* ===================== choose service details ===================== */

function newFlow(service, mode) {
  const today = parseDay(serverToday());
  return { service, mode, start: null, end: null, weekdays: new Set(), visits: 4, duration: 60, time: null, slots: null,
    period: "Morning", month: `${today.getFullYear()}-${pad(today.getMonth() + 1)}`, minRate: null, maidCount: 0, token: 0 };
}
const visitCount = (f) => (f.mode === "MULTI" ? (f.start && f.end ? Math.round((parseDay(f.end) - parseDay(f.start)) / 864e5) + 1 : 0)
  : f.mode === "WEEKLY" ? f.visits : 1);
function flowReady(f) {
  if (!f) return false;
  if (f.mode === "NOW") return true;
  if (!f.time || !f.start) return false;
  if (f.mode === "MULTI") return Boolean(f.end);
  if (f.mode === "WEEKLY") return f.weekdays.size > 0 && f.visits > 0;
  return true;
}

async function renderDetails(view, service, hint, opts = {}) {
  if (!SERVICES.includes(service)) { go("#/home"); return; }
  // A tile tap starts a clean flow; coming back from the maid list or changing a setting keeps what was chosen.
  const keep = (opts.keep || hint === "keep") && state.flow && state.flow.service === service;
  if (!keep) state.flow = newFlow(service, hint === "now" ? "NOW" : "ONE");
  const f = state.flow;
  view.append(
    topbar(`Home | ${areaLabel()}`, { back: () => go("#/home"), right: el("button", { class: "link", type: "button", id: "change-area", onclick: openAreaSheet }, "Change") }),
    el("div", { class: "section" }, el("h2", null, "Choose service details"),
      el("div", { class: "chips scroll", style: "padding-left:0;padding-right:0;margin-top:8px" }, SERVICES.map((s) =>
        el("button", { class: "chip", type: "button", "aria-pressed": String(s === f.service), "data-service": s, onclick: () => { state.flow = newFlow(s, f.mode); go(`#/details/${s}/keep`); } }, SERVICE_TITLES[s])))),
    el("div", { class: "segtabs", role: "group", "aria-label": "Booking type" },
      [["NOW", "Now"], ["ONE", "One day"], ["MULTI", "Multiple days"], ["WEEKLY", "Weekly"]].map(([mode, text]) =>
        el("button", { type: "button", "data-mode": mode, "aria-pressed": String(f.mode === mode), onclick: () => {
          f.mode = mode; f.time = null; f.slots = null;
          if (mode !== "MULTI") f.end = null;
          if (mode === "WEEKLY" && f.start && !f.weekdays.size) f.weekdays.add(wdIndex(parseDay(f.start)));
          route({ keep: true });
        } }, text))),
    el("div", { id: "sections" }), el("div", { class: "bottombar", id: "bar" }));
  const entry = (await api(servicesSummaryUrl()))[service];
  f.maidCount = entry ? entry.maids : 0;
  f.minRate = entry ? entry.minHourlyRate : null;
  drawSections();
  if (f.start && f.mode !== "NOW") loadSlots();
}

function drawSections() {
  const f = state.flow, box = document.getElementById("sections");
  if (!box) return;
  const parts = [];
  if (f.maidCount === 0) parts.push(el("div", { class: "card" }, el("div", { class: "note warn", id: "no-maids" }, `No maid offers ${SERVICE_TITLES[f.service].toLowerCase()} in ${areaLabel()}. Try another area or service.`)));
  if (f.mode === "NOW") parts.push(el("div", { class: "card" }, el("h3", null, "Starts right now"), el("p", { class: "sub" }, "We will show maids who are working and free this minute.")));
  else { parts.push(dateCard()); if (f.mode === "WEEKLY") parts.push(weeklyCard()); }
  parts.push(durationCard());
  if (f.mode !== "NOW") parts.push(timeCard());
  box.replaceChildren(...parts);
  if (f.mode !== "NOW") { drawCalendar(); drawSlots(); }
  drawBar();
}

function dateCard() {
  const f = state.flow;
  const title = f.mode === "MULTI" ? "Select dates" : f.mode === "WEEKLY" ? "Select first visit date" : "Select date";
  const head = f.mode === "MULTI" ? el("div", { class: "rangebar" },
    el("div", { class: "pillbox" + (f.start ? " on" : ""), id: "range-start" }, f.start ? fmtDay(parseDay(f.start)) : "Start date"),
    el("span", { class: "daychip" }, f.start && f.end ? `${visitCount(f)} days` : "to"),
    el("div", { class: "pillbox" + (f.end ? " on" : ""), id: "range-end" }, f.end ? fmtDay(parseDay(f.end)) : "End date")) : null;
  return el("div", { class: "card", id: "date-card" }, el("h3", null, title), head, el("div", { id: "cal" }));
}

function drawCalendar() {
  const f = state.flow, host = document.getElementById("cal");
  if (!host) return;
  const [y, m] = f.month.split("-").map(Number);
  const today = parseDay(serverToday()), last = addDays(today, 90);
  const first = new Date(y, m - 1, 1), blanks = wdIndex(first), total = new Date(y, m, 0).getDate();
  const shift = (n) => { const d = new Date(y, m - 1 + n, 1); f.month = `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; drawCalendar(); };
  const canPrev = new Date(y, m - 1, 0) >= today, canNext = new Date(y, m, 1) <= last;
  const cells = [...DAYS.map((d) => el("div", { class: "dow" }, d[0])), ...Array.from({ length: blanks }, () => el("span", { class: "blank" }))];
  for (let d = 1; d <= total; d++) {
    const date = new Date(y, m - 1, d), iso = toISO(date);
    const isSel = iso === f.start || iso === f.end;
    const inRange = f.mode === "MULTI" && f.start && f.end && iso > f.start && iso < f.end;
    cells.push(el("button", { type: "button", "data-date": iso, disabled: date < today || date > last,
      class: [iso === toISO(today) ? "today" : "", isSel ? "sel" : "", inRange ? "inrange" : ""].join(" ").trim(),
      "aria-pressed": String(isSel), "aria-label": fmtLongDay(date), onclick: () => pickDate(iso) }, String(d)));
  }
  host.replaceChildren(
    el("div", { class: "cal-head" }, el("button", { type: "button", "aria-label": "Previous month", id: "cal-prev", disabled: !canPrev, onclick: () => shift(-1) }, "‹"),
      el("span", { id: "cal-title" }, `${MONTH_NAMES[m - 1]} ${y}`), el("button", { type: "button", "aria-label": "Next month", id: "cal-next", disabled: !canNext, onclick: () => shift(1) }, "›")),
    el("div", { class: "cal" }, cells));
}

function pickDate(iso) {
  const f = state.flow;
  if (f.mode === "MULTI") {
    if (!f.start || f.end || iso < f.start) { f.start = iso; f.end = null; }
    else if ((parseDay(iso) - parseDay(f.start)) / 864e5 + 1 > MAX_RANGE_DAYS) { toast(`Pick up to ${MAX_RANGE_DAYS} days`, "err"); f.start = iso; f.end = null; }
    else f.end = iso;
  } else {
    f.start = iso;
    if (f.mode === "WEEKLY") f.weekdays = new Set([wdIndex(parseDay(iso))]);
  }
  f.time = null; f.slots = null;
  drawSections();
  loadSlots();
}

function weeklyCard() {
  const f = state.flow;
  const sync = () => document.querySelectorAll("#weekly-card .chip").forEach((c) => c.setAttribute("aria-pressed", String(f.weekdays.has(Number(c.dataset.day)))));
  return el("div", { class: "card", id: "weekly-card" }, el("h3", null, "Repeat on"),
    el("div", { class: "chips" }, DAYS.map((d, i) => el("button", { class: "chip", type: "button", "data-day": String(i), "aria-pressed": String(f.weekdays.has(i)),
      onclick: () => { if (f.weekdays.has(i)) f.weekdays.delete(i); else f.weekdays.add(i); sync(); drawBar(); } }, d))),
    field("Number of visits", el("input", { id: "visits", type: "number", min: "1", max: "52", value: String(f.visits),
      oninput: (e) => { f.visits = Math.max(1, Math.min(52, Number(e.target.value) || 1)); drawBar(); } }), "Visits are counted from the first date, on the days you pick."));
}

function durationCard() {
  const f = state.flow;
  return el("div", { class: "card", id: "duration-card" }, el("h3", null, "Select duration"),
    el("div", { class: "dur" }, DURATIONS.map((m) => el("button", { type: "button", "data-minutes": String(m), "aria-pressed": String(f.duration === m),
      onclick: () => { f.duration = m; f.time = null; f.slots = null; drawSections(); if (f.start && f.mode !== "NOW") loadSlots(); } },
      el("b", null, `${m} mins`), el("small", null, f.minRate ? `from ${money(f.minRate * m / 60)}` : "")))));
}

function timeCard() {
  const f = state.flow;
  return el("div", { class: "card", id: "time-card" }, el("h3", null, "Select start time"),
    el("div", { id: "slots-body" }, el("p", { class: "sub", id: "slots-hint" }, f.start ? "Loading times…" : "Pick a date to see available start times.")));
}

const periodOf = (hhmm) => { const h = Number(hhmm.slice(0, 2)); return h < 12 ? "Morning" : h < 17 ? "Afternoon" : "Evening"; };

async function loadSlots() {
  const f = state.flow;
  if (!f.start || f.mode === "NOW") return;
  const token = ++f.token;
  const q = new URLSearchParams({ date: f.start, durationMinutes: String(f.duration), serviceType: f.service });
  if (state.area) q.set("locality", state.area);
  let slots;
  try { slots = await api(`/api/availability/slots?${q}`); } catch (err) { toast(err.message, "err"); return; }
  if (token !== f.token) return; // a newer request replaced this one
  f.slots = slots;
  const open = ["Morning", "Afternoon", "Evening"].find((p) => slots.some((s) => periodOf(s.time) === p && s.available > 0));
  if (open && !slots.some((s) => periodOf(s.time) === f.period && s.available > 0)) f.period = open;
  drawSlots();
}

function drawSlots() {
  const f = state.flow, body = document.getElementById("slots-body");
  if (!body || !f.slots) return;
  if (!f.slots.some((s) => s.available > 0)) {
    body.replaceChildren(el("div", { class: "note warn", id: "no-slots" }, "No maid is free on this date for that duration. Try another date or a shorter duration."));
    return;
  }
  body.replaceChildren(
    el("div", { class: "chips" }, ["Morning", "Afternoon", "Evening"].map((p) => el("button", { class: "chip", type: "button", "data-period": p, "aria-pressed": String(f.period === p),
      onclick: () => { f.period = p; drawSlots(); } }, p))),
    el("div", { class: "slots" }, f.slots.filter((s) => periodOf(s.time) === f.period).map((s) =>
      el("button", { class: "slot", type: "button", "data-time": s.time, disabled: s.available === 0, "aria-pressed": String(f.time === s.time), title: s.available ? `${s.available} free` : "Nobody free",
        onclick: () => { f.time = s.time; drawSlots(); drawBar(); } }, fmtHHMM(s.time)))));
}

function drawBar() {
  const f = state.flow, bar = document.getElementById("bar");
  if (!bar) return;
  const visits = visitCount(f);
  const ready = flowReady(f) && f.maidCount > 0;
  const total = f.minRate && visits ? (f.minRate * f.duration / 60) * visits : null;
  bar.replaceChildren(
    el("div", { class: "price" }, el("b", { id: "bar-price" }, total ? `from ${money(total)}` : "—"), el("small", null, `${visits || 0} ${visits === 1 ? "visit" : "visits"} · ${f.duration} mins`)),
    el("button", { class: "btn primary", type: "button", id: "see-maids", disabled: !ready, onclick: () => go("#/maids") }, "See available maids"));
}

/* ===================== choose a maid ===================== */

function flowSlotParams(f) {
  if (f.mode === "NOW") { const now = serverNow(); return { date: toISO(now), startTime: `${pad(now.getHours())}:${pad(now.getMinutes())}` }; }
  return { date: f.start, startTime: f.time };
}
function flowSummary(f) {
  const { date, startTime } = flowSlotParams(f);
  const when = f.mode === "NOW" ? "Right now" : `${fmtDay(parseDay(date))}, ${fmtHHMM(startTime)}`;
  const span = f.mode === "MULTI" ? ` to ${fmtDay(parseDay(f.end))}` : f.mode === "WEEKLY" ? ` · ${[...f.weekdays].sort().map((d) => DAYS[d]).join(", ")}` : "";
  return `${SERVICE_TITLES[f.service]} · ${when}${span} · ${f.duration} mins`;
}

const MAIDS_PAGE_SIZE = 20;

async function renderMaids(view) {
  const f = state.flow;
  if (!flowReady(f)) { go("#/home"); return; }
  const visits = visitCount(f);
  const cards = el("div", { id: "maid-list" }, el("p", { class: "sub", style: "padding:0 16px" }, "Finding maids…"));
  const count = el("p", { class: "sub", id: "result-count" });
  const more = el("button", { class: "btn block", type: "button", id: "show-more", hidden: true, style: "width:calc(100% - 32px);margin:4px 16px 16px" }, "Show more maids");
  view.append(topbar("Choose your maid", { back: () => go(`#/details/${f.service}/keep`) }),
    el("div", { class: "section" }, el("p", { class: "sub", id: "flow-summary" }, flowSummary(f)), count), cards, more);

  const { date, startTime } = flowSlotParams(f);
  const q = new URLSearchParams({ serviceType: f.service, date, startTime, durationMinutes: String(f.duration), limit: String(MAIDS_PAGE_SIZE) });
  if (state.area) q.set("locality", state.area);
  let shown = 0;

  const card = (m) => {
    const perVisit = m.hourlyRates[f.service] * f.duration / 60;
    return el("article", { class: "card maid", "data-maid": m.name },
      el("div", { class: "maid-top" }, el("div", { class: "avatar", "aria-hidden": "true" }, m.name.charAt(0).toUpperCase()),
        el("div", null, el("h3", null, m.name), el("div", { class: "sub" }, `★ ${Number(m.rating).toFixed(1)} · ${m.locality} · ${label(m.gender)}`))),
      m.skills.length ? el("div", { class: "tags" }, m.skills.map((s) => el("span", { class: "tag" }, s))) : null,
      el("div", { class: "maid-foot" },
        el("div", null, el("b", null, money(perVisit * visits)), el("div", { class: "sub" }, visits > 1 ? `${money(perVisit)} × ${visits} visits` : `${money(m.hourlyRates[f.service])}/hour`)),
        el("button", { class: "btn primary", type: "button", "data-book": m.name, onclick: (e) => reserve(m, e.currentTarget) }, "Book")));
  };
  const loadPage = async () => {
    more.disabled = true;
    q.set("offset", String(shown));
    const page = await api(`/api/maids/search?${q}`, { withTotal: true });
    remember(page.items);
    if (!shown) cards.replaceChildren();
    if (!page.total) {
      cards.replaceChildren(el("div", { class: "empty", id: "no-match" }, el("h3", null, "No maid is free then"), el("p", null, "Try another time, date or duration."),
        el("a", { class: "btn primary", href: `#/details/${f.service}/keep` }, "Change details")));
      return;
    }
    cards.append(...page.items.map(card));
    shown += page.items.length;
    count.textContent = `${page.total} ${page.total === 1 ? "maid" : "maids"} available`;
    more.hidden = shown >= page.total;
    more.disabled = false;
  };
  more.addEventListener("click", () => loadPage().catch((err) => { toast(err.message, "err"); more.disabled = false; }));
  await loadPage();
}

async function reserve(maid, button) {
  const f = state.flow;
  if (!state.customer) { toast("Add your customer id in the Account tab first", "err"); return; }
  const body = { customerId: state.customer, maidId: maid.id, serviceType: f.service, durationMinutes: f.duration };
  if (f.mode === "NOW") body.bookingType = "INSTANT";
  else if (f.mode === "ONE") { body.bookingType = "SCHEDULED"; body.startDateTime = `${f.start}T${f.time}`; }
  else {
    body.bookingType = "RECURRING";
    body.recurrence = { daysOfWeek: f.mode === "MULTI" ? [0, 1, 2, 3, 4, 5, 6] : [...f.weekdays].sort(), startDate: f.start, startTime: f.time, occurrences: visitCount(f) };
  }
  button.disabled = true;
  try {
    const booking = await api("/api/bookings", { method: "POST", body });
    toast("Slot reserved. Complete payment to confirm.");
    openPayment(booking);
  } catch (err) {
    toast(err.message, "err");
    button.disabled = false;
  }
}

/* ===================== payment ===================== */

async function openPayment(booking, preferredOccurrenceId) {
  const maid = await getMaid(booking.maidId).catch(() => null);
  const unpaid = sortedOccs(booking).filter((o) => o.status === "PENDING_PAYMENT");
  const maidName = maid ? maid.name : "your maid";
  if (!unpaid.length) { toast("Nothing left to pay on this booking"); return; }

  let idempotencyKey = newKey();
  const errorBox = el("div", { id: "p-error" });
  const scopeValue = () => (document.querySelector("input[name=scope]:checked") || {}).value;
  const amountFor = () => {
    if (scopeValue() === "ALL") return unpaid.reduce((sum, o) => sum + Number(o.price), 0);
    const occ = unpaid.find((o) => o.id === document.getElementById("p-occ").value);
    return occ ? Number(occ.price) : 0;
  };
  const payBtn = el("button", { class: "btn primary block", type: "submit", id: "p-submit" }, "Pay");
  const updatePayLabel = () => { payBtn.textContent = `Pay ${moneyExact(amountFor())}`; document.getElementById("p-occ").disabled = scopeValue() === "ALL"; };
  const occLabel = (o) => `${fmtDay(parseLocal(o.start))}, ${fmtClock(parseLocal(o.start))} · ${moneyExact(o.price)}`;
  const scope = unpaid.length > 1
    ? el("fieldset", null, el("legend", null, "What to pay"),
      el("div", { class: "seg" },
        el("label", null, el("input", { type: "radio", name: "scope", value: "ALL", checked: !preferredOccurrenceId }), el("span", null, `All ${unpaid.length} visits`)),
        el("label", null, el("input", { type: "radio", name: "scope", value: "ONE", checked: Boolean(preferredOccurrenceId) }), el("span", null, "One visit"))),
      el("div", { style: "margin-top:8px" }, el("select", { id: "p-occ", "aria-label": "Visit to pay", style: "width:100%;padding:10px;border-radius:10px;border:1px solid var(--line)" },
        unpaid.map((o) => el("option", { value: o.id, selected: o.id === preferredOccurrenceId }, occLabel(o))))))
    : el("div", null, el("input", { type: "radio", name: "scope", value: "ONE", checked: true, hidden: true }),
      el("select", { id: "p-occ", hidden: true }, el("option", { value: unpaid[0].id }, unpaid[0].id)));

  const method = select("p-method", Object.entries(METHODS).map(([k, v]) => [k, v.label]), "UPI");
  const instrument = el("input", { id: "p-instrument", type: "text", autocomplete: "off", spellcheck: "false", required: true });
  const hint = el("span", { class: "hint", id: "p-hint" });
  const syncMethod = () => { const m = METHODS[method.value]; instrument.placeholder = m.placeholder; hint.textContent = `${m.hint}. Demo gateway: anything starting with "fail" is declined.`; };

  const form = el("form", { class: "stack", id: "payment-form" },
    el("div", { class: "summary" },
      el("div", { class: "row" }, el("b", null, `${SERVICE_TITLES[booking.serviceType]} with ${maidName}`), pill(bookingState(booking, serverNow()))),
      sortedOccs(booking).map((o) => el("div", { class: "row" }, el("span", null, `${fmtDay(parseLocal(o.start))}, ${fmtClock(parseLocal(o.start))}`),
        el("span", null, `${moneyExact(o.price)} · ${STATE_LABEL[occState(o, serverNow())]}`)))),
    scope,
    el("div", { class: "row2" }, field("Payment method", method), field("Payment details", instrument)),
    hint, errorBox,
    el("div", { class: "stack" }, payBtn, el("button", { class: "btn block", type: "button", id: "pay-later", onclick: () => { dlg.close(); go("#/bookings"); } }, "Pay later")));
  showSheet("Complete payment", form);
  syncMethod(); updatePayLabel();
  method.addEventListener("change", syncMethod);
  form.addEventListener("change", updatePayLabel);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.replaceChildren(); payBtn.disabled = true;
    const body = { method: method.value, instrument: instrument.value.trim() };
    if (scopeValue() === "ONE") body.occurrenceId = document.getElementById("p-occ").value;
    try {
      const payments = await api(`/api/bookings/${booking.id}/payments`, { method: "POST", body, headers: { "Idempotency-Key": idempotencyKey } });
      idempotencyKey = newKey();
      showPaid(await api(`/api/bookings/${booking.id}`), payments, maidName);
    } catch (err) {
      errorBox.append(el("div", { class: "note err", role: "alert" }, err.message));
      payBtn.disabled = false;
    }
  });
}

function showPaid(booking, payments, maidName) {
  const total = payments.reduce((s, p) => s + Number(p.amount), 0);
  const left = booking.occurrences.filter((o) => o.status === "PENDING_PAYMENT").length;
  showSheet("Payment received",
    el("div", { class: "done" }, el("div", { class: "tick", "aria-hidden": "true" }, "✓"),
      el("h3", { id: "paid-title" }, left ? "Visit paid" : "Booking confirmed"),
      el("p", { class: "sub", id: "paid-detail" }, `${moneyExact(total)} paid for ${payments.length} ${payments.length === 1 ? "visit" : "visits"} with ${maidName}.` + (left ? ` ${left} visit${left === 1 ? "" : "s"} still awaiting payment.` : ""))),
    el("div", { class: "stack", style: "margin-top:14px" },
      el("a", { class: "btn primary block", id: "view-booking", href: `#/booking/${booking.id}`, style: "text-align:center;text-decoration:none", onclick: () => dlg.close() }, "View booking"),
      el("button", { class: "btn block", type: "button", id: "paid-close", onclick: () => dlg.close() }, "Close")));
}

/* ===================== your bookings ===================== */

async function renderBookings(view) {
  const filter = { value: "all" };
  view.append(topbar("Your bookings"));
  if (!state.customer) {
    view.append(el("div", { class: "empty" }, el("h3", null, "Who is booking?"), el("p", null, "Add your customer id in the Account tab to see your bookings."), el("a", { class: "btn primary", href: "#/account" }, "Open Account")));
    return;
  }
  const chips = el("div", { class: "chips scroll", id: "filters" });
  const list = el("div", { id: "bookings-list" }, el("p", { class: "sub", style: "padding:12px 16px" }, "Loading…"));
  view.append(chips, list);
  const bookings = await api(`/api/bookings?customerId=${encodeURIComponent(state.customer)}`);
  await Promise.all(bookings.map((b) => getMaid(b.maidId).catch(() => null)));
  const draw = () => {
    chips.replaceChildren(...[["all", "All"], ["single", "Single"], ["multiple", "Multiple"], ["recurring", "Recurring"]].map(([v, text]) =>
      el("button", { class: "chip", type: "button", "data-filter": v, "aria-pressed": String(filter.value === v), onclick: () => { filter.value = v; draw(); } }, text)));
    const shown = bookings.filter((b) => filter.value === "all" || bookingKind(b) === filter.value);
    if (!shown.length) {
      list.replaceChildren(el("div", { class: "empty", id: "no-bookings" }, el("h3", null, bookings.length ? "Nothing in this filter" : "No bookings yet"),
        el("p", null, bookings.length ? "Try another filter." : "Book your first maid in a minute."), bookings.length ? null : el("a", { class: "btn primary", href: "#/home" }, "Find a maid")));
      return;
    }
    list.replaceChildren(...shown.map(bookingCard));
  };
  draw();
}

function bookingCard(b) {
  const now = serverNow(), occs = sortedOccs(b), kind = bookingKind(b), maid = state.maids.get(b.maidId);
  const first = parseLocal(occs[0].start), lastDay = parseLocal(occs[occs.length - 1].start), multi = occs.length > 1;
  const mins = minutesBetween(first, parseLocal(occs[0].end));
  const pending = occs.filter((o) => o.status === "PENDING_PAYMENT").reduce((s, o) => s + Number(o.price), 0), total = activeTotal(b);
  const amount = !total ? "Cancelled" : pending ? `Amount: ${moneyExact(total)} (${pending === total ? "Pending" : `${moneyExact(pending)} pending`})` : `Amount: ${moneyExact(total)} (Paid online)`;
  const title = multi ? `${fmtDay(first)} - ${fmtDay(lastDay)}` : fmtDay(first);
  const sub = `${fmtClock(first)} · ${mins} mins · ${multi ? (kind === "multiple" ? `${occs.length} days` : `${occs.length} visits`) : DAYS[wdIndex(first)]}`;
  const card = el("article", { class: "bk", "data-booking": b.id, "data-kind": kind });
  const visitsBox = el("div");
  let open = false;
  const draw = () => {
    visitsBox.replaceChildren();
    if (!multi) return;
    if (open) {
      visitsBox.append(el("div", { class: "visits" }, occs.map((o) => {
        const s = occState(o, now), d = parseLocal(o.start);
        return el("a", { class: "visit", href: `#/booking/${b.id}/${o.id}` },
          el("div", { class: `datebadge ${s}` }, el("b", null, d.getDate()), el("small", null, MONTHS[d.getMonth()].toUpperCase())),
          el("div", { class: "info" }, el("b", null, `${fmtClock(d)} · ${DAYS[wdIndex(d)]}`), el("span", { class: "sub" }, moneyExact(o.price))), pill(s));
      })));
    }
    visitsBox.append(el("button", { class: "togglevisits", type: "button", onclick: () => { open = !open; draw(); } }, open ? "View less" : `View all ${occs.length} visits`));
  };
  draw();
  card.append(el("a", { class: "bk-main", href: `#/booking/${b.id}`, style: "text-decoration:none;color:inherit" },
    el("div", { class: "bk-ico" + (b.bookingType === "INSTANT" ? " instant" : "") }, icon(b.bookingType === "INSTANT" ? SVG.BOLT : multi ? SVG.CALS : SVG.CAL)),
    el("div", { class: "bk-body" }, el("b", null, title), el("div", null, sub), el("div", null, `${SERVICE_TITLES[b.serviceType]}${maid ? ` · ${maid.name}` : ""}`), el("div", null, amount)),
    pill(bookingState(b, now))), visitsBox);
  return card;
}

/* ===================== booking details ===================== */

async function renderBookingDetails(view, id, occId) {
  const b = await api(`/api/bookings/${id}`);
  const maid = await getMaid(b.maidId).catch(() => null);
  const now = serverNow(), occs = sortedOccs(b);
  const pick = occs.find((o) => o.id === occId) || occs.find((o) => ["inprogress", "pending", "upcoming"].includes(occState(o, now))) || occs[occs.length - 1];
  const s = occState(pick, now), start = parseLocal(pick.start), end = parseLocal(pick.end);
  const headline = { upcoming: "Upcoming service", inprogress: "Service in progress", completed: "Service completed", pending: "Payment pending", cancelled: "Booking cancelled" }[s];
  const ring = el("div", { class: "ring", id: "ring" });
  const paintRing = () => {
    if (s !== "inprogress") { ring.replaceChildren(); return; }
    const total = minutesBetween(start, end), left = Math.max(0, Math.ceil((end - serverNow()) / 60000));
    const r = 40, c = 2 * Math.PI * r, frac = total ? Math.min(1, left / total) : 0;
    ring.innerHTML = `<svg viewBox="0 0 100 100" width="92" height="92" role="img" aria-label="${left} minutes left"><circle cx="50" cy="50" r="${r}" fill="#ffffff" fill-opacity=".12" stroke="#ffffff" stroke-opacity=".3" stroke-width="8"/><circle cx="50" cy="50" r="${r}" fill="none" stroke="#fff" stroke-width="8" stroke-linecap="round" stroke-dasharray="${c * frac} ${c}" transform="rotate(-90 50 50)"/><text x="50" y="40" text-anchor="middle" font-size="9" font-weight="700" opacity=".9">TIME LEFT</text><text x="50" y="62" text-anchor="middle" font-size="24" font-weight="800">${left}</text><text x="50" y="75" text-anchor="middle" font-size="10" font-weight="700">min</text></svg>`;
  };
  paintRing();
  if (s === "inprogress") state.timers.push(setInterval(paintRing, 15000));

  const unpaid = occs.filter((o) => o.status === "PENDING_PAYMENT");
  const active = occs.filter((o) => o.status !== "CANCELLED");
  const after = () => route();
  view.append(...[topbar("Booking details", { back: () => go("#/bookings") }),
    el("div", { class: `statusbar ${s}`, id: "statusbar" }, el("h1", { id: "status-title" }, headline), ring),
    el("div", { class: "card pull" },
      el("div", { class: "maid-top" }, el("div", { class: "avatar", "aria-hidden": "true" }, (maid ? maid.name : "?").charAt(0).toUpperCase()),
        el("div", null, el("h3", { id: "d-maid" }, maid ? maid.name : "Your maid"), el("div", { class: "sub" }, `${SERVICE_TITLES[b.serviceType]}${maid ? ` · ★ ${Number(maid.rating).toFixed(1)}` : ""}`)), pill(s))),
    el("div", { class: "card" }, el("h3", null, "Booking details"),
      el("div", { class: "kv" }, el("div", null, el("span", null, "Date"), el("span", { id: "d-date" }, fmtLongDay(start))),
        el("div", null, el("span", null, "Starts at"), el("span", { id: "d-start" }, fmtClock(start))),
        el("div", null, el("span", null, "Duration"), el("span", null, `${minutesBetween(start, end)} mins`)))),
    el("div", { class: "card" }, el("h3", null, "Service area"), el("p", { class: "sub" }, maid ? maid.locality : "")),
    el("div", { class: "card" }, el("h3", null, "Payment details"),
      el("div", { class: "kv" }, el("div", { class: "total" }, el("span", null, "Total payable"), el("span", { id: "d-total" }, moneyExact(pick.price))),
        el("div", null, el("span", null, "Payment status"), el("span", { id: "d-paystatus" }, pick.status === "PENDING_PAYMENT" ? "Pending" : pick.status === "CONFIRMED" ? "Paid online" : "Cancelled")),
        occs.length > 1 ? el("div", null, el("span", null, "Whole booking"), el("span", null, moneyExact(activeTotal(b)))) : null)),
    occs.length > 1 ? el("div", { class: "card" }, el("h3", null, "Multiple visits"),
      el("div", { class: "dots" }, occs.map((o) => el("button", { class: `dot ${occState(o, now)}`, type: "button", "data-occ": o.id, "aria-pressed": String(o.id === pick.id),
        "aria-label": `${fmtLongDay(parseLocal(o.start))}, ${STATE_LABEL[occState(o, now)]}`, onclick: () => go(`#/booking/${b.id}/${o.id}`) }, String(parseLocal(o.start).getDate()))))) : null,
    el("div", { class: "card" }, el("h3", null, "Cancellation policy"),
      el("p", { class: "sub" }, "Full refund when you cancel 24 hours or more before the visit, 50% from 2 to 24 hours, none after that.")),
    el("div", { class: "actions", id: "detail-actions" },
      pick.status === "PENDING_PAYMENT" ? el("button", { class: "btn primary", type: "button", id: "pay-visit", onclick: () => openPayment(b, pick.id) }, `Pay ${moneyExact(pick.price)}`) : null,
      unpaid.length > 1 ? el("button", { class: "btn primary", type: "button", id: "pay-all", onclick: () => openPayment(b) }, `Pay all ${unpaid.length} unpaid visits`) : null,
      pick.status !== "CANCELLED" && s !== "completed" ? armedButton(occs.length > 1 ? "Cancel this visit" : "Cancel booking", "Confirm cancel", () => cancelBooking(b.id, pick.id, after), "visit") : null,
      active.length > 1 ? armedButton("Cancel whole series", "Confirm cancel series", () => cancelBooking(b.id, null, after), "series") : null)].filter(Boolean));
}

async function cancelBooking(bookingId, occurrenceId, after) {
  try {
    const qs = occurrenceId ? `?occurrenceId=${encodeURIComponent(occurrenceId)}` : "";
    const result = await api(`/api/bookings/${bookingId}/cancel${qs}`, { method: "POST" });
    const n = result.cancelledOccurrenceIds.length;
    toast(`Cancelled ${n} ${n === 1 ? "visit" : "visits"}. Refund ${moneyExact(result.totalRefund)}.`);
  } catch (err) {
    toast(err.message, "err");
  }
  after();
}

/* ===================== account and partner ===================== */

function renderAccount(view) {
  const input = el("input", { id: "customer", type: "text", autocomplete: "off", spellcheck: "false", maxlength: "60", value: state.customer });
  const save = () => {
    const next = input.value.trim();
    if (next === state.customer) return;
    state.customer = next;
    try { localStorage.setItem("mb.customer", next); } catch (e) { /* storage unavailable */ }
    toast(next ? `Booking as ${next}` : "Customer id cleared");
  };
  input.addEventListener("change", save); input.addEventListener("blur", save);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") save(); });
  view.append(topbar("Account"),
    el("div", { class: "card" }, el("h3", null, "Booking as"), field("Customer id", input, "There is no login. Bookings are listed under this id.")),
    el("div", { class: "card" }, el("h3", null, "Service area"),
      el("div", { class: "list-item" }, el("span", { id: "acc-area" }, areaLabel()), el("button", { class: "btn small", type: "button", id: "acc-area-change", onclick: openAreaSheet }, "Change"))),
    el("div", { class: "card" }, el("h3", null, "For partners"),
      el("p", { class: "sub", style: "margin-bottom:10px" }, "Onboard a maid with her services, rates and working hours."),
      el("div", { class: "stack" }, el("a", { class: "btn primary block", id: "add-maid-link", href: "#/partner", style: "text-align:center;text-decoration:none" }, "Add a maid"),
        el("button", { class: "btn block", type: "button", id: "seed-btn", onclick: seedMaids }, "Add 3 sample maids"))));
}

function renderPartner(view) {
  const box = "padding:9px;border:1px solid var(--line);border-radius:10px;width:100%";
  const serviceRows = SERVICES.map((s, i) => el("div", { class: "service-row" },
    el("label", null, el("input", { type: "checkbox", name: "svc", value: s, checked: i === 0 }), SERVICE_TITLES[s]),
    el("input", { type: "number", min: "1", step: "any", name: `rate-${s}`, value: i === 0 ? "200" : "", "aria-label": `${SERVICE_TITLES[s]} rate per hour`, placeholder: "₹ / hour", style: box })));
  const windowRows = DAYS.map((d, i) => el("div", { class: "window-row" },
    el("label", { class: "day" }, el("input", { type: "checkbox", name: "wday", value: String(i), checked: i < 6 }), d),
    el("input", { type: "time", name: `ws-${i}`, value: "08:00", "aria-label": `${d} start`, style: box }),
    el("input", { type: "time", name: `we-${i}`, value: "18:00", "aria-label": `${d} end`, style: box })));
  const errorBox = el("div");
  const form = el("form", { class: "card stack", id: "add-form" },
    field("Name", el("input", { id: "m-name", type: "text", required: true, maxlength: "80" })),
    field("Area", el("input", { id: "m-locality", type: "text", required: true, maxlength: "80", placeholder: "Koramangala", list: "m-areas" })),
    el("datalist", { id: "m-areas" }, localities().map((l) => el("option", { value: l }))),
    el("div", { class: "row2" }, field("Gender", select("m-gender", GENDERS.map((g) => [g, label(g)]), "FEMALE")),
      field("Rating (0 to 5)", el("input", { id: "m-rating", type: "number", min: "0", max: "5", step: "any", value: "4.5", required: true }))),
    field("Skills", el("input", { id: "m-skills", type: "text", placeholder: "deep-cleaning, utensils" }), "Comma separated"),
    el("fieldset", { class: "stack" }, el("legend", null, "Services and hourly rate"), serviceRows),
    el("fieldset", { class: "stack" }, el("legend", null, "Weekly working hours"), windowRows),
    errorBox, el("button", { class: "btn primary block", type: "submit", id: "add-submit" }, "Add maid"));
  view.append(topbar("Add a maid", { back: () => go("#/account") }), form);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.replaceChildren();
    const fail = (msg) => errorBox.append(el("div", { class: "note err", role: "alert" }, msg));
    const hourlyRates = {};
    for (const cb of form.querySelectorAll("input[name=svc]:checked")) {
      const rate = Number(form.elements[`rate-${cb.value}`].value);
      if (!rate || rate <= 0) return fail(`Enter an hourly rate for ${SERVICE_TITLES[cb.value].toLowerCase()}.`);
      hourlyRates[cb.value] = rate;
    }
    if (!Object.keys(hourlyRates).length) return fail("Choose at least one service.");
    const availability = [...form.querySelectorAll("input[name=wday]:checked")].map((c) => ({ day: Number(c.value), start: form.elements[`ws-${c.value}`].value, end: form.elements[`we-${c.value}`].value }));
    if (!availability.length) return fail("Choose at least one working day.");
    if (availability.some((w) => !w.start || !w.end || w.end <= w.start)) return fail("Each working day needs an end time after its start time.");
    try {
      const maid = await api("/api/maids", { method: "POST", body: {
        name: document.getElementById("m-name").value.trim(), locality: document.getElementById("m-locality").value.trim(),
        gender: document.getElementById("m-gender").value, rating: Number(document.getElementById("m-rating").value), hourlyRates,
        skills: document.getElementById("m-skills").value.split(",").map((x) => x.trim()).filter(Boolean), availability } });
      remember([maid]);
      await refreshLocalities();
      toast(`${maid.name} added`);
      go("#/home");
    } catch (err) { fail(err.message); }
  });
}

/* ===================== boot ===================== */

(async function boot() {
  try { state.customer = localStorage.getItem("mb.customer") || "customer-1"; state.area = localStorage.getItem("mb.area") || ""; } catch (e) { state.customer = "customer-1"; }
  try { await syncClock(); } catch (e) { /* fall back to the browser clock */ }
  try { await refreshLocalities(); } catch (e) { /* the home screen loads them again */ }
  window.addEventListener("hashchange", () => route());
  setInterval(() => { syncClock().catch(() => {}); }, 5 * 60 * 1000);
  route();
})();
