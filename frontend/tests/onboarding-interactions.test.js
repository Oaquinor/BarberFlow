"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "js", "onboarding.js"), "utf8");

function createOnboardingSandbox() {
  const listeners = new Map();
  const nodes = new Map();
  const makeNode = (id) => ({
    id,
    value: id === "barbershopName" ? "Barbería Demo" : "",
    style: {},
    textContent: "",
    clicked: 0,
    classList: {
      values: new Set(),
      add(value) { this.values.add(value); },
      remove(value) { this.values.delete(value); },
    },
    addEventListener(name, callback) { this[name] = callback; },
    click() { this.clicked += 1; },
  });
  const document = {
    addEventListener(name, callback) { listeners.set(name, callback); },
    getElementById(id) {
      if (!nodes.has(id)) nodes.set(id, makeNode(id));
      return nodes.get(id);
    },
    querySelectorAll(selector) {
      if (selector.startsWith('input[name="')) return [];
      return [];
    },
    querySelector() { return null; },
  };
  const sandbox = {
    document,
    window: { location: { href: "", origin: "https://kingflow.test", replace() {} }, addEventListener() {} },
    sessionStorage: { getItem: (key) => key === "token" ? "test-token" : null },
    KingFlowAuth: { fetch: async () => ({ ok: true }) },
    console: { log() {}, error() {} },
    alert() {},
  };
  vm.runInNewContext(`${source}\nthis.onboardingDataForTest = onboardingData;`, sandbox);
  return { sandbox, listeners, nodes };
}

function clickTarget(attributes, dataset = {}) {
  return {
    dataset,
    hasAttribute(name) { return attributes.includes(name); },
    closest() { return this; },
  };
}

test("delegated onboarding controls advance steps, apply presets, and open logo picker", async () => {
  const { sandbox, listeners, nodes } = createOnboardingSandbox();
  const dispatchClick = (target) => listeners.get("click")({ target });

  dispatchClick(clickTarget(["data-next-step"], { nextStep: "2" }));
  assert.equal(nodes.get("step1").classList.values.has("hidden"), true);
  assert.equal(nodes.get("step2").classList.values.has("hidden"), false);
  assert.equal(nodes.get("progressBar").style.width, "20%");

  dispatchClick(clickTarget(["data-preset-primary"], {
    presetPrimary: "#123456", presetSecondary: "#654321",
  }));
  assert.equal(nodes.get("primaryColor").value, "#123456");
  assert.equal(nodes.get("secondaryColor").value, "#654321");
  assert.equal(nodes.get("primaryPreview").style.background, "#123456");
  assert.equal(nodes.get("secondaryPreview").style.background, "#654321");

  dispatchClick(clickTarget(["data-open-logo"]));
  assert.equal(nodes.get("logoFile").clicked, 1);
  assert.equal(sandbox.onboardingDataForTest.barbershopName, "Barbería Demo");
});

test("onboarding logo picker remains keyboard operable and dashboard action navigates", () => {
  const { sandbox, listeners, nodes } = createOnboardingSandbox();
  let prevented = false;
  const target = clickTarget(["data-open-logo"]);
  listeners.get("keydown")({
    key: "Enter", target, preventDefault() { prevented = true; },
  });
  assert.equal(prevented, true);
  assert.equal(nodes.get("logoFile").clicked, 1);

  listeners.get("click")({
    target: clickTarget(["data-onboarding-action"], { onboardingAction: "dashboard" }),
  });
  assert.equal(sandbox.window.location.href, "/");
});
