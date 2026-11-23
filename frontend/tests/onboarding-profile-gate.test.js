"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");
const start = source.indexOf("async function loadBarbershopProfile() {");
const end = source.indexOf("\nasync function loadDashboardLayout()", start);
const functionSource = source.slice(start, end);

function runProfileCheck(fetch) {
  const redirects = [];
  const messages = [];
  const sandbox = {
    API_ROOT: "https://api.kingflow.test",
    accessToken: "test-token",
    barbershopProfile: null,
    KingFlowAuth: { fetch },
    window: { location: { set href(value) { redirects.push(value); } } },
    showToast(message, type) { messages.push({ message, type }); },
    console: { error() {} },
  };
  const result = vm.runInNewContext(`${functionSource}\nloadBarbershopProfile()`, sandbox);
  return result.then((value) => ({ value, redirects, messages, sandbox }));
}

test("profile validation fails closed when the API returns an error", async () => {
  const result = await runProfileCheck(async () => ({ ok: false, status: 503 }));
  assert.equal(result.value, false);
  assert.deepEqual(result.redirects, []);
  assert.equal(result.messages[0].type, "error");
});

test("profile validation fails closed when the API is unavailable", async () => {
  const result = await runProfileCheck(async () => { throw new Error("offline"); });
  assert.equal(result.value, false);
  assert.deepEqual(result.redirects, []);
  assert.equal(result.messages[0].type, "error");
});

test("an authenticated tenant with incomplete onboarding is sent to setup", async () => {
  const result = await runProfileCheck(async () => ({
    ok: true,
    async json() { return { onboarding_completed: false }; },
  }));
  assert.equal(result.value, false);
  assert.deepEqual(result.redirects, ["/onboarding.html"]);
});
