const { expect, test } = require('@playwright/test');

test('barber can begin a break, resume availability and read a conflict clearly', async ({ page }) => {
  let state = 'available';
  let rejectBreak = false;
  await page.route('**/api/v1/barber/live-status', async route => {
    if (route.request().method() === 'PUT') {
      const requested = route.request().postDataJSON().state;
      if (requested === 'on_break' && rejectBreak) {
        await route.fulfill({ status: 409, json: { detail: 'Finaliza el servicio en curso antes de iniciar un descanso' } });
        return;
      }
      state = requested;
    }
    await route.fulfill({ json: { state } });
  });
  await page.goto('/index.html');
  await page.evaluate(() => {
    currentUser = { role: 'barber' };
    document.getElementById('dashboardSection').style.display = 'block';
    document.getElementById('serviceModeTab').style.display = 'block';
    document.getElementById('barberLivePresence').hidden = false;
    void loadBarberLiveStatus();
  });
  await expect(page.getByText('Estás disponible para recibir al siguiente cliente.')).toBeVisible();
  await page.getByRole('button', { name: 'Iniciar descanso' }).click();
  await expect(page.getByText('Descanso iniciado.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Volver disponible' })).toBeVisible();
  await page.getByRole('button', { name: 'Volver disponible' }).click();
  await expect(page.getByText('Disponibilidad reanudada.')).toBeVisible();

  rejectBreak = true;
  await page.getByRole('button', { name: 'Iniciar descanso' }).click();
  await expect(page.getByText('Finaliza el servicio en curso antes de iniciar un descanso')).toBeVisible();
  await page.setViewportSize({ width: 320, height: 800 });
  const geometry = await page.locator('#barberLivePresence').evaluate(el => ({
    panel: el.getBoundingClientRect(), button: el.querySelector('button').getBoundingClientRect(),
    viewport: document.documentElement.clientWidth, document: document.documentElement.scrollWidth,
  }));
  expect(geometry.document).toBeLessThanOrEqual(geometry.viewport + 1);
  expect(geometry.button.left).toBeGreaterThanOrEqual(0);
  expect(geometry.button.right).toBeLessThanOrEqual(geometry.viewport + 1);
});
