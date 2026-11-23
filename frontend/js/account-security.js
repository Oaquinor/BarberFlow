"use strict";

(() => {
  const openButton = document.getElementById("changePasswordBtn");
  const dialog = document.getElementById("passwordChangeDialog");
  const form = document.getElementById("passwordChangeForm");
  if (!openButton || !dialog || !form) return;

  const result = document.getElementById("passwordChangeResult");
  const submitButton = form.querySelector("button[type=submit]");
  const closeButton = document.getElementById("closePasswordChange");

  openButton.addEventListener("click", () => {
    result.textContent = "";
    dialog.showModal();
    document.getElementById("passwordCurrent").focus();
  });
  closeButton.addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => form.reset());

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const currentPassword = document.getElementById("passwordCurrent").value;
    const newPassword = document.getElementById("passwordNew").value;
    const confirmation = document.getElementById("passwordConfirm").value;
    if (newPassword !== confirmation) {
      result.textContent = "Las contraseñas nuevas no coinciden.";
      document.getElementById("passwordConfirm").focus();
      return;
    }

    submitButton.disabled = true;
    result.textContent = "Actualizando contraseña…";
    try {
      const response = await KingFlowAuth.fetch(
        `${(window.KINGFLOW_CONFIG?.apiBaseUrl || window.location.origin).replace(/\/$/, "")}/api/v1/auth/change-password`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
        },
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = Array.isArray(data.detail)
          ? data.detail.map((item) => item.msg).join(" ")
          : data.detail;
        throw new Error(detail || "No se pudo actualizar la contraseña.");
      }

      dialog.close();
      await KingFlowAuth.logout();
      sessionStorage.setItem("kingflow-password-changed", "1");
      window.location.assign("/index.html");
    } catch (error) {
      result.textContent = error.message || "Error de conexión al actualizar la contraseña.";
    } finally {
      submitButton.disabled = false;
    }
  });
})();
