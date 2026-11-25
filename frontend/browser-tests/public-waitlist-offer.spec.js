const { expect, test } = require("@playwright/test");

test("customer can review and accept an expiring waitlist offer", async ({ page }) => {
  const token = "x".repeat(43);
  let accepted = false;
  await page.route("**/api/v1/public/waitlist-shop", (route) => route.fulfill({ json: {
    id: 81, name: "Barbería Oferta", slug: "waitlist-shop", currency: "DOP",
    timezone: "America/Santo_Domingo", phone: "8095550000", address_line1: "Calle 1",
    city: "Santo Domingo", state: "DN", opening_time: "09:00:00", closing_time: "19:00:00",
    logo_url: null, cover_image_url: null, description: "Cortes con atención personal.",
    gallery_images: [], booking_questions: [], team: [], primary_color: "#b98752",
    secondary_color: "#5a4635", public_theme: "light", cancellation_window_hours: 0,
  } }));
  await page.route("**/api/v1/public/waitlist-shop/services", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/public/waitlist-shop/slots**", (route) => route.fulfill({ json: [] }));
  await page.route(`**/api/v1/public/waitlist-shop/waitlist-offers/${token}/accept`, async (route) => {
    accepted = true;
    await route.fulfill({ json: {
      accepted: true,
      tracking_url: `http://127.0.0.1:4173/client.html?shop=waitlist-shop&track_token=${"t".repeat(43)}`,
    } });
  });
  await page.route(`**/api/v1/public/waitlist-shop/waitlist-offers/${token}`, (route) => route.fulfill({ json: {
      status: "pending", expires_at: "2026-12-01T20:00:00Z",
      barbershop_name: "Barbería Oferta", service_name: "Corte clásico",
      barber_name: "Luis Barbero", slot_start: "2026-12-01T19:00:00Z", currency: "DOP",
  } }));

  await page.goto(`/client.html?shop=waitlist-shop&waitlist_offer=${token}`);
  await expect(page.locator("#waitlistOfferPanel")).toBeVisible();
  await expect(page.locator("#waitlistOfferDetails")).toContainText("Corte clásico");
  await page.getByRole("button", { name: /Aceptar horario/ }).click();
  await expect(page.locator("#waitlistOfferResult")).toContainText("El horario quedó reservado");
  await expect(page.locator("#waitlistOfferResult a")).toHaveText("Consultar mi cita");
  await expect(page).not.toHaveURL(/waitlist_offer=/);
  await page.setViewportSize({ width: 320, height: 800 });
  expect(await page.locator("body").evaluate((body) => body.scrollWidth))
    .toBeLessThanOrEqual(321);
  expect(accepted).toBe(true);
});
