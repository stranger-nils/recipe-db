/* Ingrediensbibliotek + Planering (inköpslista). */

function computeUsage(db) {
  // map: ingrediensnamn (lower) -> Set(recipe.id)
  const usage = {};
  db.recipes.forEach((r) => {
    const v = currentVersion(r);
    v.ingredients.forEach((x) => {
      const k = x.name.toLowerCase();
      (usage[k] = usage[k] || new Set()).add(r.id);
    });
  });
  return usage;
}

function IngredientView({ db, catFilter, query, onOpenRecipe }) {
  const usage = React.useMemo(() => computeUsage(db), [db]);
  const [rows, setRows] = React.useState(() => db.catalog.map((c) => ({ ...c })));

  const set = (i, key, val) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [key]: val } : r)));

  const visible = rows
    .map((r, i) => ({ r, i }))
    .filter(({ r }) => (!catFilter || r.cat === catFilter))
    .filter(({ r }) =>
      !query ||
      r.name.toLowerCase().includes(query.toLowerCase()) ||
      (r.aliases || "").toLowerCase().includes(query.toLowerCase()));

  const idsFor = (name) => {
    const s = usage[name.toLowerCase()];
    return s ? Array.from(s).sort((a, b) => a - b) : [];
  };

  return (
    <div className="lib">
      <div className="lib-head">
        <h1>Ingrediensbibliotek</h1>
      </div>
      <div className="lib-table-wrap">
        <table className="lib-table">
          <thead>
            <tr>
              <th className="c-name">Namn</th>
              <th className="c-cat">Kategori</th>
              <th className="c-unit">Default-enhet</th>
              <th className="c-alias">Alias</th>
              <th className="c-ids">Används i</th>
              <th className="c-pan">Skafferi</th>
            </tr>
          </thead>
          <tbody>
            {visible.map(({ r, i }) => {
              const recs = idsFor(r.name).map((id) => db.recipes.find((x) => x.id === id)).filter(Boolean);
              return (
                <tr key={r.name}>
                  <td className="c-name"><span className="ing-name">{r.name}</span></td>
                  <td className="c-cat">
                    <select value={r.cat} onChange={(e) => set(i, "cat", e.target.value)}>
                      {db.categories.map((c) => <option key={c}>{c}</option>)}
                    </select>
                  </td>
                  <td className="c-unit">
                    <input value={r.unit} onChange={(e) => set(i, "unit", e.target.value)} />
                  </td>
                  <td className="c-alias">
                    <input value={r.aliases} placeholder="—"
                      onChange={(e) => set(i, "aliases", e.target.value)} />
                  </td>
                  <td className="c-ids">
                    {recs.length ? (
                      <span className="recipe-links">
                        {recs.map((rc) => (
                          <button key={rc.id} className="recipe-link" title={`Öppna ${rc.title}`}
                            onClick={() => onOpenRecipe(rc.id)}>{rc.title}</button>
                        ))}
                      </span>
                    ) : <span className="id-none">–</span>}
                  </td>
                  <td className="c-pan">
                    <button className={cx("pan-toggle", r.pantry && "on")}
                      onClick={() => set(i, "pantry", !r.pantry)} title="Skafferivara">
                      {r.pantry ? <Ic name="check" size={14} /> : null}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {visible.length === 0 && <div className="empty">Inga ingredienser matchar.</div>}
      </div>
    </div>
  );
}

/* ---------------- PLANERING ---------------- */

function buildList(db, selIds) {
  const byCat = {};
  selIds.forEach((id) => {
    const r = db.recipes.find((x) => x.id === id);
    if (!r) return;
    const v = currentVersion(r);
    v.ingredients.forEach((x) => {
      const cat = x.cat || "Övrigt";
      const key = x.name.toLowerCase() + "|" + x.unit;
      byCat[cat] = byCat[cat] || {};
      if (!byCat[cat][key]) byCat[cat][key] = { key, name: x.name, unit: x.unit, qty: 0, pantry: x.pantry, from: new Set() };
      byCat[cat][key].qty += x.qty || 0;
      byCat[cat][key].from.add(r.title);
    });
  });
  return db.categories
    .filter((c) => byCat[c])
    .map((c) => ({ cat: c, items: Object.values(byCat[c]).sort((a, b) => a.name.localeCompare(b.name, "sv")) }));
}

function PlannerView({ db, selIds, onPrint }) {
  const [step, setStep] = React.useState("inventory");
  const [have, setHave] = React.useState({});    // override: key -> har hemma
  const [bought, setBought] = React.useState({}); // ikryssat under handling
  const [copied, setCopied] = React.useState(false);

  const sel = Array.from(selIds);
  const selRecipes = sel.map((id) => db.recipes.find((r) => r.id === id)).filter(Boolean);
  const groups = buildList(db, sel);
  const isHave = (it) => (it.key in have ? have[it.key] : it.pantry);
  const totalItems = groups.reduce((n, g) => n + g.items.length, 0);
  const haveCount = groups.reduce((n, g) => n + g.items.filter(isHave).length, 0);
  const buyGroups = groups
    .map((g) => ({ cat: g.cat, items: g.items.filter((it) => !isHave(it)) }))
    .filter((g) => g.items.length);
  const buyCount = buyGroups.reduce((n, g) => n + g.items.length, 0);

  const toggleHave = (it) => setHave((h) => ({ ...h, [it.key]: !isHave(it) }));
  const toggleBought = (it) => setBought((b) => ({ ...b, [it.key]: !b[it.key] }));

  const buildText = () => {
    const lines = [`Inköpslista — ${selRecipes.length} recept`, ""];
    buyGroups.forEach((g) => {
      lines.push(g.cat.toUpperCase());
      g.items.forEach((it) => lines.push(`- ${fmtQty(it.qty)} ${it.unit} ${it.name}`));
      lines.push("");
    });
    return lines.join("\n").trim();
  };
  const copy = async () => {
    const text = buildText();
    try {
      await navigator.clipboard.writeText(text);
    } catch (e) {
      const ta = document.createElement("textarea");
      ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); } catch (_) {}
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const onList = step === "list" && selRecipes.length > 0;

  if (selRecipes.length === 0) {
    return (
      <div className="plan">
        <div className="plan-head"><div><h1>Planering</h1>
          <p className="plan-sub">Välj recept i panelen till vänster.</p></div></div>
        <div className="plan-empty">
          <p>Bocka i recept i panelen så listas alla ingredienser för inventering,<br />
            innan du genererar en inköpslista att kopiera.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="plan">
      <div className="plan-head">
        <div>
          <h1>{onList ? "Inköpslista" : "Inventering"}</h1>
          <p className="plan-sub">
            {onList
              ? `${buyCount} varor att handla · ${selRecipes.length} recept`
              : `${totalItems} ingredienser · ${haveCount} redan hemma`}
          </p>
        </div>
        {onList && (
          <div className="plan-actions">
            <button className="btn-primary" onClick={copy}>{copied ? "Kopierat \u2713" : "Kopiera lista"}</button>
          </div>
        )}
      </div>

      <div className="plan-steps">
        <button className={cx("plan-step", !onList && "active")} onClick={() => setStep("inventory")}>
          <span className="ps-n">1</span> Inventering
        </button>
        <span className="ps-sep" />
        <button className={cx("plan-step", onList && "active")}
          onClick={() => buyCount && setStep("list")} disabled={!buyCount}>
          <span className="ps-n">2</span> Inköpslista
        </button>
      </div>

      <div className="plan-chips">
        {selRecipes.map((r) => <span key={r.id} className="plan-chip">{r.title}</span>)}
      </div>

      {!onList ? (
        <React.Fragment>
          <p className="plan-instr">Bocka i det du redan har hemma — skafferivaror är förbockade. Resten hamnar på inköpslistan.</p>
          <div className="plan-list">
            {groups.map((g) => (
              <section key={g.cat} className="plan-cat">
                <h3 className="plan-cat-h">{g.cat}</h3>
                <ul>
                  {g.items.map((it) => {
                    const on = isHave(it);
                    return (
                      <li key={it.key} className={cx("plan-item", on && "have")} onClick={() => toggleHave(it)}>
                        <span className={cx("pi-box", on && "on")}>{on ? <Ic name="check" size={12} /> : null}</span>
                        <span className="pi-qty">{fmtQty(it.qty)} {it.unit}</span>
                        <span className="pi-name">{it.name}</span>
                        {it.pantry && <span className="pi-pantry">skafferi</span>}
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
          </div>
          <div className="plan-foot">
            <button className="btn-primary" onClick={() => setStep("list")} disabled={!buyCount}>
              Skapa inköpslista &rarr;
            </button>
            <span className="foot-note">{haveCount} av {totalItems} redan hemma · {buyCount} att handla</span>
          </div>
        </React.Fragment>
      ) : (
        <div className="plan-list">
          {buyGroups.map((g) => (
            <section key={g.cat} className="plan-cat">
              <h3 className="plan-cat-h">{g.cat}</h3>
              <ul>
                {g.items.map((it) => {
                  const on = bought[it.key];
                  return (
                    <li key={it.key} className={cx("plan-item", on && "done")} onClick={() => toggleBought(it)}>
                      <span className={cx("pi-box", on && "on")}>{on ? <Ic name="check" size={12} /> : null}</span>
                      <span className="pi-qty">{fmtQty(it.qty)} {it.unit}</span>
                      <span className="pi-name">{it.name}</span>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

Object.assign(window, { IngredientView, PlannerView });
