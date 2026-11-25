const { expect, test } = require('@playwright/test');
const path = require('node:path');

test('owner creates a product and records a stock receipt from the inventory panel', async ({ page }) => {
  const requests = [];
  const products = [];
  const movements = [];
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await page.addInitScript(() => sessionStorage.setItem('token', 'inventory-browser-owner'));
  await page.route('**/api/v1/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace('/api/v1', '');
    const movementPost = path.match(/^\/owner\/inventory\/products\/(\d+)\/movements$/) && request.method() === 'POST';
    let payload = {};
    let status = 200;
    if (path === '/auth/me') {
      payload = { id: 4, email: 'owner@example.com', full_name: 'Dueño Demo', role: 'barbershop_owner' };
    } else if (path === '/onboarding/profile') {
      payload = {
        id: 1, name: 'Barbería Demo', slug: 'barberia-demo', currency: 'DOP',
        timezone: 'America/Santo_Domingo', onboarding_completed: true,
        opening_time: '09:00:00', closing_time: '19:00:00', booking_questions: [], gallery_images: [],
      };
    } else if (path === '/owner/barbers' || path === '/owner/barber-commissions' || path === '/owner/clients' || path === '/owner/waitlist') {
      payload = { items: [], total: 0, totals: {} };
    } else if (path === '/owner/inventory/products' && request.method() === 'POST') {
      const body = request.postDataJSON();
      requests.push({ path, method: request.method(), body });
      payload = { id: 81, ...body, stock_quantity: 0, low_stock: false, is_active: true };
      products.push(payload);
      status = 201;
    } else if (path === '/owner/inventory/products') {
      payload = { items: products, total: products.length };
    } else if (movementPost) {
      const body = request.postDataJSON();
      requests.push({ path, method: request.method(), body });
      payload = { id: 91, product_id: Number(path.split('/')[4]), ...body, created_at: new Date().toISOString() };
      movements.unshift(payload);
      const product = products.find(item => item.id === 81);
      product.stock_quantity += body.quantity_delta;
      product.unit_cost_cents = body.unit_cost_cents;
      product.low_stock = product.stock_minimum > 0 && product.stock_quantity <= product.stock_minimum;
      status = 201;
    } else if (path === '/owner/inventory/movements') {
      payload = { items: movements, total: movements.length };
    } else if (path === '/notifications/unread-count') {
      payload = { count: 0 };
    } else if (path === '/barber/share-link') {
      payload = { url: 'http://localhost:8000/client.html?shop=barberia-demo' };
    } else if (path === '/barber/cash/today') {
      payload = { payments: [], totals: {} };
    } else if (path === '/analytics/financial-report') {
      payload = { currency: 'DOP', gross_cents: 0, service_revenue_cents: 0, tip_cents: 0, payment_count: 0, by_day: [], by_method: [], by_barber: [], start_date: '2026-11-25', end_date: '2026-11-25', timezone: 'America/Santo_Domingo' };
    } else {
      payload = {};
    }
    await route.fulfill({ status, json: payload });
  });

  await page.goto('/index.html');
  await expect(page.locator('#dashboardSection')).toBeVisible();
  await page.locator('#ownerManagementTabButton').click();
  await expect(page.locator('#ownerManagementTab')).toBeVisible();
  const evidenceDir = path.join(__dirname, '..', '..', 'docs', 'evidence');
  await page.locator('[aria-labelledby="ownerInventoryHeading"]').screenshot({ path: path.join(evidenceDir, 'owner-inventory-before.png') });
  await page.locator('#inventoryProductName').fill('Pomada mate');
  await page.locator('#inventoryProductCategory').fill('Cabello');
  await page.locator('#inventoryProductBarcode').fill('840000000001');
  await page.locator('#inventoryProductUnit').fill('unidad');
  await page.locator('#inventoryProductCost').fill('5.50');
  await page.locator('#inventoryProductPrice').fill('9.00');
  await page.locator('#inventoryProductMinimum').fill('3');
  await page.getByRole('button', { name: 'Crear producto' }).click();
  await expect(page.getByText('Producto creado. Registra una recepción para cargar sus existencias.')).toBeVisible();
  await expect(page.locator('#ownerInventoryProductsBody')).toContainText('Pomada mate');

  await page.locator('#inventoryMovementProduct').selectOption('81');
  await page.locator('#inventoryMovementQuantity').fill('8');
  await page.locator('#inventoryMovementCost').fill('4.75');
  await page.locator('#inventoryMovementNote').fill('Compra inicial');
  await page.getByRole('button', { name: 'Registrar movimiento' }).click();
  await expect(page.getByText('Movimiento registrado en el historial de inventario.')).toBeVisible();
  await expect(page.locator('#ownerInventoryProductsBody')).toContainText('8 unidad');
  await expect(page.locator('#ownerInventoryMovementsBody')).toContainText('Compra inicial');
  await page.locator('[aria-labelledby="ownerInventoryHeading"]').screenshot({ path: path.join(evidenceDir, 'owner-inventory-after.png') });
  expect(requests[0].body).toMatchObject({ name: 'Pomada mate', category: 'Cabello', unit_cost_cents: 550, unit_price_cents: 900, stock_minimum: 3 });
  expect(requests[1].body).toMatchObject({ quantity_delta: 8, reason: 'receipt', unit_cost_cents: 475, note: 'Compra inicial' });
  expect(requests[1].body.idempotency_key).toMatch(/^[0-9a-f-]{36}$/i);
  await page.setViewportSize({ width: 320, height: 800 });
  for (const id of ['ownerInventoryProductForm', 'ownerInventoryMovementForm']) {
    const geometry = await page.locator(`#${id}`).evaluate(form => ({
      width: form.clientWidth,
      scrollWidth: form.scrollWidth,
      childrenFit: [...form.querySelectorAll('input, select, button')].every(control => {
        const rect = control.getBoundingClientRect();
        const bounds = form.getBoundingClientRect();
        return rect.left >= bounds.left - 1 && rect.right <= bounds.right + 1;
      }),
    }));
    expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.width + 1);
    expect(geometry.childrenFit).toBe(true);
  }
  expect(pageErrors).toEqual([]);
});
