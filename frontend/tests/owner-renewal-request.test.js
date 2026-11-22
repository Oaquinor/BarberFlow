"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");
const start = source.indexOf("async function loadOwnerSubscription()");
const end = source.indexOf("document.getElementById('ownerClientsBody')", start);
assert.ok(start >= 0 && end > start, "could not isolate owner subscription controls");

function createPanel({ status = "active", daysRemaining }, renewalResponse = { created: true, ticket_id: 42 }) {
  const summary = { textContent: "", innerHTML: "" };
  const result = { textContent: "" };
  const calls = [];
  const button = {
    hidden: true,
    disabled: false,
    listener: null,
    addEventListener(_event, listener) { this.listener = listener; },
  };
  const elements = {
    ownerSubscriptionSummary: summary,
    ownerRenewalRequestBtn: button,
    ownerRenewalRequestResult: result,
    refreshOwnerSubscription: { addEventListener() {} },
  };
  const sandbox = {
    document: { getElementById: (id) => elements[id] || null },
    currentUser: { role: "barbershop_owner" },
    barbershopProfile: { timezone: "America/Santo_Domingo" },
    escapeHtml: (value) => String(value ?? ""),
    ownerFetch: async (url, options = {}) => {
      calls.push({ url, options });
      if (url === "/billing/subscription") {
        return {
          plan: "free", status, days_remaining: daysRemaining,
          current_period_start: "2026-11-01T00:00:00",
          current_period_end: "2026-11-30T00:00:00",
          usage: { barbers: { used: 1, limit: 1 } },
        };
      }
      return renewalResponse;
    },
  };
  vm.runInNewContext(`
    const document = globalThis.document;
    const currentUser = globalThis.currentUser;
    const barbershopProfile = globalThis.barbershopProfile;
    const escapeHtml = globalThis.escapeHtml;
    const ownerFetch = globalThis.ownerFetch;
    ${source.slice(start, end)}
    globalThis.loadSubscription = loadOwnerSubscription;
  `, sandbox);
  return { summary, result, button, calls, load: sandbox.loadSubscription };
}

test("near-expiry owner can file a manual renewal request through support", async () => {
  const panel = createPanel({ daysRemaining: 3 });
  await panel.load();
  assert.equal(panel.button.hidden, false);
  assert.match(panel.summary.innerHTML, /no procesa ni programa cargos automáticos/);

  await panel.button.listener({ currentTarget: panel.button });

  assert.deepEqual(panel.calls.map((call) => call.url), [
    "/billing/subscription", "/billing/renewal-request",
  ]);
  assert.equal(panel.calls[1].options.method, "POST");
  assert.match(panel.result.textContent, /Solicitud #42 guardada en la bandeja de soporte/);
  assert.match(panel.result.textContent, /No procesa pagos ni reactiva la cuenta/);
  assert.equal(panel.button.disabled, false);
});

test("active owner sees no renewal request action when the period has time left", async () => {
  const panel = createPanel({ daysRemaining: 12 });
  await panel.load();
  assert.equal(panel.button.hidden, true);
});

test("duplicate manual renewal request reports the existing open support ticket", async () => {
  const panel = createPanel(
    { status: "expired", daysRemaining: 0 },
    { created: false, ticket_id: 19 },
  );
  await panel.load();
  await panel.button.listener({ currentTarget: panel.button });
  assert.match(panel.result.textContent, /Ya hay una solicitud abierta \(#19\)/);
});
