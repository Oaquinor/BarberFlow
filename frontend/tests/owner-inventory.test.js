const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const mainScript = fs.readFileSync(path.join(__dirname, '..', 'js', 'main.js'), 'utf8');
const start = mainScript.indexOf('let ownerInventoryProducts = [];');
const end = mainScript.indexOf("\ndocument.getElementById('refreshOwnerInventory')", start);
const loaderSource = mainScript.slice(start, end);

function renderInventory({ products, movements, userRole = 'barbershop_owner' }) {
  const nodes = {
    ownerInventoryProductsBody: { innerHTML: '', replaceChildren() { this.innerHTML = ''; } },
    ownerInventoryMovementsBody: { innerHTML: '', replaceChildren() { this.innerHTML = ''; } },
    ownerInventorySummary: { textContent: '' },
    inventoryMovementProduct: {
      value: '', options: [],
      add(option) { this.options.push(option); },
      replaceChildren(...options) { this.options = options; },
    },
    retailProduct: {
      value: '', options: [],
      add(option) { this.options.push(option); },
      replaceChildren(...options) { this.options = options; },
    },
    retailCart: { innerHTML: '', addEventListener() {} },
    retailAddCartItem: { addEventListener() {} },
    retailSaleForm: { querySelector() { return { disabled: false }; } },
    ownerInventoryProductResult: { textContent: '' },
    ownerInventoryMovementResult: { textContent: '' },
  };
  const requests = [];
  const sandbox = {
    currentUser: { role: userRole },
    barbershopProfile: { timezone: 'America/Santo_Domingo' },
    Date,
    Map,
    Option: function Option(text, value) { this.text = text; this.value = value; },
    document: {
      getElementById: (id) => nodes[id] || null,
      querySelector: (selector) => selector === '#retailSaleForm [type="submit"]' ? { disabled: false } : null,
    },
    escapeHtml: (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[char]),
    fmtMoneyFromCents: (value) => `M${Number(value)}`,
    ownerFetch: async (url) => {
      requests.push(url);
      return url.includes('/products?') ? { items: products, total: products.length }
        : { items: movements, total: movements.length };
    },
  };
  vm.runInNewContext(`${loaderSource}\nthis.load = loadOwnerInventory;`, sandbox);
  return sandbox.load().then(() => ({ nodes, requests }));
}

test('owner inventory renders escaped products and their immutable movement history', async () => {
  const { nodes, requests } = await renderInventory({
    products: [{ id: 8, name: '<script>producto</script>', category: 'Cabello', unit: 'unidad', barcode: null,
      unit_cost_cents: 5000, unit_price_cents: 9000, stock_quantity: 1, stock_minimum: 2, low_stock: true, is_active: true }],
    movements: [{ id: 2, product_id: 8, quantity_delta: 3, unit_cost_cents: 5000, reason: 'receipt', note: '<b>factura</b>', created_at: '2026-11-25T12:00:00Z' }],
  });
  assert.deepEqual(requests, ['/owner/inventory/products?include_inactive=true&limit=100', '/owner/inventory/movements?limit=100']);
  assert.match(nodes.ownerInventoryProductsBody.innerHTML, /&lt;script&gt;producto&lt;\/script&gt;/);
  assert.doesNotMatch(nodes.ownerInventoryProductsBody.innerHTML, /<script>/);
  assert.match(nodes.ownerInventoryProductsBody.innerHTML, /Reponer/);
  assert.match(nodes.ownerInventoryMovementsBody.innerHTML, /&lt;b&gt;factura&lt;\/b&gt;/);
  assert.match(nodes.ownerInventoryMovementsBody.innerHTML, /\+3/);
  assert.equal(nodes.retailProduct.options.length, 2);
  assert.match(nodes.retailProduct.options[1].text, /Pomada|producto/);
  assert.match(nodes.retailCart.innerHTML, /El carrito está vacío/);
  assert.equal(nodes.ownerInventorySummary.textContent, '1 producto(s) · 1 movimiento(s) recientes');
});

test('inventory data is not requested in non-owner dashboards', async () => {
  const { nodes, requests } = await renderInventory({ userRole: 'barber', products: [], movements: [] });
  assert.deepEqual(requests, []);
  assert.equal(nodes.ownerInventorySummary.textContent, '');
});
