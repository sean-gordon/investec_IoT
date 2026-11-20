// Investec Display sidebar page: edit the display script with a live preview
// against your real Investec data, browse variables and use test mode.
// Plain web component, no build step. Talks to the integration over websocket.

const DOMAIN = "investec_budget";

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const money = (n) =>
  typeof n === "number" ? "R" + n.toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : esc(n);

// Split display text into 4 cells; a full stop attaches to the character before it.
function cells(text) {
  const out = [];
  for (const ch of String(text ?? "")) {
    if (ch === "." && out.length) out[out.length - 1].dot = true;
    else out.push({ ch, dot: false });
  }
  while (out.length < 4) out.unshift({ ch: " ", dot: false });
  return out.slice(-4);
}

class InvestecDisplayPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._state = null;
    this._draft = "";
    this._draftVars = [];
    this._preview = null;
    this._status = "";
    this._loaded = false;
    this._timer = null;
    this._txFilter = "";
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loaded) {
      this._loaded = true;
      this._renderShell();
      this._load();
    }
  }

  set panel(panel) {
    this._panel = panel;
  }

  get _entryId() {
    return this._panel?.config?.entry_id;
  }

  async _ws(type, extra = {}) {
    const msg = { type: `${DOMAIN}/${type}`, ...extra };
    if (this._entryId) msg.entry_id = this._entryId;
    return this._hass.callWS(msg);
  }

  async _load(keepDraft = false) {
    try {
      this._state = await this._ws("state");
      if (!keepDraft) {
        this._draft = this._state.template;
        this._draftVars = (this._state.custom_variables || []).map((v) => ({ ...v }));
      }
      this._error = null;
    } catch (err) {
      this._error = err.message || String(err);
    }
    this._renderAll();
    if (this._state) this._runPreview();
  }

  _schedulePreview() {
    clearTimeout(this._timer);
    this._timer = setTimeout(() => this._runPreview(), 400);
  }

  async _runPreview() {
    try {
      this._preview = await this._ws("preview", { template: this._draft, custom_variables: this._draftVars });
    } catch (err) {
      this._preview = { value: "Err", error: err.message || String(err), raw: "" };
    }
    this._renderPreview();
  }

  async _save() {
    this._setStatus("Saving...");
    try {
      const res = await this._ws("save", { template: this._draft, custom_variables: this._draftVars });
      this._setStatus(res.error ? `Saved. The screen will show Err: ${res.error}` : `Saved. The screen now shows ${res.value}.`);
      await this._load(true);
    } catch (err) {
      this._setStatus(err.message || String(err), true);
    }
  }

  async _setTestMode(on) {
    const id = this._state?.entities?.test_mode;
    if (!id) return;
    await this._hass.callService("switch", on ? "turn_on" : "turn_off", { entity_id: id });
    setTimeout(() => this._load(true), 400);
  }

  async _setTestBalance(value) {
    const id = this._state?.entities?.test_balance;
    const n = Number(value);
    if (!id || Number.isNaN(n)) return;
    await this._hass.callService("number", "set_value", { entity_id: id, value: n });
    setTimeout(() => this._load(true), 400);
  }

  _setStatus(text, isError = false) {
    this._status = text;
    const el = this.shadowRoot.getElementById("status");
    if (el) {
      el.textContent = text;
      el.className = isError ? "status error" : "status";
    }
  }

  _insert(text) {
    const ta = this.shadowRoot.getElementById("editor");
    if (!ta) return;
    const start = ta.selectionStart, end = ta.selectionEnd;
    ta.value = ta.value.slice(0, start) + text + ta.value.slice(end);
    ta.selectionStart = ta.selectionEnd = start + text.length;
    ta.focus();
    this._draft = ta.value;
    this._renderDirty();
    this._schedulePreview();
  }

  // ---------- rendering ----------

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; background:var(--primary-background-color); color:var(--primary-text-color);
                font-family:var(--paper-font-body1_-_font-family, Roboto, sans-serif); min-height:100vh; }
        header { display:flex; align-items:center; gap:12px; padding:0 16px; height:56px;
                 background:var(--app-header-background-color, var(--primary-color)); color:var(--app-header-text-color, #fff); }
        header h1 { font-size:20px; font-weight:400; margin:0; flex:1; }
        header button { background:transparent; border:1px solid currentColor; color:inherit; }
        main { display:grid; grid-template-columns: minmax(0,3fr) minmax(0,2fr); gap:16px; padding:16px; max-width:1400px; margin:0 auto; }
        @media (max-width: 900px) { main { grid-template-columns: 1fr; } }
        .card { background:var(--card-background-color); border-radius:var(--ha-card-border-radius, 12px);
                box-shadow:var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.2)); padding:16px; }
        .card h2 { font-size:16px; font-weight:500; margin:0 0 12px; }
        .full { grid-column: 1 / -1; }
        textarea { width:100%; box-sizing:border-box; min-height:260px; resize:vertical; font:13px/1.5 ui-monospace, Consolas, monospace;
                   background:var(--secondary-background-color); color:var(--primary-text-color);
                   border:1px solid var(--divider-color); border-radius:8px; padding:10px; tab-size:2; }
        select, input { font:inherit; padding:8px; border-radius:8px; border:1px solid var(--divider-color);
                        background:var(--secondary-background-color); color:var(--primary-text-color); }
        button { font:inherit; padding:8px 16px; border-radius:20px; border:none; cursor:pointer;
                 background:var(--primary-color); color:var(--text-primary-color, #fff); }
        button.secondary { background:transparent; color:var(--primary-color); border:1px solid var(--primary-color); }
        button:disabled { opacity:.5; cursor:default; }
        .row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:8px 0; }
        .grow { flex:1; }
        .hint { color:var(--secondary-text-color); font-size:13px; }
        .status { font-size:13px; color:var(--secondary-text-color); min-height:18px; }
        .status.error, .err { color:var(--error-color, #db4437); }
        .led { display:flex; gap:10px; justify-content:center; background:#111; border-radius:10px; padding:22px 16px; margin-bottom:12px; }
        .cell { position:relative; width:52px; height:80px; display:flex; align-items:center; justify-content:center;
                font:700 60px/1 ui-monospace, Consolas, monospace; color:#ffb000; text-shadow:0 0 8px rgba(255,176,0,.8);
                background:#1b1b1b; border-radius:4px; }
        .cell.err { color:#ff3b30; text-shadow:0 0 8px rgba(255,59,48,.8); }
        .cell .dot { position:absolute; right:-7px; bottom:8px; width:9px; height:9px; border-radius:50%; background:#ffb000; box-shadow:0 0 6px #ffb000; }
        table { width:100%; border-collapse:collapse; font-size:13px; }
        th, td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--divider-color); vertical-align:top; }
        th { color:var(--secondary-text-color); font-weight:500; }
        td.num { text-align:right; white-space:nowrap; }
        code { font-family:ui-monospace, Consolas, monospace; font-size:12px; }
        .var { cursor:pointer; color:var(--primary-color); }
        .var:hover { text-decoration:underline; }
        .pill { display:inline-block; padding:2px 8px; border-radius:10px; font-size:12px; background:var(--secondary-background-color); }
        .pill.test { background:var(--warning-color, #ffa600); color:#000; }
        .scroll { max-height:360px; overflow:auto; }
        label.switch { display:flex; align-items:center; gap:8px; cursor:pointer; }
        table.vars-edit td { vertical-align:middle; }
        table.vars-edit td.num code { font-size:14px; }
      </style>
      <header>
        <h1>Investec Display</h1>
        <button id="refresh" title="Reload data from Home Assistant">Refresh</button>
      </header>
      <div id="body"></div>`;
    this.shadowRoot.getElementById("refresh").addEventListener("click", () => this._load(true));
    // One delegated handler for every clickable variable name.
    this.shadowRoot.addEventListener("click", (e) => {
      const t = e.target.closest?.("[data-insert]");
      if (t) this._insert(t.dataset.insert);
    });
  }

  _renderAll() {
    const body = this.shadowRoot.getElementById("body");
    if (this._error) {
      body.innerHTML = `<main><div class="card full"><h2>Not available</h2><p class="err">${esc(this._error)}</p>
        <p class="hint">Check that the Investec Display integration is set up and loaded under Settings &gt; Devices &amp; services.</p></div></main>`;
      return;
    }
    const s = this._state;
    const ex = s.examples.map((e, i) => `<option value="${i}">${esc(e.name)}</option>`).join("");
    body.innerHTML = `
      <main>
        <div class="card">
          <h2>Display script</h2>
          <div class="row">
            <select id="examples" class="grow"><option value="">Load an example...</option>${ex}</select>
          </div>
          <div class="hint" id="exampleHelp"></div>
          <textarea id="editor" spellcheck="false"></textarea>
          <div class="row">
            <button id="save">Save</button>
            <button id="revert" class="secondary">Revert</button>
            <span class="grow"></span>
            <span class="hint" id="dirty"></span>
          </div>
          <div id="status" class="status">${esc(this._status)}</div>
          <p class="hint">Jinja template. It must return 4 characters or fewer (digits, letters, space, minus; full stops are free). The display cannot draw K, M, X, q, w or z.
            Click a variable on the right to insert it. The preview uses your real data and is not saved until you click Save.</p>
        </div>

        <div>
          <div class="card">
            <h2>Preview</h2>
            <div id="preview"></div>
          </div>
          <div class="card" style="margin-top:16px">
            <h2>Test mode</h2>
            <label class="switch"><input type="checkbox" id="testMode" ${s.test_mode ? "checked" : ""}> Use the test balance instead of the real one</label>
            <div class="row">
              <input id="testBalance" type="number" min="0" step="1" value="${esc(s.test_balance)}" style="width:140px">
              <button id="applyBalance" class="secondary">Set test balance</button>
            </div>
            <div class="hint">Transactions and spend stay real. The real balance is ${money(s.variables.live_balance)}.</div>
          </div>
        </div>

        <div class="card full">
          <h2>Variables <span class="pill ${s.test_mode ? "test" : ""}">${s.test_mode ? "test mode" : "live"}</span></h2>
          <div class="row hint">Last fetched ${esc(s.diagnostics.last_fetch || "not yet")}.
            ${s.diagnostics.accounts_skipped?.length ? `<span class="err">Skipped accounts: ${esc(s.diagnostics.accounts_skipped.join(", "))}</span>` : ""}</div>
          <div id="vars"></div>
        </div>

        <div class="card full">
          <h2>Your variables</h2>
          <p class="hint">Name a value once and use it anywhere in your display script, like the built-in variables.
            Each expression is a Jinja template and can use the built-in variables and any of your variables above it.
            Values update live; click Save to keep them.</p>
          <div id="customVars"></div>
          <div class="row">
            <button id="addVar" class="secondary">Add variable</button>
            <select id="suggestVar" class="grow"><option value="">Add a suggested variable...</option>
              ${(s.variable_suggestions || []).map((v, i) => `<option value="${i}">${esc(v.name)}: ${esc(v.description)}</option>`).join("")}</select>
          </div>
        </div>

        <div class="card full">
          <h2>Accounts <code class="var" data-insert="{{ accounts }}">accounts</code></h2>
          <div id="accounts"></div>
        </div>

        <div class="card full">
          <h2>Transactions <code class="var" data-insert="{{ transactions }}">transactions</code></h2>
          <div class="row"><input id="txFilter" class="grow" placeholder="Filter by description, type, status or date" value="${esc(this._txFilter)}"></div>
          <div id="transactions" class="scroll"></div>
        </div>
      </main>`;

    const ta = this.shadowRoot.getElementById("editor");
    ta.value = this._draft;
    ta.addEventListener("input", () => {
      this._draft = ta.value;
      this._renderDirty();
      this._schedulePreview();
    });
    ta.addEventListener("keydown", (e) => {
      if (e.key === "Tab") { e.preventDefault(); this._insert("  "); }
      if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); this._save(); }
    });
    this.shadowRoot.getElementById("save").addEventListener("click", () => this._save());
    this.shadowRoot.getElementById("revert").addEventListener("click", () => {
      this._draft = this._state.template;
      this._draftVars = (this._state.custom_variables || []).map((v) => ({ ...v }));
      ta.value = this._draft;
      this._renderCustomVars();
      this._renderDirty();
      this._runPreview();
      this._setStatus("Reverted to the saved script and variables.");
    });
    this.shadowRoot.getElementById("examples").addEventListener("change", (e) => {
      const ex = this._state.examples[e.target.value];
      const help = this.shadowRoot.getElementById("exampleHelp");
      if (!ex) { help.textContent = ""; return; }
      this._draft = ex.template;
      ta.value = ex.template;
      help.textContent = ex.description;
      this._renderDirty();
      this._runPreview();
      this._setStatus(`Loaded "${ex.name}". Click Save to use it.`);
    });
    this.shadowRoot.getElementById("testMode").addEventListener("change", (e) => this._setTestMode(e.target.checked));
    this.shadowRoot.getElementById("applyBalance").addEventListener("click", () =>
      this._setTestBalance(this.shadowRoot.getElementById("testBalance").value));
    this.shadowRoot.getElementById("addVar").addEventListener("click", () => {
      this._draftVars.push({ name: "", template: "" });
      this._renderCustomVars(true);
      this._renderDirty();
    });
    this.shadowRoot.getElementById("suggestVar").addEventListener("change", (e) => {
      const sug = (this._state.variable_suggestions || [])[e.target.value];
      e.target.value = "";
      if (!sug) return;
      let name = sug.name, n = 2;
      while (this._draftVars.some((v) => v.name === name)) name = `${sug.name}_${n++}`;
      this._draftVars.push({ name, template: sug.template });
      this._renderCustomVars();
      this._renderDirty();
      this._runPreview();
      this._setStatus(`Added the variable ${name}. Click Save to keep it.`);
    });
    this.shadowRoot.getElementById("txFilter").addEventListener("input", (e) => {
      this._txFilter = e.target.value;
      this._renderTransactions();
    });
    this._renderDirty();
    this._renderCustomVars();
    this._renderVariables();
    this._renderAccounts();
    this._renderTransactions();
    this._renderPreview();
  }

  _renderDirty() {
    const el = this.shadowRoot.getElementById("dirty");
    const dirty = this._state && (this._draft !== this._state.template ||
      JSON.stringify(this._draftVars.filter((v) => v.name || v.template)) !==
      JSON.stringify(this._state.custom_variables || []));
    if (el) el.textContent = dirty ? "Unsaved changes" : "Saved";
    const save = this.shadowRoot.getElementById("save");
    if (save) save.disabled = !dirty;
  }

  _renderPreview() {
    this._renderCustomValues();
    const el = this.shadowRoot.getElementById("preview");
    if (!el) return;
    const p = this._preview;
    const cur = this._state?.current;
    if (!p) { el.innerHTML = `<p class="hint">Rendering...</p>`; return; }
    const isErr = !!p.error;
    const led = cells(p.value).map((c) =>
      `<div class="cell ${isErr ? "err" : ""}">${esc(c.ch)}${c.dot ? '<span class="dot"></span>' : ""}</div>`).join("");
    el.innerHTML = `
      <div class="led">${led}</div>
      ${isErr ? `<p class="err">${esc(p.error)}</p>` : `<p class="hint">This is what the screen would show.</p>`}
      <table>
        <tr><th>Script returned</th><td><code>${esc(p.raw || "(nothing)")}</code></td></tr>
        <tr><th>On the screen now</th><td><code>${esc(cur?.value ?? "")}</code>${cur?.error ? ` <span class="err">(${esc(cur.error)})</span>` : ""}</td></tr>
      </table>`;
  }

  _renderCustomVars(focusLast = false) {
    const el = this.shadowRoot.getElementById("customVars");
    if (!el) return;
    if (!this._draftVars.length) {
      el.innerHTML = `<p class="hint">No variables yet. Add one, or pick a suggestion below.</p>`;
      return;
    }
    el.innerHTML = `<table class="vars-edit">
      <tr><th style="width:18%">Name</th><th>Expression</th><th style="width:16%">Value now</th><th style="width:1%"></th></tr>
      ${this._draftVars.map((v, i) => `
        <tr>
          <td><input data-i="${i}" data-f="name" value="${esc(v.name)}" placeholder="my_variable" spellcheck="false" style="width:100%;box-sizing:border-box;font-family:ui-monospace,Consolas,monospace"></td>
          <td><textarea data-i="${i}" data-f="template" rows="1" spellcheck="false" placeholder="{{ balance / days_to_payday }}"
               style="min-height:38px;width:100%">${esc(v.template)}</textarea></td>
          <td class="num" data-value="${i}"></td>
          <td><button class="secondary" data-remove="${i}" title="Remove">Remove</button></td>
        </tr>`).join("")}</table>`;
    el.querySelectorAll("[data-f]").forEach((input) => input.addEventListener("input", (e) => {
      const i = Number(e.target.dataset.i);
      this._draftVars[i][e.target.dataset.f] = e.target.value;
      this._renderDirty();
      this._schedulePreview();
    }));
    el.querySelectorAll("[data-remove]").forEach((b) => b.addEventListener("click", (e) => {
      this._draftVars.splice(Number(e.target.dataset.remove), 1);
      this._renderCustomVars();
      this._renderDirty();
      this._runPreview();
    }));
    if (focusLast) el.querySelector(`input[data-i="${this._draftVars.length - 1}"]`)?.focus();
    this._renderCustomValues();
  }

  _renderCustomValues() {
    const p = this._preview || {};
    const values = p.custom || {}, errors = p.custom_errors || {};
    this._draftVars.forEach((v, i) => {
      const cell = this.shadowRoot.querySelector(`[data-value="${i}"]`);
      if (!cell) return;
      if (!v.name) { cell.innerHTML = ""; return; }
      if (errors[v.name]) { cell.innerHTML = `<span class="err" title="${esc(errors[v.name])}">error</span>`; return; }
      const val = values[v.name];
      const shown = typeof val === "number" ? val.toLocaleString("en-ZA", { maximumFractionDigits: 2 }) : JSON.stringify(val);
      cell.innerHTML = `<code class="var" data-insert="{{ ${esc(v.name)} }}" title="Click to insert">${esc(shown ?? "")}</code>`;
    });
  }

  _renderVariables() {
    const v = this._state.variables || {};
    // Built-in variables and their meanings come from the integration; lists have their own cards.
    const help = this._state.variable_descriptions || {};
    const rows = Object.keys(help).filter((k) => k !== "accounts" && k !== "transactions").map((k) => {
      const val = v[k];
      const shown = typeof val === "number" && /balance|spent/.test(k) ? money(val) : esc(JSON.stringify(val));
      return `<tr><td><code class="var" data-insert="{{ ${k} }}">${k}</code></td><td class="num">${shown}</td><td class="hint">${esc(help[k])}</td></tr>`;
    }).join("");
    this.shadowRoot.getElementById("vars").innerHTML =
      `<table><tr><th>Variable</th><th>Current value</th><th>Meaning</th></tr>${rows}</table>
       <p class="hint">Home Assistant functions also work, for example <code>now()</code> and <code>states('sensor.x')</code>.</p>`;
  }

  _renderAccounts() {
    const a = this._state.variables.accounts || [];
    this.shadowRoot.getElementById("accounts").innerHTML = a.length
      ? `<table><tr><th>name</th><th>balance</th></tr>${a.map((x) =>
          `<tr><td>${esc(x.name)}</td><td class="num">${money(x.balance)}</td></tr>`).join("")}</table>`
      : `<p class="hint">No accounts returned.</p>`;
  }

  _renderTransactions() {
    const all = this._state.variables.transactions || [];
    const f = this._txFilter.trim().toLowerCase();
    const list = f
      ? all.filter((t) => [t.description, t.transaction_type, t.status, t.date, t.type, t.account].join(" ").toLowerCase().includes(f))
      : all;
    const rows = list.slice(0, 200).map((t) => `
      <tr><td>${esc(t.date)}</td><td>${esc(t.description)}</td><td class="num">${t.type === "DEBIT" ? "-" : "+"}${money(t.amount)}</td>
          <td><code>${esc(t.type)}</code></td><td><code>${esc(t.transaction_type)}</code></td><td><code>${esc(t.status)}</code></td>
          <td class="hint">${esc(t.account)}</td></tr>`).join("");
    this.shadowRoot.getElementById("transactions").innerHTML = list.length
      ? `<table><tr><th>date</th><th>description</th><th>amount</th><th>type</th><th>transaction_type</th><th>status</th><th>account</th></tr>${rows}</table>
         <p class="hint">${list.length} of ${all.length} transactions${list.length > 200 ? " (first 200 shown)" : ""}.</p>`
      : `<p class="hint">No transactions match.</p>`;
  }
}

// Guard: after an update, an open browser tab can load the new version next to the old one.
if (!customElements.get("investec-display-panel")) {
  customElements.define("investec-display-panel", InvestecDisplayPanel);
}
