"use strict";

(() => {
  const apiRoot = (window.KINGFLOW_CONFIG?.apiBaseUrl || window.location.origin).replace(/\/$/, "");
  const params = new URLSearchParams(window.location.search);
  const token = params.get("token") || "";
  const requestForm = document.getElementById("requestForm");
  const confirmForm = document.getElementById("confirmForm");
  const result = document.getElementById("result");
  const requestButton = requestForm.querySelector("button[type=submit]");
  const confirmButton = confirmForm.querySelector("button[type=submit]");

  if (token) {
    requestForm.hidden = true;
    confirmForm.hidden = false;
    // Keep the single-use credential out of browser history and later referrers.
    window.history.replaceState(null, "", window.location.pathname);
  }

  async function post(path, payload) {
    const response = await fetch(`${apiRoot}/api/v1/auth/password-reset/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = Array.isArray(data.detail)
        ? data.detail.map((item) => item.msg).join(" ")
        : data.detail;
      throw new Error(detail || "No fue posible completar la solicitud.");
    }
    return data;
  }

  requestForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    requestButton.disabled = true;
    result.textContent = "";
    try {
      const data = await post("request", { email: document.getElementById("email").value.trim() });
      result.textContent = data.message;
      requestForm.reset();
    } catch (error) {
      result.textContent = error.message;
    } finally {
      requestButton.disabled = false;
    }
  });

  confirmForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!token) return;
    confirmButton.disabled = true;
    result.textContent = "";
    try {
      const data = await post("confirm", {
        token,
        new_password: document.getElementById("newPassword").value,
      });
      result.textContent = data.message;
      confirmForm.reset();
      confirmForm.hidden = true;
    } catch (error) {
      result.textContent = error.message;
    } finally {
      confirmButton.disabled = false;
    }
  });
})();
