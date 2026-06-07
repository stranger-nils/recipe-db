/* mise — klientlogik för Recept-IDE. Server-rendered fragment + vanilla JS. */
(function () {
  "use strict";

  const DATA = JSON.parse(document.getElementById("mise-data").textContent);
  const MODE = DATA.mode;                       // 'recept' | 'ingredienser' | 'planering'
  const RECIPES = DATA.recipes || [];           // [{id,title,kitchen,type,version_count}]
  const CATALOG = DATA.catalog || [];           // [{name,grocery_category}]
  const TAB_STORAGE_KEY = "mise.tabs.v1";

  /* ---------- helpers ---------- */
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const svgCheck = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5L20 7"/></svg>';
  const svgClose = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';

  function fmtQty(q) {
    if (q == null || q === "" || isNaN(q)) return q == null ? "" : String(q);
    const map = { 0.25: "¼", 0.5: "½", 0.75: "¾", 0.33: "⅓", 0.67: "⅔" };
    const whole = Math.floor(q);
    const frac = +(q - whole).toFixed(2);
    if (map[frac]) return (whole ? whole + " " : "") + map[frac];
    if (Math.abs(q - Math.round(q)) < 0.01) return String(Math.round(q));
    return String(+q.toFixed(2));
  }

  function parseQty(s) {
    if (s == null) return null;
    let t = String(s).trim().replace(",", ".").toLowerCase();
    if (!t) return null;
    // Strippa vanliga prefix som inte är siffror: "ca", "ungefär", "ung."
    t = t.replace(/^(ca\.?|ung\.?|ungefär|ungefar|cirka|drygt|knappt)\s+/, "");
    // "1/2" eller "1 1/2"
    const frac = t.match(/^(\d+)?\s*(\d+)\/(\d+)/);
    if (frac) {
      const w = parseInt(frac[1] || "0", 10);
      const n = parseInt(frac[2], 10);
      const d = parseInt(frac[3], 10);
      return d ? w + n / d : null;
    }
    const m = t.match(/^[\d.]+/);
    if (!m) return null;
    const n = parseFloat(m[0]);
    return isNaN(n) ? null : n;
  }

  function groupRecipes(recipes, grouping) {
    if (grouping === "az") {
      return [{ key: "A–Ö", items: [...recipes].sort((a, b) => a.title.localeCompare(b.title, "sv")) }];
    }
    const field = grouping === "kategori" ? "type" : "kitchen";
    const map = {};
    recipes.forEach((r) => {
      const k = (r[field] || "(Ej angiven)").trim();
      (map[k] = map[k] || []).push(r);
    });
    return Object.keys(map).sort((a, b) => a.localeCompare(b, "sv"))
      .map((k) => ({ key: k, items: map[k].sort((a, b) => a.title.localeCompare(b.title, "sv")) }));
  }

  /* ---------- aktivitetsrad navigation ---------- */
  $$(".rail-btn[data-mode-link]").forEach((btn) => {
    btn.addEventListener("click", () => { window.location.href = btn.dataset.modeLink; });
  });

  /* ---------- mobil: toggla explorern ---------- */
  const explorerToggle = $("#explorer-toggle");
  const ideEl = document.querySelector(".ide");
  explorerToggle && ideEl && explorerToggle.addEventListener("click", () => {
    ideEl.classList.toggle("show-explorer");
  });

  /* ---------- kommandopalett ---------- */
  const cmdOverlay = $("#cmd-overlay");
  const cmdInput = $("#cmd-input");
  const cmdRes = $("#cmd-res");
  let cmdSelIndex = 0;
  let cmdMatches = [];

  function openPalette() {
    cmdOverlay.hidden = false;
    cmdInput.value = "";
    renderPalette("");
    setTimeout(() => cmdInput.focus(), 30);
  }
  function closePalette() { cmdOverlay.hidden = true; }
  function renderPalette(q) {
    const ql = q.toLowerCase();
    cmdMatches = RECIPES.filter((r) =>
      r.title.toLowerCase().includes(ql) || (r.kitchen || "").toLowerCase().includes(ql)
    ).slice(0, 8);
    cmdSelIndex = 0;
    if (!cmdMatches.length) {
      cmdRes.innerHTML = '<div class="cmd-none">Inga recept matchar.</div>';
      return;
    }
    cmdRes.innerHTML = cmdMatches.map((r, i) =>
      `<button class="cmd-row${i === 0 ? " sel" : ""}" data-id="${r.id}">
        <span class="cmd-title">${escapeHtml(r.title)}</span>
        <span class="cmd-meta">${escapeHtml(r.kitchen || "")}</span>
      </button>`).join("");
    $$(".cmd-row", cmdRes).forEach((row, i) => {
      row.addEventListener("click", () => { openRecipe(+row.dataset.id); closePalette(); });
      row.addEventListener("mouseenter", () => { setCmdSel(i); });
    });
  }
  function setCmdSel(i) {
    cmdSelIndex = i;
    $$(".cmd-row", cmdRes).forEach((r, j) => r.classList.toggle("sel", j === i));
  }
  cmdInput && cmdInput.addEventListener("input", () => renderPalette(cmdInput.value));
  cmdInput && cmdInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && cmdMatches[cmdSelIndex]) { openRecipe(cmdMatches[cmdSelIndex].id); closePalette(); }
    else if (e.key === "Escape") closePalette();
    else if (e.key === "ArrowDown") { e.preventDefault(); setCmdSel(Math.min(cmdSelIndex + 1, cmdMatches.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setCmdSel(Math.max(cmdSelIndex - 1, 0)); }
  });
  cmdOverlay && cmdOverlay.addEventListener("click", (e) => { if (e.target === cmdOverlay) closePalette(); });
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      cmdOverlay.hidden ? openPalette() : closePalette();
    }
  });

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  /* ---------- Recept-vyn: explorer + tabs ---------- */

  // Default-implementation: navigera till receptvyn. Skrivs över inne i
  // MODE==="recept"-blocket nedan så öppning sker som ny flik utan reload.
  let openRecipe = (id) => { window.location.href = "/?open=" + id; };

  if (MODE === "recept") {
    openRecipe = (id) => activateTab("r:" + id, () => createRecipeTab(id));

    /* tabs-state måste finnas innan renderTree() kör (den anropar
       highlightActiveTreeRow → currentActiveTab → TABS). */
    const tabstrip = $("#tabstrip");
    const editorBody = $("#editor-body");
    let TABS = [];
    try {
      TABS = JSON.parse(sessionStorage.getItem(TAB_STORAGE_KEY)) || [];
    } catch (_) { TABS = []; }
    let activeTabKey = null;

    const recGrouping = $("#rec-grouping");
    const recSearch = $("#rec-search");
    const recTree = $("#rec-tree");
    const recCount = $("#rec-count");
    let grouping = localStorage.getItem("mise.recGrouping") || "kok";
    if (recGrouping) recGrouping.value = grouping;

    function renderTree() {
      const q = (recSearch.value || "").toLowerCase().trim();
      const filtered = RECIPES.filter((r) =>
        !q || r.title.toLowerCase().includes(q) || (r.kitchen || "").toLowerCase().includes(q));
      const groups = groupRecipes(filtered, grouping);
      recCount.textContent = filtered.length + " recept";
      if (!filtered.length) { recTree.innerHTML = '<div class="empty sm">Inga träffar.</div>'; return; }
      recTree.innerHTML = groups.map((g) => `
        <div class="tree-group">
          <div class="tree-group-h"><span>${escapeHtml(g.key)}</span><span class="tg-count">${g.items.length}</span></div>
          ${g.items.map((r) => `
            <button class="tree-row" data-recipe-id="${r.id}">
              <span class="tr-name">${escapeHtml(r.title)}</span>
              ${r.version_count > 1 ? `<span class="tr-ver">v${r.version_count}</span>` : ""}
            </button>`).join("")}
        </div>`).join("");
      $$(".tree-row", recTree).forEach((btn) => {
        btn.addEventListener("click", () => openRecipe(+btn.dataset.recipeId));
      });
      highlightActiveTreeRow();
    }
    function highlightActiveTreeRow() {
      const active = currentActiveTab();
      const rid = active && active.kind === "recipe" ? active.recipeId : null;
      $$(".tree-row", recTree).forEach((row) => {
        row.classList.toggle("active", rid != null && +row.dataset.recipeId === rid);
      });
    }
    recGrouping && recGrouping.addEventListener("change", () => {
      grouping = recGrouping.value;
      localStorage.setItem("mise.recGrouping", grouping);
      renderTree();
    });
    recSearch && recSearch.addEventListener("input", renderTree);
    renderTree();

    window._miseHighlightTree = highlightActiveTreeRow;

    function persistTabs() {
      try { sessionStorage.setItem(TAB_STORAGE_KEY, JSON.stringify(TABS)); } catch (_) {}
    }
    function currentActiveTab() { return TABS.find((t) => t.key === activeTabKey); }

    function renderTabstrip() {
      tabstrip.innerHTML = TABS.map((t) => `
        <div class="tab${t.key === activeTabKey ? " active" : ""}" data-tab-key="${escapeHtml(t.key)}">
          <span class="tab-label">${escapeHtml(t.title)}</span>
          <button class="tab-close" data-tab-close="${escapeHtml(t.key)}" title="Stäng">${svgClose}</button>
        </div>`).join("");
      $$(".tab", tabstrip).forEach((el) => {
        el.addEventListener("click", (e) => {
          if (e.target.closest(".tab-close")) return;
          activateTab(el.dataset.tabKey);
        });
      });
      $$(".tab-close", tabstrip).forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          closeTab(btn.dataset.tabClose);
        });
      });
    }

    function showWelcome(visible) {
      const w = $('.tab-pane[data-pane="welcome"]', editorBody);
      if (!w) return;
      w.classList.toggle("active", !!visible);
    }

    function ensurePane(key) {
      let pane = $(`.tab-pane[data-pane="${CSS.escape(key)}"]`, editorBody);
      if (!pane) {
        pane = document.createElement("div");
        pane.className = "tab-pane";
        pane.dataset.pane = key;
        pane.innerHTML = '<div class="welcome"><p>Laddar…</p></div>';
        editorBody.appendChild(pane);
      }
      return pane;
    }

    function activateTab(key, createIfMissing) {
      if (!TABS.find((t) => t.key === key)) {
        if (createIfMissing) createIfMissing();
        else return;
      }
      activeTabKey = key;
      persistTabs();
      $$(".tab-pane", editorBody).forEach((p) => p.classList.remove("active"));
      const pane = $(`.tab-pane[data-pane="${CSS.escape(key)}"]`, editorBody);
      if (pane) pane.classList.add("active"); else showWelcome(true);
      $$(".tab", tabstrip).forEach((el) => el.classList.toggle("active", el.dataset.tabKey === key));
      showWelcome(false);
      highlightActiveTreeRow();
      updateStatusBar();
    }

    function closeTab(key) {
      const idx = TABS.findIndex((t) => t.key === key);
      if (idx < 0) return;
      TABS.splice(idx, 1);
      const pane = $(`.tab-pane[data-pane="${CSS.escape(key)}"]`, editorBody);
      if (pane) pane.remove();
      persistTabs();
      renderTabstrip();
      if (activeTabKey === key) {
        const next = TABS[Math.max(0, idx - 1)];
        if (next) activateTab(next.key);
        else { activeTabKey = null; showWelcome(true); updateStatusBar(); }
      }
      highlightActiveTreeRow();
    }

    async function createRecipeTab(id, version) {
      const r = RECIPES.find((x) => x.id === id);
      if (!r) return;
      const key = "r:" + id + (version ? ":v" + version : "");
      TABS.push({ key, kind: "recipe", recipeId: id, title: r.title, version: version || null });
      persistTabs();
      renderTabstrip();
      const pane = ensurePane(key);
      try {
        const url = "/_frag/recipe/" + id + (version ? "?v=" + version : "");
        const html = await fetch(url).then((r) => r.text());
        pane.innerHTML = html;
        wireRecipePane(pane, id);
      } catch (e) {
        pane.innerHTML = '<div class="welcome"><p>Kunde inte ladda recept.</p></div>';
      }
    }

    async function createDiffTab(id, initialVer) {
      const r = RECIPES.find((x) => x.id === id);
      if (!r) return;
      const key = "d:" + id;
      if (!TABS.find((t) => t.key === key)) {
        TABS.push({ key, kind: "diff", recipeId: id, title: r.title + " · diff" });
        persistTabs();
      }
      renderTabstrip();
      activeTabKey = key;
      $$(".tab-pane", editorBody).forEach((p) => p.classList.remove("active"));
      const pane = ensurePane(key);
      pane.classList.add("active");
      showWelcome(false);
      $$(".tab", tabstrip).forEach((el) => el.classList.toggle("active", el.dataset.tabKey === key));
      try {
        const url = "/_frag/recipe/" + id + "/diff" + (initialVer ? "?to=" + initialVer : "");
        const html = await fetch(url).then((r) => r.text());
        pane.innerHTML = html;
        wireDiffPane(pane, id);
      } catch (e) {
        pane.innerHTML = '<div class="welcome"><p>Kunde inte ladda diff.</p></div>';
      }
      updateStatusBar();
    }

    function updateStatusBar() {
      const sb = $("#sb-info");
      const t = currentActiveTab();
      if (!t) { sb.textContent = ""; return; }
      const r = RECIPES.find((x) => x.id === t.recipeId);
      if (!r) { sb.textContent = ""; return; }
      sb.textContent = (t.kind === "diff" ? "diff · " : "") + (r.kitchen || "") + (r.type ? " · " + r.type : "");
    }

    // open from query (?open=ID, valfri &diff=1) eller återställ flikar
    const params = new URLSearchParams(window.location.search);
    const openId = params.get("open");
    const openDiff = params.get("diff") === "1";
    if (openId) {
      history.replaceState(null, "", "/");
      if (openDiff) createDiffTab(+openId, null);
      else openRecipe(+openId);
    } else if (TABS.length) {
      renderTabstrip();
      // re-fetch all tab panes
      TABS.forEach(async (t) => {
        const pane = ensurePane(t.key);
        try {
          let url;
          if (t.kind === "diff") url = "/_frag/recipe/" + t.recipeId + "/diff";
          else url = "/_frag/recipe/" + t.recipeId + (t.version ? "?v=" + t.version : "");
          const html = await fetch(url).then((r) => r.text());
          pane.innerHTML = html;
          if (t.kind === "diff") wireDiffPane(pane, t.recipeId);
          else wireRecipePane(pane, t.recipeId);
        } catch (e) { /* ignore */ }
      });
      activateTab(TABS[TABS.length - 1].key);
    } else {
      renderTabstrip();
    }

    window._miseOpenDiff = createDiffTab;
  }

  /* ---------- Recept-pane: skalning, anteckningar, versionsbyte ---------- */

  async function wireRecipePane(pane, recipeId) {
    const doc = $(".doc", pane);
    if (!doc) return;
    const base = parseFloat(doc.dataset.baseServings) || 4;
    let serv = base;
    const stepperBtns = $$('[data-stepper]', doc);
    const stepperVal = $('[data-stepper-value]', doc);
    const servDisplay = $('[data-serv-display]', doc);

    function applyScale() {
      const factor = serv / base;
      $$('.ing-q[data-base-qty]', doc).forEach((el) => {
        const base = el.dataset.baseQty;
        const n = parseQty(base);
        if (n == null) { el.textContent = base; return; }
        // preserve trailing text like " (ca)"
        const m = String(base).match(/^[\d.,]+(.*)$/);
        const suffix = m ? m[1] : "";
        el.textContent = fmtQty(+(n * factor).toFixed(3)) + suffix;
      });
      stepperVal.textContent = serv;
      if (servDisplay) servDisplay.textContent = serv;
    }
    applyScale();
    stepperBtns.forEach((b) => b.addEventListener("click", () => {
      serv = Math.max(1, serv + (b.dataset.stepper === "+" ? 1 : -1));
      applyScale();
    }));

    // version picker
    const vpick = $('[data-version-picker]', doc);
    vpick && vpick.addEventListener("change", async () => {
      const v = vpick.value;
      const tabKey = "r:" + recipeId + (v ? ":v" + v : "");
      // rewrite current tab to load this version
      const url = "/_frag/recipe/" + recipeId + (v ? "?v=" + v : "");
      const html = await fetch(url).then((r) => r.text());
      pane.innerHTML = html;
      pane.dataset.pane = tabKey;
      wireRecipePane(pane, recipeId);
    });

    // open diff
    const diffBtn = $('[data-open-diff]', doc);
    diffBtn && diffBtn.addEventListener("click", () => {
      const v = vpick ? vpick.value : "";
      window._miseOpenDiff && window._miseOpenDiff(recipeId, v ? +v : null);
    });

    // annotations
    const activeVersion = doc.dataset.activeVersion || ""; // empty = live
    $$('.ing-item, .step-item', doc).forEach((item) => {
      const toggleBtn = $('[data-anno-toggle]', item);
      const key = item.dataset.annoKey;
      toggleBtn && toggleBtn.addEventListener("click", () => startAnnoEdit(item, key));
      const display = $('[data-anno-display]', item);
      display && display.addEventListener("click", () => startAnnoEdit(item, key));
    });

    function startAnnoEdit(item, key) {
      if ($('.anno-edit', item)) return;
      const existing = ($('[data-anno-display]', item) || {}).textContent || "";
      const edit = document.createElement("div");
      edit.className = "anno-edit";
      const input = document.createElement("input");
      input.placeholder = "Minnesanteckning till nästa gång…";
      input.value = existing.trim();
      edit.appendChild(input);
      const isStep = item.classList.contains("step-item");
      if (isStep) $('.step-main', item).appendChild(edit);
      else item.appendChild(edit);
      input.focus();
      const save = async () => {
        const val = input.value.trim();
        edit.remove();
        await saveAnnotation(recipeId, activeVersion, key, val);
        renderAnnotation(item, val);
      };
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); save(); }
        else if (e.key === "Escape") { edit.remove(); }
      });
      input.addEventListener("blur", save);
    }
    function renderAnnotation(item, val) {
      const isStep = item.classList.contains("step-item");
      let display = $('[data-anno-display]', item);
      if (val) {
        if (!display) {
          display = document.createElement("div");
          display.className = isStep ? "step-anno" : "ing-anno";
          display.dataset.annoDisplay = "";
          if (isStep) $('.step-main', item).appendChild(display);
          else item.appendChild(display);
          display.addEventListener("click", () => startAnnoEdit(item, item.dataset.annoKey));
        }
        display.textContent = val;
        const btn = $('[data-anno-toggle]', item);
        if (btn) { btn.textContent = "redigera"; btn.classList.add("has"); }
      } else {
        if (display) display.remove();
        const btn = $('[data-anno-toggle]', item);
        if (btn) { btn.textContent = "+ anteckning"; btn.classList.remove("has"); }
      }
    }
  }

  async function saveAnnotation(recipeId, version, key, text) {
    const [target_type, ...rest] = key.split(":");
    const target_key = rest.join(":");
    try {
      await fetch("/api/annotation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          recipe_id: recipeId,
          version: version === "" ? null : +version,
          target_type, target_key, text,
        }),
      });
    } catch (e) { /* swallow */ }
  }

  /* ---------- Diff-pane ---------- */
  function wireDiffPane(pane, recipeId) {
    const diff = $(".diff", pane);
    if (!diff) return;
    const a = $('[data-diff-side="from"]', diff);
    const b = $('[data-diff-side="to"]', diff);
    const reload = async () => {
      const url = "/_frag/recipe/" + recipeId + "/diff?from=" + a.value + "&to=" + b.value;
      const html = await fetch(url).then((r) => r.text());
      pane.innerHTML = html;
      wireDiffPane(pane, recipeId);
    };
    a && a.addEventListener("change", reload);
    b && b.addEventListener("change", reload);
  }

  /* ---------- Ingrediensbibliotek ---------- */
  if (MODE === "ingredienser") {
    const cats = $("#lib-cats");
    const search = $("#lib-search");
    const table = $("#lib-table");
    const allCats = ["Alla"].concat(Array.from(new Set(CATALOG.map((c) => c.grocery_category).filter(Boolean))).sort((a, b) => a.localeCompare(b, "sv")));
    let activeCat = "Alla";

    function renderCats() {
      cats.innerHTML = allCats.map((c) => {
        const count = c === "Alla" ? CATALOG.length : CATALOG.filter((x) => x.grocery_category === c).length;
        return `<button class="cat-row${c === activeCat ? " active" : ""}" data-cat="${escapeHtml(c)}">
          <span>${escapeHtml(c)}</span><span class="cat-count">${count}</span>
        </button>`;
      }).join("");
      $$(".cat-row", cats).forEach((b) => b.addEventListener("click", () => {
        activeCat = b.dataset.cat;
        renderCats();
        applyFilter();
      }));
    }
    function applyFilter() {
      const q = (search.value || "").toLowerCase().trim();
      $$("tr[data-name]", table).forEach((tr) => {
        const matchesCat = activeCat === "Alla" || tr.dataset.cat === activeCat;
        const matchesQ = !q || tr.dataset.name.includes(q) || tr.dataset.aliases.includes(q);
        tr.classList.toggle("hidden", !(matchesCat && matchesQ));
      });
    }
    renderCats();
    applyFilter();
    search && search.addEventListener("input", applyFilter);

    // pantry toggle (visuell + sync av hidden checkbox)
    $$("[data-pan-toggle]", table).forEach((span) => {
      span.addEventListener("click", (e) => {
        e.preventDefault();
        const cb = span.parentElement.querySelector('input[type="checkbox"]');
        cb.checked = !cb.checked;
        span.classList.toggle("on", cb.checked);
        span.innerHTML = cb.checked ? svgCheck : "";
      });
    });

    // "Används i"-länkar öppnar recept (navigerar bort till receptvyn)
    $$("[data-open-recipe]", table).forEach((btn) => {
      btn.addEventListener("click", () => { window.location.href = "/?open=" + btn.dataset.openRecipe; });
    });

    $("#sb-info").textContent = CATALOG.length + " ingredienser";
  }

  /* ---------- Planering ---------- */
  if (MODE === "planering") {
    const PLAN_SEL_KEY = "mise.planSel.v1";
    let grouping = localStorage.getItem("mise.planGrouping") || "kok";
    let query = "";
    let selected = new Set();
    try { selected = new Set(JSON.parse(sessionStorage.getItem(PLAN_SEL_KEY)) || []); } catch (_) {}
    const have = {}; // override per key -> bool
    const bought = {};
    let step = "inventory";
    let copied = false;

    const planGroupingSel = $("#plan-grouping");
    const planSearch = $("#plan-search");
    const planTree = $("#plan-tree");
    const planCount = $("#plan-count");
    const planClear = $("#plan-clear");
    if (planGroupingSel) planGroupingSel.value = grouping;

    function persistSel() { sessionStorage.setItem(PLAN_SEL_KEY, JSON.stringify(Array.from(selected))); }

    function renderTree() {
      const q = query.toLowerCase();
      const filtered = RECIPES.filter((r) =>
        !q || r.title.toLowerCase().includes(q) || (r.kitchen || "").toLowerCase().includes(q));
      const groups = groupRecipes(filtered, grouping);
      if (!filtered.length) { planTree.innerHTML = '<div class="empty sm">Inga träffar.</div>'; }
      else {
        planTree.innerHTML = groups.map((g) => `
          <div class="tree-group">
            <div class="tree-group-h"><span>${escapeHtml(g.key)}</span><span class="tg-count">${g.items.length}</span></div>
            ${g.items.map((r) => `
              <button class="pick-row${selected.has(r.id) ? " on" : ""}" data-id="${r.id}">
                <span class="pi-box sm${selected.has(r.id) ? " on" : ""}">${selected.has(r.id) ? svgCheck : ""}</span>
                <span class="pick-name">${escapeHtml(r.title)}</span>
              </button>`).join("")}
          </div>`).join("");
        $$(".pick-row", planTree).forEach((b) => b.addEventListener("click", () => {
          const id = +b.dataset.id;
          if (selected.has(id)) selected.delete(id); else selected.add(id);
          persistSel(); renderTree(); renderView();
        }));
      }
      planCount.textContent = selected.size + " valda";
    }
    planGroupingSel && planGroupingSel.addEventListener("change", () => {
      grouping = planGroupingSel.value;
      localStorage.setItem("mise.planGrouping", grouping);
      renderTree();
    });
    planSearch && planSearch.addEventListener("input", () => { query = planSearch.value; renderTree(); });
    planClear && planClear.addEventListener("click", () => { selected.clear(); persistSel(); renderTree(); renderView(); });

    async function buildAggregate() {
      if (!selected.size) return [];
      const params = new URLSearchParams();
      Array.from(selected).forEach((id) => params.append("ids", id));
      const res = await fetch("/api/plan/aggregate?" + params.toString());
      const data = await res.json();
      return data.groups || [];
    }

    function isHave(it) { return it.key in have ? have[it.key] : !!it.pantry; }

    async function renderView() {
      const empty = $("#plan-empty");
      const active = $("#plan-active");
      if (!selected.size) {
        empty.style.display = "";
        active.hidden = true;
        $("#sb-info").textContent = "0 recept valda";
        return;
      }
      empty.style.display = "none";
      active.hidden = false;
      const groups = await buildAggregate();
      const totalItems = groups.reduce((n, g) => n + g.items.length, 0);
      const haveCount = groups.reduce((n, g) => n + g.items.filter(isHave).length, 0);
      const buyGroups = groups.map((g) => ({ cat: g.cat, items: g.items.filter((it) => !isHave(it)) }))
        .filter((g) => g.items.length);
      const buyCount = buyGroups.reduce((n, g) => n + g.items.length, 0);

      // chips
      const sel = Array.from(selected).map((id) => RECIPES.find((r) => r.id === id)).filter(Boolean);
      $("#plan-chips").innerHTML = sel.map((r) => `<span class="plan-chip">${escapeHtml(r.title)}</span>`).join("");

      const onList = step === "list" && buyCount > 0;
      $("#plan-title").textContent = onList ? "Inköpslista" : "Inventering";
      $("#plan-subtitle").textContent = onList
        ? `${buyCount} varor att handla · ${sel.length} recept`
        : `${totalItems} ingredienser · ${haveCount} redan hemma`;

      // steps state
      $$(".plan-step").forEach((b) => {
        const target = b.dataset.planStep;
        b.classList.toggle("active", onList ? target === "list" : target === "inventory");
        if (target === "list") b.disabled = buyCount === 0;
      });

      const list = $("#plan-list");
      const foot = $("#plan-foot");
      const instr = $("#plan-instr");
      const actions = $("#plan-actions");

      if (!onList) {
        instr.style.display = "";
        foot.style.display = "";
        actions.innerHTML = "";
        list.innerHTML = groups.map((g) => `
          <section class="plan-cat">
            <h3 class="plan-cat-h">${escapeHtml(g.cat)}</h3>
            <ul>
              ${g.items.map((it) => {
                const on = isHave(it);
                return `<li class="plan-item${on ? " have" : ""}${it.pantry ? " is-pantry" : ""}" data-key="${escapeHtml(it.key)}">
                  <span class="pi-box${on ? " on" : ""}">${on ? svgCheck : ""}</span>
                  <span class="pi-qty">${escapeHtml(it.qty_display)} ${escapeHtml(it.unit || "")}</span>
                  <span class="pi-name">${escapeHtml(it.name)}</span>
                  ${it.pantry ? '<span class="pi-pantry">skafferi</span>' : ""}
                </li>`;
              }).join("")}
            </ul>
          </section>`).join("");
        $$(".plan-item", list).forEach((li) => li.addEventListener("click", () => {
          const k = li.dataset.key;
          have[k] = !(k in have ? have[k] : groupsItemPantry(groups, k));
          renderView();
        }));
        $("#plan-create").disabled = buyCount === 0;
        $("#plan-foot-note").textContent = `${haveCount} av ${totalItems} redan hemma · ${buyCount} att handla`;
      } else {
        instr.style.display = "none";
        foot.style.display = "none";
        actions.innerHTML = `<button class="btn-primary" id="plan-copy">${copied ? "Kopierat ✓" : "Kopiera lista"}</button>`;
        list.innerHTML = buyGroups.map((g) => `
          <section class="plan-cat">
            <h3 class="plan-cat-h">${escapeHtml(g.cat)}</h3>
            <ul>
              ${g.items.map((it) => {
                const on = !!bought[it.key];
                return `<li class="plan-item${on ? " done" : ""}" data-key="${escapeHtml(it.key)}">
                  <span class="pi-box${on ? " on" : ""}">${on ? svgCheck : ""}</span>
                  <span class="pi-qty">${escapeHtml(it.qty_display)} ${escapeHtml(it.unit || "")}</span>
                  <span class="pi-name">${escapeHtml(it.name)}</span>
                </li>`;
              }).join("")}
            </ul>
          </section>`).join("");
        $$(".plan-item", list).forEach((li) => li.addEventListener("click", () => {
          bought[li.dataset.key] = !bought[li.dataset.key];
          renderView();
        }));
        $("#plan-copy").addEventListener("click", async () => {
          const lines = [`Inköpslista — ${sel.length} recept`, ""];
          buyGroups.forEach((g) => {
            lines.push(g.cat.toUpperCase());
            g.items.forEach((it) => lines.push(`- ${it.qty_display} ${it.unit || ""} ${it.name}`));
            lines.push("");
          });
          const text = lines.join("\n").trim();
          try { await navigator.clipboard.writeText(text); }
          catch (_) {
            const ta = document.createElement("textarea");
            ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
            document.body.appendChild(ta); ta.select();
            try { document.execCommand("copy"); } catch (_) {}
            document.body.removeChild(ta);
          }
          copied = true; renderView();
          setTimeout(() => { copied = false; renderView(); }, 1800);
        });
      }

      $("#sb-info").textContent = `${sel.length} recept valda`;
    }
    function groupsItemPantry(groups, key) {
      for (const g of groups) for (const it of g.items) if (it.key === key) return !!it.pantry;
      return false;
    }

    $$(".plan-step").forEach((b) => b.addEventListener("click", () => {
      if (b.disabled) return;
      step = b.dataset.planStep; renderView();
    }));
    $("#plan-create").addEventListener("click", () => { step = "list"; renderView(); });

    renderTree();
    renderView();
  }
})();
