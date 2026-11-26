const { expect, test } = require('@playwright/test');

test('owner workspace exposes FlowJ-style sections with working data and safe screen view', async ({ page }) => {
  const requests = [];
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await page.addInitScript(() => sessionStorage.setItem('token', 'workspace-owner-session'));
  await page.route('**/health', route => route.fulfill({ json: { status: 'healthy', database: 'connected' } }));
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace('/api/v1', '');
    requests.push(path);
    let payload = {};
    if (path === '/auth/me') payload = { id: 4, email: 'owner@example.com', full_name: 'Dueño Demo', role: 'barbershop_owner' };
    else if (path === '/onboarding/profile') payload = { id: 1, name: 'Barbería Demo', slug: 'barberia-demo', currency: 'DOP', timezone: 'America/Santo_Domingo', onboarding_completed: true, opening_time: '09:00:00', closing_time: '19:00:00', booking_questions: [], gallery_images: [] };
    else if (path === '/barber/share-link') payload = { url: 'http://localhost:8000/client.html?shop=barberia-demo' };
    else if (path === '/barber/dashboard') payload = { summary: {}, appointments: [], services: [] };
    else if (path === '/barber/cash/today') payload = { business_date: '2026-11-26', currency: 'DOP', payment_count: 0, total_cents: 0, by_method: {}, expected_cash_cents: 0, closed: false, close: null };
    else if (path === '/barber/appointments') payload = { business_date: '2026-11-26', appointments: [{ id: 1, client_name: 'Nombre Privado', service_type: 'Corte clásico', scheduled_time: '2026-11-26T15:00:00Z', estimated_duration: 30, checked_in_at: '2026-11-26T14:00:00Z', client_notes: 'Llegó antes', status: 'confirmed' }] };
    else if (path === '/barber/cash/history') payload = { currency: 'DOP', items: [{ business_date: '2026-11-25', closed_by_name: 'Dueño Demo', closed_by_role: 'barbershop_owner', expected_cash_cents: 10000, declared_cash_cents: 9900, difference_cents: -100, payment_count: 4, closed_at: '2026-11-25T22:00:00Z' }] };
    else if (path === '/notifications/unread-count') payload = { unread_count: 0 };
    else if (path.startsWith('/owner/')) payload = { items: [], total: 0, totals: {} };
    await route.fulfill({ status: 200, json: payload });
  });

  await page.goto('/index.html');
  await expect(page.locator('#dashboardSection')).toBeVisible();
  await page.getByRole('button', { name: 'Citas', exact: true }).click();
  await expect(page.locator('#appointmentsTab > h2')).toHaveText('Citas');
  await expect(page.locator('#walkInForm')).toBeHidden();
  await expect(page.locator('#appointmentsList')).toContainText('Nombre Privado');

  await page.getByRole('button', { name: 'Turnos', exact: true }).click();
  await expect(page.locator('#appointmentsTab > h2')).toHaveText('Turnos');
  await expect(page.locator('#walkInForm')).toBeVisible();
  await expect(page.locator('#appointmentsList')).toContainText('En espera · turno 1');

  await page.getByRole('button', { name: 'Pantallas', exact: true }).click();
  await expect(page.locator('#screenBoardQueue')).toContainText('Corte clásico');
  await expect(page.locator('#screenBoard')).not.toContainText('Nombre Privado');
  await expect(page.locator('#screenBoardStatus')).toContainText('1 turno');

  await page.getByRole('button', { name: 'Historial', exact: true }).click();
  await expect(page.locator('#cashHistoryBody')).toContainText('Dueño Demo');
  await expect(page.locator('#cashHistoryResult')).toContainText('1 cierre');

  await page.getByRole('button', { name: 'Mi sitio', exact: true }).click();
  await expect(page.locator('#ownerManagementTab')).toBeVisible();
  await expect(page.locator('#publicGalleryEditorTitle')).toBeInViewport();
  await page.getByRole('button', { name: 'Configuración', exact: true }).click();
  await expect(page.locator('#businessSettingsTitle')).toBeInViewport();
  await page.getByRole('button', { name: 'Acerca de', exact: true }).click();
  await page.getByRole('button', { name: 'Probar conexión' }).click();
  await expect(page.locator('#connectionResult')).toContainText('MySQL: connected');
  expect(requests).toContain('/barber/cash/history');
  expect(pageErrors).toEqual([]);
});

test('every workspace section fits mobile and desktop', async ({ page }) => {
  await page.goto('/index.html');
  await page.evaluate(() => {
    document.getElementById('loginSection').style.display = 'none';
    document.getElementById('dashboardSection').style.display = 'grid';
    document.querySelectorAll('#dashboardSection > .tabs button').forEach(el => el.hidden = false);
    currentUser = { role: 'barbershop_owner' };
  });
  const panels = await page.locator('#dashboardSection > .tab-content').evaluateAll(els => els.map(el => el.id));
  for (const width of [320, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const id of panels) {
      await page.evaluate(id => {
        document.querySelectorAll('#dashboardSection > .tab-content').forEach(el => el.style.display = el.id === id ? 'block' : 'none');
      }, id);
      const size = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, content: document.documentElement.scrollWidth }));
      expect(size.content, `${id} at ${width}px`).toBeLessThanOrEqual(size.viewport + 1);
    }
  }
});
