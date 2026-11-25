const { expect, test } = require("@playwright/test");

test("customer can request contact when a selected shop has no available slots", async ({ page }) => {
  let submitted;
  await page.route("**/api/v1/public/waitlist-shop", (route) => route.fulfill({ json: {
    id: 51, name: "Barbería Lista", slug: "waitlist-shop", currency: "DOP",
    timezone: "America/Santo_Domingo", phone: "8095550000", address_line1: "Calle 1",
    city: "Santo Domingo", state: "DN", opening_time: "09:00:00", closing_time: "19:00:00",
    logo_url: null, cover_image_url: null, description: "Cortes con atención personal.",
    gallery_images: [], booking_questions: [], team: [{ id: 7, name: "Luis Barbero" }], primary_color: "#b98752",
    secondary_color: "#5a4635", public_theme: "light", cancellation_window_hours: 0,
  } }));
  await page.route("**/api/v1/public/waitlist-shop/services", (route) => route.fulfill({ json: [{
    id: 22, name: "Corte clásico", description: "Corte y acabado", duration_minutes: 30,
    price_cents: 150000, category: "haircut", image_url: null,
  }] }));
  await page.route("**/api/v1/public/waitlist-shop/slots**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/public/waitlist-shop/waitlist", async (route) => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 202, json: {
      accepted: true,
      message: "Tu solicitud quedó registrada. La barbería te contactará si encuentra un horario adecuado.",
    } });
  });

  await page.goto("/client.html?shop=waitlist-shop");
  await page.locator("#serviceSelect").selectOption("22");
  const openWaitlist = page.getByRole("button", { name: "Avísenme si se libera un horario" });
  await expect(openWaitlist).toBeVisible();
  await page.screenshot({ path: "../docs/evidence/public-waitlist-before.png", fullPage: true });
  await openWaitlist.click();
  await page.getByLabel("¿Cómo te llamas?").fill("Ana Prueba");
  await page.locator("#clientPhone").fill("8095551234");
  await page.getByLabel("Barbero", { exact: true }).selectOption("7");
  await page.getByLabel("Desde (opcional)").fill("2030-01-15");
  await page.getByLabel("Hasta (opcional)").fill("2030-01-18");
  await page.getByLabel("Preferencia de horario o detalle (opcional)").fill("Después de las cinco");
  await page.getByRole("button", { name: /Solicitar aviso/ }).click();
  await expect(page.locator("#waitlistResult")).toContainText("quedó registrada");
  await page.screenshot({ path: "../docs/evidence/public-waitlist-after.png", fullPage: true });
  expect(submitted).toEqual({
    client_name: "Ana Prueba", phone: "8095551234", service_id: 22,
    idempotency_key: expect.stringMatching(/^[0-9a-f-]{36}$/i), barber_id: 7,
    preferred_date_start: "2030-01-15", preferred_date_end: "2030-01-18",
    notes: "Después de las cinco",
  });
  await expect(page.locator("#waitlistSubmitBtn")).toBeDisabled();
  await expect(page.locator("#waitlistFields")).toBeHidden();
  await page.setViewportSize({ width: 320, height: 800 });
  expect(await page.locator("body").evaluate((body) => body.scrollWidth))
    .toBeLessThanOrEqual(321);
});
