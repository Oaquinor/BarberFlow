"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");
const start = source.indexOf("function applyBranding(profile) {");
const end = source.indexOf("\nasync function loadBarbershopProfile()", start);
const brandingFunction = source.slice(start, end);

function renderLogo({ pageOrigin, apiRoot, logoUrl }) {
  const heading = {
    children: [],
    replaceChildren() { this.children = []; },
    append(child) { this.children.push(child); },
  };
  const sandbox = {
    API_ROOT: apiRoot,
    currentUser: null,
    URL,
    window: { location: { origin: pageOrigin } },
    document: {
      querySelector(selector) { return selector === ".logo h1" ? heading : null; },
      createElement(tag) { return { tag, style: {} }; },
      createTextNode(text) { return { text }; },
      documentElement: { style: { setProperty() {} } },
    },
  };
  vm.runInNewContext(`${brandingFunction}\napplyBranding(profile);`, {
    ...sandbox,
    profile: {
      name: "KingFlow",
      logo_url: logoUrl,
      primary_color: "#112233",
      secondary_color: "#445566",
    },
  });
  return heading.children;
}

test("owner branding accepts the configured API origin for uploaded logos", () => {
  const children = renderLogo({
    pageOrigin: "https://app.kingflow.test",
    apiRoot: "https://api.kingflow.test",
    logoUrl: "/uploads/barbershops/17/logo.png",
  });

  assert.equal(children[0].tag, "img");
  assert.equal(children[0].src, "https://api.kingflow.test/uploads/barbershops/17/logo.png");
  assert.equal(children[1].text, "KingFlow");
});

test("owner branding rejects untrusted cross-origin and script logos", () => {
  for (const logoUrl of [
    "https://attacker.example/logo.png",
    "javascript:alert(1)",
    "https://user@api.kingflow.test/uploads/logo.png",
  ]) {
    const children = renderLogo({
      pageOrigin: "https://app.kingflow.test",
      apiRoot: "https://api.kingflow.test",
      logoUrl,
    });

    assert.deepEqual(children, [{ text: "KingFlow" }]);
  }
});
