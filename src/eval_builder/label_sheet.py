"""The offline HTML labeling sheet: one file, no network, no external assets.

The cases are embedded as JSON. Labels live in the page (and in the browser's local
storage when it allows it, so a reload does not lose work) until the person exports
them. A static page cannot write files, so the export is a download (labels.jsonl, in
the exact format judge-check reads) plus the same text in a box to copy.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any


def _embed(data: Any) -> str:
    """JSON that is safe inside a <script> element."""
    s = json.dumps(data, ensure_ascii=False)
    return (
        s.replace("</", "<\\/")
        .replace("<!--", "<\\!--")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


def render_sheet(sheet: dict[str, Any]) -> str:
    title = f"Label {len(sheet['cases'])} cases"
    if sheet.get("suite"):
        title += f": {sheet['suite']}"
    parts = {"__TITLE__": html.escape(title), "__DATA__": _embed(sheet)}
    return re.sub("__TITLE__|__DATA__", lambda m: parts[m.group(0)], TEMPLATE)


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'">
<title>__TITLE__</title>
<style>
:root {
  --bg: #f6f6f4; --card: #ffffff; --ink: #1d1d1b; --muted: #6b6b66; --line: #deded8;
  --user: #eef3fb; --assistant: #f3f3ef; --reply: #fff8e6; --reply-line: #e0b84a;
  --accent: #2f5fb3; --pass: #1f7a3f; --fail: #b3261e; --other: #5a4fb3; --warn: #8a5a00;
  --warn-bg: #fff4dc;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #161615; --card: #1f1f1d; --ink: #ececea; --muted: #a2a29b; --line: #34342f;
    --user: #1c2636; --assistant: #262624; --reply: #2c2614; --reply-line: #a8862e;
    --accent: #7aa2e8; --pass: #5cc382; --fail: #f08a80; --other: #a99ef0; --warn: #f0c060;
    --warn-bg: #2e2612;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
header { position: sticky; top: 0; z-index: 2; background: var(--card); border-bottom: 1px solid var(--line);
  padding: 10px 16px; display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; }
header h1 { font-size: 16px; margin: 0; flex: 1 1 260px; }
.progress { flex: 1 1 200px; display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 13px; }
.bar { flex: 1; height: 6px; background: var(--line); border-radius: 3px; overflow: hidden; }
.bar > div { height: 100%; background: var(--accent); width: 0; }
header label { font-size: 13px; color: var(--muted); }
header input { font: inherit; padding: 4px 8px; border: 1px solid var(--line); border-radius: 6px;
  background: var(--bg); color: var(--ink); width: 150px; }
button { font: inherit; cursor: pointer; border: 1px solid var(--line); background: var(--card); color: var(--ink);
  border-radius: 8px; padding: 6px 12px; }
button:hover { border-color: var(--accent); }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
main { max-width: 860px; margin: 0 auto; padding: 16px 16px 140px; }
.dots { display: flex; flex-wrap: wrap; gap: 4px; margin: 0 0 12px; }
.dots button { width: 26px; height: 26px; padding: 0; font-size: 11px; border-radius: 50%; color: var(--muted); }
.dots button.done { background: var(--accent); color: #fff; border-color: var(--accent); }
.dots button.here { outline: 2px solid var(--ink); outline-offset: 1px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px; }
.meta { color: var(--muted); font-size: 13px; margin-bottom: 8px; display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); margin: 18px 0 6px; }
.turn { border-radius: 8px; padding: 8px 12px; margin: 6px 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.turn .role { display: block; font-size: 12px; color: var(--muted); margin-bottom: 2px; }
.turn.user { background: var(--user); }
.turn.assistant, .turn.system { background: var(--assistant); }
.turn.reply { background: var(--reply); border-left: 4px solid var(--reply-line); }
details.earlier > summary { cursor: pointer; color: var(--muted); font-size: 13px; }
.expected { white-space: pre-wrap; }
.criteria { margin: 6px 0 0; padding-left: 20px; color: var(--muted); }
.question { font-weight: 600; margin-top: 18px; }
textarea { width: 100%; font: inherit; padding: 8px; border-radius: 8px; border: 1px solid var(--line);
  background: var(--bg); color: var(--ink); resize: vertical; }
.note { min-height: 56px; }
footer { position: fixed; bottom: 0; left: 0; right: 0; background: var(--card); border-top: 1px solid var(--line);
  padding: 10px 16px; }
.actions { max-width: 860px; margin: 0 auto; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.labels { display: flex; flex-wrap: wrap; gap: 8px; flex: 1 1 auto; }
.labels button { min-width: 96px; padding: 10px 16px; font-weight: 600; }
.labels button .key { font-weight: 400; color: var(--muted); font-size: 12px; margin-left: 6px; }
.labels button.pass[aria-pressed="true"] { background: var(--pass); border-color: var(--pass); color: #fff; }
.labels button.fail[aria-pressed="true"] { background: var(--fail); border-color: var(--fail); color: #fff; }
.labels button.other[aria-pressed="true"] { background: var(--other); border-color: var(--other); color: #fff; }
.labels button[aria-pressed="true"] .key { color: #fff; }
.nav { display: flex; gap: 8px; }
.small { font-size: 13px; color: var(--muted); }
.warn { background: var(--warn-bg); color: var(--warn); border-radius: 8px; padding: 8px 12px; margin: 10px 0; }
.help { font-size: 13px; color: var(--muted); }
.help kbd, .small kbd { border: 1px solid var(--line); border-bottom-width: 2px; border-radius: 4px; padding: 0 4px; font-size: 12px; }
#export textarea { min-height: 220px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
#export code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px;
  background: var(--assistant); padding: 2px 6px; border-radius: 4px; overflow-wrap: anywhere; }
.row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 10px 0; }
[hidden] { display: none !important; }
@media (max-width: 600px) {
  .labels button { min-width: 0; flex: 1 1 30%; }
  .labels button.clear { flex: 0 1 auto; padding: 10px; }
  .nav { flex: 1 1 100%; }
  .nav button { flex: 1; }
  header input { width: 120px; }
}
</style>
</head>
<body>
<header>
  <h1 id="title"></h1>
  <div class="progress"><span id="count"></span><div class="bar"><div id="bar"></div></div></div>
  <label>Your name <input id="labeler" autocomplete="name" placeholder="optional"></label>
  <button id="to-export" type="button">Export</button>
</header>
<main>
  <section id="cases">
    <p class="help">Read the conversation and the reply, then decide whether the reply does what a good reply
      does. The judges' verdicts are hidden on purpose. Keys: <kbd>1</kbd> <kbd>2</kbd> ... or the first
      letter of a label, <kbd>&larr;</kbd> <kbd>&rarr;</kbd> previous and next, <kbd>U</kbd> next unlabeled,
      <kbd>Backspace</kbd> clear, <kbd>N</kbd> note, <kbd>E</kbd> export. <span id="saved"></span></p>
    <div class="dots" id="dots" aria-label="Cases"></div>
    <article class="card" id="card"></article>
  </section>
  <section id="export" hidden>
    <div class="card">
      <h2 style="margin-top:0">Export labels</h2>
      <p id="export-summary"></p>
      <div id="export-warn" class="warn" hidden></div>
      <div class="row">
        <button id="download" type="button">Download labels.jsonl</button>
        <button id="copy" type="button">Copy</button>
        <span id="copy-status" class="small"></span>
      </div>
      <p class="small">Then, in a terminal:</p>
      <p><code id="import-cmd"></code></p>
      <p class="small">If you copied the text instead, save it to a file and import that file, or on a Mac run
        <code id="paste-cmd"></code>. Each line is one label in the format <code>judge-check</code> reads:
        <code>{"case_id": ..., "label": ...}</code> plus your name, note and the time.</p>
      <textarea id="blob" readonly aria-label="Labels as JSON lines"></textarea>
      <div class="row"><button id="back" type="button">Back to the cases</button></div>
    </div>
  </section>
</main>
<footer id="bottom">
  <div class="actions">
    <div class="labels" id="labels"></div>
    <div class="nav">
      <button id="prev" type="button" aria-label="Previous case">&larr; Prev</button>
      <button id="next" type="button" aria-label="Next case">Next &rarr;</button>
    </div>
  </div>
  <div class="actions"><label class="small"><input type="checkbox" id="auto" checked> go to the next case after labeling</label></div>
</footer>
<script id="sheet-data" type="application/json">__DATA__</script>
<script>
(function () {
  "use strict";
  var DATA = JSON.parse(document.getElementById("sheet-data").textContent);
  var CASES = DATA.cases;
  var KEY = "eval-builder-labels:" + DATA.sheet_id;
  var state = { labeler: "", labels: {}, notes: {}, at: {}, pos: 0, auto: true };
  var storage = "unknown";
  var view = "cases";

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  try {
    var saved = window.localStorage.getItem(KEY);
    if (saved) {
      var s = JSON.parse(saved);
      ["labeler", "labels", "notes", "at", "pos", "auto"].forEach(function (k) { if (k in s) state[k] = s[k]; });
    }
    storage = "ok";
  } catch (e) { storage = "blocked"; }
  if (state.pos < 0 || state.pos >= CASES.length) state.pos = 0;

  function save() {
    try { window.localStorage.setItem(KEY, JSON.stringify(state)); storage = "ok"; }
    catch (e) { storage = "blocked"; }
    $("saved").textContent = storage === "ok"
      ? "Progress is kept in this browser until you export."
      : "This browser does not allow saving here: export before you close the page.";
  }

  function labeledCount() {
    return CASES.filter(function (c) { return state.labels[c.id] !== undefined; }).length;
  }

  function cls(label) {
    var l = String(label).toLowerCase();
    if (l === "pass" || l === "yes" || l === "good") return "pass";
    if (l === "fail" || l === "no" || l === "bad") return "fail";
    return "other";
  }

  function keymap(labels) {
    var map = {}, firsts = {};
    labels.forEach(function (l, i) {
      if (i < 9) map[String(i + 1)] = l;
      var f = String(l).charAt(0).toLowerCase();
      firsts[f] = (firsts[f] || 0) + 1;
    });
    labels.forEach(function (l) {
      var f = String(l).charAt(0).toLowerCase();
      if (firsts[f] === 1 && /[a-z]/.test(f)) map[f] = l;
    });
    return map;
  }

  function keyHint(labels, label) {
    var m = keymap(labels), keys = [];
    Object.keys(m).forEach(function (k) { if (m[k] === label) keys.push(k.toUpperCase()); });
    return keys.reverse().join(" / ");
  }

  function turn(role, text, extra) {
    var d = el("div", "turn " + (extra || role));
    d.appendChild(el("span", "role", role));
    d.appendChild(document.createTextNode(text));
    return d;
  }

  function renderHeader() {
    var n = labeledCount();
    $("title").textContent = document.title;
    $("count").textContent = n + " of " + CASES.length + " labeled";
    $("bar").style.width = (CASES.length ? (100 * n / CASES.length) : 0) + "%";
    var dots = $("dots");
    dots.textContent = "";
    CASES.forEach(function (c, i) {
      var b = el("button", (state.labels[c.id] !== undefined ? "done" : "") + (i === state.pos ? " here" : ""), String(i + 1));
      b.type = "button";
      b.title = c.id + (state.labels[c.id] !== undefined ? ": " + state.labels[c.id] : ": not labeled");
      b.setAttribute("aria-label", "Case " + (i + 1) + ", " + b.title);
      b.addEventListener("click", function () { go(i); });
      dots.appendChild(b);
    });
  }

  function renderCase() {
    var c = CASES[state.pos];
    var card = $("card");
    card.textContent = "";
    var meta = el("div", "meta");
    meta.appendChild(el("span", "", "Case " + (state.pos + 1) + " of " + CASES.length));
    meta.appendChild(el("span", "", c.id));
    card.appendChild(meta);

    if (c.context && c.context.length) {
      card.appendChild(el("h2", "", "Earlier in the conversation"));
      var holder = card;
      if (c.context.length > 4) {
        holder = el("details", "earlier");
        holder.appendChild(el("summary", "", "Show " + c.context.length + " earlier turns"));
        card.appendChild(holder);
      }
      c.context.forEach(function (t) { holder.appendChild(turn(t.role, t.content)); });
    }
    card.appendChild(el("h2", "", "Latest user message"));
    card.appendChild(turn("user", c.input));
    if (c.mode === "pairwise") {
      card.appendChild(el("h2", "", "Answer A"));
      card.appendChild(turn("assistant (A)", c.output, "reply"));
      card.appendChild(el("h2", "", "Answer B"));
      card.appendChild(turn("assistant (B)", c.compare_output, "reply"));
    } else {
      card.appendChild(el("h2", "", "Reply to label"));
      card.appendChild(turn("assistant", c.output, "reply"));
    }
    if (c.expected_behavior) {
      card.appendChild(el("h2", "", "What a good reply does"));
      card.appendChild(el("div", "expected", c.expected_behavior));
    }
    if (c.criteria && c.criteria.length) {
      var ul = el("ul", "criteria");
      c.criteria.forEach(function (k) { ul.appendChild(el("li", "", k.id + (k.description ? ": " + k.description : ""))); });
      card.appendChild(ul);
    }
    card.appendChild(el("p", "question", c.mode === "pairwise"
      ? "Which answer is better? Choose a label below."
      : "Does the reply do what a good reply does? Choose a label below."));
    card.appendChild(el("h2", "", "Note (optional)"));
    var note = el("textarea", "note");
    note.id = "note";
    note.placeholder = "Why, if it was a close call";
    note.value = state.notes[c.id] || "";
    note.addEventListener("input", function () {
      if (note.value) state.notes[c.id] = note.value; else delete state.notes[c.id];
      save();
    });
    card.appendChild(note);

    var labels = $("labels");
    labels.textContent = "";
    c.labels.forEach(function (l) {
      var b = el("button", cls(l));
      b.type = "button";
      b.appendChild(document.createTextNode(l));
      b.appendChild(el("span", "key", keyHint(c.labels, l)));
      b.setAttribute("aria-pressed", state.labels[c.id] === l ? "true" : "false");
      b.addEventListener("click", function () { setLabel(l); });
      labels.appendChild(b);
    });
    var clear = el("button", "clear", "Clear");
    clear.type = "button";
    clear.disabled = state.labels[c.id] === undefined;
    clear.addEventListener("click", function () { setLabel(undefined); });
    labels.appendChild(clear);
    $("prev").disabled = state.pos === 0;
    $("next").disabled = state.pos === CASES.length - 1;
  }

  function render() {
    renderHeader();
    if (view === "cases") renderCase(); else renderExport();
  }

  function go(i) {
    state.pos = Math.max(0, Math.min(CASES.length - 1, i));
    save();
    showCases();
    window.scrollTo(0, 0);
  }

  function nextUnlabeled() {
    for (var k = 1; k <= CASES.length; k++) {
      var i = (state.pos + k) % CASES.length;
      if (state.labels[CASES[i].id] === undefined) return i;
    }
    return -1;
  }

  function setLabel(l) {
    var c = CASES[state.pos];
    if (l === undefined) { delete state.labels[c.id]; delete state.at[c.id]; }
    else { state.labels[c.id] = l; state.at[c.id] = new Date().toISOString(); }
    save();
    if (l !== undefined && state.auto) {
      var nxt = nextUnlabeled();
      if (nxt === -1) { showExport(); return; }
      if (nxt !== state.pos) { setTimeout(function () { go(nxt); }, 120); }
    }
    render();
  }

  function rows() {
    var out = [];
    CASES.forEach(function (c) {
      if (state.labels[c.id] === undefined) return;
      var r = { case_id: c.id, label: state.labels[c.id], mode: c.mode };
      if (state.labeler) r.labeler = state.labeler;
      if (state.notes[c.id]) r.note = state.notes[c.id];
      if (state.at[c.id]) r.labeled_at = state.at[c.id];
      r.sheet = DATA.sheet_id;
      out.push(r);
    });
    return out;
  }

  function jsonl() {
    return rows().map(function (r) { return JSON.stringify(r); }).join("\n") + (rows().length ? "\n" : "");
  }

  function renderExport() {
    var rs = rows(), n = rs.length, counts = {};
    rs.forEach(function (r) { counts[r.label] = (counts[r.label] || 0) + 1; });
    var parts = Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; })
      .map(function (k) { return k + " " + counts[k] + " (" + Math.round(100 * counts[k] / n) + "%)"; });
    var missing = CASES.length - n;
    $("export-summary").textContent = n + " of " + CASES.length + " cases labeled" +
      (parts.length ? ": " + parts.join(", ") : "") +
      (missing ? ". " + missing + " unlabeled case(s) are left out of the export." : ".") +
      (state.labeler ? "" : " Add your name at the top so labels from several people stay apart.");
    var warn = $("export-warn");
    var top = parts.length ? counts[Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; })[0]] : 0;
    if (n >= 5 && top / n >= 0.8) {
      warn.hidden = false;
      warn.textContent = "Most of these labels are the same (" + parts.join(", ") +
        "). A judge that always gives that answer would look accurate on them. That is fine if it is what you saw; it means the judge check needs cases of the other outcome too.";
    } else { warn.hidden = true; }
    $("blob").value = jsonl();
    $("import-cmd").textContent = "uvx eval-builder label import ~/Downloads/labels.jsonl -w " + shellQuote(DATA.workspace);
    $("paste-cmd").textContent = "pbpaste | uvx eval-builder label import - -w " + shellQuote(DATA.workspace);
    $("download").disabled = n === 0;
    $("copy").disabled = n === 0;
  }

  function shellQuote(s) {
    return /^[A-Za-z0-9_\/.~:-]+$/.test(s) ? s : "'" + String(s).replace(/'/g, "'\\''") + "'";
  }

  function showExport() {
    view = "export";
    $("cases").hidden = true; $("export").hidden = false; $("bottom").hidden = true;
    render();
    window.scrollTo(0, 0);
  }
  function showCases() {
    view = "cases";
    $("cases").hidden = false; $("export").hidden = true; $("bottom").hidden = false;
    render();
  }

  $("labeler").value = state.labeler;
  $("labeler").addEventListener("input", function (e) { state.labeler = e.target.value.trim(); save(); });
  $("auto").checked = !!state.auto;
  $("auto").addEventListener("change", function (e) { state.auto = e.target.checked; save(); });
  $("prev").addEventListener("click", function () { go(state.pos - 1); });
  $("next").addEventListener("click", function () { go(state.pos + 1); });
  $("to-export").addEventListener("click", showExport);
  $("back").addEventListener("click", showCases);
  $("download").addEventListener("click", function () {
    var blob = new Blob([jsonl()], { type: "application/x-ndjson" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "labels.jsonl";
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
  });
  $("copy").addEventListener("click", function () {
    var text = jsonl(), status = $("copy-status");
    function fallback() {
      var box = $("blob");
      box.focus(); box.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      status.textContent = ok ? "Copied." : "Select the text below and copy it (Cmd+C or Ctrl+C).";
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { status.textContent = "Copied."; }, fallback);
    } else { fallback(); }
  });

  document.addEventListener("keydown", function (e) {
    var t = e.target;
    if (t && (t.tagName === "TEXTAREA" || t.tagName === "INPUT")) {
      if (e.key === "Escape") t.blur();
      return;
    }
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (view === "export") { if (e.key === "Escape") { showCases(); e.preventDefault(); } return; }
    var c = CASES[state.pos], k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    var m = keymap(c.labels);
    if (m[k] !== undefined) { setLabel(m[k]); e.preventDefault(); return; }
    if (k === "ArrowRight" || k === "Enter") { go(state.pos + 1); e.preventDefault(); }
    else if (k === "ArrowLeft") { go(state.pos - 1); e.preventDefault(); }
    else if (k === "Backspace" || k === "Delete") { setLabel(undefined); e.preventDefault(); }
    else if (k === "u") { var i = nextUnlabeled(); if (i !== -1) go(i); e.preventDefault(); }
    else if (k === "n") { $("note").focus(); e.preventDefault(); }
    else if (k === "e") { showExport(); e.preventDefault(); }
  });

  save();
  showCases();
})();
</script>
</body>
</html>
"""
