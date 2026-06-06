/* Skal: aktivitetsrad, utforskare, flikstrip, statusrad, kommandopalett, App. */

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "fontPair": "spectral",
  "density": "kompakt",
  "accent": "#2f3e46",
  "ide": "tydlig"
}/*EDITMODE-END*/;

const FONT_PAIRS = {
  archivo: { serif: "'Archivo', sans-serif", mono: "'IBM Plex Mono', monospace", label: "Archivo / IBM Plex" },
  plex: { serif: "'IBM Plex Sans', sans-serif", mono: "'IBM Plex Mono', monospace", label: "IBM Plex Sans / Mono" },
  spectral: { serif: "'Spectral', Georgia, serif", mono: "'IBM Plex Mono', monospace", label: "Spectral / IBM Plex" },
};

/* ---- Aktivitetsrad ---- */
function ActivityRail({ mode, setMode }) {
  const items = [
    { id: "recept", icon: "recept", label: "Recept" },
    { id: "ingredienser", icon: "bibliotek", label: "Ingredienser" },
    { id: "planering", icon: "planering", label: "Planering" },
  ];
  return (
    <nav className="rail">
      <div className="rail-items">
        {items.map((it) => (
          <button key={it.id} className={cx("rail-btn", mode === it.id && "active")}
            onClick={() => setMode(it.id)} title={it.label}>
            <Ic name={it.icon} size={22} />
            <span className="rail-tip">{it.label}</span>
          </button>
        ))}
      </div>
    </nav>
  );
}

/* ---- Utforskare (sidopanel) ---- */
function groupRecipes(recipes, grouping) {
  if (grouping === "az")
    return [{ key: "A–Ö", items: [...recipes].sort((a, b) => a.title.localeCompare(b.title, "sv")) }];
  const field = grouping === "kategori" ? "category" : "cuisine";
  const map = {};
  recipes.forEach((r) => { (map[r[field]] = map[r[field]] || []).push(r); });
  return Object.keys(map).sort((a, b) => a.localeCompare(b, "sv"))
    .map((k) => ({ key: k, items: map[k].sort((a, b) => a.title.localeCompare(b.title, "sv")) }));
}

function Explorer({ mode, db, grouping, setGrouping, query, setQuery, activeKey,
  onOpenRecipe, catFilter, setCatFilter, selIds, toggleSel, setAllSel,
  planGrouping, setPlanGrouping, planQuery, setPlanQuery }) {

  if (mode === "ingredienser") {
    const cats = ["Alla", ...db.categories];
    return (
      <aside className="explorer">
        <div className="exp-head"><span className="exp-title">Kategorier</span></div>
        <div className="exp-search">
          <Ic name="search" size={14} />
          <input placeholder="Filtrera namn / alias…" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <div className="exp-scroll">
          {cats.map((c) => (
            <button key={c} className={cx("cat-row", (catFilter || "Alla") === c && "active")}
              onClick={() => setCatFilter(c === "Alla" ? "" : c)}>
              <span>{c}</span>
              <span className="cat-count">
                {c === "Alla" ? db.catalog.length : db.catalog.filter((x) => x.cat === c).length}
              </span>
            </button>
          ))}
        </div>
      </aside>
    );
  }

  if (mode === "planering") {
    const filtered = db.recipes.filter((r) =>
      !planQuery || r.title.toLowerCase().includes(planQuery.toLowerCase()) ||
      r.cuisine.toLowerCase().includes(planQuery.toLowerCase()));
    const groups = groupRecipes(filtered, planGrouping);
    return (
      <aside className="explorer">
        <div className="exp-head">
          <span className="exp-title">Välj recept</span>
          <select className="group-sel" value={planGrouping} onChange={(e) => setPlanGrouping(e.target.value)}>
            <option value="kok">efter kök</option>
            <option value="kategori">efter kategori</option>
            <option value="az">A–Ö</option>
          </select>
        </div>
        <div className="exp-search">
          <Ic name="search" size={14} />
          <input placeholder="Sök recept…" value={planQuery} onChange={(e) => setPlanQuery(e.target.value)} />
        </div>
        <div className="exp-sub">
          <div className="exp-mini">
            <button onClick={() => setAllSel(false)}>rensa</button>
          </div>
          <span className="exp-count">{selIds.size} valda</span>
        </div>
        <div className="exp-scroll">
          {groups.map((g) => (
            <div key={g.key} className="tree-group">
              <div className="tree-group-h">
                <span>{g.key}</span>
                <span className="tg-count">{g.items.length}</span>
              </div>
              {g.items.map((r) => (
                <button key={r.id} className={cx("pick-row", selIds.has(r.id) && "on")}
                  onClick={() => toggleSel(r.id)}>
                  <span className={cx("pi-box sm", selIds.has(r.id) && "on")}>
                    {selIds.has(r.id) ? <Ic name="check" size={11} /> : null}
                  </span>
                  <span className="pick-name">{r.title}</span>
                </button>
              ))}
            </div>
          ))}
          {filtered.length === 0 && <div className="empty sm">Inga träffar.</div>}
        </div>
      </aside>
    );
  }

  // recept-läge: filträd
  const filtered = db.recipes.filter((r) =>
    !query || r.title.toLowerCase().includes(query.toLowerCase()) ||
    r.cuisine.toLowerCase().includes(query.toLowerCase()));
  const groups = groupRecipes(filtered, grouping);
  return (
    <aside className="explorer">
      <div className="exp-head">
        <span className="exp-title">Recept</span>
        <select className="group-sel" value={grouping} onChange={(e) => setGrouping(e.target.value)}>
          <option value="kok">efter kök</option>
          <option value="kategori">efter kategori</option>
          <option value="az">A–Ö</option>
        </select>
      </div>
      <div className="exp-search">
        <Ic name="search" size={14} />
        <input placeholder="Sök recept…" value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>
      <div className="exp-scroll">
        {groups.map((g) => (
          <div key={g.key} className="tree-group">
            <div className="tree-group-h">
              <span>{g.key}</span>
              <span className="tg-count">{g.items.length}</span>
            </div>
            {g.items.map((r) => (
              <button key={r.id} className={cx("tree-row", activeKey === `r:${r.id}` && "active")}
                onClick={() => onOpenRecipe(r.id)}>
                <span className="tr-name">{r.title}</span>
                {r.versions.length > 1 && <span className="tr-ver">v{r.versions.length}</span>}
              </button>
            ))}
          </div>
        ))}
        {filtered.length === 0 && <div className="empty sm">Inga träffar.</div>}
      </div>
    </aside>
  );
}

/* ---- Flikstrip ---- */
function TabStrip({ tabs, activeKey, setActive, closeTab }) {
  return (
    <div className="tabstrip">
      {tabs.map((t) => (
        <div key={t.key} className={cx("tab", activeKey === t.key && "active", t.fixed && "fixed")}
          onClick={() => setActive(t.key)}>
          <span className="tab-label">{t.title}</span>
          {!t.fixed && (
            <button className="tab-close" onClick={(e) => { e.stopPropagation(); closeTab(t.key); }}>
              <Ic name="close" size={13} />
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

/* ---- Statusrad ---- */
function StatusBar({ mode, info, ide }) {
  return (
    <div className="statusbar">
      <span className="sb-mode">{mode}</span>
      {info.branch && <span className="sb-item">{info.branch}</span>}
      {info.left && <span className="sb-item">{info.left}</span>}
      <span className="sb-spacer" />
      <span className="sb-item dim">ide: {ide}</span>
      <span className="sb-item">⌘K</span>
    </div>
  );
}

/* ---- Kommandopalett ---- */
function CommandPalette({ open, onClose, db, onOpenRecipe }) {
  const [q, setQ] = React.useState("");
  const inputRef = React.useRef(null);
  React.useEffect(() => { if (open) { setQ(""); setTimeout(() => inputRef.current && inputRef.current.focus(), 30); } }, [open]);
  if (!open) return null;
  const res = db.recipes
    .filter((r) => r.title.toLowerCase().includes(q.toLowerCase()) || r.cuisine.toLowerCase().includes(q.toLowerCase()))
    .slice(0, 8);
  return (
    <div className="cmd-overlay" onClick={onClose}>
      <div className="cmd-box" onClick={(e) => e.stopPropagation()}>
        <div className="cmd-input">
          <Ic name="search" size={16} />
          <input ref={inputRef} placeholder="Öppna recept…" value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && res[0]) { onOpenRecipe(res[0].id); onClose(); }
              if (e.key === "Escape") onClose();
            }} />
          <span className="cmd-esc">esc</span>
        </div>
        <div className="cmd-res">
          {res.map((r) => (
            <button key={r.id} className="cmd-row" onClick={() => { onOpenRecipe(r.id); onClose(); }}>
              <span className="cmd-title">{r.title}</span>
              <span className="cmd-meta">{r.cuisine}</span>
            </button>
          ))}
          {res.length === 0 && <div className="cmd-none">Inga recept matchar.</div>}
        </div>
      </div>
    </div>
  );
}

/* ============== APP ============== */
function App() {
  const db = window.RECIPE_DB;
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [mode, setMode] = React.useState("recept");
  const [grouping, setGrouping] = React.useState("kok");
  const [query, setQuery] = React.useState("");
  const [planGrouping, setPlanGrouping] = React.useState("kok");
  const [planQuery, setPlanQuery] = React.useState("");
  const [catFilter, setCatFilter] = React.useState("");
  const [tabs, setTabs] = React.useState(() => {
    const first = db.recipes.find((r) => r.versions.length > 1) || db.recipes[0];
    return [{ key: `r:${first.id}`, kind: "recipe", recipeId: first.id, title: first.title, icon: "file" }];
  });
  const [activeKey, setActiveKey] = React.useState(tabs[0].key);
  const [selIds, setSelIds] = React.useState(() => new Set([3]));
  const [hidePantry, setHidePantry] = React.useState(false);
  const [palette, setPalette] = React.useState(false);
  const [annos, setAnnos] = React.useState(() => {
    try { return JSON.parse(localStorage.getItem("mise.annos.v1")) || {}; } catch (e) { return {}; }
  });
  const setAnno = (key, text) => setAnnos((prev) => {
    const n = { ...prev };
    if (text) n[key] = text; else delete n[key];
    try { localStorage.setItem("mise.annos.v1", JSON.stringify(n)); } catch (e) {}
    return n;
  });

  React.useEffect(() => {
    const h = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((p) => !p); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  const openRecipe = (id) => {
    setMode("recept");
    const key = `r:${id}`;
    setTabs((ts) => ts.some((x) => x.key === key) ? ts
      : [...ts, { key, kind: "recipe", recipeId: id, title: db.recipes.find((r) => r.id === id).title, icon: "file" }]);
    setActiveKey(key);
  };
  const openDiff = (recipe, vid) => {
    const key = `d:${recipe.id}`;
    setTabs((ts) => ts.some((x) => x.key === key) ? ts
      : [...ts, { key, kind: "diff", recipeId: recipe.id, initial: vid, title: `${recipe.title} · diff`, icon: "diff" }]);
    setActiveKey(key);
  };
  const closeTab = (key) => {
    setTabs((ts) => {
      const idx = ts.findIndex((x) => x.key === key);
      const next = ts.filter((x) => x.key !== key);
      if (activeKey === key && next.length) setActiveKey(next[Math.max(0, idx - 1)].key);
      return next;
    });
  };
  const toggleSel = (id) => setSelIds((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const setAllSel = (all) => setSelIds(all ? new Set(db.recipes.map((r) => r.id)) : new Set());

  // editor-flikar beror på läge
  const recipeTabs = tabs;
  const toolTab = mode === "ingredienser"
    ? [{ key: "lib", fixed: true, title: "ingrediensbibliotek", icon: "bibliotek" }]
    : mode === "planering"
      ? [{ key: "plan", fixed: true, title: "inköpslista", icon: "planering" }]
      : null;
  const stripTabs = mode === "recept" ? recipeTabs : toolTab;
  const stripActive = mode === "recept" ? activeKey : stripTabs[0].key;

  const activeTab = recipeTabs.find((x) => x.key === activeKey);
  const activeRecipe = activeTab && db.recipes.find((r) => r.id === activeTab.recipeId);

  // statusrad-info
  let info = {};
  if (mode === "recept" && activeTab) {
    const r = activeRecipe;
    if (activeTab.kind === "recipe") info = { branch: currentVersion(r).label, left: `${r.cuisine} · ${r.time}` };
    else info = { branch: "diff", left: r.title };
  } else if (mode === "ingredienser") {
    info = { left: `${db.catalog.length} ingredienser` };
  } else {
    info = { left: `${selIds.size} recept valda` };
  }

  const printList = () => window.print();

  return (
    <div className={cx("ide", `dens-${t.density}`, `ide-${t.ide}`)}
      style={{ "--serif": FONT_PAIRS[t.fontPair].serif, "--mono": FONT_PAIRS[t.fontPair].mono, "--accent": t.accent }}>
      <ActivityRail mode={mode} setMode={setMode} />
      <Explorer mode={mode} db={db} grouping={grouping} setGrouping={setGrouping}
        query={query} setQuery={setQuery} activeKey={activeKey} onOpenRecipe={openRecipe}
        catFilter={catFilter} setCatFilter={setCatFilter}
        selIds={selIds} toggleSel={toggleSel} setAllSel={setAllSel}
        planGrouping={planGrouping} setPlanGrouping={setPlanGrouping}
        planQuery={planQuery} setPlanQuery={setPlanQuery} />
      <main className="editor">
        <TabStrip tabs={stripTabs} activeKey={stripActive}
          setActive={setActiveKey} closeTab={closeTab} />
        <div className="editor-body">
          {mode === "recept" && (!activeTab ? (
            <div className="welcome">
              <div className="welcome-mark">mise</div>
              <p>Öppna ett recept i panelen till vänster, eller tryck <kbd>⌘K</kbd>.</p>
            </div>
          ) : activeTab.kind === "recipe" ? (
            <RecipeView key={activeTab.key} recipe={activeRecipe} ide={t.ide} onOpenDiff={openDiff}
              annos={annos} setAnno={setAnno} />
          ) : (
            <DiffView key={activeTab.key} recipe={activeRecipe} initial={activeTab.initial} />
          ))}
          {mode === "ingredienser" && (
            <IngredientView db={db} catFilter={catFilter} query={query} onOpenRecipe={openRecipe} />
          )}
          {mode === "planering" && (
            <PlannerView db={db} selIds={selIds} onPrint={printList} />
          )}
        </div>
        <StatusBar mode={mode} info={info} ide={t.ide} />
      </main>

      <CommandPalette open={palette} onClose={() => setPalette(false)} db={db} onOpenRecipe={openRecipe} />

      <TweaksPanel>
        <TweakSection label="Typografi" />
        <TweakSelect label="Typsnittspar" value={t.fontPair}
          options={[{ value: "archivo", label: "Archivo / IBM Plex" },
            { value: "plex", label: "IBM Plex Sans / Mono" },
            { value: "spectral", label: "Spectral / IBM Plex" }]}
          onChange={(v) => setTweak("fontPair", v)} />
        <TweakSection label="Layout" />
        <TweakRadio label="Densitet" value={t.density}
          options={["kompakt", "normal", "luftig"]} onChange={(v) => setTweak("density", v)} />
        <TweakRadio label="IDE-känsla" value={t.ide}
          options={["subtil", "tydlig", "nördig"]} onChange={(v) => setTweak("ide", v)} />
        <TweakSection label="Färg" />
        <TweakColor label="Accent" value={t.accent}
          options={["#2f3e46", "#3f6b73", "#454b54", "#6a5040", "#5c6b7a"]}
          onChange={(v) => setTweak("accent", v)} />
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
