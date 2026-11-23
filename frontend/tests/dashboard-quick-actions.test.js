"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
const script = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");

test("dashboard quick actions navigate to their matching tabs", () => {
  assert.match(html, /id="quickStatsButton"[\s\S]*?Ver Stats/);
  assert.match(html, /id="quickAgendaButton"[\s\S]*?Ver agenda/);
  assert.match(script, /getElementById\('quickStatsButton'\)\?\.addEventListener\('click',\s*\(\)\s*=>\s*showTab\('performance'\)\)/);
  assert.match(script, /getElementById\('quickAgendaButton'\)\?\.addEventListener\('click',\s*\(\)\s*=>\s*showTab\('appointments'\)\)/);
});
