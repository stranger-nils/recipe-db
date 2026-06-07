/* Delade hjälpare, ikoner och småkomponenter för Recept-IDE. */

const cx = (...a) => a.filter(Boolean).join(" ");

// Snygga bråk för halvor/kvartar
function fmtQty(q) {
  if (q == null || q === "") return "";
  const map = { 0.25: "¼", 0.5: "½", 0.75: "¾", 0.33: "⅓", 0.67: "⅔" };
  const whole = Math.floor(q);
  const frac = +(q - whole).toFixed(2);
  if (map[frac]) return (whole ? whole + " " : "") + map[frac];
  return String(q);
}

function currentVersion(recipe) {
  return recipe.versions.find((v) => v.current) || recipe.versions[recipe.versions.length - 1];
}

// LCS-baserad rad-diff för steg
function diffLines(a, b) {
  const n = a.length, m = b.length;
  const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { out.push({ type: "same", a: a[i], b: b[j] }); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push({ type: "del", a: a[i], b: null }); i++; }
    else { out.push({ type: "add", a: null, b: b[j] }); j++; }
  }
  while (i < n) { out.push({ type: "del", a: a[i], b: null }); i++; }
  while (j < m) { out.push({ type: "add", a: null, b: b[j] }); j++; }
  return out;
}

// Ingrediens-diff: aligna på namn
function ingKey(x) { return x.name.toLowerCase(); }
function ingEqual(x, y) {
  return x.qty === y.qty && x.unit === y.unit && (x.note || "") === (y.note || "");
}
function diffIngredients(a, b) {
  const bMap = new Map(b.map((x) => [ingKey(x), x]));
  const aMap = new Map(a.map((x) => [ingKey(x), x]));
  const rows = [];
  const seen = new Set();
  a.forEach((x) => {
    const y = bMap.get(ingKey(x));
    if (!y) rows.push({ type: "del", a: x, b: null });
    else if (!ingEqual(x, y)) rows.push({ type: "chg", a: x, b: y });
    else rows.push({ type: "same", a: x, b: y });
    seen.add(ingKey(x));
  });
  b.forEach((y) => { if (!seen.has(ingKey(y))) rows.push({ type: "add", a: null, b: y }); });
  return rows;
}

function ingLine(x) {
  if (!x) return "";
  return [fmtQty(x.qty), x.unit, x.name].filter(Boolean).join(" ") + (x.note ? `, ${x.note}` : "");
}

/* ---- Ikoner (enkla streck) ---- */
const Icon = ({ d, size = 18, fill = false, stroke = 1.6, style }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={fill ? "currentColor" : "none"}
    stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" style={style}>
    {Array.isArray(d) ? d.map((p, i) => <path key={i} d={p} />) : <path d={d} />}
  </svg>
);
const icons = {
  recept: ["M12 6c-1.5-1.2-3.6-2-6-2v13c2.4 0 4.5.8 6 2", "M12 6c1.5-1.2 3.6-2 6-2v13c-2.4 0-4.5.8-6 2", "M12 6v13"],
  bibliotek: ["M8 3.5h8V6H8z", "M9.2 6v1.7c-1.4.6-2.2 1.9-2.2 3.5V18a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2v-6.8c0-1.6-.8-2.9-2.2-3.5V6", "M9 13h6"],
  planering: ["M9 4h6v3H9z", "M9 5H7a1 1 0 0 0-1 1v13a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-2", "M9 13l2 2 4-4"],
  chevron: "M9 6l6 6-6 6",
  file: "M7 3h7l4 4v14H7z",
  diff: ["M6 3v12a3 3 0 0 0 3 3h6", "M6 6a2 2 0 1 0 0-4 2 2 0 0 0 0 4z", "M18 22a2 2 0 1 0 0-4 2 2 0 0 0 0 4z", "M9 9l3-3 3 3M12 6v6"],
  close: "M6 6l12 12M18 6L6 18",
  plus: "M12 5v14M5 12h14",
  search: ["M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z", "M21 21l-4-4"],
  pin: "M9 4h6l-1 6 3 3H7l3-3-1-6zM12 16v4",
  print: ["M7 9V3h10v6", "M7 18H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2", "M7 14h10v6H7z"],
  copy: ["M9 9h10v10H9z", "M5 15V5h10"],
  dot: "M12 12h.01",
  check: "M5 12l5 5L20 7",
  clock: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z", "M12 7v5l3 2"],
  users: ["M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0z", "M3 21v-1a6 6 0 0 1 12 0v1", "M17 14a6 6 0 0 1 4 6"],
  layers: ["M12 3l9 5-9 5-9-5 9-5z", "M3 13l9 5 9-5"],
  folder: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z",
  cmd: "M9 9a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v6a3 3 0 1 0 3 3H6a3 3 0 1 0 3-3V9z",
  filter: "M3 5h18l-7 8v6l-4 2v-8L3 5z",
  arrow: "M5 12h14M13 6l6 6-6 6",
};
const Ic = ({ name, ...p }) => <Icon d={icons[name]} {...p} />;

Object.assign(window, {
  cx, fmtQty, currentVersion, diffLines, diffIngredients, ingLine, ingKey, Icon, Ic, icons,
});
