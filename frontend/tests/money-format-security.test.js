"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.join(__dirname, "..");
const mainSource = fs.readFileSync(path.join(root, "js", "main.js"), "utf8");
const clientSource = fs.readFileSync(path.join(root, "js", "client.js"), "utf8");
const adminSource = fs.readFileSync(path.join(root, "js", "admin.js"), "utf8");
const hostileCurrency = '<img src=x onerror="alert(1)">';

function extractFunction(source, name) {
  const start = source.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `${name} exists`);
  const end = source.indexOf("\n}", start);
  assert.notEqual(end, -1, `${name} ends`);
  return source.slice(start, end + 2);
}

function renderMoney({ source, functionName, globals = {}, expression }) {
  const escapeHtml = extractFunction(source, "escapeHtml");
  const formatter = extractFunction(source, functionName);
  const context = { ...globals };
  vm.runInNewContext(`${escapeHtml}\n${formatter}\nresult = ${expression};`, context);
  return context.result;
}

test("invalid tenant currency is escaped in barber dashboard money fallback", () => {
  const result = renderMoney({
    source: mainSource,
    functionName: "fmtMoneyFromCents",
    globals: { barbershopProfile: { currency: hostileCurrency } },
    expression: "fmtMoneyFromCents(1250)",
  });

  assert.equal(result, "&lt;img src=x onerror=&quot;alert(1)&quot;&gt; 12.50");
});

test("invalid tenant currency is escaped in public booking money fallback", () => {
  const result = renderMoney({
    source: clientSource,
    functionName: "formatMoney",
    globals: { shopCurrency: hostileCurrency },
    expression: "formatMoney(1250)",
  });

  assert.equal(result, "&lt;img src=x onerror=&quot;alert(1)&quot;&gt; 12.50");
});

test("invalid affiliate currency is escaped in admin money fallback", () => {
  const result = renderMoney({
    source: adminSource,
    functionName: "formatAffiliateMoney",
    expression: `formatAffiliateMoney(1250, ${JSON.stringify(hostileCurrency)})`,
  });

  assert.equal(result, "&lt;img src=x onerror=&quot;alert(1)&quot;&gt; 12.50");
});
