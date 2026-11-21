"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const frontend = path.join(__dirname, "..");

test("frontend pages use external scripts and no inline event handlers", () => {
  const pages = fs.readdirSync(frontend).filter((name) => name.endsWith(".html"));
  assert.ok(pages.length > 0);

  for (const page of pages) {
    const html = fs.readFileSync(path.join(frontend, page), "utf8");
    assert.doesNotMatch(html, /\son(?:click|change|submit|input|load|error)\s*=/i, page);
    for (const [, attributes] of html.matchAll(/<script\b([^>]*)>/gi)) {
      assert.match(attributes, /\bsrc\s*=/i, `${page} has an inline script`);
    }
  }
});

test("dynamic frontend templates do not add inline script handlers", () => {
  for (const file of ["main.js", "admin.js", "client.js", "onboarding.js"]) {
    const source = fs.readFileSync(path.join(frontend, "js", file), "utf8");
    assert.doesNotMatch(source, /\bon(?:click|change|submit|input|load|error)\s*=\s*["']/i, file);
  }
});
