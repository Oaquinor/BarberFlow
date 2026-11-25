const { expect, test } = require("@playwright/test");

test("public booking submits configured consultation answers separately from notes", async ({ page }) => {
  let submitted;
  await page.route("**/api/v1/public/consultation-shop", (route) => route.fulfill({ json: {
    id: 45, name: "Barbería Consulta", slug: "consultation-shop", currency: "DOP",
    timezone: "America/Santo_Domingo", phone: "8095550000", address_line1: "Calle 1",
    city: "Santo Domingo", state: "DN", opening_time: "09:00:00", closing_time: "19:00:00",
    logo_url: null, cover_image_url: null, description: "Cortes con atención personal.",
    gallery_images: [], booking_questions: ["¿Qué resultado quieres lograr?"], team: [],
    primary_color: "#b98752", secondary_color: "#5a4635", public_theme: "light",
    cancellation_window_hours: 12,
  } }));
  await page.route("**/api/v1/public/consultation-shop/services", (route) => route.fulfill({ json: [{
    id: 12, name: "Corte clásico", description: "Corte y acabado", duration_minutes: 30,
    price_cents: 150000, category: "haircut", image_url: null,
  }] }));
  await page.route("**/api/v1/public/consultation-shop/slots**", (route) => route.fulfill({ json: [{
    availability_id: 81, barber_id: 7, barber_name: "Luis", slot_start: "2030-01-15T14:00:00Z",
    slot_end: "2030-01-15T15:00:00Z",
  }] }));
  await page.route("**/api/v1/public/consultation-shop/appointments", async (route) => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ json: {
      appointment_id: 101,
      tracking_link: "http://127.0.0.1:4173/client.html?shop=consultation-shop&track_token=private-test-token",
    } });
  });

  await page.goto("/client.html?shop=consultation-shop");
  const serviceCard = page.locator("#publicServices .service-card");
  const cardMetrics = await serviceCard.evaluate((card) => {
    const cardBottom = card.getBoundingClientRect().bottom;
    const priceBottom = card.querySelector(".service-bottom").getBoundingClientRect().bottom;
    return { gap: cardBottom - priceBottom, scrollWidth: card.scrollWidth, clientWidth: card.clientWidth };
  });
  expect(cardMetrics.gap).toBeGreaterThanOrEqual(8);
  expect(cardMetrics.scrollWidth).toBeLessThanOrEqual(cardMetrics.clientWidth);
  await expect(serviceCard.locator(".public-favorite-button")).toBeVisible();
  await page.screenshot({ path: "../docs/evidence/public-booking-answers-before.png", fullPage: true });
  await page.getByLabel("¿Cómo te llamas?").fill("Ana Prueba");
  await page.locator("#clientPhone").fill("8095551234");
  await page.getByLabel("¿Qué estilo tienes en mente?").selectOption({ label: "Degradado / fade" });
  await page.getByLabel("¿Cómo llevas el cabello ahora?").selectOption({ label: "Medio" });
  await page.getByLabel("¿Alguna preferencia?").selectOption({ label: "Acabado natural" });
  await page.getByLabel("Referencias o algo que debamos saber").fill("Mantener volumen arriba");
  await page.getByLabel("¿Qué resultado quieres lograr?").fill("Líneas limpias, sin bajar demasiado los lados");
  await page.getByRole("button", { name: /Confirmar cita/ }).click();

  await expect(page.getByRole("status")).toContainText("Cita creada (ID 101)");
  await page.screenshot({ path: "../docs/evidence/public-booking-answers-after.png", fullPage: true });
  expect(submitted).toMatchObject({
    client_name: "Ana Prueba",
    phone: "8095551234",
    service_id: 12,
    barber_id: 7,
    notes: null,
    booking_answers: {
      "Estilo buscado": "Degradado / fade",
      "Largo actual": "Medio",
      "Acabado preferido": "Acabado natural",
      "Referencia del cliente": "Mantener volumen arriba",
      "¿Qué resultado quieres lograr?": "Líneas limpias, sin bajar demasiado los lados",
    },
  });
  await page.setViewportSize({ width: 320, height: 800 });
  const mobileMetrics = await serviceCard.evaluate((card) => ({
    gap: card.getBoundingClientRect().bottom - card.querySelector(".service-bottom").getBoundingClientRect().bottom,
    scrollWidth: card.scrollWidth,
    clientWidth: card.clientWidth,
  }));
  expect(mobileMetrics.gap).toBeGreaterThanOrEqual(8);
  expect(mobileMetrics.scrollWidth).toBeLessThanOrEqual(mobileMetrics.clientWidth);
});
