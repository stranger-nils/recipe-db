/* Receptvy (öppen i flik) + versionsdiff sida-vid-sida. */

function MetaChip({ icon, children }) {
  return (
    <span className="chip">
      {icon ? <Ic name={icon} size={13} /> : null}
      <span>{children}</span>
    </span>
  );
}

function VersionPicker({ recipe, value, onChange, compact }) {
  return (
    <div className={cx("vpick", compact && "vpick-c")}>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {recipe.versions.map((v) => (
          <option key={v.id} value={v.id}>
            {v.label}{v.current ? " · aktuell" : ""} — {v.date}
          </option>
        ))}
      </select>
    </div>
  );
}

function RecipeView({ recipe, ide, onOpenDiff, annos, setAnno }) {
  const [vid, setVid] = React.useState(currentVersion(recipe).id);
  const ver = recipe.versions.find((v) => v.id === vid) || currentVersion(recipe);
  const base = ver.servings || 4;
  const [serv, setServ] = React.useState(base);
  React.useEffect(() => { setServ(ver.servings || 4); }, [vid]);
  const factor = base ? serv / base : 1;
  const showNums = ide !== "subtil";
  const code = ide === "nördig";
  const [editKey, setEditKey] = React.useState(null);
  const annoKey = (x) => `${recipe.id}:${ver.id}:${x.name}`;
  const stepKey = (i) => `${recipe.id}:${ver.id}:step:${i}`;
  const saveAnno = (key, val) => { setAnno(key, (val || "").trim()); setEditKey(null); };

  const scaleQty = (q) => (q == null ? q : +(q * factor).toFixed(2));

  return (
    <div className={cx("doc", code && "doc-code")}>
      <div className="doc-inner">
        {/* sökväg / frontmatter */}
        {showNums && (
          <div className="breadcrumb">
            <span>{recipe.cuisine.toLowerCase()}</span>
            <Ic name="chevron" size={12} />
            <span>{recipe.slug}.recept</span>
            <span className="bc-ver">@{ver.label}</span>
          </div>
        )}

        <header className="doc-head">
          <h1>{recipe.title}</h1>
          <p className="doc-desc">{recipe.desc}</p>
          <div className="doc-meta">
            <MetaChip>{recipe.cuisine}</MetaChip>
            <MetaChip>{recipe.category}</MetaChip>
            <MetaChip>{recipe.time}</MetaChip>
            <MetaChip>{serv ? `${serv} port` : "ger sats"}</MetaChip>
          </div>
        </header>

        {/* version + skalning */}
        <div className="doc-bar">
          <div className="doc-bar-l">
            <VersionPicker recipe={recipe} value={vid} onChange={setVid} />
            {recipe.versions.length > 1 && (
              <button className="btn-ghost" onClick={() => onOpenDiff(recipe, vid)}>
                Jämför versioner
              </button>
            )}
          </div>
          {base > 0 && (
            <div className="stepper" title="Skala receptet">
              <button onClick={() => setServ((s) => Math.max(1, s - 1))}>–</button>
              <span><b>{serv}</b> port</span>
              <button onClick={() => setServ((s) => s + 1)}>+</button>
            </div>
          )}
        </div>

        {ver.note && (
          <div className="ver-note">
            <span className="ver-note-tag">{ver.label}</span>
            {ver.note}
          </div>
        )}

        {/* ingredienser */}
        <section className="block">
          <h2 className="block-h">{code ? "# ingredienser" : "Ingredienser"}</h2>
          <ul className="ing-list">
            {ver.ingredients.map((x, i) => {
              const key = annoKey(x);
              const note = (annos && annos[key]) || "";
              const editing = editKey === key;
              return (
                <li key={i} className="ing-item">
                  <div className="ing-row">
                    <span className="ing-q">{fmtQty(scaleQty(x.qty))}</span>
                    <span className="ing-u">{x.unit}</span>
                    <span className="ing-n">
                      {x.name}
                      {x.note ? <span className="ing-note">, {x.note}</span> : null}
                      {x.pantry ? <span className="pantry-dot" title="Skafferivara">skafferi</span> : null}
                    </span>
                    <button className={cx("anno-add", note && "has")}
                      onClick={() => setEditKey(editing ? null : key)}>
                      {note ? "redigera" : "+ anteckning"}
                    </button>
                  </div>
                  {editing ? (
                    <div className="anno-edit">
                      <input autoFocus defaultValue={note}
                        placeholder="Minnesanteckning till nästa gång…"
                        onKeyDown={(e) => {
                          if (e.key === "Enter") saveAnno(key, e.target.value);
                          if (e.key === "Escape") setEditKey(null);
                        }}
                        onBlur={(e) => saveAnno(key, e.target.value)} />
                    </div>
                  ) : note ? (
                    <div className="ing-anno" onClick={() => setEditKey(key)} title="Klicka för att redigera">{note}</div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </section>

        {/* steg */}
        <section className="block">
          <h2 className="block-h">{code ? "# tillvägagångssätt" : "Tillvägagångssätt"}</h2>
          <ol className="step-list">
            {ver.steps.map((s, i) => {
              const key = stepKey(i);
              const note = (annos && annos[key]) || "";
              const editing = editKey === key;
              return (
                <li key={i} className="step-item">
                  <div className="step-row">
                    {showNums && <span className="step-num">{String(i + 1).padStart(2, "0")}</span>}
                    <div className="step-main">
                      <span className="step-txt">{s}</span>
                      {editing ? (
                        <div className="anno-edit">
                          <input autoFocus defaultValue={note}
                            placeholder="Minnesanteckning till nästa gång…"
                            onKeyDown={(e) => {
                              if (e.key === "Enter") saveAnno(key, e.target.value);
                              if (e.key === "Escape") setEditKey(null);
                            }}
                            onBlur={(e) => saveAnno(key, e.target.value)} />
                        </div>
                      ) : note ? (
                        <div className="step-anno" onClick={() => setEditKey(key)} title="Klicka för att redigera">{note}</div>
                      ) : null}
                    </div>
                    <button className={cx("anno-add", note && "has")}
                      onClick={() => setEditKey(editing ? null : key)}>
                      {note ? "redigera" : "+ anteckning"}
                    </button>
                  </div>
                </li>
              );
            })}
          </ol>
        </section>
      </div>
    </div>
  );
}

/* ---------------- DIFF ---------------- */

function diffCounts(ingRows, stepRows) {
  let add = 0, del = 0, chg = 0;
  ingRows.concat(stepRows).forEach((r) => {
    if (r.type === "add") add++; else if (r.type === "del") del++; else if (r.type === "chg") chg++;
  });
  return { add, del, chg };
}

function DiffCell({ side, row, kind }) {
  // kind: 'ing' | 'step'
  const isIng = kind === "ing";
  const item = side === "a" ? row.a : row.b;
  let cls = "df-line";
  if (row.type === "add") cls += side === "b" ? " df-add" : " df-empty";
  else if (row.type === "del") cls += side === "a" ? " df-del" : " df-empty";
  else if (row.type === "chg") cls += " df-chg";
  const text = isIng ? ingLine(item) : item;
  return (
    <div className={cls}>
      <span className="df-mark">
        {row.type === "add" && side === "b" ? "+" : row.type === "del" && side === "a" ? "−" : row.type === "chg" ? "~" : ""}
      </span>
      <span className="df-text">{text || ""}</span>
    </div>
  );
}

function DiffSection({ title, rows, kind }) {
  return (
    <div className="df-section">
      <div className="df-sec-h">{title}</div>
      <div className="df-rows">
        {rows.map((r, i) => (
          <div className="df-pair" key={i}>
            <DiffCell side="a" row={r} kind={kind} />
            <DiffCell side="b" row={r} kind={kind} />
          </div>
        ))}
      </div>
    </div>
  );
}

function DiffView({ recipe, initial }) {
  const vs = recipe.versions;
  const startA = initial && vs.length > 1
    ? vs[Math.max(0, vs.findIndex((v) => v.id === initial) - 1)].id
    : vs[0].id;
  const startB = initial || currentVersion(recipe).id;
  const [aid, setAid] = React.useState(startA === startB && vs.length > 1 ? vs[0].id : startA);
  const [bid, setBid] = React.useState(startB);
  const A = vs.find((v) => v.id === aid), B = vs.find((v) => v.id === bid);

  const ingRows = diffIngredients(A.ingredients, B.ingredients);
  const stepRows = diffLines(A.steps, B.steps).map((r) => ({ type: r.type, a: r.a, b: r.b }));
  const c = diffCounts(ingRows, stepRows);

  return (
    <div className="diff">
      <div className="diff-top">
        <div className="diff-title">
          <span>{recipe.title}</span>
          <span className="diff-sub">versionsjämförelse</span>
        </div>
        <div className="diff-counts">
          <span className="dc dc-add">+{c.add} tillagda</span>
          <span className="dc dc-del">−{c.del} borttagna</span>
          <span className="dc dc-chg">~{c.chg} ändrade</span>
        </div>
      </div>
      <div className="diff-cols-h">
        <div className="diff-col-h">
          <span className="col-side">vänster</span>
          <VersionPicker recipe={recipe} value={aid} onChange={setAid} compact />
          <span className="col-date">{A.date}</span>
        </div>
        <div className="diff-col-h diff-col-hr">
          <span className="col-side">höger</span>
          <VersionPicker recipe={recipe} value={bid} onChange={setBid} compact />
          <span className="col-date">{B.date}</span>
        </div>
      </div>
      <div className="diff-body">
        {(A.note || B.note) && (
          <div className="df-pair df-notes">
            <div className="df-note-cell">{A.note}</div>
            <div className="df-note-cell">{B.note}</div>
          </div>
        )}
        <DiffSection title="Ingredienser" rows={ingRows} kind="ing" />
        <DiffSection title="Tillvägagångssätt" rows={stepRows} kind="step" />
      </div>
    </div>
  );
}

Object.assign(window, { RecipeView, DiffView });
