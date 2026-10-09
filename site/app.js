// Renders data/signals.json. All data-derived text goes through textContent;
// links are restricted to http(s). The data is LLM- and third-party-derived.

// Minutes to midnight shown on the clock for each status. The only place this mapping lives.
const MINUTES_TO_MIDNIGHT = { accelerating: 2, unclear: 7, stabilizing: 15 };

const STATUS = {
  accelerating: { label: "Accelerating", glyph: "▲" },
  stabilizing: { label: "Stabilizing", glyph: "▼" },
  unclear: { label: "Unclear", glyph: "?" },
};

const SVG_NS = "http://www.w3.org/2000/svg";
const PERIOD_RE = /^(\d{4})-(\d{2})$/;

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const c of children) if (c != null) node.append(c);
  return node;
}

function svg(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

function safeUrl(u) {
  try {
    const url = new URL(u);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

function periodDate(p) {
  const m = String(p).match(PERIOD_RE);
  return m ? new Date(Date.UTC(+m[1], +m[2] - 1, 1)) : null;
}

function formatPeriod(p, month = "long") {
  const d = periodDate(p);
  if (!d) return String(p);
  return d.toLocaleDateString("en-US", { month, year: month === "long" ? "numeric" : "2-digit", timeZone: "UTC" });
}

function formatDate(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return String(iso);
  return d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });
}

function knownStatus(s) {
  return Object.hasOwn(STATUS, s) ? s : null;
}

// Clock face. status null → no hands.
function dial(status, label) {
  const box = el("div", { class: "dial" });
  const s = svg("svg", { viewBox: "0 0 120 120", role: "img", "aria-label": label });
  const cx = 60, cy = 60, r = 54;
  const rad = (d) => (d * Math.PI) / 180;
  s.append(svg("circle", { class: "face", cx, cy, r }));
  for (let i = 0; i < 60; i += 5) {
    const a = rad(i * 6);
    const major = i % 15 === 0;
    const r1 = major ? r - 11 : r - 7;
    s.append(svg("line", {
      class: major ? "tick major" : "tick",
      x1: cx + r1 * Math.sin(a), y1: cy - r1 * Math.cos(a),
      x2: cx + (r - 3) * Math.sin(a), y2: cy - (r - 3) * Math.cos(a),
    }));
  }
  if (status) {
    const min = MINUTES_TO_MIDNIGHT[status];
    const minuteDeg = (60 - min) * 6;
    const hourDeg = (11 + (60 - min) / 60) * 30;
    // Wedge from the minute hand to midnight.
    const wr = r - 4;
    const sx = cx + wr * Math.sin(rad(minuteDeg)), sy = cy - wr * Math.cos(rad(minuteDeg));
    s.append(svg("path", { class: "wedge", d: `M${cx},${cy} L${sx},${sy} A${wr},${wr} 0 0 1 ${cx},${cy - wr} Z` }));
    const hand = (deg, len, cls) => svg("line", {
      class: cls, x1: cx, y1: cy,
      x2: cx + len * Math.sin(rad(deg)), y2: cy - len * Math.cos(rad(deg)),
    });
    s.append(hand(hourDeg, 30, "hand hour"));
    s.append(hand(minuteDeg, 46, status === "unclear" ? "hand minute dashed" : "hand minute"));
    s.append(svg("circle", { class: "hub", cx, cy, r: 3.5 }));
  } else {
    const t = svg("text", { class: "empty-label", x: cx, y: cy + 3 });
    t.textContent = "NO READING";
    s.append(t);
  }
  box.append(s);
  return box;
}

function dialLabel(name, status) {
  if (!status) return `${name}: no reading`;
  return `${name}: ${STATUS[status].label}. Clock reads ${MINUTES_TO_MIDNIGHT[status]} minutes to midnight.`;
}

function statusLine(status) {
  if (!status) return el("div", { class: "status", text: "No reading" });
  return el("div", { class: "status" },
    el("span", { "aria-hidden": "true", text: STATUS[status].glyph }),
    el("span", { text: STATUS[status].label }));
}

// Overall dial. `overall` is null until the aggregate rule is defined.
function renderOverall(overall) {
  const box = document.getElementById("overall");
  box.replaceChildren();
  const status = overall ? knownStatus(overall.status) : null;
  const body = el("div", {}, el("h2", { text: "Overall" }));
  if (status) {
    box.dataset.status = status;
    body.append(statusLine(status));
    if (overall.justification) body.append(el("p", { class: "note", text: String(overall.justification) }));
  } else {
    body.append(el("p", { text: "Not defined yet" }));
    body.append(el("p", { class: "note", text: "The overall reading will be defined after the five signals have produced real data." }));
  }
  box.append(dial(status, dialLabel("Overall", status)), body);
}

function renderCard(signal, entries, periods) {
  const byPeriod = new Map(entries.map((e) => [e.period, e]));
  const latest = entries.length ? entries.reduce((a, b) => (b.period > a.period ? b : a)) : null;
  const status = latest ? knownStatus(latest.status) : null;
  const name = String(signal.name ?? signal.id);
  const runLabel = (e) => (e.run === "scheduled" ? "scheduled" : "backfilled");

  const card = el("article", { class: "card", "aria-labelledby": `sig-${signal.id}` });
  if (status) card.dataset.status = status;

  card.append(el("div", { class: "card-head" },
    el("h3", { id: `sig-${signal.id}`, text: name }),
    latest ? el("span", { class: "period", text: formatPeriod(latest.period) }) : null));

  const info = el("div", {}, statusLine(status));
  if (latest) {
    const c = Number(latest.confidence);
    const conf = Number.isInteger(c) && c >= 1 && c <= 5 ? `${c}/5` : "unknown";
    info.append(el("p", { class: "meta-line", text: `Confidence ${conf}` }));
    info.append(el("p", { class: "meta-line", text: latest.run === "scheduled" ? "Monthly run" : "Backfilled" }));
    info.append(el("p", { class: "meta-line model", text: String(latest.model ?? "model unknown") }));
  }
  card.append(el("div", { class: "reading" }, dial(status, dialLabel(name, status)), info));

  card.append(el("p", { class: "justification", text: latest ? String(latest.justification ?? "") : "No reading yet for this signal." }));

  if (periods.length) {
    const strip = el("ol", { class: "strip", "aria-label": `${name} history, oldest to newest` });
    for (const p of periods) {
      const e = byPeriod.get(p);
      const st = e ? knownStatus(e.status) : null;
      const mark = el("li", { class: st ? "mark" : "mark none" });
      if (st) {
        mark.dataset.status = st;
        mark.dataset.run = e.run === "scheduled" ? "scheduled" : "backfill";
        mark.textContent = STATUS[st].glyph;
        mark.title = `${formatPeriod(p)}: ${STATUS[st].label} (${runLabel(e)})`;
      } else {
        mark.textContent = "–";
        mark.title = `${formatPeriod(p)}: no reading`;
      }
      mark.setAttribute("aria-label", mark.title);
      strip.append(mark);
    }
    card.append(el("div", { class: "history" },
      el("span", { class: "history-label", text: "History" }),
      el("div", { class: "strip-box" }, strip,
        el("div", { class: "strip-axis", "aria-hidden": "true" },
          el("span", { text: formatPeriod(periods[0], "short") }),
          el("span", { text: formatPeriod(periods[periods.length - 1], "short") })))));
  }

  const sources = Array.isArray(latest?.sources) ? latest.sources : [];
  if (sources.length) {
    const ul = el("ul");
    for (const s of sources) {
      const title = String(s?.title ?? s?.url ?? "Source");
      const url = safeUrl(s?.url);
      ul.append(el("li", {}, url ? el("a", { href: url, rel: "noopener noreferrer", text: title }) : el("span", { text: title })));
    }
    card.append(el("div", { class: "sources" }, el("h4", { text: "Sources" }), ul));
  }
  return card;
}

function renderDashboard(data) {
  document.getElementById("sample-banner").hidden = !data.sample;
  document.getElementById("updated").textContent = data.updated ? `Last updated ${formatDate(data.updated)}` : "Not updated yet";

  renderOverall(data.overall ?? null);

  const entries = (Array.isArray(data.entries) ? data.entries : []).filter((e) => PERIOD_RE.test(e?.period));
  const periods = [...new Set(entries.map((e) => e.period))].sort().slice(-12);
  document.getElementById("signals").replaceChildren(...(data.signals ?? []).map((s) =>
    renderCard(s, entries.filter((e) => e.signal === s.id), periods)));
}

function renderDefinitions(data) {
  const dl = document.getElementById("definitions");
  dl.replaceChildren();
  for (const s of data.signals ?? []) {
    dl.append(el("dt", { text: String(s.name ?? s.id) }));
    dl.append(el("dd", {},
      el("p", {}, el("span", { class: "tag a", text: "▲ Accelerating: " }), String(s.accelerating ?? "")),
      el("p", {}, el("span", { class: "tag s", text: "▼ Stabilizing: " }), String(s.stabilizing ?? ""))));
  }
}

async function main() {
  const page = document.body.dataset.page;
  if (page !== "dashboard" && page !== "signals") return;
  try {
    const res = await fetch("data/signals.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (page === "dashboard") renderDashboard(data);
    else renderDefinitions(data);
  } catch (err) {
    const target = document.getElementById(page === "dashboard" ? "signals" : "definitions");
    target.replaceWith(el("p", { class: "error", role: "alert", text: `The signal data could not be loaded (${err.message}). Try again later.` }));
  }
}

main();
