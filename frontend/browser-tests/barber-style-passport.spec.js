const { expect, test } = require("@playwright/test");

test("barber reads and updates style notes only for an appointment client", async ({ page }) => {
  const calls = [];
  await page.addInitScript(() => sessionStorage.setItem("token", "style-passport-barber-token"));
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v1", "");
    calls.push({ path, method: request.method() });
    let status = 200;
    let payload = {};
    if (path === "/auth/me") {
      payload = { id: 17, email: "barbero@example.com", full_name: "Luis Barbero", role: "barber" };
    } else if (path === "/onboarding/profile") {
      payload = {
        id: 1, name: "Barbería Demo", slug: "barberia-demo", currency: "DOP",
        timezone: "America/Santo_Domingo", onboarding_completed: true,
        opening_time: "09:00:00", closing_time: "19:00:00", booking_questions: [], gallery_images: [],
      };
    } else if (path === "/barber/dashboard") {
      payload = {
        business_date: "2026-11-25",
        summary: { total: 1, pending: 0, completed: 1, in_progress: 0 },
        appointments: [{
          id: 804, client_id: 42, client_name: "Ana Cliente", service_type: "Corte clásico",
          scheduled_time: "2026-11-25T15:00:00Z", estimated_duration: 30,
          service_price: 2500, status: "completed",
        }],
        services: [], weekly_counts: [], achievements: {},
      };
    } else if (path === "/barber/share-link") {
      payload = { url: "https://kingflow.test/client.html?shop=barberia-demo" };
    } else if (path === "/barber/absences" || path === "/notifications/unread-count") {
      payload = path.endsWith("unread-count") ? { count: 0 } : { items: [] };
    } else if (path === "/barber/cash/today") {
      payload = { business_date: "2026-11-25", currency: "DOP", payment_count: 0, total_cents: 0, by_method: {}, expected_cash_cents: 0, closed: false };
    } else if (path === "/barber/commissions") {
      payload = { items: [], summary: {} };
    } else if (path === "/owner/clients/42/style-passport" && request.method() === "GET") {
      payload = { items: [{
        id: 81, haircut_type: "Crop texturizado", service: "Corte clásico",
        service_date: "2026-11-20T15:00:00", fade_style: "Low fade",
        preferences: "Conservar textura natural", barber_notes: "", recommendations: "",
        share_with_shop: true, photos: [],
      }], limit: 25 };
    } else if (path === "/owner/clients/42/style-passport/81" && request.method() === "PATCH") {
      payload = { id: 81 };
    }
    await route.fulfill({ status, json: payload });
  });

  await page.goto("/index.html");
  await page.locator('.tab[data-tab="appointments"]').click();
  await expect(page.getByText("Ana Cliente", { exact: true })).toBeVisible();
  const passport = page.locator(".barber-style-passport");
  await expect(passport).toBeVisible();
  await passport.locator("summary").click();
  await passport.getByRole("button", { name: "Consultar registros compartidos" }).click();
  await expect(passport.getByText("Conservar textura natural")).toBeVisible();
  await passport.getByLabel("Nota técnica").fill("Mantener el largo superior");
  await passport.getByLabel("Recomendación para la próxima visita").fill("Retoque en cuatro semanas");
  await passport.getByRole("button", { name: "Guardar notas técnicas" }).click();
  await expect(passport.getByRole("status")).toContainText("se guardaron");
  expect(calls).toContainEqual({ path: "/owner/clients/42/style-passport", method: "GET" });
  expect(calls).toContainEqual({ path: "/owner/clients/42/style-passport/81", method: "PATCH" });
  await page.locator("#appointmentsList").screenshot({ path: "../docs/evidence/barber-style-passport.png" });
});
