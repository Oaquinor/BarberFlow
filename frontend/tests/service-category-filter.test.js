"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
const source = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");
const filterStart = source.indexOf("function filterServices(");
const dashboardStart = source.indexOf("async function loadBarberDashboardData()", filterStart);
assert.ok(filterStart >= 0 && dashboardStart > filterStart, "could not isolate service catalog functions");
const catalogSource = `${source.slice(filterStart, dashboardStart)}\n${source.slice(source.indexOf("function trustedBusinessImage(", dashboardStart), source.indexOf("function renderBusinessGallery(", dashboardStart))}`;
const clickStart = source.indexOf("function handleServiceCategoryClick(", filterStart);
const clickEnd = source.indexOf("\nasync function loadBarberDashboardData()", clickStart);
assert.ok(clickStart >= 0 && clickEnd > clickStart, "could not isolate category click handler");
const clickHandlerSource = source.slice(clickStart, clickEnd);

function createButton() {
  return {
    dataset: {},
    attributes: {},
    setAttribute(name, value) { this.attributes[name] = value; },
  };
}

function createCatalogSandbox() {
  const categories = { buttons: [], replaceChildren(...buttons) { this.buttons = buttons; } };
  const list = { innerHTML: "", querySelectorAll: () => [] };
  const elements = { serviceCategories: categories, servicesList: list };
  const sandbox = {
    document: {
      getElementById: (id) => elements[id] || null,
      createElement: (tag) => tag === "button" ? createButton() : {},
    },
    selectedServiceCategory: null,
    serviceSearchQuery: "",
    currentUser: { role: "barbershop_owner" },
    escapeHtml: (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]),
    fmtMoneyFromCents: (value) => String(value),
    API_ROOT: "https://api.kingflow.example",
    URL,
    window: { location: { origin: "https://api.kingflow.example" } },
    elements,
  };
  vm.runInNewContext(catalogSource, sandbox);
  return sandbox;
}

const services = [
  { id: 1, name: "Corte clásico", description: "Cabello", category: "haircut", duration_minutes: 30, price_cents: 1000 },
  { id: 2, name: "Barba premium", description: "Perfilado", category: "beard", duration_minutes: 20, price_cents: 800 },
  { id: 3, name: "Combo corte y barba", description: "", category: "combo", duration_minutes: 50, price_cents: 1600 },
];

test("service categories and search filter the same live catalog", () => {
  const sandbox = createCatalogSandbox();

  assert.deepEqual(
    Array.from(sandbox.filterServices(services, "beard", "premium"), (service) => service.id),
    [2],
  );
  assert.deepEqual(
    Array.from(sandbox.filterServices(services, null, "perfilado"), (service) => service.id),
    [2],
  );
  assert.deepEqual(
    Array.from(sandbox.filterServices(services, "haircut", "premium"), (service) => service.id),
    [],
  );
});

test("category buttons are generated from current services and expose selection state", () => {
  const sandbox = createCatalogSandbox();
  sandbox.selectedServiceCategory = "beard";

  sandbox.renderServiceCategoryFilters(services);

  assert.deepEqual(
    sandbox.elements.serviceCategories.buttons.map((button) => button.textContent),
    ["Todos", "beard", "combo", "haircut"],
  );
  const selected = sandbox.elements.serviceCategories.buttons.find((button) => button.textContent === "beard");
  assert.equal(selected.className, "category-btn active");
  assert.equal(selected.attributes["aria-pressed"], "true");
});

test("rendered catalog applies the selected category and escapes service data", () => {
  const sandbox = createCatalogSandbox();
  sandbox.selectedServiceCategory = "haircut";
  const untrustedServices = [
    ...services,
    { id: 4, name: "<img src=x onerror=alert(1)>", description: "unsafe", category: "haircut", duration_minutes: 10, price_cents: 400 },
  ];

  sandbox.renderServiceCatalog(untrustedServices);

  assert.match(sandbox.elements.servicesList.innerHTML, /Corte clásico/);
  assert.match(sandbox.elements.servicesList.innerHTML, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(sandbox.elements.servicesList.innerHTML, /Barba premium/);
  assert.doesNotMatch(sandbox.elements.servicesList.innerHTML, /<img src=x/);
});

test("service photos appear in the owner catalog only from the trusted API origin", () => {
  const sandbox = createCatalogSandbox();
  sandbox.renderServiceCatalog([
    { ...services[0], image_url: "/uploads/barbershops/8/gallery-cut.jpg" },
    { ...services[1], image_url: "https://untrusted.example/cut.jpg" },
  ]);

  assert.match(sandbox.elements.servicesList.innerHTML, /class="service-catalog-photo[^"]*"/);
  assert.match(sandbox.elements.servicesList.innerHTML, /Foto de Corte clásico/);
  assert.doesNotMatch(sandbox.elements.servicesList.innerHTML, /untrusted\.example/);
  assert.match(sandbox.elements.servicesList.innerHTML, /class="service-icon[^"]*"/);
});

test("category button clicks update selection and rerender the current service list", () => {
  const start = clickHandlerSource.indexOf("function handleServiceCategoryClick(");
  const end = clickHandlerSource.indexOf("\n}", start) + 2;
  const rendered = { items: null };
  const sandbox = {
    selectedServiceCategory: null,
    serviceCache: services,
    renderServiceCatalog(items) { rendered.items = items; },
  };
  vm.runInNewContext(clickHandlerSource.slice(start, end), sandbox);
  const selectedButton = { dataset: { allCategories: "false", category: "beard" } };
  sandbox.handleServiceCategoryClick({
    target: { closest: () => selectedButton },
    currentTarget: { contains: () => true },
  });

  assert.equal(sandbox.selectedServiceCategory, "beard");
  assert.equal(rendered.items, services);
});

test("the visible category controls and search are wired to the catalog", () => {
  assert.match(html, /id="serviceCategories"[^>]*aria-label="Filtrar servicios por categoría"/);
  assert.match(source, /getElementById\('serviceCategories'\)\?\.addEventListener\('click',\s*handleServiceCategoryClick\)/);
  assert.match(source, /serviceSearch'\)\?\.addEventListener\('input',[\s\S]*?renderServiceCatalog\(serviceCache\)/);
});
