/* Strukturerad ingrediensredigerare för skapa/redigera-formuläret.
   - Radbaserad inmatning: mängd / enhet / ingrediens / anteckning.
   - Livevalidering mot katalogen (namn + alias), okända namn listas och blockerar spara.
   - Serialiserar raderna till JSON i #ingredients-json vid submit. */
(function () {
  "use strict";

  const DATA_EL = document.getElementById("edit-data");
  if (!DATA_EL) return;
  const DATA = JSON.parse(DATA_EL.textContent);
  const CATALOG = DATA.catalog || [];

  const COMMON_UNITS = [
    "st", "msk", "tsk", "krm", "nypa", "dl", "cl", "ml", "l",
    "g", "kg", "skiva", "klyfta", "kruka", "blad", "burk",
    "förpackning", "paket", "filé", "bit", "portion", "cm",
  ];

  const form = document.getElementById("edit-form");
  const rowsEl = document.getElementById("ing-rows");
  const addBtn = document.getElementById("ing-add");
  const statusEl = document.getElementById("ing-status");
  const jsonField = document.getElementById("ingredients-json");

  /* ---------- datalistor ---------- */
  const nameList = document.getElementById("cat-ings");
  const unitList = document.getElementById("cat-units");
  const nameLookup = new Map(); // lowercase name/alias -> canon
  const seenNames = new Set();

  CATALOG.forEach((c) => {
    [c.name].concat(c.aliases || []).forEach((n) => {
      const k = String(n).toLowerCase().trim();
      if (k && !seenNames.has(k)) {
        seenNames.add(k);
        const opt = document.createElement("option");
        opt.value = n;
        nameList.appendChild(opt);
        nameLookup.set(k, c.name);
      }
    });
  });
  new Set(COMMON_UNITS.concat(CATALOG.map((c) => c.default_unit).filter(Boolean)))
    .forEach((u) => {
      const opt = document.createElement("option");
      opt.value = u;
      unitList.appendChild(opt);
    });

  function resolveName(value) {
    const k = String(value || "").toLowerCase().trim();
    return k ? nameLookup.get(k) || null : null;
  }

  /* ---------- rader ---------- */
  function buildRow(initial) {
    const wrap = document.createElement("div");
    wrap.className = "ing-row";

    const amt = document.createElement("input");
    amt.type = "text"; amt.className = "ing-f ing-f-amt"; amt.placeholder = "200";
    amt.autocomplete = "off"; amt.inputMode = "decimal"; amt.value = initial.amount || "";

    const unit = document.createElement("input");
    unit.type = "text"; unit.className = "ing-f ing-f-unit"; unit.placeholder = "g";
    unit.autocomplete = "off"; unit.setAttribute("list", "cat-units");
    unit.value = initial.unit || "";

    const name = document.createElement("input");
    name.type = "text"; name.className = "ing-f ing-f-name"; name.placeholder = "ingrediens";
    name.autocomplete = "off"; name.setAttribute("list", "cat-ings");
    name.value = initial.name || "";

    const note = document.createElement("input");
    note.type = "text"; note.className = "ing-f ing-f-note"; note.placeholder = "anteckning (valfritt)";
    note.autocomplete = "off"; note.value = initial.note || "";

    const del = document.createElement("button");
    del.type = "button"; del.className = "ing-f-del"; del.title = "Ta bort rad";
    del.setAttribute("aria-label", "Ta bort rad");
    del.textContent = "\u00d7";

    const warn = document.createElement("span");
    warn.className = "ing-f-warn";
    warn.textContent = "finns ej i katalogen \u2014 lägg till i biblioteket eller ta bort raden";

    [amt, unit, name, note, del, warn].forEach((el) => wrap.appendChild(el));

    const validate = () => {
      const val = name.value.trim();
      if (!val) { wrap.classList.remove("bad"); return true; }
      const ok = !!resolveName(val);
      wrap.classList.toggle("bad", !ok);
      return ok;
    };
    name.addEventListener("input", () => { validate(); updateStatus(); });
    name.addEventListener("change", () => { name.value = resolveName(name.value) || name.value; });

    del.addEventListener("click", () => { wrap.remove(); updateStatus(); });

    // Enter i namnfältet -> ny rad nedanför
    name.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (validate()) addRow();
      }
    });

    wrap._validate = validate;
    validate();
    return wrap;
  }

  function addRow(initial) {
    const row = buildRow(initial || { amount: "", unit: "", name: "", note: "" });
    rowsEl.appendChild(row);
    updateStatus();
    return row;
  }

  function collectRows() {
    const out = [];
    rowsEl.querySelectorAll(".ing-row").forEach((row) => {
      const name = row.querySelector(".ing-f-name").value.trim();
      if (!name) return;
      out.push({
        name: name,
        amount: row.querySelector(".ing-f-amt").value.trim(),
        unit: row.querySelector(".ing-f-unit").value.trim(),
        note: row.querySelector(".ing-f-note").value.trim(),
      });
    });
    return out;
  }

  function unknownCount() {
    let n = 0;
    rowsEl.querySelectorAll(".ing-row").forEach((r) => { if (r.classList.contains("bad")) n++; });
    return n;
  }

  function updateStatus() {
    if (!statusEl) return;
    const rows = collectRows();
    const unknown = unknownCount();
    if (!rows.length) { statusEl.textContent = ""; statusEl.classList.remove("err"); return; }
    if (unknown > 0) {
      statusEl.textContent = unknown + " okänd" + (unknown > 1 ? "a" : "") + " ingredienser \u2014 spara blockerat";
      statusEl.classList.add("err");
    } else {
      statusEl.textContent = rows.length + " rader";
      statusEl.classList.remove("err");
    }
  }

  addBtn && addBtn.addEventListener("click", () => addRow());

  /* ---------- taggar ---------- */
  const tagInput = document.getElementById("tags");
  const chipBox = document.querySelector("[data-tag-chips]");
  if (tagInput && chipBox) {
    const current = () => tagInput.value.split(",").map((s) => s.trim()).filter(Boolean);
    const sync = () => {
      const set = new Set(current().map((s) => s.toLowerCase()));
      chipBox.querySelectorAll("[data-tag]").forEach((c) => {
        const on = set.has(c.dataset.tag.toLowerCase());
        c.classList.toggle("on", on);
      });
    };
    chipBox.addEventListener("click", (e) => {
      const chip = e.target.closest("[data-tag]");
      if (!chip) return;
      const arr = current();
      const v = chip.dataset.tag;
      const idx = arr.map((s) => s.toLowerCase()).indexOf(v.toLowerCase());
      if (idx === -1) arr.push(v); else arr.splice(idx, 1);
      tagInput.value = arr.join(", ");
      sync();
    });
    tagInput.addEventListener("input", sync);
    sync();
  }

  /* ---------- submit ---------- */
  form && form.addEventListener("submit", (e) => {
    const title = document.getElementById("title").value.trim();
    if (!title) {
      e.preventDefault();
      document.getElementById("title").focus();
      return;
    }
    rowsEl.querySelectorAll(".ing-row").forEach((r) => r._validate());
    const unknown = [];
    rowsEl.querySelectorAll(".ing-row.bad").forEach((r) => {
      unknown.push(r.querySelector(".ing-f-name").value.trim());
    });
    if (unknown.length) {
      e.preventDefault();
      let box = document.querySelector(".ef-errors");
      if (!box) {
        box = document.createElement("div");
        box.className = "errbox ef-errors";
        box.setAttribute("role", "alert");
        const head = document.querySelector(".ef-head");
        head.parentNode.insertBefore(box, head.nextSibling);
      }
      box.innerHTML = "<strong>Kan inte spara:</strong> dessa ingredienser finns inte i katalogen: "
        + unknown.join(", ")
        + ". Lägg till dem i <a href=\"/ingredients\">ingrediensbiblioteket</a> först.";
      box.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (jsonField) jsonField.value = JSON.stringify(collectRows());
  });

  /* ---------- init ---------- */
  (DATA.ingredients || []).forEach((ing) => addRow(ing));
  if (!(DATA.ingredients || []).length) addRow();
  updateStatus();
})();