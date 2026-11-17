"""Static HTML reader -- deployment-design.md's "Frontend Rendering is
displaying already-stored JSON" reduced to a single self-contained file: no
server, no build step, no network, nothing that depends on an LLM call at
read time (per the task's "do not make browsing depend on an active LLM
call"). The case JSON is embedded once; a small vanilla-JS renderer builds
the DOM with textContent only, so nothing in a case -- including any model
or mock output -- is ever interpreted as HTML (deployment-design.md section
3's "禁用原始 HTML、脚本和外部图片").
"""

from __future__ import annotations

import json
import re

GLOSSARY = {
    "HCCL": "Huawei Collective Communication Library -- NPU collective-communication runtime.",
    "EP": "Expert Parallelism -- a MoE sharding strategy that splits experts across devices.",
    "CANN": "Compute Architecture for Neural Networks -- the Ascend software stack below the framework.",
    "HDK": "Huawei Driver Kit -- the Ascend device driver/firmware layer.",
    "all_to_all": "A collective op that exchanges distinct data between every pair of ranks.",
}

PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Learning Case Reader</title>
<style>
body{font-family:-apple-system,Segoe UI,Arial,sans-serif;margin:0;background:#0f1115;color:#e6e6e6}
header{padding:16px 24px;border-bottom:1px solid #2a2d35;position:sticky;top:0;background:#0f1115}
h1{font-size:18px;margin:0 0 4px}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;margin-right:6px}
.b-draft{background:#3a3310;color:#e0c050}
.b-published{background:#123a1c;color:#5bd17a}
.b-withdrawn{background:#3a1212;color:#e06060}
.b-generated{background:#123a1c;color:#5bd17a}
.b-failed{background:#3a1212;color:#e06060}
.b-synthetic{background:#1a2a3a;color:#6fb0e0}
main{padding:16px 24px;max-width:960px}
.tabs{display:flex;gap:8px;margin:12px 0}
.tab{padding:6px 12px;border:1px solid #2a2d35;border-radius:6px;cursor:pointer;background:#181a20}
.tab.active{background:#23262e;border-color:#4a7dff}
.view-pane{display:none}
.view-pane.active{display:block}
.step{border:1px solid #2a2d35;border-radius:8px;padding:10px 14px;margin:10px 0;background:#15171c}
.step .role{font-size:11px;text-transform:uppercase;color:#9aa0ac;letter-spacing:.05em}
.kv{color:#9aa0ac;font-size:12px}
.card{border-left:3px solid #4a7dff;padding:6px 10px;margin:6px 0;background:#121722}
.origin{font-size:11px;color:#8aa0cc}
.evidence{border:1px dashed #2a2d35;border-radius:6px;padding:8px;margin:6px 0;font-size:13px}
.integrity-mismatch{color:#e06060}
.integrity-unavailable{color:#9aa0ac}
.integrity-quote-matched{color:#5bd17a}
.missing{color:#e0a060}
.finding-error{color:#e06060}
.finding-review{color:#e0c050}
.finding-warning{color:#9aa0ac}
pre{white-space:pre-wrap;word-break:break-word;margin:4px 0}
abbr{text-decoration:underline dotted;cursor:help}
</style>
</head>
<body>
<header>
  <h1 id="case-title"></h1>
  <div id="badges"></div>
</header>
<main>
  <section id="overview"></section>
  <h2>Validation findings</h2>
  <section id="findings"></section>
  <h2>Diagnostic steps</h2>
  <div class="tabs" id="tabs"></div>
  <div id="panes"></div>
  <h2>Evidence</h2>
  <section id="evidence"></section>
</main>
<script id="case-data" type="application/json">__CASE_JSON__</script>
<script id="head-data" type="application/json">__HEAD_JSON__</script>
<script id="glossary-data" type="application/json">__GLOSSARY_JSON__</script>
<script>
(function () {
  "use strict";
  var caseData = JSON.parse(document.getElementById("case-data").textContent);
  var head = JSON.parse(document.getElementById("head-data").textContent);
  var glossary = JSON.parse(document.getElementById("glossary-data").textContent);

  function el(tag, opts) {
    var e = document.createElement(tag);
    opts = opts || {};
    if (opts.cls) e.className = opts.cls;
    if (opts.text !== undefined && opts.text !== null) e.textContent = opts.text;
    return e;
  }

  function badge(text, cls) {
    var b = el("span", {cls: "badge " + cls, text: text});
    return b;
  }

  function glossed(text) {
    var frag = document.createDocumentFragment();
    var keys = Object.keys(glossary);
    if (!keys.length) { frag.appendChild(document.createTextNode(text)); return frag; }
    var re = new RegExp("\\\\b(" + keys.join("|") + ")\\\\b", "g");
    var lastIndex = 0;
    var m;
    while ((m = re.exec(text)) !== null) {
      frag.appendChild(document.createTextNode(text.slice(lastIndex, m.index)));
      var abbr = el("abbr", {text: m[1]});
      abbr.title = glossary[m[1]];
      frag.appendChild(abbr);
      lastIndex = m.index + m[1].length;
    }
    frag.appendChild(document.createTextNode(text.slice(lastIndex)));
    return frag;
  }

  document.getElementById("case-title").textContent = caseData.title || "(untitled)";
  var badges = document.getElementById("badges");
  badges.appendChild(badge("gen: " + head.generation_status, "b-" + head.generation_status));
  badges.appendChild(badge("pub: " + head.publication_status, "b-" + head.publication_status));
  if (head.synthetic) badges.appendChild(badge("synthetic", "b-synthetic"));

  var ov = document.getElementById("overview");
  var p1 = el("p");
  p1.appendChild(document.createTextNode("Teaching class: " + caseData.diagnosis.teaching_class +
    " · Applicability: " + caseData.applicability.assessment +
    " (" + (caseData.applicability.platforms.join(", ") || "unspecified") + ")"));
  ov.appendChild(p1);
  var context = caseData.source_context || {};
  [["Workload", context.workload_type || context.side],
   ["Workload source", context.workload_type_source || context.side_source],
   ["Environment", context.incident_env], ["Trace created", context.created_at],
   ["Trace updated", context.updated_at]].forEach(function (item) {
    if (item[1]) ov.appendChild(el("div", {cls: "kv", text: item[0] + ": " + item[1]}));
  });

  if (caseData.source_context && caseData.source_context.not_projected) {
    ov.appendChild(el("p", {cls: "missing", text: "Additional source timelines are not displayed here; review these fields in the local packaged Trace: " + caseData.source_context.not_projected.join(", ") + ". Files referenced only there were not collected."}));
  }

  var findingsSec = document.getElementById("findings");
  if (!caseData.validation.length) {
    findingsSec.appendChild(el("p", {text: "No findings.", cls: "kv"}));
  }
  caseData.validation.forEach(function (f) {
    var row = el("div", {cls: "finding-" + f.severity});
    row.textContent = "[" + f.severity + "/" + f.code + "] " + f.pointer + ": " + f.message;
    findingsSec.appendChild(row);
  });

  var evMap = {};
  caseData.evidence.forEach(function (e) { evMap[e.id] = e; });

  var tabs = document.getElementById("tabs");
  var panes = document.getElementById("panes");
  caseData.views.forEach(function (view, vi) {
    var tab = el("div", {cls: "tab" + (vi === 0 ? " active" : ""), text: view.style + " (" + view.state + ")"});
    var pane = el("div", {cls: "view-pane" + (vi === 0 ? " active" : "")});
    if (view.state !== "available") {
      pane.appendChild(el("p", {text: "Unavailable: " + (view.reason || ""), cls: "kv"}));
    }
    var viewDescriptions = {
      replay: "Original recorded process and reasoning.",
      agent: "Teaching commentary: explain and assess the recorded choices.",
      engineer: "Teaching commentary: evidence gaps, alternative checks and transferable lessons."
    };
    pane.appendChild(el("p", {text: viewDescriptions[view.style] || view.style}));
    if (caseData.generator.mode === "mock" && view.style !== "replay") pane.appendChild(el("p", {cls: "missing", text: "Template mock only; this is not agent-authored teaching."}));
    if (caseData.generator.model_id && caseData.generator.model_id.indexOf("local-agent:") === 0 && view.style !== "replay") pane.appendChild(el("p", {cls: "missing", text: "Agent-authored reconstruction; requires professional review."}));
    var cardByStep = {};
    view.cards.forEach(function (c) { cardByStep[c.step_id] = c; });
    caseData.steps.forEach(function (step) {
      var stepEl = el("div", {cls: "step"});
      stepEl.appendChild(el("div", {cls: "role", text: step.role + (step.action ? " · " + step.action : "")}));
      if (step.output) {
        var out = el("pre");
        out.appendChild(glossed(step.output));
        stepEl.appendChild(out);
      }
      stepEl.appendChild(el("div", {cls: "kv", text: "Source: " + step.source_pointer.json_pointer + " (source array order; not causal order)"}));
      if (step.reason && step.role !== "agent") stepEl.appendChild(el("pre", {text: "Recorded reasoning: " + step.reason}));
      if (!step.reason) stepEl.appendChild(el("div", {cls: "kv", text: "Diagnostic reasoning not recorded."}));
      stepEl.appendChild(el("div", {cls: "kv", text: "Recorded commands / tool-use records"}));
      if (!(step.commands || []).length) stepEl.appendChild(el("div", {cls: "kv", text: "No command recorded."}));
      (step.commands || []).forEach(function (cmd) {
        stepEl.appendChild(el("pre", {text: cmd.text}));
        stepEl.appendChild(el("div", {cls: "kv", text: cmd.execution + " (execution not independently verified) · " + cmd.source.json_pointer}));
      });
      (step.evidence_links || []).forEach(function (link) {
        var evidence = evMap[link.evidence_id];
        if (evidence) stepEl.appendChild(evidenceRow(evidence));
      });
      var recorded = step.recorded_context || {};
      [["Source step", recorded.step], ["Recorded time", recorded.at || recorded.timestamp],
       ["Rank", recorded.rank], ["Node", recorded.node]].forEach(function (item) {
        if (item[1] !== undefined && item[1] !== null) stepEl.appendChild(el("div", {cls: "kv", text: item[0] + ": " + item[1]}));
      });
      var card = cardByStep[step.id];
      if (!card && view.style !== "replay" && view.state === "available") stepEl.appendChild(el("p", {cls: "kv", text: "No teaching card supplied for this step; recorded process retained."}));
      if (card) {
        if (card.purpose) stepEl.appendChild(el("div", {cls: "origin", text: "purpose: " + card.purpose}));
        if (card.explanation) {
          var cdiv = el("div", {cls: "card"});
          cdiv.appendChild(el("div", {cls: "origin", text: "origin: " + card.origin}));
          var expl = el("div");
          expl.appendChild(glossed(card.explanation));
          cdiv.appendChild(expl);
          stepEl.appendChild(cdiv);
        }
        if (card.citations && card.citations.length) stepEl.appendChild(el("div", {cls: "kv", text: "Teaching sources: " + card.citations.map(function (p) { return p.file_id + (p.json_pointer || "") + (p.lines ? " line " + p.lines.start : ""); }).join(", ")}));
        if (card.question) stepEl.appendChild(el("div", {cls: "kv", text: "Open question: " + card.question}));
      }
      if (step.missing && step.missing.length) {
        step.missing.forEach(function (m) {
          stepEl.appendChild(el("div", {cls: "missing", text: "Missing: " + m}));
        });
      }
      pane.appendChild(stepEl);
    });
    tab.addEventListener("click", function () {
      tabs.querySelectorAll(".tab").forEach(function (t) { t.classList.remove("active"); });
      panes.querySelectorAll(".view-pane").forEach(function (p) { p.classList.remove("active"); });
      tab.classList.add("active");
      pane.classList.add("active");
    });
    tabs.appendChild(tab);
    panes.appendChild(pane);
  });

  function evidenceRow(e) {
    var row = el("div", {cls: "evidence"});
    var lineage = e.lineage || {};
    row.appendChild(el("div", {cls: "kv", text: e.id + " · integrity: " + e.integrity + " · support: " + e.support}));
    row.appendChild(el("div", {cls: "kv", text: "Source: " + (lineage.source_ref || "See local trace") + " · " + (lineage.trace_pointer || "source pointer unavailable")}));
    if (lineage.availability) row.appendChild(el("div", {cls: "kv", text: lineage.availability + (lineage.omission_reason ? " · " + lineage.omission_reason : "")}));
    if (e.pointer) row.appendChild(el("div", {cls: "kv", text: "Package file: " + e.pointer.file_id + (e.pointer.lines ? " · line " + e.pointer.lines.start : "")}));
    row.appendChild(el("pre", {text: e.quote || "(no quoted text -- reference only)"}));
    return row;
  }
  var evSec = document.getElementById("evidence");
  caseData.evidence.forEach(function (e) { evSec.appendChild(evidenceRow(e)); });
})();
</script>
</body>
</html>
"""


def _embed(value) -> str:
    """JSON text safe to place inside <script type="application/json">: a
    literal `</script` substring in any string field would otherwise close
    the tag early and let the rest be parsed as HTML."""
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def render_html(case, head: dict) -> str:
    values = {"__CASE_JSON__": case.to_dict(), "__HEAD_JSON__": head, "__GLOSSARY_JSON__": GLOSSARY}
    return re.sub(r"__(?:CASE|HEAD|GLOSSARY)_JSON__", lambda m: _embed(values[m.group()]), PAGE_TEMPLATE)
