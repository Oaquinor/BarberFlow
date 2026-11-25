const { expect, test } = require("@playwright/test");

test("verified customer can sign in and claim a booking with its private tracking token", async ({ page }) => {
  const trackingToken = "claim-token-" + "x".repeat(40);
  let claimPayload;
  let listCalls = 0;
  await page.route("**/api/v1/auth/login", (route) => route.fulfill({ json: {
    access_token: "client-access", refresh_token: "client-refresh", token_type: "bearer",
    user: { id: 9, email: "ana@example.com", full_name: "Ana Cliente", role: "client" },
  } }));
  await page.route("**/api/v1/client-account/appointments/claim", async (route) => {
    claimPayload = route.request().postDataJSON();
    await route.fulfill({ json: { success: true, appointment_id: 42, message: "La cita se añadió a tu historial." } });
  });
  await page.route("**/api/v1/client-account/appointments", async (route) => {
    listCalls += 1;
    await route.fulfill({ json: { items: listCalls > 1 ? [{
      appointment_id: 42, barbershop: "KingFlow de Prueba", service: "Corte clásico",
      status: "confirmed", scheduled_time: "2026-12-02T15:00:00", barber: "Luis Barbero",
    }] : [] } });
  });

  await page.goto(`/client-account.html#claim=${encodeURIComponent(trackingToken)}`);
  await page.getByLabel("Correo", { exact: true }).fill("ana@example.com");
  await page.getByLabel("Contraseña", { exact: true }).fill("CustomerPass123");
  await page.getByRole("button", { name: "Entrar a mi cuenta" }).click();

  await expect(page.getByRole("heading", { name: "Mis citas" })).toBeVisible();
  await expect(page.getByText("KingFlow de Prueba")).toBeVisible();
  await expect(page.getByText("Corte clásico · Confirmada")).toBeVisible();
  expect(claimPayload).toEqual({ tracking_token: trackingToken });
  await expect(page).toHaveURL(/client-account\.html$/);
});

test("registration explains that an email verification link is required", async ({ page }) => {
  await page.route("**/api/v1/client-account/register", (route) => route.fulfill({
    status: 202, json: { message: "Si el correo puede registrarse, enviaremos un enlace de verificación." },
  }));
  await page.goto("/client-account.html");
  await page.getByText("Crear cuenta de cliente").click();
  await page.getByLabel("Nombre", { exact: true }).fill("Ana");
  await page.getByLabel("Apellido").fill("Cliente");
  await page.getByLabel("Correo para verificar tu cuenta").fill("ana@example.com");
  await page.getByLabel(/Teléfono/).fill("8095551212");
  await page.getByLabel("Contraseña (12 caracteres, una mayúscula y un número)").fill("CustomerPass123");
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await expect(page.getByRole("status")).toContainText("enlace de verificación");
});

test("customer cancels an upcoming appointment only after an in-page confirmation", async ({ page }) => {
  let cancelRequest;
  let listCalls = 0;
  await page.route("**/api/v1/auth/login", (route) => route.fulfill({ json: {
    access_token: "client-access", refresh_token: "client-refresh", token_type: "bearer",
    user: { id: 9, email: "ana@example.com", full_name: "Ana Cliente", role: "client" },
  } }));
  await page.route("**/api/v1/client-account/appointments/42/cancel", async (route) => {
    cancelRequest = route.request().postDataJSON();
    await route.fulfill({ json: { success: true, appointment_id: 42, status: "cancelled" } });
  });
  await page.route("**/api/v1/client-account/appointments", async (route) => {
    listCalls += 1;
    const status = listCalls > 1 ? "cancelled" : "confirmed";
    await route.fulfill({ json: { items: [{
      appointment_id: 42, barbershop: "KingFlow de Prueba", service: "Corte clásico",
      status, scheduled_time: "2026-12-02T15:00:00Z", barber: "Luis Barbero",
    }] } });
  });

  await page.goto("/client-account.html");
  await page.getByLabel("Correo", { exact: true }).fill("ana@example.com");
  await page.getByLabel("Contraseña", { exact: true }).fill("CustomerPass123");
  await page.getByRole("button", { name: "Entrar a mi cuenta" }).click();
  await page.getByRole("button", { name: "Cancelar cita" }).click();
  await expect(page.getByRole("button", { name: "Confirmar cancelación" })).toBeVisible();
  await page.getByRole("button", { name: "Confirmar cancelación" }).click();

  await expect(page.getByRole("status")).toContainText("se canceló");
  await expect(page.getByText("Corte clásico · Cancelada")).toBeVisible();
  expect(cancelRequest).toEqual({});
});

test("verified customer can reschedule an appointment from account history", async ({ page }) => {
  let rescheduleRequest;
  let listCalls = 0;
  await page.route("**/api/v1/auth/login", (route) => route.fulfill({ json: {
    access_token: "client-access", refresh_token: "client-refresh", token_type: "bearer",
    user: { id: 9, email: "ana@example.com", full_name: "Ana Cliente", role: "client" },
  } }));
  await page.route("**/api/v1/public/kingflow-prueba/slots?duration_minutes=30", (route) => route.fulfill({ json: [{
    availability_id: 84, barber_id: 5, barber_name: "Luis Barbero",
    slot_start: "2026-12-03T16:00:00Z", slot_end: "2026-12-03T16:30:00Z",
  }] }));
  await page.route("**/api/v1/public/kingflow-prueba/appointments/reschedule", async (route) => {
    rescheduleRequest = { body: route.request().postDataJSON(), authorization: route.request().headers().authorization };
    await route.fulfill({ json: { success: true, appointment_id: 42, status: "confirmed" } });
  });
  await page.route("**/api/v1/client-account/appointments", async (route) => {
    listCalls += 1;
    await route.fulfill({ json: { items: [{
      appointment_id: 42, barbershop: "KingFlow de Prueba", barbershop_slug: "kingflow-prueba",
      service: "Corte clásico", duration_minutes: 30, status: "confirmed",
      scheduled_time: "2026-12-02T15:00:00Z", barber: "Luis Barbero",
    }] } });
  });

  await page.goto("/client-account.html");
  await page.getByLabel("Correo", { exact: true }).fill("ana@example.com");
  await page.getByLabel("Contraseña", { exact: true }).fill("CustomerPass123");
  await page.getByRole("button", { name: "Entrar a mi cuenta" }).click();
  await page.getByRole("button", { name: "Cambiar fecha y hora" }).click();
  await expect(page.getByLabel("Nuevo horario disponible")).toContainText("Luis Barbero");
  await page.getByRole("button", { name: "Confirmar nuevo horario" }).click();

  await expect(page.getByRole("status")).toContainText("cambió al nuevo horario");
  expect(rescheduleRequest.body).toEqual({ appointment_id: 42, availability_id: 84 });
  expect(rescheduleRequest.authorization).toBe("Bearer client-access");
  expect(listCalls).toBe(2);
});
