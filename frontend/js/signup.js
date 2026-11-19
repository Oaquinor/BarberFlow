"use strict";

const config = window.KINGFLOW_CONFIG || {};
const apiRoot = (config.apiBaseUrl || window.location.origin).replace(/\/$/, "");
const form = document.getElementById("signupForm");
const result = document.getElementById("result");
const button = document.getElementById("submitButton");

async function loadRegistrationStatus() {
  button.disabled = true;
  try {
    const response = await fetch(`${apiRoot}/api/v1/saas/registration-status`);
    if (!response.ok) throw new Error("No se pudo consultar el estado del registro.");
    const status = await response.json();
    if (!status.registrations_enabled) {
      document.getElementById("registrationStatus").textContent = "El registro de nuevas barberías está temporalmente cerrado.";
      form.querySelectorAll("input, select, button").forEach((control) => { control.disabled = true; });
      return;
    }
  } catch (_) {
    // The registration endpoint enforces the setting even if this status request fails.
  }
  button.disabled = false;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  result.textContent = "";
  button.disabled = true;
  const fields = ["owner_first_name", "owner_last_name", "owner_email", "owner_password", "owner_phone", "barbershop_name", "barbershop_email", "barbershop_phone", "address_line1", "city", "state", "postal_code", "country", "timezone", "currency", "affiliate_code"];
  const payload = Object.fromEntries(fields.map((name) => [name, document.getElementById(name).value.trim()]));
  try {
    const response = await fetch(`${apiRoot}/api/v1/saas/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      result.textContent = typeof data.detail === "string" ? data.detail : "Revisa los datos e intenta de nuevo.";
      return;
    }
    window.KingFlowAuth.setTokens(data.access_token, data.refresh_token);
    localStorage.setItem("userEmail", data.user.email);
    window.location.replace("/onboarding.html");
  } catch (_) {
    result.textContent = "No se pudo conectar con KingFlow. Intenta nuevamente.";
  } finally {
    button.disabled = false;
  }
});

loadRegistrationStatus();
