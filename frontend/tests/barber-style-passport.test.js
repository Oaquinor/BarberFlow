"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");
const start = source.indexOf("async function loadBarberStylePassport(");
const end = source.indexOf("\nfunction trustedBusinessImage", start);
assert.ok(start >= 0 && end > start, "could not isolate the barber style passport reader");
const passportSource = source.slice(start, end);

function createElement(tagName) {
  return {
    tagName,
    children: [],
    listeners: new Map(),
    textContent: "",
    value: "",
    disabled: false,
    className: "",
    maxLength: undefined,
    append(...nodes) { this.children.push(...nodes); },
    replaceChildren(...nodes) { this.children = [...nodes]; },
    addEventListener(name, callback) { this.listeners.set(name, callback); },
  };
}

function flatten(node) {
  return [node, ...(node.children || []).flatMap(flatten)];
}

function createSandbox(ownerFetch) {
  const status = createElement("p");
  const list = createElement("div");
  const container = {
    dataset: { clientId: "42", appointmentId: "804" },
    querySelector(selector) {
      return selector === ".barber-style-passport-status" ? status : list;
    },
  };
  const sandbox = {
    accessToken: "barber-access",
    API_ROOT: "https://api.kingflow.test",
    barbershopProfile: { timezone: "America/Santo_Domingo" },
    Intl,
    ownerFetch,
    document: { createElement },
    URL: { createObjectURL: () => "blob:private-photo", revokeObjectURL() {} },
    KingFlowAuth: { async fetch() { return { ok: true, async blob() { return new Blob(); } }; } },
    container,
    status,
    list,
  };
  vm.runInNewContext(`${passportSource}\nthis.loadBarberStylePassport = loadBarberStylePassport;`, sandbox);
  return sandbox;
}

test("barber agenda reads only the shared passport route for its CRM client", async () => {
  const calls = [];
  const sandbox = createSandbox(async (url) => {
    calls.push(url);
    return { items: [] };
  });

  await sandbox.loadBarberStylePassport(42, 804, sandbox.container);

  assert.deepEqual(calls, ["/owner/clients/42/style-passport"]);
  assert.equal(
    sandbox.status.textContent,
    "El cliente no ha compartido registros de estilo con esta barbería.",
  );
});

test("barber sees approved preferences as text and can save technical notes", async () => {
  const calls = [];
  const sandbox = createSandbox(async (url, options) => {
    calls.push({ url, options });
    if (options?.method === "PATCH") return { id: 81 };
    return { items: [{
      id: 81,
      haircut_type: "Crop texturizado",
      service: "Corte clásico",
      service_date: "2026-11-25T15:00:00",
      preferences: "<img src=x onerror=alert(1)>",
      barber_notes: "Textura natural",
      recommendations: "Agendar retoque en 3 semanas",
      photos: [],
    }] };
  });

  await sandbox.loadBarberStylePassport(42, 804, sandbox.container);

  const nodes = flatten(sandbox.list);
  assert.equal(nodes.find((node) => node.tagName === "h5").textContent, "Crop texturizado");
  assert.ok(nodes.some((node) => node.textContent === "Preferencias: <img src=x onerror=alert(1)>"));
  assert.equal(sandbox.status.textContent, "1 registro(s) compartido(s)");
  const form = nodes.find((node) => node.tagName === "form");
  const textareas = flatten(form).filter((node) => node.tagName === "textarea");
  textareas[0].value = "Nota técnica nueva";
  textareas[1].value = "Volver en cuatro semanas";
  await form.listeners.get("submit")({ preventDefault() {} });

  assert.equal(calls[1].url, "/owner/clients/42/style-passport/81");
  assert.equal(calls[1].options.method, "PATCH");
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    barber_notes: "Nota técnica nueva",
    recommendations: "Volver en cuatro semanas",
  });
});
