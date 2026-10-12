const $ = (id) => document.getElementById(id);
const filters = { status: $("status"), tag: $("tag"), country: $("country"), search: $("search") };
const regions = new Intl.DisplayNames(["en"], { type: "region" });
const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });
const deadlineFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

let cfps = [];

// Recomputed here rather than trusted from the file, so a deadline that passed since the
// last build shows as closed.
function statusOf(cfp, now) {
  if (!cfp.cfp_close_utc || now > new Date(cfp.cfp_close_utc)) return "closed";
  if (cfp.cfp_open && now.toISOString().slice(0, 10) < cfp.cfp_open) return "upcoming";
  return "open";
}

function countryName(code) {
  try {
    return regions.of(code);
  } catch {
    return code;
  }
}

function where(cfp) {
  if (cfp.online) return "Online";
  return (cfp.location ?? "").split(",").slice(-2).join(",").trim();
}

function timeLeft(close, now) {
  const hours = (close - now) / 36e5;
  if (hours < 0) return "";
  if (hours < 48) return `${Math.max(1, Math.round(hours))}h left`;
  return `${Math.round(hours / 24)} days left`;
}

function cell(row, ...children) {
  const td = row.insertCell();
  td.append(...children);
  return td;
}

function element(tag, text, attributes = {}) {
  const node = Object.assign(document.createElement(tag), attributes);
  node.textContent = text;
  return node;
}

function fill(select, entries) {
  for (const [value, label] of entries) select.append(new Option(label, value));
}

function render() {
  const now = new Date();
  const query = filters.search.value.trim().toLowerCase();
  const shown = cfps.filter(
    (cfp) =>
      (!filters.status.value || statusOf(cfp, now) === filters.status.value) &&
      (!filters.tag.value || cfp.tags.includes(filters.tag.value)) &&
      (!filters.country.value ||
        (filters.country.value === "online" ? cfp.online : cfp.country === filters.country.value)) &&
      (!query || `${cfp.name} ${cfp.location ?? ""}`.toLowerCase().includes(query)),
  );

  const rows = $("rows");
  rows.replaceChildren();
  for (const cfp of shown) {
    const row = rows.insertRow();
    cell(row, element("a", cfp.name, { href: cfp.url, rel: "noopener" }));
    if (cfp.cfp_close_utc) {
      const close = new Date(cfp.cfp_close_utc);
      const left = timeLeft(close, now);
      cell(row, deadlineFormat.format(close), ...(left ? [element("small", left)] : []));
    } else {
      cell(row, "");
    }
    cell(row, cfp.event_start ? dateFormat.format(new Date(`${cfp.event_start}T00:00`)) : "");
    cell(row, where(cfp));
    cell(row, ...cfp.tags.map((tag) => element("span", tag, { className: "tag" })));
  }
  $("count").textContent = `${shown.length} of ${cfps.length} CFPs`;

  const params = new URLSearchParams();
  for (const [key, input] of Object.entries(filters)) {
    if (input.value && !(key === "status" && input.value === "open")) params.set(key, input.value);
  }
  history.replaceState(null, "", params.size ? `?${params}` : location.pathname);
}

async function start() {
  const response = await fetch("api/active.json");
  if (!response.ok) throw new Error(`api/active.json: ${response.status}`);
  const data = await response.json();
  cfps = data.cfps;

  const tags = [...new Set(cfps.flatMap((cfp) => cfp.tags))].sort();
  const codes = [...new Set(cfps.map((cfp) => cfp.country).filter(Boolean))];
  fill(filters.tag, tags.map((tag) => [tag, tag]));
  fill(filters.country, [
    ["online", "Online"],
    ...codes.map((code) => [code, countryName(code)]).sort((a, b) => a[1].localeCompare(b[1])),
  ]);

  const params = new URLSearchParams(location.search);
  for (const [key, input] of Object.entries(filters)) {
    if (params.has(key)) input.value = params.get(key);
  }
  $("generated").textContent = `Last update ${deadlineFormat.format(new Date(data.generated_at))}.`;
  $("filters").addEventListener("input", render);
  $("filters").addEventListener("submit", (event) => event.preventDefault());
  render();
}

start().catch((error) => {
  $("count").textContent = `Could not load CFPs: ${error.message}`;
});
