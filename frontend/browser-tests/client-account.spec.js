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
  await page.route("**/api/v1/client-account/profile", (route) => route.fulfill({ json: {
    email: "ana@example.com", first_name: "Ana", last_name: "Cliente", phone: "18095551213",
  } }));
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
  await expect(page.locator(".appointment-card").getByText("KingFlow de Prueba")).toBeVisible();
  await expect(page.getByText("Corte clásico · Confirmada")).toBeVisible();
  expect(claimPayload).toEqual({ tracking_token: trackingToken });
  await expect(page).toHaveURL(/client-account\.html$/);
});

test("registration explains that an email verification link is required", async ({ page }) => {
  await page.route("**/api/v1/client-account/register", (route) => route.fulfill({
    status: 202, json: { message: "Si el correo puede registrarse, enviaremos un enlace de verificación." },
  }));
  await page.goto("/client-account.html");
  await expect(page.locator("#accountStatus")).toHaveCSS("display", "none");
  await page.getByText("Crear cuenta de cliente").click();
  await page.getByLabel("Nombre", { exact: true }).fill("Ana");
  await page.getByLabel("Apellido", { exact: true }).fill("Cliente");
  await page.getByLabel("Correo para verificar tu cuenta").fill("ana@example.com");
  await page.getByLabel("Teléfono (no se usa para reclamar citas)").fill("8095551212");
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
  await page.route("**/api/v1/client-account/profile", (route) => route.fulfill({ json: {
    email: "ana@example.com", first_name: "Ana", last_name: "Cliente", phone: "18095551213",
  } }));
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
  await page.route("**/api/v1/client-account/profile", (route) => route.fulfill({ json: {
    email: "ana@example.com", first_name: "Ana", last_name: "Cliente", phone: "18095551213",
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
  await expect(page.getByRole("heading", { name: "Tu próxima cita" })).toBeVisible();
  await expect(page.locator(".next-appointment")).toContainText("KingFlow de Prueba");
  await expect(page.locator(".next-appointment")).toContainText("Faltan 7 días");
  await page.getByRole("button", { name: "Cambiar fecha y hora" }).click();
  await expect(page.getByLabel("Nuevo horario disponible")).toContainText("Luis Barbero");
  await page.getByRole("button", { name: "Confirmar nuevo horario" }).click();

  await expect(page.getByRole("status")).toContainText("cambió al nuevo horario");
  expect(rescheduleRequest.body).toEqual({ appointment_id: 42, availability_id: 84 });
  expect(rescheduleRequest.authorization).toBe("Bearer client-access");
  expect(listCalls).toBe(2);
});

test("customer can update account name and phone while email remains verified and read only", async ({ page }) => {
  let profileUpdate;
  await page.route("**/api/v1/auth/login", (route) => route.fulfill({ json: {
    access_token: "client-access", refresh_token: "client-refresh", token_type: "bearer",
    user: { id: 9, email: "ana@example.com", full_name: "Ana Cliente", role: "client" },
  } }));
  await page.route("**/api/v1/client-account/profile", async (route) => {
    if (route.request().method() === "PATCH") {
      profileUpdate = route.request().postDataJSON();
      await route.fulfill({ json: { success: true, email: "ana@example.com", ...profileUpdate } });
      return;
    }
    await route.fulfill({ json: { email: "ana@example.com", first_name: "Ana", last_name: "Cliente", phone: "18095551213" } });
  });
  await page.route("**/api/v1/client-account/export", (route) => route.fulfill({ json: {
    exported_at: "2026-11-25T12:00:00Z",
    account: { email: "ana@example.com", first_name: "Andrea", last_name: "Pérez", phone: "18095550099" },
    appointments: [],
  } }));
  await page.route("**/api/v1/client-account/appointments", (route) => route.fulfill({ json: { items: [] } }));

  await page.goto("/client-account.html");
  await page.getByLabel("Correo", { exact: true }).fill("ana@example.com");
  await page.getByLabel("Contraseña", { exact: true }).fill("CustomerPass123");
  await page.getByRole("button", { name: "Entrar a mi cuenta" }).click();
  await expect(page.getByLabel("Correo verificado")).toHaveValue("ana@example.com");
  await expect(page.getByLabel("Correo verificado")).toHaveAttribute("readonly", "");
  await page.getByLabel("Nombre de tu cuenta").fill("Andrea");
  await page.getByLabel("Apellido de tu cuenta").fill("Pérez");
  await page.getByLabel("Teléfono de tu cuenta").fill("809 555 0099");
  await page.getByRole("button", { name: "Guardar perfil" }).click();

  await expect(page.getByRole("status")).toContainText("perfil se guardó");
  expect(profileUpdate).toEqual({ first_name: "Andrea", last_name: "Pérez", phone: "809 555 0099" });
  await expect(page.getByText("Hola, Andrea Pérez")).toBeVisible();
  await expect(page.getByRole("button", { name: "Descargar mis datos" })).toHaveCSS(
    "background-color", "rgba(0, 0, 0, 0)",
  );
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Descargar mis datos" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("kingflow-mis-datos.json");
  await expect(page.getByRole("status")).toContainText("archivo con los datos");
});

test("customer can review and remove a saved service from account favorites", async ({ page }) => {
  let favoritesRead = 0;
  let deletedFavorite;
  await page.route("**/api/v1/auth/login", (route) => route.fulfill({ json: {
    access_token: "client-access", refresh_token: "client-refresh", token_type: "bearer",
    user: { id: 9, email: "ana@example.com", full_name: "Ana Cliente", role: "client" },
  } }));
  await page.route("**/api/v1/client-account/profile", (route) => route.fulfill({ json: {
    email: "ana@example.com", first_name: "Ana", last_name: "Cliente", phone: "18095551213",
  } }));
  await page.route("**/api/v1/client-account/appointments", (route) => route.fulfill({ json: { items: [] } }));
  await page.route("**/api/v1/client-account/favorites**", async (route) => {
    if (route.request().method() === "DELETE") {
      deletedFavorite = route.request().url();
      await route.fulfill({ json: { success: true } });
      return;
    }
    favoritesRead += 1;
    await route.fulfill({ json: { items: favoritesRead === 1 ? [{
      favorite_id: 71, barbershop: "KingFlow de Prueba", barbershop_slug: "kingflow-prueba",
      target_type: "service", target_id: 14, name: "Corte clásico", price_cents: 25000,
      duration_minutes: 30, image_url: null,
    }] : [] } });
  });

  await page.goto("/client-account.html");
  await page.getByLabel("Correo", { exact: true }).fill("ana@example.com");
  await page.getByLabel("Contraseña", { exact: true }).fill("CustomerPass123");
  await page.getByRole("button", { name: "Entrar a mi cuenta" }).click();

  await expect(page.getByRole("heading", { name: "Mis favoritos" })).toBeVisible();
  await expect(page.locator(".favorite-card")).toContainText("Corte clásico");
  await expect(page.locator(".favorite-card")).toContainText("KingFlow de Prueba");
  await page.getByRole("button", { name: "Quitar de favoritos" }).click();
  await expect(page.getByText("Aún no guardas servicios ni barberos.")).toBeVisible();
  expect(deletedFavorite).toContain("/client-account/favorites/71");
});

test("customer can save and unsave a barbershop from its public page", async ({ page }) => {
  let savedPayload;
  let favoriteIsSaved = false;
  await page.addInitScript(() => {
    sessionStorage.setItem("token", "client-access");
    sessionStorage.setItem("refresh_token", "client-refresh");
  });
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: {
    id: 9, email: "ana@example.com", full_name: "Ana Cliente", role: "client",
    barbershop_id: null, is_verified: true, phone: "18095551213",
  } }));
  await page.route("**/api/v1/public/favorite-shop", (route) => route.fulfill({ json: {
    id: 25, name: "Barbería Favorita", slug: "favorite-shop", currency: "DOP",
    timezone: "America/Santo_Domingo", cancellation_window_hours: 12,
    opening_time: "09:00:00", closing_time: "19:00:00", team: [],
    gallery_images: [], booking_questions: [], public_theme: "light",
  } }));
  await page.route("**/api/v1/public/favorite-shop/services", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/public/favorite-shop/slots**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/client-account/favorites**", async (route) => {
    const method = route.request().method();
    if (method === "GET") {
      await route.fulfill({ json: { items: favoriteIsSaved ? [{
        favorite_id: 84, barbershop: "Barbería Favorita", barbershop_slug: "favorite-shop",
        target_type: "barbershop", target_id: 25, name: "Barbería Favorita", image_url: null,
      }] : [] } });
    } else if (method === "POST") {
      savedPayload = route.request().postDataJSON();
      favoriteIsSaved = true;
      await route.fulfill({ json: { success: true, favorite_id: 84 } });
    } else {
      favoriteIsSaved = false;
      await route.fulfill({ json: { success: true } });
    }
  });

  await page.goto("/client.html?shop=favorite-shop");
  const favoriteButton = page.locator("#shopFavoriteButton");
  await page.screenshot({ path: "../docs/evidence/client-barbershop-favorite-before.png", fullPage: true });
  await favoriteButton.click();
  await expect(favoriteButton).toHaveAttribute("aria-pressed", "true");
  await page.screenshot({ path: "../docs/evidence/client-barbershop-favorite-after.png", fullPage: true });
  expect(savedPayload).toEqual({ barbershop_slug: "favorite-shop", target_type: "barbershop", target_id: 25 });
  await favoriteButton.click();
  await expect(favoriteButton).toHaveAttribute("aria-pressed", "false");
});
