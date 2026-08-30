#!/usr/bin/env python3
"""
build_plan_page.py — renderar veckomeny-JSON till fristående HTML.

Veckomeny-skillen producerar *data* (plans/<slug>.json). Det här skriptet äger
*utseendet*. Delningen är medveten: sidan ser likadan ut varje vecka, och
designen kan ändras utan att skillen rörs.

Utdata är fristående — inline CSS/JS, ingen backend. Enda externa anropet är
sajtens webbfont; utan nät faller sidan tillbaka på systemets mono. Recepten är serverrenderade (läsbara utan JS); inköpslistan räknas
om i webbläsaren utifrån vilka rätter som är ibockade, och avbockning i butik
sparas i localStorage per slug.

Användning:
    python3 scripts/build_plan_page.py plans/2026-w36.json   # en plan + index
    python3 scripts/build_plan_page.py --all                 # rendera om allt
    python3 scripts/build_plan_page.py --all --plans-dir /annan/plats

Idempotent: samma JSON in ger samma HTML ut. Kör om så ofta du vill.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1"

# Butiksordning. Värdena är exakt de grocery_category som recept-DB:n tillåter
# (CHECK-constraint i ingredient-tabellen) — ordnade efter hur man går genom
# butiken, inte alfabetiskt.
CATEGORY_ORDER = [
    "Frukt och grönt",
    "Färska örter",
    "Kött",
    "Fågel",
    "Fläsk",
    "Fisk",
    "Mejeri",
    "Bageri",
    "Kolhydrater",
    "Baljväxter",
    "Konserver",
    "Smaksättare",
    "Färdiga tillbehör",
    "Frys",
    "Alkohol",
    "Övrigt",
]

CATEGORY_EMOJI = {
    "Frukt och grönt": "🥕",
    "Färska örter": "🌿",
    "Kött": "🥩",
    "Fågel": "🍗",
    "Fläsk": "🥓",
    "Fisk": "🐟",
    "Mejeri": "🥚",
    "Bageri": "🍞",
    "Kolhydrater": "🍚",
    "Baljväxter": "🫘",
    "Konserver": "🥫",
    "Smaksättare": "🧴",
    "Färdiga tillbehör": "🥗",
    "Frys": "🧊",
    "Alkohol": "🍷",
    "Övrigt": "🛒",
}


def fmt_amount(value) -> str:
    """DB:n lagrar mängder som text ("100.0", "0.5"). Visa dem som människor
    skriver dem: heltal utan decimaler, decimaltal med komma."""
    raw = str("" if value is None else value).strip()
    if not raw:
        return ""
    try:
        num = float(raw.replace(",", "."))
    except ValueError:
        return raw
    if abs(num - round(num)) < 1e-9:
        return str(int(round(num)))
    return ("%g" % num).replace(".", ",")


def esc(value) -> str:
    # CRLF från databasen normaliseras — annars skiljer sig det som skrivs från
    # det som läses tillbaka, och write_if_changed tror att allt ändrats.
    text_value = "" if value is None else str(value)
    text_value = text_value.replace("\r\n", "\n").replace("\r", "\n")
    return html.escape(text_value, quote=True)


def _steps(instructions: str) -> list[str]:
    """Delar instruktionstext i steg. Tål både '1. ...'-numrering och radbrytning."""
    out = []
    for raw in (instructions or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        # Strippa ledande numrering — <ol> lägger på egen.
        i = 0
        while i < len(line) and line[i].isdigit():
            i += 1
        if i and i < len(line) and line[i] in ".):":
            line = line[i + 1:].strip()
        if line:
            out.append(line)
    return out


def _dish_meta(dish: dict) -> str:
    bits = []
    for key in ("kitchen", "type"):
        if dish.get(key):
            bits.append(str(dish[key]))
    if dish.get("time"):
        bits.append(str(dish["time"]))
    if dish.get("servings"):
        bits.append(f"{dish['servings']} port")
    return " · ".join(bits)


def render_dish(dish: dict) -> str:
    ings = dish.get("ingredients") or []
    ing_rows = []
    for ing in ings:
        qty = " ".join(x for x in (fmt_amount(ing.get("amount")), str(ing.get("unit") or "").strip()) if x)
        note = f' <span class="i-note">({esc(ing.get("note"))})</span>' if ing.get("note") else ""
        flag = ' <span class="i-new" title="Finns inte i receptdatabasen än">ny</span>' if ing.get("new") else ""
        ing_rows.append(
            f'<li><span class="i-q">{esc(qty)}</span>'
            f'<span class="i-n">{esc(ing.get("name"))}{flag}{note}</span></li>'
        )

    steps = "".join(f"<li>{esc(s)}</li>" for s in _steps(dish.get("instructions")))
    notes = (
        f'<p class="d-notes"><span class="lbl">Noter</span>{esc(dish.get("notes"))}</p>'
        if dish.get("notes") else ""
    )
    why = (
        f'<p class="d-why">{esc(dish.get("why"))}</p>'
        if dish.get("why") else ""
    )
    desc = (
        f'<p class="d-desc">{esc(dish.get("description"))}</p>'
        if dish.get("description") else ""
    )

    if dish.get("source") == "db" and dish.get("url"):
        origin = (
            f'<a class="d-src is-db" href="{esc(dish["url"])}" target="_blank" rel="noreferrer">'
            f'i databasen · öppna receptet ↗</a>'
        )
    elif dish.get("source") == "db":
        origin = '<span class="d-src is-db">i databasen</span>'
    else:
        origin = '<span class="d-src is-draft">utkast — inte sparat</span>'

    return f"""<article class="dish" data-id="{esc(dish.get('id'))}">
  <label class="d-hd">
    <input type="checkbox" class="d-cb" checked>
    <span class="d-t">{esc(dish.get('title'))}</span>
  </label>
  <div class="d-meta">{esc(_dish_meta(dish))}</div>
  {desc}
  {why}
  <details class="d-body">
    <summary>Recept</summary>
    <div class="d-cols">
      <div class="d-col">
        <h3>Ingredienser</h3>
        <ul class="i-list">{''.join(ing_rows)}</ul>
      </div>
      <div class="d-col">
        <h3>Gör så här</h3>
        <ol class="s-list">{steps}</ol>
      </div>
    </div>
    {notes}
  </details>
  {origin}
</article>"""


def render_plan(plan: dict) -> str:
    dishes = plan.get("dishes") or []
    created = plan.get("created_at") or ""
    try:
        created_fmt = datetime.fromisoformat(created.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        created_fmt = created

    meta_bits = [f"{len(dishes)} rätter"]
    if created_fmt:
        meta_bits.append(f"genererad {created_fmt}")
    note = f'<p class="hd-note">{esc(plan.get("note"))}</p>' if plan.get("note") else ""

    return (
        PAGE_TEMPLATE
        .replace("__TITLE__", esc(plan.get("title") or plan.get("slug") or "Veckomeny"))
        .replace("__WEEK__", esc(plan.get("week") or ""))
        .replace("__NOTE__", note)
        .replace("__META__", esc(" · ".join(meta_bits)))
        .replace("__DISHES__", "\n".join(render_dish(d) for d in dishes))
        .replace("__CATEGORY_ORDER__", json.dumps(CATEGORY_ORDER, ensure_ascii=False))
        .replace("__CATEGORY_EMOJI__", json.dumps(CATEGORY_EMOJI, ensure_ascii=False))
        .replace("__PLAN_JSON__", json.dumps(plan, ensure_ascii=False).replace("</", "<\\/"))
    )


def render_index(plans: list[dict]) -> str:
    rows = []
    for plan in plans:
        dishes = plan.get("dishes") or []
        titles = ", ".join(str(d.get("title", "")) for d in dishes if d.get("title"))
        rows.append(
            f'<li><a href="{esc(plan["slug"])}.html">'
            f'<span class="ix-w">{esc(plan.get("week") or plan["slug"])}</span>'
            f'<span class="ix-t">{esc(plan.get("title") or plan["slug"])}</span>'
            f'<span class="ix-n">{len(dishes)} rätter</span>'
            f'</a><p class="ix-d">{esc(titles)}</p></li>'
        )
    body = "".join(rows) or '<li class="ix-empty">Inga veckomenyer publicerade än.</li>'
    # Stämpeln härleds ur nyaste planen, inte klockan. Skulle den bygga på "nu"
    # ändrades index.html vid varje körning — och en mapp-vakt som triggar på
    # ändringar skulle jaga sin egen svans.
    newest = ""
    for plan in plans:
        created = str(plan.get("created_at") or "")
        if created > newest:
            newest = created
    try:
        stamp = datetime.fromisoformat(newest.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        stamp = newest
    return INDEX_TEMPLATE.replace("__ROWS__", body).replace("__STAMP__", esc(stamp))


BASE_CSS = """
:root{
  --paper:#fdfdfe; --bg:#f2f4f6; --panel:#f8f9fa;
  --ink:#3c4450; --ink2:#5f6975; --ink3:#8d959f;
  --line:#e2e5e9; --line2:#c9cfd6;
  --accent:#1f9ab4; --rail:#1d4f5e;
  --ok:#2f7d5c; --warn:#a2622a;
  --mono:'IBM Plex Mono',ui-monospace,'SF Mono',Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){
  :root{
    --paper:#171b1f; --bg:#101316; --panel:#1c2126;
    --ink:#dbe0e6; --ink2:#a4adb6; --ink3:#767f89;
    --line:#272d34; --line2:#3b434c;
    --accent:#3fb6cf; --rail:#0f2a33;
    --ok:#5fbf94; --warn:#d29a5e;
  }
}
*{box-sizing:border-box;}
html,body{margin:0;background:var(--bg);color:var(--ink);
  font-family:var(--mono);font-size:15px;line-height:1.6;
  -webkit-font-smoothing:antialiased;-webkit-text-size-adjust:100%;}
a{color:var(--accent);text-decoration:none;}
button{font:inherit;color:inherit;background:none;border:none;cursor:pointer;}
.wrap{max-width:960px;margin:0 auto;padding:0 16px 64px;
  padding-left:max(16px,env(safe-area-inset-left));
  padding-right:max(16px,env(safe-area-inset-right));}
.hd{background:var(--rail);color:#e6f2f5;margin:0 -16px 0;padding:22px 16px 18px;
  padding-top:max(22px,calc(env(safe-area-inset-top) + 14px));}
.hd-week{font-size:11px;letter-spacing:.14em;text-transform:uppercase;opacity:.72;}
.hd h1{margin:4px 0 0;font-size:22px;font-weight:500;letter-spacing:-.01em;}
.hd-note{margin:8px 0 0;font-size:13px;opacity:.82;max-width:60ch;}
.hd-meta{margin-top:10px;font-size:11px;opacity:.6;letter-spacing:.04em;}
.tabs{display:flex;gap:0;border-bottom:1px solid var(--line2);
  margin:0 -16px 18px;padding:0 16px;position:sticky;top:0;z-index:5;
  background:var(--bg);}
.tab{padding:11px 14px;font-size:12.5px;letter-spacing:.03em;color:var(--ink3);
  border-bottom:2px solid transparent;margin-bottom:-1px;}
.tab.active{color:var(--ink);border-bottom-color:var(--accent);}
.tab-n{color:var(--accent);}
.dish{border-top:1px solid var(--line);padding:16px 0 14px;}
.dish:first-child{border-top:none;}
.dish.off{opacity:.4;}
.d-hd{display:flex;align-items:baseline;gap:10px;cursor:pointer;}
.d-cb{appearance:none;width:15px;height:15px;flex:0 0 15px;border:1px solid var(--line2);
  background:var(--paper);position:relative;top:2px;cursor:pointer;}
.d-cb:checked{background:var(--accent);border-color:var(--accent);}
.d-cb:checked::after{content:"";position:absolute;left:4px;top:1px;width:4px;height:8px;
  border:solid var(--paper);border-width:0 2px 2px 0;transform:rotate(42deg);}
.d-t{font-size:17px;font-weight:500;letter-spacing:-.01em;}
.d-meta{margin:3px 0 0 25px;font-size:11.5px;color:var(--ink3);letter-spacing:.02em;}
.d-desc{margin:9px 0 0 25px;font-size:13.5px;color:var(--ink2);max-width:66ch;}
.d-why{margin:7px 0 0 25px;font-size:12.5px;color:var(--ink2);max-width:66ch;
  border-left:2px solid var(--line2);padding-left:9px;}
.d-body{margin:11px 0 0 25px;}
.d-body summary{font-size:11px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--ink3);cursor:pointer;list-style:none;padding:3px 0;}
.d-body summary::-webkit-details-marker{display:none;}
.d-body summary::before{content:"▸ ";}
.d-body[open] summary::before{content:"▾ ";}
.d-cols{display:grid;grid-template-columns:1fr;gap:16px;margin-top:10px;
  background:var(--panel);border:1px solid var(--line);padding:14px;}
@media(min-width:720px){.d-cols{grid-template-columns:minmax(0,1fr) minmax(0,1.35fr);gap:26px;}}
.d-col h3{margin:0 0 7px;font-size:10.5px;letter-spacing:.11em;text-transform:uppercase;
  color:var(--ink3);font-weight:500;}
.i-list{list-style:none;margin:0;padding:0;font-size:13.5px;}
.i-list li{display:flex;gap:9px;padding:2.5px 0;}
.i-q{flex:0 0 6.5em;color:var(--ink2);text-align:right;}
.i-n{flex:1;min-width:0;}
.i-note{color:var(--ink3);font-size:12px;}
.i-new{font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--warn);
  border:1px solid currentColor;padding:0 3px;vertical-align:1px;}
.s-list{margin:0;padding-left:1.35em;font-size:13.5px;}
.s-list li{padding:2.5px 0;}
.d-notes{margin:12px 0 0;font-size:12.5px;color:var(--ink2);}
.d-notes .lbl{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink3);
  margin-right:7px;}
.d-src{display:inline-block;margin:11px 0 0 25px;font-size:10.5px;letter-spacing:.07em;
  text-transform:uppercase;}
.d-src.is-db{color:var(--ok);}
.d-src.is-draft{color:var(--warn);}
.l-head{display:flex;flex-wrap:wrap;align-items:center;gap:12px;
  padding-bottom:12px;border-bottom:1px solid var(--line);}
.l-sub{flex:1;min-width:14em;margin:0;font-size:12.5px;color:var(--ink3);}
.l-btn{font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--ink2);
  border:1px solid var(--line2);padding:5px 10px;}
.l-btn:hover{color:var(--accent);border-color:var(--accent);}
.cat{margin-top:22px;}
.cat h2{margin:0 0 6px;font-size:11px;letter-spacing:.11em;text-transform:uppercase;
  color:var(--ink3);font-weight:500;display:flex;align-items:center;gap:8px;}
.cat h2::after{content:"";flex:1;height:1px;background:var(--line);}
.cat.staples{margin-top:30px;padding-top:4px;}
.row{display:flex;align-items:flex-start;gap:11px;padding:7px 0;
  border-bottom:1px solid var(--line);cursor:pointer;}
.row input{appearance:none;width:17px;height:17px;flex:0 0 17px;border:1px solid var(--line2);
  background:var(--paper);position:relative;top:2px;cursor:pointer;}
.row input:checked{background:var(--accent);border-color:var(--accent);}
.row input:checked::after{content:"";position:absolute;left:5px;top:1.5px;width:4px;height:9px;
  border:solid var(--paper);border-width:0 2px 2px 0;transform:rotate(42deg);}
.row.done .r-body{opacity:.38;text-decoration:line-through;}
.r-body{flex:1;min-width:0;}
.r-q{color:var(--ink2);font-size:13px;}
.r-n{font-size:14.5px;}
.r-from{display:block;font-size:11px;color:var(--ink3);margin-top:1px;}
.empty{padding:28px 0;color:var(--ink3);font-size:13px;}
.toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%) translateY(8px);
  background:var(--ink);color:var(--paper);font-size:12px;padding:8px 15px;
  opacity:0;transition:.18s;pointer-events:none;z-index:20;}
.toast.on{opacity:1;transform:translateX(-50%);}
"""

PAGE_TEMPLATE = """<!doctype html>
<html lang="sv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>__TITLE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500&display=swap" rel="stylesheet">\n<style>__CSS__</style>
</head>
<body>
<div class="wrap">
  <header class="hd">
    <div class="hd-week">__WEEK__</div>
    <h1>__TITLE__</h1>
    __NOTE__
    <div class="hd-meta">__META__</div>
  </header>

  <nav class="tabs">
    <button class="tab active" data-pane="menu">Veckans rätter</button>
    <button class="tab" data-pane="list">Inköpslista <span class="tab-n" id="tab-n"></span></button>
  </nav>

  <section id="pane-menu">
__DISHES__
  </section>

  <section id="pane-list" hidden>
    <div class="l-head">
      <p class="l-sub" id="l-sub"></p>
      <button class="l-btn" id="copy-btn">Kopiera</button>
      <button class="l-btn" id="reset-btn">Nollställ</button>
    </div>
    <div id="l-body"></div>
  </section>
</div>
<div class="toast" id="toast"></div>

<script id="plan-data" type="application/json">__PLAN_JSON__</script>
<script>
(function(){
"use strict";
var PLAN = JSON.parse(document.getElementById('plan-data').textContent);
var CATS = __CATEGORY_ORDER__;
var EMOJI = __CATEGORY_EMOJI__;
var SLUG = PLAN.slug || 'plan';
var K_DISH = 'veckomeny:' + SLUG + ':dishes';
var K_CHK  = 'veckomeny:' + SLUG + ':checked';

function load(key, fallback){
  try { var raw = localStorage.getItem(key); return raw ? JSON.parse(raw) : fallback; }
  catch(e){ return fallback; }
}
function save(key, value){
  try { localStorage.setItem(key, JSON.stringify(value)); } catch(e){}
}

/* Mängder kommer som fri text från recepten. Vi summerar det som går att
   summera och bär med resten ordagrant — hellre "2 dl + en skvätt" än en
   siffra som ljuger. */
function parseAmount(raw){
  var s = String(raw == null ? '' : raw).trim().replace(',', '.');
  if (!s) return {num:null, text:null};
  var frac = s.match(/^(\\d+(?:\\.\\d+)?)\\s*\\/\\s*(\\d+(?:\\.\\d+)?)$/);
  if (frac && parseFloat(frac[2]) !== 0) return {num: parseFloat(frac[1]) / parseFloat(frac[2]), text:null};
  var range = s.match(/^(\\d+(?:\\.\\d+)?)\\s*[-\\u2013]\\s*(\\d+(?:\\.\\d+)?)$/);
  if (range) return {num: parseFloat(range[2]), text:null};
  var plain = s.match(/^(\\d+(?:\\.\\d+)?)$/);
  if (plain) return {num: parseFloat(plain[1]), text:null};
  return {num:null, text:s};
}
function fmtNum(n){
  var r = Math.round(n * 100) / 100;
  return String(r).replace('.', ',');
}

function activeIds(){
  var stored = load(K_DISH, null);
  var ids = (PLAN.dishes || []).map(function(d){ return d.id; });
  if (!stored) return ids.slice();
  return ids.filter(function(id){ return stored.indexOf(id) !== -1; });
}

function buildList(){
  var active = activeIds();
  var byKey = {};
  var order = [];
  (PLAN.dishes || []).forEach(function(dish){
    if (active.indexOf(dish.id) === -1) return;
    (dish.ingredients || []).forEach(function(ing){
      var name = String(ing.name || '').trim();
      if (!name) return;
      /* En vara = en rad, oavsett hur recepten mäter den. Ingefära som är
         "1 tsk" i ett recept och "1 st" i ett annat ska du köpa en gång — vi
         slår ihop raden och redovisar båda måtten. */
      var unit = String(ing.unit || '').trim();
      var key = name.toLowerCase();
      var entry = byKey[key];
      if (!entry){
        entry = byKey[key] = {
          key:key, name:name,
          cat: ing.grocery_category || 'Övrigt',
          staple:false, units:{}, unitOrder:[], from:[]
        };
        order.push(key);
      }
      entry.staple = entry.staple || !!ing.kitchen_staple;
      var slot = entry.units[unit];
      if (!slot){ slot = entry.units[unit] = {num:0, hasNum:false, texts:[]}; entry.unitOrder.push(unit); }
      var p = parseAmount(ing.amount);
      if (p.num !== null){ slot.num += p.num; slot.hasNum = true; }
      else if (p.text){ slot.texts.push(p.text); }
      if (entry.from.indexOf(dish.title) === -1) entry.from.push(dish.title);
    });
  });

  var groups = {};
  order.forEach(function(key){
    var e = byKey[key];
    var bucket = e.staple ? '__staples__' : (CATS.indexOf(e.cat) === -1 ? 'Övrigt' : e.cat);
    (groups[bucket] = groups[bucket] || []).push(e);
  });
  Object.keys(groups).forEach(function(k){
    groups[k].sort(function(a,b){ return a.name.localeCompare(b.name, 'sv'); });
  });
  return {groups:groups, count:order.length, dishes:active.length};
}

function qtyText(e){
  var out = [];
  e.unitOrder.forEach(function(unit){
    var slot = e.units[unit];
    var bits = [];
    if (slot.hasNum && slot.num > 0) bits.push(fmtNum(slot.num));
    if (slot.texts.length) bits.push(slot.texts.join(' + '));
    var qty = bits.join(' + ');
    if (!qty && !unit) return;
    out.push(unit ? (qty ? qty + ' ' + unit : unit) : qty);
  });
  return out.join(' + ');
}

function renderList(){
  var data = buildList();
  var checked = load(K_CHK, []);
  var body = document.getElementById('l-body');
  var order = CATS.filter(function(c){ return data.groups[c]; });
  if (data.groups['__staples__']) order.push('__staples__');

  if (!order.length){
    body.innerHTML = '<p class="empty">Inga rätter valda — bocka i något under Veckans rätter.</p>';
    document.getElementById('l-sub').textContent = '';
    document.getElementById('tab-n').textContent = '';
    return;
  }

  var open = 0;
  var out = '';
  order.forEach(function(cat){
    var staples = cat === '__staples__';
    var label = staples ? '🧂 Skafferi — kolla hemma först' :
      (EMOJI[cat] ? EMOJI[cat] + ' ' + cat : cat);
    out += '<div class="cat' + (staples ? ' staples' : '') + '"><h2>' + label + '</h2>';
    data.groups[cat].forEach(function(e){
      var done = checked.indexOf(e.key) !== -1;
      if (!done) open++;
      out += '<label class="row' + (done ? ' done' : '') + '" data-key="' + escAttr(e.key) + '">' +
        '<input type="checkbox"' + (done ? ' checked' : '') + '>' +
        '<span class="r-body"><span class="r-q">' + escHtml(qtyText(e)) + '</span> ' +
        '<span class="r-n">' + escHtml(e.name) + '</span>' +
        '<span class="r-from">' + escHtml(e.from.join(' · ')) + '</span></span></label>';
    });
    out += '</div>';
  });
  body.innerHTML = out;
  document.getElementById('l-sub').textContent =
    data.count + ' varor från ' + data.dishes + ' rätter · ' + open + ' kvar';
  document.getElementById('tab-n').textContent = open ? '(' + open + ')' : '';
}

function escHtml(s){
  return String(s).replace(/[&<>"]/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];
  });
}
function escAttr(s){ return escHtml(s).replace(/'/g, '&#39;'); }

function toast(msg){
  var el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('on');
  clearTimeout(el._t);
  el._t = setTimeout(function(){ el.classList.remove('on'); }, 1800);
}

/* --- rätter: val + persistens --- */
var stored = load(K_DISH, null);
Array.prototype.forEach.call(document.querySelectorAll('.dish'), function(card){
  var cb = card.querySelector('.d-cb');
  if (stored) cb.checked = stored.indexOf(card.dataset.id) !== -1;
  card.classList.toggle('off', !cb.checked);
  cb.addEventListener('change', function(){
    card.classList.toggle('off', !cb.checked);
    var on = [];
    Array.prototype.forEach.call(document.querySelectorAll('.dish'), function(c){
      if (c.querySelector('.d-cb').checked) on.push(c.dataset.id);
    });
    save(K_DISH, on);
    renderList();
  });
});

/* --- flikar --- */
Array.prototype.forEach.call(document.querySelectorAll('.tab'), function(tab){
  tab.addEventListener('click', function(){
    Array.prototype.forEach.call(document.querySelectorAll('.tab'), function(t){
      t.classList.toggle('active', t === tab);
    });
    document.getElementById('pane-menu').hidden = tab.dataset.pane !== 'menu';
    document.getElementById('pane-list').hidden = tab.dataset.pane !== 'list';
    window.scrollTo(0, 0);
  });
});

/* --- avbockning i butik --- */
document.getElementById('l-body').addEventListener('change', function(ev){
  var row = ev.target.closest('.row');
  if (!row) return;
  var checked = load(K_CHK, []);
  var idx = checked.indexOf(row.dataset.key);
  if (ev.target.checked){ if (idx === -1) checked.push(row.dataset.key); }
  else if (idx !== -1){ checked.splice(idx, 1); }
  save(K_CHK, checked);
  renderList();
});

document.getElementById('reset-btn').addEventListener('click', function(){
  save(K_CHK, []);
  renderList();
  toast('Avbockningen nollställd');
});

document.getElementById('copy-btn').addEventListener('click', function(){
  var data = buildList();
  var order = CATS.filter(function(c){ return data.groups[c]; });
  if (data.groups['__staples__']) order.push('__staples__');
  var lines = [PLAN.title || 'Inköpslista', ''];
  order.forEach(function(cat){
    lines.push(cat === '__staples__' ? 'Skafferi — kolla hemma först' : cat);
    data.groups[cat].forEach(function(e){
      lines.push('  - ' + (qtyText(e) ? qtyText(e) + ' ' : '') + e.name);
    });
    lines.push('');
  });
  var text = lines.join('\\n');
  if (navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(text).then(function(){ toast('Listan kopierad'); },
      function(){ toast('Kunde inte kopiera'); });
  } else {
    toast('Kopiering stöds inte här');
  }
});

renderList();
})();
</script>
</body>
</html>
"""

INDEX_TEMPLATE = """<!doctype html>
<html lang="sv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>Veckomenyer</title>
<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500&display=swap" rel="stylesheet">\n<style>__CSS__
.ix{list-style:none;margin:22px 0 0;padding:0;}
.ix li{border-top:1px solid var(--line);padding:13px 0;}
.ix li:first-child{border-top:none;}
.ix a{display:flex;flex-wrap:wrap;align-items:baseline;gap:11px;color:var(--ink);}
.ix a:hover .ix-t{color:var(--accent);}
.ix-w{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink3);
  flex:0 0 5.5em;}
.ix-t{font-size:16.5px;font-weight:500;}
.ix-n{margin-left:auto;font-size:11px;color:var(--ink3);}
.ix-d{margin:3px 0 0 calc(5.5em + 11px);font-size:12.5px;color:var(--ink3);}
.ix-empty{color:var(--ink3);font-size:13px;}
</style>
</head>
<body>
<div class="wrap">
  <header class="hd">
    <div class="hd-week">Veckomeny</div>
    <h1>Publicerade veckor</h1>
    <div class="hd-meta">uppdaterad __STAMP__</div>
  </header>
  <ul class="ix">__ROWS__</ul>
</div>
</body>
</html>
"""


def _sort_key(plan: dict):
    return (str(plan.get("week") or ""), str(plan.get("created_at") or ""), str(plan.get("slug") or ""))


def write_if_changed(path: Path, content: str) -> bool:
    """Skriv bara när innehållet skiljer sig. Håller mtime stilla vid omkörning,
    vilket gör bygget säkert att trigga från en mapp-vakt."""
    # newline="" — ingen radslutsöversättning, så jämförelsen är exakt.
    if path.exists():
        with open(path, "r", encoding="utf-8", newline="") as fh:
            if fh.read() == content:
                return False
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    return True


def build(plans_dir: Path, targets: list[Path]) -> int:
    plans_dir.mkdir(parents=True, exist_ok=True)
    for path in targets:
        plan = json.loads(path.read_text(encoding="utf-8"))
        plan.setdefault("slug", path.stem)
        out = plans_dir / f"{plan['slug']}.html"
        changed = write_if_changed(out, render_plan(plan))
        print(f"  {'✓' if changed else '·'} {out.relative_to(plans_dir.parent)}"
              f"{'' if changed else '  (oförändrad)'}")

    every = []
    for path in sorted(plans_dir.glob("*.json")):
        try:
            every.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            print(f"  ! hoppar över {path.name}: {exc}", file=sys.stderr)
    every.sort(key=_sort_key, reverse=True)
    index = plans_dir / "index.html"
    changed = write_if_changed(index, render_index(every))
    print(f"  {'✓' if changed else '·'} {index.relative_to(plans_dir.parent)} "
          f"({len(every)} veckor){'' if changed else '  (oförändrad)'}")
    return 0


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Rendera veckomeny-JSON till fristående HTML.")
    ap.add_argument("files", nargs="*", help="plans/<slug>.json att rendera")
    ap.add_argument("--all", action="store_true", help="rendera om alla planer i plans-katalogen")
    ap.add_argument("--plans-dir", default=str(repo_root / "plans"),
                    help="katalog med plan-JSON och renderad HTML (default: <repo>/plans)")
    args = ap.parse_args()

    plans_dir = Path(args.plans_dir).resolve()
    if args.all:
        targets = sorted(plans_dir.glob("*.json"))
    else:
        targets = [Path(f).resolve() for f in args.files]
    if not targets and not args.all:
        ap.error("ange minst en JSON-fil, eller --all")
    for path in targets:
        if not path.exists():
            print(f"Saknas: {path}", file=sys.stderr)
            return 1
    print(f"Renderar {len(targets)} plan(er) → {plans_dir}")
    return build(plans_dir, targets)


PAGE_TEMPLATE = PAGE_TEMPLATE.replace("__CSS__", BASE_CSS)
INDEX_TEMPLATE = INDEX_TEMPLATE.replace("__CSS__", BASE_CSS)


if __name__ == "__main__":
    sys.exit(main())
