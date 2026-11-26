#!/usr/bin/env python3
"""Minimal zero-dependency local Web GUI (Kanban + dependency graph) for Beads (bd)."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ISSUE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
VALID_TYPES = frozenset({"bug", "feature", "task", "epic", "chore"})
VALID_STATUSES = frozenset({"open", "in_progress", "blocked", "deferred", "closed"})
VALID_DEP_TYPES = frozenset({"blocks", "parent-child", "related", "discovered-from"})

HTML_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Beads — Local Task Board</title>
<style>
  :root {
    --bg: #0f1115;
    --surface: #171a21;
    --surface-2: #1f242e;
    --border: #2c3342;
    --text: #e6ebf5;
    --muted: #8b95a7;
    --accent: #6ea8fe;
    --open: #3b82f6;
    --ready: #10b981;
    --progress: #f59e0b;
    --blocked: #ef4444;
    --closed: #64748b;
    --p0: #ef4444;
    --p1: #f97316;
    --p2: #eab308;
    --p3: #3b82f6;
    --p4: #64748b;
    --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    --sans: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: var(--sans);
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }
  header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
    padding: 12px 20px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
  }
  header h1 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    letter-spacing: -0.01em;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .pill {
    font-family: var(--mono);
    font-size: 11px;
    padding: 2px 7px;
    border-radius: 999px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    color: var(--muted);
  }
  .tabs {
    display: inline-flex;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 2px;
  }
  .tabs button {
    border: 0;
    background: transparent;
    color: var(--muted);
    padding: 6px 12px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
  }
  .tabs button.active {
    background: var(--surface-2);
    color: var(--text);
  }
  .controls {
    margin-left: auto;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }
  input, select, textarea, button {
    font: inherit;
    color: var(--text);
  }
  .input, select {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
  }
  .btn {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
    cursor: pointer;
  }
  .btn:hover { border-color: var(--accent); }
  .btn.primary {
    background: #2563eb;
    border-color: #2563eb;
    color: #fff;
  }
  .btn.primary:hover { background: #1d4ed8; }
  .btn.sm { padding: 3px 8px; font-size: 12px; }
  main {
    flex: 1;
    padding: 16px 20px;
    overflow: auto;
  }
  .board {
    display: grid;
    grid-template-columns: repeat(4, minmax(260px, 1fr));
    gap: 14px;
    align-items: start;
  }
  @media (max-width: 1100px) {
    .board { grid-template-columns: repeat(2, minmax(260px, 1fr)); }
  }
  @media (max-width: 640px) {
    .board { grid-template-columns: 1fr; }
  }
  .col {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 10px;
    min-height: 220px;
  }
  .col-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 4px 4px 10px;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
  }
  .col-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 6px;
  }
  .cards { display: flex; flex-direction: column; gap: 8px; }
  .card {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 12px;
    cursor: pointer;
    transition: border-color 0.12s;
  }
  .card:hover { border-color: var(--accent); }
  .card-top {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 6px;
    flex-wrap: wrap;
  }
  .id {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--muted);
  }
  .badge {
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 600;
    padding: 1px 6px;
    border-radius: 4px;
    text-transform: uppercase;
  }
  .badge.type-epic { background: #312e81; color: #c7d2fe; }
  .badge.type-feature { background: #064e3b; color: #a7f3d0; }
  .badge.type-task { background: #1e293b; color: #cbd5e1; }
  .badge.type-bug { background: #7f1d1d; color: #fecaca; }
  .badge.type-chore { background: #3f3f46; color: #e4e4e7; }
  .badge.ready { background: #065f46; color: #6ee7b7; }
  .badge.blocked { background: #7f1d1d; color: #fca5a5; }
  .prio {
    margin-left: auto;
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 700;
  }
  .card-title {
    font-size: 13.5px;
    font-weight: 500;
    line-height: 1.35;
    margin-bottom: 6px;
  }
  .card-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    font-size: 11px;
    color: var(--muted);
  }
  .graph-wrap {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 12px;
    overflow: auto;
    min-height: 520px;
  }
  .graph-legend {
    display: flex;
    gap: 16px;
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 10px;
    flex-wrap: wrap;
  }
  svg text { font-family: var(--sans); user-select: none; }
  .g-node { cursor: pointer; }
  .g-node:hover rect { stroke: var(--accent); stroke-width: 2; }
  .toast {
    position: fixed;
    right: 20px;
    bottom: 20px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 13px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
    display: none;
    max-width: 420px;
    z-index: 40;
  }
  .toast.error { border-color: var(--blocked); color: #fecaca; }
  dialog {
    background: var(--surface);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 0;
    width: min(560px, 94vw);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6);
  }
  dialog::backdrop { background: rgba(0, 0, 0, 0.6); }
  .dlg-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 18px;
    border-bottom: 1px solid var(--border);
  }
  .dlg-body {
    padding: 16px 18px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .field { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); }
  .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  textarea.input { min-height: 84px; resize: vertical; }
  .actions-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--border);
  }
  .dep-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
    font-family: var(--mono);
  }
  .empty { color: var(--muted); font-size: 12px; padding: 14px 6px; text-align: center; }
</style>
</head>
<body>
<header>
  <h1>Beads <span id="stats" class="pill">loading…</span></h1>
  <div class="tabs" role="tablist">
    <button id="tab-board" class="active" type="button">Kanban</button>
    <button id="tab-graph" type="button">Dependency Graph</button>
  </div>
  <div class="controls">
    <input id="q" class="input" type="search" placeholder="Search title, ID, owner…">
    <select id="type-filter" aria-label="Filter by type">
      <option value="">All types</option>
      <option value="epic">Epic</option>
      <option value="feature">Feature</option>
      <option value="task">Task</option>
      <option value="bug">Bug</option>
      <option value="chore">Chore</option>
    </select>
    <button id="btn-refresh" class="btn" type="button" title="Refresh (r)">Refresh</button>
    <button id="btn-new" class="btn primary" type="button" title="New bead (n)">+ New Bead</button>
  </div>
</header>

<main>
  <section id="view-board" class="board"></section>
  <section id="view-graph" class="graph-wrap" hidden>
    <div class="graph-legend">
      <span>Solid arrow: <strong>blocks</strong> (blocker → dependent)</span>
      <span>Dashed arrow: <strong>parent-child</strong> (epic → child)</span>
      <span>Click any node to inspect or transition status.</span>
    </div>
    <div id="graph-canvas"></div>
  </section>
</main>

<dialog id="dlg-create">
  <form id="form-create" method="dialog">
    <div class="dlg-head">
      <strong>Create Bead</strong>
      <button class="btn sm" type="button" onclick="document.getElementById('dlg-create').close()">Close</button>
    </div>
    <div class="dlg-body">
      <label class="field">Title
        <input class="input" name="title" required placeholder="Short imperative title">
      </label>
      <div class="row">
        <label class="field">Type
          <select name="issue_type">
            <option value="task">task</option>
            <option value="bug">bug</option>
            <option value="feature">feature</option>
            <option value="epic">epic</option>
            <option value="chore">chore</option>
          </select>
        </label>
        <label class="field">Priority (0 = highest)
          <select name="priority">
            <option value="0">P0 — Critical</option>
            <option value="1">P1 — High</option>
            <option value="2" selected>P2 — Medium</option>
            <option value="3">P3 — Low</option>
            <option value="4">P4 — Backlog</option>
          </select>
        </label>
      </div>
      <label class="field">Parent Epic (optional)
        <select name="parent" id="create-parent">
          <option value="">None</option>
        </select>
      </label>
      <label class="field">Description
        <textarea class="input" name="description" placeholder="Context, acceptance criteria, or repro steps"></textarea>
      </label>
      <div class="actions-bar">
        <button class="btn primary" type="submit">Create</button>
      </div>
    </div>
  </form>
</dialog>

<dialog id="dlg-detail">
  <div class="dlg-head">
    <span id="detail-id" class="id"></span>
    <button class="btn sm" type="button" onclick="document.getElementById('dlg-detail').close()">Close</button>
  </div>
  <div id="detail-body" class="dlg-body"></div>
</dialog>

<div id="toast" class="toast" role="status"></div>

<script>
const state = { issues: [], readyIds: new Set(), view: "board" };
const PRIO_COLORS = ["var(--p0)", "var(--p1)", "var(--p2)", "var(--p3)", "var(--p4)"];
const STATUS_COLORS = {
  ready: "#10b981",
  open: "#3b82f6",
  in_progress: "#f59e0b",
  blocked: "#ef4444",
  deferred: "#64748b",
  closed: "#64748b",
};

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, String(v));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined) continue;
    node.append(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

let toastTimer;
function toast(msg, isError = false) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = isError ? "toast error" : "toast";
  t.style.display = "block";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.style.display = "none"; }, 3500);
}

async function api(path, body) {
  const res = await fetch(path, body ? {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  } : undefined);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function isBlockedIssue(issue, byId) {
  if (issue.status === "blocked") return true;
  if (issue.status !== "open") return false;
  const deps = issue.dependencies || [];
  return deps.some(d => d.type === "blocks" && byId.get(d.depends_on_id)?.status !== "closed");
}

function effectiveBucket(issue, byId) {
  if (issue.status === "closed") return "closed";
  if (issue.status === "in_progress") return "in_progress";
  if (isBlockedIssue(issue, byId)) return "blocked";
  return "open";
}

function filteredIssues() {
  const q = document.getElementById("q").value.trim().toLowerCase();
  const t = document.getElementById("type-filter").value;
  return state.issues.filter(i => {
    if (t && i.issue_type !== t) return false;
    if (!q) return true;
    return [i.id, i.title, i.description, i.assignee, i.owner]
      .filter(Boolean)
      .some(s => String(s).toLowerCase().includes(q));
  });
}

function renderBoard() {
  const board = document.getElementById("view-board");
  board.replaceChildren();
  const byId = new Map(state.issues.map(i => [i.id, i]));
  const items = filteredIssues();
  const columns = [
    { key: "open", label: "Open / Ready", color: "var(--ready)" },
    { key: "in_progress", label: "In Progress", color: "var(--progress)" },
    { key: "blocked", label: "Blocked", color: "var(--blocked)" },
    { key: "closed", label: "Closed", color: "var(--closed)" },
  ];
  for (const col of columns) {
    const colItems = items
      .filter(i => effectiveBucket(i, byId) === col.key)
      .sort((a, b) => (a.priority - b.priority) || a.id.localeCompare(b.id));
    const cards = el("div", { class: "cards" });
    if (!colItems.length) {
      cards.append(el("div", { class: "empty" }, "No beads"));
    } else {
      for (const issue of colItems) {
        const isReady = state.readyIds.has(issue.id);
        const blockers = (issue.dependencies || []).filter(d => d.type === "blocks");
        const card = el("article", { class: "card", onclick: () => openDetail(issue.id) },
          el("div", { class: "card-top" },
            el("span", { class: "id" }, issue.id),
            el("span", { class: `badge type-${issue.issue_type || "task"}` }, issue.issue_type || "task"),
            isReady && issue.status === "open" ? el("span", { class: "badge ready" }, "ready") : null,
            col.key === "blocked" ? el("span", { class: "badge blocked" }, "blocked") : null,
            el("span", { class: "prio", style: `color:${PRIO_COLORS[issue.priority] || "var(--muted)"}` }, `P${issue.priority}`)
          ),
          el("div", { class: "card-title" }, issue.title),
          el("div", { class: "card-meta" },
            issue.parent ? el("span", {}, `parent: ${issue.parent}`) : null,
            blockers.length ? el("span", {}, `blocked by: ${blockers.map(b => b.depends_on_id).join(", ")}`) : null,
            issue.assignee ? el("span", {}, `@${issue.assignee}`) : null
          )
        );
        cards.append(card);
      }
    }
    board.append(el("div", { class: "col" },
      el("div", { class: "col-head" },
        el("span", {}, el("span", { class: "col-dot", style: `background:${col.color}` }), col.label),
        el("span", { class: "pill" }, String(colItems.length))
      ),
      cards
    ));
  }
}

function renderGraph() {
  const wrap = document.getElementById("graph-canvas");
  wrap.replaceChildren();
  const items = filteredIssues();
  if (!items.length) {
    wrap.append(el("div", { class: "empty" }, "No beads to display."));
    return;
  }
  const byId = new Map(items.map(i => [i.id, i]));
  const edges = [];
  const indeg = new Map(items.map(i => [i.id, 0]));
  const outgoing = new Map(items.map(i => [i.id, []]));
  for (const issue of items) {
    for (const d of (issue.dependencies || [])) {
      if (!byId.has(d.depends_on_id)) continue;
      if (d.type !== "blocks" && d.type !== "parent-child") continue;
      edges.push({ from: d.depends_on_id, to: issue.id, type: d.type });
      outgoing.get(d.depends_on_id).push(issue.id);
      indeg.set(issue.id, (indeg.get(issue.id) || 0) + 1);
    }
  }

  // Kahn topological layering
  const depth = new Map(items.map(i => [i.id, 0]));
  const queue = items.filter(i => indeg.get(i.id) === 0).map(i => i.id);
  const visited = new Set();
  while (queue.length) {
    const u = queue.shift();
    visited.add(u);
    for (const v of outgoing.get(u)) {
      depth.set(v, Math.max(depth.get(v), depth.get(u) + 1));
      indeg.set(v, indeg.get(v) - 1);
      if (indeg.get(v) === 0) queue.push(v);
    }
  }
  const layers = new Map();
  for (const issue of items) {
    const d = depth.get(issue.id) || 0;
    if (!layers.has(d)) layers.set(d, []);
    layers.get(d).push(issue);
  }
  const colW = 240, rowH = 88, padX = 24, padY = 24, nodeW = 200, nodeH = 60;
  const maxLayer = Math.max(...layers.keys(), 0);
  const maxRows = Math.max(...[...layers.values()].map(a => a.length), 1);
  const svgW = Math.max(720, (maxLayer + 1) * colW + padX * 2);
  const svgH = Math.max(320, maxRows * rowH + padY * 2);
  const pos = new Map();
  for (const [d, list] of layers.entries()) {
    list.sort((a, b) => (a.priority - b.priority) || a.id.localeCompare(b.id));
    list.forEach((issue, idx) => {
      pos.set(issue.id, { x: padX + d * colW, y: padY + idx * rowH });
    });
  }

  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("width", svgW);
  svg.setAttribute("height", svgH);
  svg.setAttribute("viewBox", `0 0 ${svgW} ${svgH}`);

  const defs = document.createElementNS(ns, "defs");
  for (const [id, color] of [["arrow-blocks", "#f59e0b"], ["arrow-parent", "#64748b"]]) {
    const marker = document.createElementNS(ns, "marker");
    marker.setAttribute("id", id);
    marker.setAttribute("viewBox", "0 0 10 10");
    marker.setAttribute("refX", "9");
    marker.setAttribute("refY", "5");
    marker.setAttribute("markerWidth", "6");
    marker.setAttribute("markerHeight", "6");
    marker.setAttribute("orient", "auto-start-reverse");
    const path = document.createElementNS(ns, "path");
    path.setAttribute("d", "M 0 1 L 10 5 L 0 9 z");
    path.setAttribute("fill", color);
    marker.append(path);
    defs.append(marker);
  }
  svg.append(defs);

  for (const e of edges) {
    const a = pos.get(e.from);
    const b = pos.get(e.to);
    if (!a || !b) continue;
    const x1 = a.x + nodeW, y1 = a.y + nodeH / 2;
    const x2 = b.x, y2 = b.y + nodeH / 2;
    const cx = (x1 + x2) / 2;
    const path = document.createElementNS(ns, "path");
    path.setAttribute("d", `M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", e.type === "blocks" ? "#f59e0b" : "#475569");
    path.setAttribute("stroke-width", e.type === "blocks" ? "2" : "1.5");
    if (e.type === "parent-child") path.setAttribute("stroke-dasharray", "5 4");
    path.setAttribute("marker-end", e.type === "blocks" ? "url(#arrow-blocks)" : "url(#arrow-parent)");
    svg.append(path);
  }

  const allById = new Map(state.issues.map(i => [i.id, i]));
  for (const issue of items) {
    const p = pos.get(issue.id);
    const bucket = effectiveBucket(issue, allById);
    const stroke = state.readyIds.has(issue.id) && bucket === "open"
      ? STATUS_COLORS.ready
      : (STATUS_COLORS[bucket] || "#475569");
    const g = document.createElementNS(ns, "g");
    g.setAttribute("class", "g-node");
    g.addEventListener("click", () => openDetail(issue.id));

    const rect = document.createElementNS(ns, "rect");
    rect.setAttribute("x", p.x);
    rect.setAttribute("y", p.y);
    rect.setAttribute("width", nodeW);
    rect.setAttribute("height", nodeH);
    rect.setAttribute("rx", "8");
    rect.setAttribute("fill", "#1f242e");
    rect.setAttribute("stroke", stroke);
    rect.setAttribute("stroke-width", "1.5");
    g.append(rect);

    const t1 = document.createElementNS(ns, "text");
    t1.setAttribute("x", p.x + 10);
    t1.setAttribute("y", p.y + 20);
    t1.setAttribute("fill", "#8b95a7");
    t1.setAttribute("font-size", "11");
    t1.textContent = `${issue.id} · ${issue.issue_type} · P${issue.priority}`;
    g.append(t1);

    const t2 = document.createElementNS(ns, "text");
    t2.setAttribute("x", p.x + 10);
    t2.setAttribute("y", p.y + 42);
    t2.setAttribute("fill", "#e6ebf5");
    t2.setAttribute("font-size", "12");
    t2.setAttribute("font-weight", "500");
    t2.textContent = issue.title.length > 26 ? issue.title.slice(0, 25) + "…" : issue.title;
    g.append(t2);

    svg.append(g);
  }
  wrap.append(svg);
}

function openDetail(id) {
  const issue = state.issues.find(i => i.id === id);
  if (!issue) return;
  document.getElementById("detail-id").textContent = `${issue.id} · ${issue.issue_type} · P${issue.priority} · ${issue.status}`;
  const body = document.getElementById("detail-body");
  body.replaceChildren();

  body.append(el("h3", { style: "margin:0;font-size:16px" }, issue.title));
  if (issue.description) {
    body.append(el("p", { style: "margin:0;color:var(--muted);font-size:13px;white-space:pre-wrap" }, issue.description));
  }

  const deps = issue.dependencies || [];
  const depList = el("div", { class: "dep-list" });
  if (deps.length) {
    for (const d of deps) {
      depList.append(el("div", {}, `${d.type}: ${d.depends_on_id}`));
    }
  } else {
    depList.append(el("div", { style: "color:var(--muted)" }, "None"));
  }
  body.append(el("div", { class: "field" }, "Dependencies", depList));

  // Add dependency inline
  const depSelect = el("select", { class: "input" },
    el("option", { value: "" }, "Select blocker issue…"),
    ...state.issues
      .filter(other => other.id !== issue.id)
      .map(other => el("option", { value: other.id }, `${other.id} — ${other.title}`))
  );
  const addDepBtn = el("button", {
    class: "btn sm",
    type: "button",
    onclick: async () => {
      if (!depSelect.value) return;
      try {
        await api("/api/deps", { issue_id: issue.id, depends_on_id: depSelect.value, type: "blocks" });
        toast(`Added blocker ${depSelect.value} → ${issue.id}`);
        await loadState();
        openDetail(issue.id);
      } catch (err) { toast(err.message, true); }
    }
  }, "Add Blocker");
  body.append(el("div", { class: "field" }, "Add Blocking Dependency",
    el("div", { style: "display:flex;gap:8px" }, depSelect, addDepBtn)
  ));

  const actions = el("div", { class: "actions-bar" });
  const transitions = [
    ["Open", "open"],
    ["In Progress", "in_progress"],
    ["Blocked", "blocked"],
    ["Close", "closed"],
  ];
  for (const [label, status] of transitions) {
    if (issue.status === status) continue;
    actions.append(el("button", {
      class: status === "closed" ? "btn primary sm" : "btn sm",
      type: "button",
      onclick: async () => {
        try {
          let reason = "";
          if (status === "closed") {
            reason = window.prompt("Close reason (optional):", "Completed via Beads UI") || "";
          }
          await api(`/api/issues/${encodeURIComponent(issue.id)}/status`, { status, reason });
          toast(`${issue.id} → ${status}`);
          document.getElementById("dlg-detail").close();
          await loadState();
        } catch (err) { toast(err.message, true); }
      }
    }, label));
  }
  body.append(actions);
  document.getElementById("dlg-detail").showModal();
}

function render() {
  const readyCount = state.readyIds.size;
  const openCount = state.issues.filter(i => i.status !== "closed").length;
  document.getElementById("stats").textContent = `${openCount} active · ${readyCount} ready · ${state.issues.length} total`;
  const parentSel = document.getElementById("create-parent");
  const prev = parentSel.value;
  parentSel.replaceChildren(
    el("option", { value: "" }, "None"),
    ...state.issues
      .filter(i => i.issue_type === "epic" && i.status !== "closed")
      .map(i => el("option", { value: i.id }, `${i.id} — ${i.title}`))
  );
  parentSel.value = prev;

  document.getElementById("view-board").hidden = state.view !== "board";
  document.getElementById("view-graph").hidden = state.view !== "graph";
  document.getElementById("tab-board").classList.toggle("active", state.view === "board");
  document.getElementById("tab-graph").classList.toggle("active", state.view === "graph");

  if (state.view === "board") renderBoard();
  else renderGraph();
}

async function loadState() {
  try {
    const data = await api("/api/state");
    state.issues = data.issues || [];
    state.readyIds = new Set((data.ready || []).map(i => i.id));
    render();
  } catch (err) {
    toast(`Failed to load beads: ${err.message}`, true);
  }
}

document.getElementById("tab-board").addEventListener("click", () => { state.view = "board"; render(); });
document.getElementById("tab-graph").addEventListener("click", () => { state.view = "graph"; render(); });
document.getElementById("q").addEventListener("input", render);
document.getElementById("type-filter").addEventListener("change", render);
document.getElementById("btn-refresh").addEventListener("click", loadState);
document.getElementById("btn-new").addEventListener("click", () => document.getElementById("dlg-create").showModal());
document.getElementById("form-create").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  try {
    const created = await api("/api/issues", {
      title: fd.get("title"),
      issue_type: fd.get("issue_type"),
      priority: Number(fd.get("priority")),
      parent: fd.get("parent"),
      description: fd.get("description"),
    });
    e.target.reset();
    document.getElementById("dlg-create").close();
    toast(`Created ${created.id}`);
    await loadState();
  } catch (err) { toast(err.message, true); }
});

window.addEventListener("keydown", (e) => {
  if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;
  if (e.key === "r") loadState();
  if (e.key === "n") document.getElementById("dlg-create").showModal();
});

loadState();
</script>
</body>
</html>
"""


def run_bd(args: list[str], cwd: Path) -> Any:
    env = os.environ.copy()
    env["BD_NO_DEP_TYPE_WARNING"] = "1"
    proc = subprocess.run(
        ["bd", *args, "--json"],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or f"bd exited with {proc.returncode}").strip()
        raise RuntimeError(msg)
    out = proc.stdout.strip()
    if not out:
        return {}
    return json.loads(out)


def export_jsonl(cwd: Path) -> None:
    subprocess.run(
        ["bd", "export", "-o", ".beads/issues.jsonl"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def validate_issue_id(issue_id: str) -> str:
    if not ISSUE_ID_RE.fullmatch(issue_id):
        raise ValueError(f"Invalid issue ID: {issue_id!r}")
    return issue_id


class BeadsHandler(BaseHTTPRequestHandler):
    repo_root: Path

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1_000_000:
            raise ValueError("Invalid request body size")
        raw = self.rfile.read(length).decode("utf-8")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("Expected JSON object")
        return parsed

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            body = HTML_PAGE.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/state":
            try:
                issues = run_bd(["list", "--all"], self.repo_root)
                ready = run_bd(["ready"], self.repo_root)
                self._send_json(
                    {
                        "issues": issues if isinstance(issues, list) else [],
                        "ready": ready if isinstance(ready, list) else [],
                    }
                )
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            body = self._read_json()
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/issues":
            try:
                title = str(body.get("title", "")).strip()
                if not title:
                    raise ValueError("Title is required")
                issue_type = str(body.get("issue_type", "task")).strip()
                if issue_type not in VALID_TYPES:
                    raise ValueError(f"Unsupported type: {issue_type}")
                priority = int(body.get("priority", 2))
                if not (0 <= priority <= 4):
                    raise ValueError("Priority must be between 0 and 4")
                description = str(body.get("description", "")).strip()
                parent = str(body.get("parent", "")).strip()

                cmd = ["create", "-t", issue_type, "-p", str(priority)]
                if description:
                    cmd.extend(["-d", description])
                if parent:
                    cmd.extend(["--parent", validate_issue_id(parent)])
                cmd.extend(["--", title])

                created = run_bd(cmd, self.repo_root)
                export_jsonl(self.repo_root)
                self._send_json(created, HTTPStatus.CREATED)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if parsed.path == "/api/deps":
            try:
                issue_id = validate_issue_id(str(body.get("issue_id", "")).strip())
                depends_on_id = validate_issue_id(str(body.get("depends_on_id", "")).strip())
                dep_type = str(body.get("type", "blocks")).strip()
                if dep_type not in VALID_DEP_TYPES:
                    raise ValueError(f"Unsupported dependency type: {dep_type}")
                result = run_bd(["dep", "add", "-t", dep_type, "--", issue_id, depends_on_id], self.repo_root)
                export_jsonl(self.repo_root)
                self._send_json(result)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        m = re.fullmatch(r"/api/issues/([^/]+)/status", parsed.path)
        if m:
            try:
                issue_id = validate_issue_id(m.group(1))
                status = str(body.get("status", "")).strip()
                if status not in VALID_STATUSES:
                    raise ValueError(f"Unsupported status: {status}")
                reason = str(body.get("reason", "")).strip()
                if status == "closed":
                    cmd = ["close"]
                    if reason:
                        cmd.extend(["--reason", reason])
                    cmd.extend(["--", issue_id])
                else:
                    cmd = ["update", "--status", status, "--", issue_id]
                result = run_bd(cmd, self.repo_root)
                export_jsonl(self.repo_root)
                self._send_json(result)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Local Web GUI for Beads (bd)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("BEADS_UI_PORT", "7474")),
        help="Bind port (default: 7474 or $BEADS_UI_PORT)",
    )
    parser.add_argument("--repo", default=".", help="Repository root containing .beads/")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo).resolve()
    if not (repo_root / ".beads").is_dir():
        print(f"Error: no .beads directory found in {repo_root} (run `bd init` first)", file=sys.stderr)
        return 1

    handler_cls = type("BoundBeadsHandler", (BeadsHandler,), {"repo_root": repo_root})
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((args.host, args.port), handler_cls)
    actual_port = server.server_address[1]
    print(f"Beads Web GUI running at http://{args.host}:{actual_port} (repo: {repo_root})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Beads Web GUI.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
