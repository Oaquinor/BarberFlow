"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "js", "signup.js"), "utf8");

test("signup omits an empty optional affiliate code", async () => {
  const values = {
    owner_first_name: "Demo",
    owner_last_name: "KingFlow",
    owner_email: "kingflow.test@example.com",
    owner_password: "KingFlowDemo2026!",
    owner_phone: "8095550199",
    barbershop_name: "Barbería de Prueba",
    barbershop_email: "barberia.test@example.com",
    barbershop_phone: "8095550188",
    address_line1: "Calle de Prueba 123",
    city: "Santo Domingo",
    state: "Distrito Nacional",
    postal_code: "10101",
    country: "República Dominicana",
    timezone: "America/Santo_Domingo",
    currency: "DOP",
    affiliate_code: "   ",
  };
  const form = { listeners: {}, addEventListener(name, callback) { this.listeners[name] = callback; }, querySelectorAll() { return []; } };
  const result = { textContent: "" };
  const button = { disabled: false };
  const registrationOffer = { textContent: "" };
  const registrationStatus = { textContent: "" };
  let requestBody;
  const redirects = [];
  const sandbox = {
    window: {
      KINGFLOW_CONFIG: { apiBaseUrl: "http://localhost:8000" },
      location: { origin: "http://localhost:3000", replace: (url) => redirects.push(url) },
      KingFlowAuth: { setTokens() {} },
    },
    document: {
      getElementById(id) {
        return ({ signupForm: form, result, submitButton: button, registrationOffer, registrationStatus, ...Object.fromEntries(Object.entries(values).map(([key, value]) => [key, { value }])) })[id];
      },
    },
    localStorage: { setItem() {} },
    fetch: async (url, options) => {
      if (String(url).endsWith("registration-status")) {
        return { ok: true, json: async () => ({ registrations_enabled: true, free_period_days: 30 }) };
      }
      requestBody = JSON.parse(options.body);
      return { ok: true, json: async () => ({ access_token: "access", refresh_token: "refresh", user: { email: values.owner_email } }) };
    },
  };

  vm.runInNewContext(source, sandbox, { filename: "signup.js" });
  await form.listeners.submit({ preventDefault() {} });

  assert.equal(Object.hasOwn(requestBody, "affiliate_code"), false);
  assert.deepEqual(redirects, ["/onboarding.html"]);
  assert.equal(result.textContent, "");
});
