"use strict";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]; // index = weekday number the API uses (0 = Monday)
const SERVICES = ["CLEANING", "COOKING", "DISHWASHING", "LAUNDRY", "BABYSITTING"];
const GENDERS = ["FEMALE", "MALE", "OTHER"];
const METHODS = {
  CARD: { label: "Card", placeholder: "4111111111111111", hint: "12 to 19 digit card number" },
  UPI: { label: "UPI", placeholder: "asha@upi", hint: "UPI id, for example name@bank" },
  WALLET: { label: "Wallet", placeholder: "wallet-123", hint: "Wallet id" },
};
const DURATIONS = [30, 60, 90, 120, 180, 240];
const SAMPLE_MAIDS = [
  { name: "Asha Rao", locality: "Koramangala", gender: "FEMALE", rating: 4.8, hourlyRates: { CLEANING: 250, COOKING: 300 },
    skills: ["deep-cleaning", "north-indian"], days: [0, 1, 2, 3, 4, 5], start: "08:00", end: "18:00" },
  { name: "Ravi Kumar", locality: "Koramangala", gender: "MALE", rating: 4.2, hourlyRates: { CLEANING: 180, DISHWASHING: 120 },
    skills: ["utensils"], days: [0, 1, 2, 3, 4], start: "09:00", end: "17:00" },
  { name: "Meena Iyer", locality: "Indiranagar", gender: "FEMALE", rating: 4.6, hourlyRates: { COOKING: 350, BABYSITTING: 280 },
    skills: ["south-indian", "infant-care"], days: [1, 2, 3, 4, 5, 6], start: "10:00", end: "20:00" },
];

const state = { customer: "", maids: new Map(), localities: new Set() };

/* ---------- small helpers ---------- */

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
const money = (n) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(n));
const pad = (n) => String(n).padStart(2, "0");
const hhmm = (t) => String(t).slice(0, 5);

// The API sends naive local date-times ("2030-01-08T10:00:00"); build the Date from parts so no timezone shift happens.
function parseLocal(iso) {
  const [d, t] = iso.split("T");
  const [y, m, day] = d.split("-").map(Number);
  const [hh, mm] = t.split(":").map(Number);
  return new Date(y, m - 1, day, hh, mm);
}
function fmtRange(start, end) {
  const s = parseLocal(start), e = parseLocal(end);
  const day = s.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  return `${day}, ${pad(s.getHours())}:${pad(s.getMinutes())} to ${pad(e.getHours())}:${pad(e.getMinutes())}`;
}
const todayISO = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
const tomorrowISO = () => { const d = new Date(); d.setDate(d.getDate() + 1); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
const newKey = () => (window.crypto && crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2));

class ApiError extends Error {
  constructor(message, code, status) { super(message); this.code = code; this.status = status; }
}

async function api(path, { method = "GET", body, headers = {} } = {}) {
  const res = await fetch(path, {
    method,
    headers: { ...(body ? { "Content-Type": "application/json" } : {}), ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* empty body */ }
  if (!res.ok) throw new ApiError((data && data.message) || `Request failed (${res.status})`, data && data.code, res.status);
  return data;
}

function toast(message, kind) {
  const t = el("div", { class: "toast" + (kind === "err" ? " err" : "") }, message);
  document.getElementById("toasts").append(t);
  setTimeout(() => t.remove(), kind === "err" ? 6000 : 3800);
}

async function getMaid(id) {
  if (!state.maids.has(id)) state.maids.set(id, await api(`/api/maids/${id}`));
  return state.maids.get(id);
}

function compressDays(indexes) {
  const sorted = [...new Set(indexes)].sort((a, b) => a - b);
  const parts = [];
  for (let i = 0; i < sorted.length;) {
    let j = i;
    while (j + 1 < sorted.length && sorted[j + 1] === sorted[j] + 1) j++;
    parts.push(j - i >= 2 ? `${DAYS[sorted[i]]} to ${DAYS[sorted[j]]}` : sorted.slice(i, j + 1).map((d) => DAYS[d]).join(", "));
    i = j + 1;
  }
  return parts.join(", ");
}

function hoursSummary(windows) {
  const groups = new Map();
  for (const w of windows) {
    const key = `${hhmm(w.start)} to ${hhmm(w.end)}`;
    const dayIndex = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"].indexOf(w.day);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(dayIndex);
  }
  return [...groups].map(([range, days]) => `${compressDays(days)} ${range}`).join(" · ");
}

function field(labelText, input, hint) {
  return el("label", { class: "field" }, el("span", null, labelText), input, hint ? el("span", { class: "hint" }, hint) : null);
}
function select(id, options, value) {
  return el("select", { id }, options.map(([v, text]) => el("option", { value: v, selected: v === value }, text)));
}

/* ---------- routing ---------- */

const routes = { find: renderFind, bookings: renderBookings, add: renderAdd };

function route() {
  const name = (location.hash || "#find").slice(1);
  const tab = routes[name] ? name : "find";
  document.querySelectorAll(".tabs a").forEach((a) => {
    if (a.dataset.tab === tab) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  const view = document.getElementById("view");
  view.replaceChildren();
  routes[tab](view);
}

/* ---------- find a maid ---------- */

function renderFind(view) {
  view.append(el("div", { class: "page-head" },
    el("h1", null, "Find a maid"),
    el("p", null, "Search by area and service. Add a date and start time to see only the maids who are free then.")));

  const form = el("form", { class: "panel", id: "search-form" },
    el("div", { class: "form-grid" },
      field("Area", el("input", { id: "f-locality", type: "text", placeholder: "Koramangala", list: "localities", autocomplete: "off" }),
        "Exact area name; suggestions come from maids on the platform"),
      field("Service", select("f-service", [["", "Any service"], ...SERVICES.map((s) => [s, label(s)])], "")),
      field("Date", el("input", { id: "f-date", type: "date", min: todayISO() })),
      field("Start time", el("input", { id: "f-time", type: "time" })),
      field("Duration", select("f-duration", DURATIONS.map((m) => [String(m), `${m} minutes`]), "60")),
      field("Min rating", select("f-rating", [["", "Any"], ["3", "3.0+"], ["4", "4.0+"], ["4.5", "4.5+"]], "")),
      field("Max rate per hour (₹)", el("input", { id: "f-rate", type: "number", min: "0", step: "any", placeholder: "No limit" })),
      field("Gender", select("f-gender", [["", "No preference"], ...GENDERS.map((g) => [g, label(g)])], "")),
      field("Skills", el("input", { id: "f-skills", type: "text", placeholder: "deep-cleaning, utensils" }), "Comma separated")),
    el("div", { class: "actions" },
      el("button", { class: "btn primary", type: "submit" }, "Search"),
      el("button", { class: "btn", type: "button", id: "f-reset" }, "Clear")));
  const results = el("div", { id: "results" });
  view.append(form, el("datalist", { id: "localities" }), results);

  form.addEventListener("submit", (e) => { e.preventDefault(); runSearch(); });
  form.querySelector("#f-reset").addEventListener("click", () => { form.reset(); runSearch(); });
  runSearch();
}

function searchParams() {
  const v = (id) => document.getElementById(id).value.trim();
  const p = new URLSearchParams();
  const map = { locality: "f-locality", serviceType: "f-service", date: "f-date", startTime: "f-time",
    minRating: "f-rating", maxHourlyRate: "f-rate", gender: "f-gender" };
  for (const [name, id] of Object.entries(map)) if (v(id)) p.set(name, v(id));
  if (v("f-date") && v("f-time")) p.set("durationMinutes", v("f-duration"));
  v("f-skills").split(",").map((s) => s.trim()).filter(Boolean).forEach((s) => p.append("skills", s));
  return p;
}

async function runSearch() {
  const box = document.getElementById("results");
  box.replaceChildren(el("p", { class: "sub" }, "Searching…"));
  const date = document.getElementById("f-date").value, time = document.getElementById("f-time").value;
  if ((date && !time) || (!date && time)) {
    box.replaceChildren(el("div", { class: "banner info" }, "Pick both a date and a start time, or leave both empty."));
    return;
  }
  try {
    const maids = await api(`/api/maids/search?${searchParams()}`);
    maids.forEach((m) => { state.maids.set(m.id, m); state.localities.add(m.locality); });
    document.getElementById("localities").replaceChildren(...[...state.localities].sort().map((l) => el("option", { value: l })));
    renderResults(box, maids, Boolean(date && time));
  } catch (err) {
    box.replaceChildren(el("div", { class: "banner err", role: "alert" }, err.message));
  }
}

function renderResults(box, maids, timed) {
  const head = el("div", { class: "results-head" },
    el("h2", null, `${maids.length} ${maids.length === 1 ? "maid" : "maids"}${timed ? " available" : ""}`),
    timed ? el("span", { class: "sub" }, "Showing only maids free for that time") : null);
  if (!maids.length) {
    box.replaceChildren(head, el("div", { class: "panel empty" },
      el("p", null, timed ? "No maid is free at that time. Try another time or relax a filter."
        : "No maids match yet. Add one, or load a few sample maids to try the flow."),
      el("div", { class: "actions" },
        el("a", { class: "btn", href: "#add" }, "Add a maid"),
        el("button", { class: "btn primary", type: "button", id: "seed-btn", onclick: seedMaids }, "Load sample maids"))));
    return;
  }
  box.replaceChildren(head, el("div", { class: "grid" }, maids.map(maidCard)));
}

function maidCard(m) {
  return el("article", { class: "panel maid", "data-maid": m.name },
    el("div", { class: "maid-top" },
      el("div", { class: "avatar", "aria-hidden": "true" }, m.name.charAt(0).toUpperCase()),
      el("div", null,
        el("h3", null, m.name),
        el("div", { class: "sub" }, `${m.locality} · ${label(m.gender)} · ★ ${Number(m.rating).toFixed(1)}`))),
    el("div", { class: "chips" }, Object.entries(m.hourlyRates).map(([s, r]) => el("span", { class: "chip rate" }, `${label(s)} ${money(r)}/h`))),
    m.skills.length ? el("div", { class: "chips" }, m.skills.map((s) => el("span", { class: "chip" }, s))) : null,
    el("div", { class: "hours" }, hoursSummary(m.availability)),
    el("div", { class: "actions" }, el("button", { class: "btn primary", type: "button", onclick: () => openBooking(m) }, `Book ${m.name.split(" ")[0]}`)));
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
    runSearch();
  } catch (err) {
    toast(err.message, "err");
    if (btn) btn.disabled = false;
  }
}

/* ---------- dialog plumbing ---------- */

const dlg = document.getElementById("dlg");
document.getElementById("dlg-close").addEventListener("click", () => dlg.close());
dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
dlg.addEventListener("close", () => { if (location.hash === "#bookings") renderBookingsList(); });

function showDialog(title, ...content) {
  document.getElementById("dlg-title").textContent = title;
  document.getElementById("dlg-body").replaceChildren(...content);
  if (!dlg.open) dlg.showModal();
}

/* ---------- booking dialog ---------- */

function openBooking(maid) {
  const services = Object.keys(maid.hourlyRates);
  const searchedDate = document.getElementById("f-date") ? document.getElementById("f-date").value : "";
  const searchedTime = document.getElementById("f-time") ? document.getElementById("f-time").value : "";
  const searchedService = document.getElementById("f-service") ? document.getElementById("f-service").value : "";
  const defaultType = "SCHEDULED";

  const typeRadio = (value, text) => el("label", null,
    el("input", { type: "radio", name: "bookingType", value, checked: value === defaultType }), el("span", null, text));
  const dayBox = (i) => el("label", null, el("input", { type: "checkbox", name: "day", value: String(i) }), el("span", null, DAYS[i]));

  const scheduled = el("div", { id: "sched-fields", class: "form-grid" },
    field("Date", el("input", { id: "b-date", type: "date", min: todayISO(), value: searchedDate || tomorrowISO(), required: true })),
    field("Start time", el("input", { id: "b-time", type: "time", value: searchedTime || "10:00", required: true })));
  const recurring = el("div", { id: "rec-fields", class: "stack", hidden: true },
    el("fieldset", null, el("legend", null, "Repeat on"), el("div", { class: "days" }, DAYS.map((_, i) => dayBox(i)))),
    el("div", { class: "form-grid" },
      field("First date", el("input", { id: "b-rdate", type: "date", min: todayISO(), value: searchedDate || tomorrowISO() })),
      field("Start time", el("input", { id: "b-rtime", type: "time", value: searchedTime || "10:00" })),
      field("Number of visits", el("input", { id: "b-count", type: "number", min: "1", max: "52", value: "4" }))));

  const estimate = el("div", { class: "summary", id: "estimate", "aria-live": "polite" });
  const errorBox = el("div", { id: "b-error" });
  const form = el("form", { class: "stack", id: "booking-form" },
    el("p", { class: "sub", style: "margin:0" }, `${maid.name} · ${maid.locality} · ${hoursSummary(maid.availability)}`),
    field("Service", select("b-service", services.map((s) => [s, `${label(s)} (${money(maid.hourlyRates[s])}/h)`]),
      services.includes(searchedService) ? searchedService : services[0])),
    el("fieldset", null, el("legend", null, "Booking type"),
      el("div", { class: "seg" }, typeRadio("INSTANT", "Instant"), typeRadio("SCHEDULED", "Scheduled"), typeRadio("RECURRING", "Recurring"))),
    el("div", { id: "instant-note", class: "banner info", hidden: true }, "Starts right now. The maid must be working at this moment."),
    scheduled, recurring,
    field("Duration", select("b-duration", DURATIONS.map((m) => [String(m), `${m} minutes`]), "60")),
    estimate,
    errorBox,
    el("p", { class: "hint", style: "margin:0" }, "Your slot is held for you until you pay or cancel."),
    el("div", { class: "actions", style: "margin:0" },
      el("button", { class: "btn primary", type: "submit", id: "b-submit" }, "Reserve and continue to payment"),
      el("button", { class: "btn", type: "button", onclick: () => dlg.close() }, "Cancel")));

  function currentType() { return form.querySelector("input[name=bookingType]:checked").value; }
  function refresh() {
    const type = currentType();
    document.getElementById("sched-fields").hidden = type !== "SCHEDULED";
    document.getElementById("rec-fields").hidden = type !== "RECURRING";
    document.getElementById("instant-note").hidden = type !== "INSTANT";
    const service = document.getElementById("b-service").value;
    const minutes = Number(document.getElementById("b-duration").value);
    const perVisit = (maid.hourlyRates[service] * minutes) / 60;
    const visits = type === "RECURRING" ? Number(document.getElementById("b-count").value) || 0 : 1;
    estimate.replaceChildren(
      el("div", { class: "row" }, el("span", null, "Per visit"), el("span", null, money(perVisit))),
      visits > 1 ? el("div", { class: "row" }, el("span", null, `${visits} visits`), el("span", null, "")) : null,
      el("div", { class: "row total" }, el("span", null, "Estimated total"), el("span", null, money(perVisit * visits))));
  }
  form.addEventListener("input", refresh);
  form.addEventListener("change", refresh);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.replaceChildren();
    if (!state.customer) { errorBox.append(el("div", { class: "banner err", role: "alert" }, "Enter your customer id at the top of the page first.")); return; }
    const type = currentType();
    const body = { customerId: state.customer, maidId: maid.id, serviceType: document.getElementById("b-service").value,
      bookingType: type, durationMinutes: Number(document.getElementById("b-duration").value) };
    if (type === "SCHEDULED") body.startDateTime = `${document.getElementById("b-date").value}T${document.getElementById("b-time").value}`;
    if (type === "RECURRING") {
      const days = [...form.querySelectorAll("input[name=day]:checked")].map((c) => Number(c.value));
      if (!days.length) { errorBox.append(el("div", { class: "banner err", role: "alert" }, "Choose at least one day to repeat on.")); return; }
      body.recurrence = { daysOfWeek: days, startDate: document.getElementById("b-rdate").value,
        startTime: document.getElementById("b-rtime").value, occurrences: Number(document.getElementById("b-count").value) };
    }
    const submit = document.getElementById("b-submit");
    submit.disabled = true;
    try {
      const booking = await api("/api/bookings", { method: "POST", body });
      toast("Slot reserved. Complete payment to confirm.");
      openPayment(booking);
    } catch (err) {
      errorBox.append(el("div", { class: "banner err", role: "alert" }, err.message));
      submit.disabled = false;
    }
  });
  showDialog(`Book ${maid.name}`, form);
  refresh();
}

/* ---------- payment dialog ---------- */

async function openPayment(booking, preferredOccurrenceId) {
  const maid = await getMaid(booking.maidId).catch(() => null);
  const unpaid = booking.occurrences.filter((o) => o.status === "PENDING_PAYMENT");
  const maidName = maid ? maid.name : "your maid";
  if (!unpaid.length) {
    showDialog("Payment", el("div", { class: "banner ok" }, "Nothing left to pay on this booking."),
      el("div", { class: "actions" }, el("button", { class: "btn", type: "button", onclick: () => dlg.close() }, "Close")));
    return;
  }

  let idempotencyKey = newKey();
  const errorBox = el("div", { id: "p-error" });
  const scopeValue = () => (document.querySelector("input[name=scope]:checked") || {}).value;
  const amountFor = () => {
    const scope = scopeValue();
    if (scope === "ALL") return unpaid.reduce((sum, o) => sum + Number(o.price), 0);
    const occ = unpaid.find((o) => o.id === document.getElementById("p-occ").value);
    return occ ? Number(occ.price) : 0;
  };
  const payBtn = el("button", { class: "btn primary", type: "submit", id: "p-submit" }, "Pay");
  const updatePayLabel = () => {
    payBtn.textContent = `Pay ${money(amountFor())}`;
    document.getElementById("p-occ").disabled = scopeValue() === "ALL";
  };

  const scope = unpaid.length > 1
    ? el("fieldset", null, el("legend", null, "What to pay"),
      el("div", { class: "seg" },
        el("label", null, el("input", { type: "radio", name: "scope", value: "ALL", checked: !preferredOccurrenceId }), el("span", null, `All ${unpaid.length} visits`)),
        el("label", null, el("input", { type: "radio", name: "scope", value: "ONE", checked: Boolean(preferredOccurrenceId) }), el("span", null, "One visit"))),
      el("div", { style: "margin-top:8px" }, el("select", { id: "p-occ", "aria-label": "Visit to pay" },
        unpaid.map((o) => el("option", { value: o.id, selected: o.id === preferredOccurrenceId }, `${fmtRange(o.start, o.end)} · ${money(o.price)}`)))))
    : el("div", null,
      el("input", { type: "radio", name: "scope", value: "ONE", checked: true, hidden: true }),
      el("select", { id: "p-occ", hidden: true }, el("option", { value: unpaid[0].id }, unpaid[0].id)));

  const method = select("p-method", Object.entries(METHODS).map(([k, v]) => [k, v.label]), "UPI");
  const instrument = el("input", { id: "p-instrument", type: "text", autocomplete: "off", spellcheck: "false", required: true });
  const instrumentHint = el("span", { class: "hint", id: "p-hint" });
  const syncMethod = () => {
    const m = METHODS[method.value];
    instrument.placeholder = m.placeholder;
    instrumentHint.textContent = `${m.hint}. Demo gateway: anything starting with "fail" is declined.`;
  };

  const form = el("form", { class: "stack", id: "payment-form" },
    el("div", { class: "summary" },
      el("div", { class: "row" }, el("strong", null, `${label(booking.serviceType)} with ${maidName}`), el("span", { class: `pill ${booking.status}` }, label(booking.status))),
      booking.occurrences.map((o) => el("div", { class: "row" }, el("span", { class: o.status === "CANCELLED" ? "cancelled" : "" }, fmtRange(o.start, o.end)),
        el("span", null, `${money(o.price)} · ${label(o.status)}`)))),
    scope,
    el("div", { class: "form-grid" },
      field("Payment method", method),
      field("Payment details", instrument, null)),
    instrumentHint,
    errorBox,
    el("div", { class: "actions", style: "margin:0" }, payBtn,
      el("button", { class: "btn", type: "button", onclick: () => dlg.close() }, "Pay later")));
  showDialog("Complete payment", form);
  syncMethod(); updatePayLabel();
  method.addEventListener("change", syncMethod);
  form.addEventListener("change", updatePayLabel);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.replaceChildren();
    payBtn.disabled = true;
    const body = { method: method.value, instrument: instrument.value.trim() };
    if (scopeValue() === "ONE") body.occurrenceId = document.getElementById("p-occ").value;
    try {
      const payments = await api(`/api/bookings/${booking.id}/payments`, { method: "POST", body, headers: { "Idempotency-Key": idempotencyKey } });
      idempotencyKey = newKey();
      const fresh = await api(`/api/bookings/${booking.id}`);
      showPaid(fresh, payments, maidName);
    } catch (err) {
      errorBox.append(el("div", { class: "banner err", role: "alert" }, err.message));
      payBtn.disabled = false;
    }
  });
}

function showPaid(booking, payments, maidName) {
  const total = payments.reduce((s, p) => s + Number(p.amount), 0);
  const stillUnpaid = booking.occurrences.filter((o) => o.status === "PENDING_PAYMENT").length;
  showDialog("Payment received",
    el("div", { class: "done" },
      el("div", { class: "tick", "aria-hidden": "true" }, "✓"),
      el("h3", null, stillUnpaid ? "Visit paid" : "Booking confirmed"),
      el("p", { class: "sub" }, `${money(total)} paid for ${payments.length} ${payments.length === 1 ? "visit" : "visits"} with ${maidName}.` +
        (stillUnpaid ? ` ${stillUnpaid} visit${stillUnpaid === 1 ? "" : "s"} still awaiting payment.` : ""))),
    el("div", { class: "actions", style: "justify-content:center" },
      el("a", { class: "btn primary", href: "#bookings", onclick: () => dlg.close() }, "View my bookings"),
      el("button", { class: "btn", type: "button", onclick: () => dlg.close() }, "Close")));
}

/* ---------- my bookings ---------- */

function renderBookings(view) {
  view.append(el("div", { class: "page-head" },
    el("h1", null, "My bookings"),
    el("p", null, "Everything booked under your customer id. Pay held visits, or cancel one visit or a whole series.")),
    el("div", { id: "bookings-list" }));
  renderBookingsList();
}

async function renderBookingsList() {
  const box = document.getElementById("bookings-list");
  if (!box) return;
  if (!state.customer) { box.replaceChildren(el("div", { class: "panel empty" }, "Enter your customer id at the top to see your bookings.")); return; }
  box.replaceChildren(el("p", { class: "sub" }, "Loading…"));
  try {
    const bookings = await api(`/api/bookings?customerId=${encodeURIComponent(state.customer)}`);
    await Promise.all(bookings.map((b) => getMaid(b.maidId).catch(() => null)));
    if (!bookings.length) {
      box.replaceChildren(el("div", { class: "panel empty" }, el("p", null, "No bookings yet."),
        el("div", { class: "actions" }, el("a", { class: "btn primary", href: "#find" }, "Find a maid"))));
      return;
    }
    box.replaceChildren(...bookings.map(bookingCard));
  } catch (err) {
    box.replaceChildren(el("div", { class: "banner err", role: "alert" }, err.message));
  }
}

function armedButton(text, armedText, action, extraClass) {
  const btn = el("button", { class: `btn small danger ${extraClass || ""}`, type: "button" }, text);
  let timer = null;
  btn.addEventListener("click", () => {
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

async function cancelBooking(bookingId, occurrenceId) {
  try {
    const qs = occurrenceId ? `?occurrenceId=${encodeURIComponent(occurrenceId)}` : "";
    const result = await api(`/api/bookings/${bookingId}/cancel${qs}`, { method: "POST" });
    const n = result.cancelledOccurrenceIds.length;
    toast(`Cancelled ${n} ${n === 1 ? "visit" : "visits"}. Refund ${money(result.totalRefund)}.`);
  } catch (err) {
    toast(err.message, "err");
  }
  renderBookingsList();
}

function bookingCard(b) {
  const maid = state.maids.get(b.maidId);
  const active = b.occurrences.filter((o) => o.status !== "CANCELLED");
  const unpaid = b.occurrences.filter((o) => o.status === "PENDING_PAYMENT");
  const multi = b.occurrences.length > 1;
  return el("article", { class: "panel booking", "data-booking": b.id },
    el("div", { class: "booking-head" },
      el("h3", null, `${label(b.serviceType)} with ${maid ? maid.name : "maid"}`),
      el("div", { class: "chips" },
        el("span", { class: "chip" }, label(b.bookingType)),
        el("span", { class: `pill ${b.status}` }, label(b.status)))),
    el("ul", { class: "occ" }, b.occurrences.map((o) => el("li", { class: o.status === "CANCELLED" ? "cancelled-row" : "" },
      el("span", { class: "when" + (o.status === "CANCELLED" ? " cancelled" : "") }, fmtRange(o.start, o.end)),
      el("span", { class: "price" }, money(o.price)),
      el("span", { class: `pill ${o.status}` }, label(o.status)),
      o.status === "PENDING_PAYMENT" ? el("button", { class: "btn small primary", type: "button", onclick: () => openPayment(b, o.id) }, "Pay") : null,
      o.status !== "CANCELLED" ? armedButton("Cancel", "Confirm cancel", () => cancelBooking(b.id, o.id)) : null))),
    (unpaid.length > 1 || (multi && active.length > 1)) ? el("div", { class: "actions" },
      unpaid.length > 1 ? el("button", { class: "btn small primary", type: "button", onclick: () => openPayment(b) }, `Pay all ${unpaid.length} unpaid`) : null,
      active.length > 1 ? armedButton("Cancel whole series", "Confirm cancel series", () => cancelBooking(b.id, null)) : null) : null);
}

/* ---------- add a maid ---------- */

function renderAdd(view) {
  view.append(el("div", { class: "page-head" },
    el("h1", null, "Add a maid"),
    el("p", null, "Onboard a maid with the services she offers, her hourly rate for each, and the weekly hours she works.")));

  const serviceRows = SERVICES.map((s, i) => el("div", { class: "service-row" },
    el("label", null, el("input", { type: "checkbox", name: "svc", value: s, checked: i === 0 }), label(s)),
    el("input", { type: "number", min: "1", step: "any", name: `rate-${s}`, value: i === 0 ? "200" : "", "aria-label": `${label(s)} rate per hour`, placeholder: "₹ / hour" })));
  const windowRows = DAYS.map((d, i) => el("div", { class: "window-row" },
    el("label", { class: "day" }, el("input", { type: "checkbox", name: "wday", value: String(i), checked: i < 6 }), d),
    el("input", { type: "time", name: `ws-${i}`, value: "08:00", "aria-label": `${d} start` }),
    el("input", { type: "time", name: `we-${i}`, value: "18:00", "aria-label": `${d} end` })));

  const errorBox = el("div");
  const form = el("form", { class: "panel stack", id: "add-form" },
    el("div", { class: "form-grid" },
      field("Name", el("input", { id: "m-name", type: "text", required: true, maxlength: "80" })),
      field("Area", el("input", { id: "m-locality", type: "text", required: true, maxlength: "80", placeholder: "Koramangala" })),
      field("Gender", select("m-gender", GENDERS.map((g) => [g, label(g)]), "FEMALE")),
      field("Rating (0 to 5)", el("input", { id: "m-rating", type: "number", min: "0", max: "5", step: "any", value: "4.5", required: true })),
      field("Skills", el("input", { id: "m-skills", type: "text", placeholder: "deep-cleaning, utensils" }), "Comma separated")),
    el("fieldset", { class: "stack" }, el("legend", null, "Services and hourly rate"), serviceRows),
    el("fieldset", { class: "stack" }, el("legend", null, "Weekly working hours"), windowRows),
    errorBox,
    el("div", { class: "actions", style: "margin:0" },
      el("button", { class: "btn primary", type: "submit" }, "Add maid"),
      el("button", { class: "btn", type: "button", id: "seed-btn", onclick: seedMaids }, "Add 3 sample maids")));
  view.append(form);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.replaceChildren();
    const fail = (msg) => errorBox.append(el("div", { class: "banner err", role: "alert" }, msg));
    const hourlyRates = {};
    for (const box of form.querySelectorAll("input[name=svc]:checked")) {
      const rate = Number(form.elements[`rate-${box.value}`].value);
      if (!rate || rate <= 0) return fail(`Enter an hourly rate for ${label(box.value)}.`);
      hourlyRates[box.value] = rate;
    }
    if (!Object.keys(hourlyRates).length) return fail("Choose at least one service.");
    const availability = [...form.querySelectorAll("input[name=wday]:checked")].map((c) => ({
      day: Number(c.value), start: form.elements[`ws-${c.value}`].value, end: form.elements[`we-${c.value}`].value }));
    if (!availability.length) return fail("Choose at least one working day.");
    if (availability.some((w) => !w.start || !w.end || w.end <= w.start)) return fail("Each working day needs an end time after its start time.");
    try {
      const maid = await api("/api/maids", { method: "POST", body: {
        name: document.getElementById("m-name").value.trim(), locality: document.getElementById("m-locality").value.trim(),
        gender: document.getElementById("m-gender").value, rating: Number(document.getElementById("m-rating").value), hourlyRates,
        skills: document.getElementById("m-skills").value.split(",").map((s) => s.trim()).filter(Boolean), availability } });
      state.maids.set(maid.id, maid);
      toast(`${maid.name} added`);
      location.hash = "#find";
    } catch (err) {
      fail(err.message);
    }
  });
}

/* ---------- boot ---------- */

(function boot() {
  const input = document.getElementById("customer");
  try { state.customer = localStorage.getItem("mb.customer") || "customer-1"; } catch (e) { state.customer = "customer-1"; }
  input.value = state.customer;
  const applyCustomer = () => {
    const next = input.value.trim();
    if (next === state.customer) return;
    state.customer = next;
    try { localStorage.setItem("mb.customer", next); } catch (e) { /* storage unavailable */ }
    if (location.hash === "#bookings") renderBookingsList();
  };
  input.addEventListener("change", applyCustomer);
  input.addEventListener("blur", applyCustomer);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") applyCustomer(); });
  window.addEventListener("hashchange", route);
  route();
})();
