"use strict";

(() => {
  const apiRoot = (window.KINGFLOW_CONFIG?.apiBaseUrl || window.location.origin).replace(/\/$/, "");
  const api = `${apiRoot}/api/v1/client-account`;
  const status = document.getElementById("accountStatus");
  const authPanel = document.getElementById("authPanel");
  const customerPanel = document.getElementById("customerPanel");
  const verifyPanel = document.getElementById("verifyPanel");
  const appointmentsList = document.getElementById("appointmentsList");
  const labels = { pending: "Pendiente", confirmed: "Confirmada", in_progress: "En curso", completed: "Completada", cancelled: "Cancelada", no_show: "No asistió" };
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  let pendingClaimToken = fragment.get("claim");
  if (window.location.hash) history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);

  function message(value) {
    status.textContent = value || "";
  }

  async function readJson(response) {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "No se pudo completar la solicitud.");
    return data;
  }

  function formatAppointmentDate(value) {
    const date = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
    return Number.isNaN(date.getTime()) ? "Fecha por confirmar" : new Intl.DateTimeFormat("es-DO", { dateStyle: "medium", timeStyle: "short" }).format(date);
  }

  function renderAppointments(items) {
    appointmentsList.replaceChildren();
    if (!items.length) {
      const empty = document.createElement("p");
      empty.textContent = "Aún no hay citas vinculadas. Puedes añadir una con el código privado de seguimiento.";
      appointmentsList.append(empty);
      return;
    }
    items.forEach((item) => {
      const card = document.createElement("article");
      card.className = "appointment-card";
      const title = document.createElement("h3");
      title.textContent = item.barbershop || "Barbería";
      const details = document.createElement("p");
      details.textContent = `${item.service} · ${labels[item.status] || item.status}`;
      const date = document.createElement("p");
      date.textContent = formatAppointmentDate(item.scheduled_time);
      const barber = document.createElement("p");
      barber.textContent = `Atiende: ${item.barber || "Equipo"}`;
      card.append(title, details, date, barber);
      if (["pending", "confirmed"].includes(item.status)) {
        if (item.barbershop_slug) {
          const rescheduleButton = document.createElement("button");
          rescheduleButton.type = "button";
          rescheduleButton.className = "account-action";
          rescheduleButton.dataset.action = "start-reschedule";
          rescheduleButton.dataset.appointmentId = String(item.appointment_id);
          rescheduleButton.dataset.shopSlug = item.barbershop_slug;
          rescheduleButton.dataset.duration = String(item.duration_minutes || 30);
          rescheduleButton.textContent = "Cambiar fecha y hora";
          const chooser = document.createElement("div");
          chooser.className = "reschedule-chooser";
          chooser.hidden = true;
          const select = document.createElement("select");
          select.setAttribute("aria-label", "Nuevo horario disponible");
          const save = document.createElement("button");
          save.type = "button";
          save.className = "account-action";
          save.dataset.action = "confirm-reschedule";
          save.dataset.appointmentId = String(item.appointment_id);
          save.textContent = "Confirmar nuevo horario";
          const dismiss = document.createElement("button");
          dismiss.type = "button";
          dismiss.className = "button-secondary";
          dismiss.dataset.action = "dismiss-reschedule";
          dismiss.textContent = "Conservar horario actual";
          chooser.append(select, save, dismiss);
          card.append(rescheduleButton, chooser);
        }
        const cancelButton = document.createElement("button");
        cancelButton.type = "button";
        cancelButton.className = "account-action";
        cancelButton.dataset.action = "start-cancel";
        cancelButton.textContent = "Cancelar cita";
        const confirmation = document.createElement("div");
        confirmation.className = "cancel-confirmation";
        confirmation.hidden = true;
        const warning = document.createElement("p");
        warning.textContent = "¿Quieres cancelar esta cita? La barbería recibirá una notificación.";
        const confirmButton = document.createElement("button");
        confirmButton.type = "button";
        confirmButton.className = "account-action account-action-danger";
        confirmButton.dataset.action = "confirm-cancel";
        confirmButton.dataset.appointmentId = String(item.appointment_id);
        confirmButton.textContent = "Confirmar cancelación";
        const keepButton = document.createElement("button");
        keepButton.type = "button";
        keepButton.className = "button-secondary";
        keepButton.dataset.action = "dismiss-cancel";
        keepButton.textContent = "Conservar cita";
        confirmation.append(warning, confirmButton, keepButton);
        card.append(cancelButton, confirmation);
      }
      appointmentsList.append(card);
    });
  }

  async function loadAppointments() {
    appointmentsList.textContent = "Cargando tus citas…";
    const response = await window.KingFlowAuth.fetch(`${api}/appointments`);
    const data = await readJson(response);
    renderAppointments(data.items || []);
  }

  appointmentsList.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    if (button.dataset.action === "start-reschedule") {
      const chooser = button.nextElementSibling;
      const select = chooser.querySelector("select");
      button.disabled = true;
      try {
        const response = await fetch(`${apiRoot}/api/v1/public/${encodeURIComponent(button.dataset.shopSlug)}/slots?duration_minutes=${encodeURIComponent(button.dataset.duration)}`);
        const data = await readJson(response);
        select.replaceChildren();
        data.forEach((slot) => {
          const option = document.createElement("option");
          option.value = String(slot.availability_id);
          option.textContent = `${formatAppointmentDate(slot.slot_start)} · ${slot.barber_name}`;
          select.append(option);
        });
        chooser.hidden = false;
        if (!data.length) message("No hay horarios disponibles para esta duración.");
        else select.focus();
      } catch (error) {
        message(error.message);
      } finally {
        button.disabled = false;
      }
      return;
    }
    if (button.dataset.action === "dismiss-reschedule") {
      button.closest(".reschedule-chooser").hidden = true;
      return;
    }
    if (button.dataset.action === "confirm-reschedule") {
      const chooser = button.closest(".reschedule-chooser");
      const select = chooser.querySelector("select");
      if (!select.value) { message("Selecciona un horario disponible."); return; }
      button.disabled = true;
      try {
        await readJson(await window.KingFlowAuth.fetch(
          `${apiRoot}/api/v1/public/${encodeURIComponent(button.closest(".appointment-card").querySelector("[data-action=start-reschedule]").dataset.shopSlug)}/appointments/reschedule`,
          { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ appointment_id: Number(button.dataset.appointmentId), availability_id: Number(select.value) }) },
        ));
        message("La cita cambió al nuevo horario y la barbería recibió una notificación.");
        await loadAppointments();
      } catch (error) {
        message(error.message);
        button.disabled = false;
      }
      return;
    }
    if (button.dataset.action === "start-cancel") {
      const confirmation = button.nextElementSibling;
      confirmation.hidden = false;
      confirmation.querySelector("button[data-action=confirm-cancel]").focus();
      return;
    }
    if (button.dataset.action === "dismiss-cancel") {
      button.closest(".cancel-confirmation").hidden = true;
      return;
    }
    if (button.dataset.action !== "confirm-cancel") return;
    button.disabled = true;
    message("");
    try {
      await readJson(await window.KingFlowAuth.fetch(
        `${api}/appointments/${encodeURIComponent(button.dataset.appointmentId)}/cancel`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) },
      ));
      message("La cita se canceló y se liberó el horario.");
      await loadAppointments();
    } catch (error) {
      message(error.message);
      button.disabled = false;
    }
  });

  async function showAccount(user) {
    authPanel.hidden = true;
    verifyPanel.hidden = true;
    customerPanel.hidden = false;
    document.getElementById("customerGreeting").textContent = `Hola, ${user.full_name || user.email}`;
    try {
      const profile = await readJson(await window.KingFlowAuth.fetch(`${api}/profile`));
      document.getElementById("profileEmail").value = profile.email;
      document.getElementById("profileFirstName").value = profile.first_name;
      document.getElementById("profileLastName").value = profile.last_name;
      document.getElementById("profilePhone").value = profile.phone;
    } catch (error) {
      message(error.message);
    }
    await loadAppointments();
    if (pendingClaimToken) {
      document.getElementById("claimToken").value = pendingClaimToken;
      const token = pendingClaimToken;
      pendingClaimToken = null;
      await claimAppointment(token);
    }
  }

  async function claimAppointment(token) {
    message("");
    try {
      await readJson(await window.KingFlowAuth.fetch(`${api}/appointments/claim`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tracking_token: token }),
      }));
      document.getElementById("claimToken").value = "";
      message("La cita se añadió a tu historial.");
      await loadAppointments();
    } catch (error) {
      message(error.message);
    }
  }

  document.getElementById("loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button[type=submit]");
    button.disabled = true;
    message("");
    try {
      const response = await fetch(`${apiRoot}/api/v1/auth/login`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: document.getElementById("loginEmail").value.trim(),
          password: document.getElementById("loginPassword").value,
        }),
      });
      const data = await readJson(response);
      if (data.user?.role !== "client") throw new Error("Este acceso es para cuentas de cliente.");
      window.KingFlowAuth.setTokens(data.access_token, data.refresh_token);
      await showAccount(data.user);
    } catch (error) {
      message(error.message || "No pudimos iniciar sesión.");
    } finally {
      button.disabled = false;
    }
  });

  document.getElementById("registerForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      const data = await readJson(await fetch(`${api}/register`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: document.getElementById("registerFirstName").value.trim(),
          last_name: document.getElementById("registerLastName").value.trim(),
          email: document.getElementById("registerEmail").value.trim(),
          phone: document.getElementById("registerPhone").value.trim(),
          password: document.getElementById("registerPassword").value,
        }),
      }));
      message(data.message || "Revisa tu correo para verificar la cuenta.");
      form.reset();
    } catch (error) {
      message(error.message);
    } finally {
      button.disabled = false;
    }
  });

  document.getElementById("resendForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      const data = await readJson(await fetch(`${api}/resend-verification`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: document.getElementById("resendEmail").value.trim() }),
      }));
      message(data.message || "Si la cuenta necesita verificación, enviaremos un enlace.");
    } catch (error) {
      message(error.message);
    } finally {
      button.disabled = false;
    }
  });

  document.getElementById("claimForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    await claimAppointment(document.getElementById("claimToken").value.trim());
  });

  document.getElementById("profileForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      const result = await readJson(await window.KingFlowAuth.fetch(`${api}/profile`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: document.getElementById("profileFirstName").value.trim(),
          last_name: document.getElementById("profileLastName").value.trim(),
          phone: document.getElementById("profilePhone").value.trim(),
        }),
      }));
      document.getElementById("customerGreeting").textContent = `Hola, ${result.first_name} ${result.last_name}`;
      message("Tu perfil se guardó correctamente.");
    } catch (error) {
      message(error.message);
    } finally {
      button.disabled = false;
    }
  });

  document.getElementById("logoutButton").addEventListener("click", async () => {
    await window.KingFlowAuth.logout();
    customerPanel.hidden = true;
    authPanel.hidden = false;
    message("Has cerrado sesión.");
  });

  async function initialize() {
    const verifyToken = new URLSearchParams(window.location.search).get("verify");
    if (verifyToken) {
      history.replaceState(null, "", window.location.pathname);
      authPanel.hidden = true;
      verifyPanel.hidden = false;
      try {
        const result = await readJson(await fetch(`${api}/verify`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: verifyToken }),
        }));
        verifyPanel.hidden = true;
        authPanel.hidden = false;
        message(result.message);
      } catch (error) {
        verifyPanel.hidden = true;
        authPanel.hidden = false;
        message(error.message);
      }
      return;
    }
    if (!sessionStorage.getItem("token")) {
      if (pendingClaimToken) message("Inicia sesión o crea una cuenta para añadir la cita del enlace privado.");
      return;
    }
    try {
      const response = await window.KingFlowAuth.fetch(`${apiRoot}/api/v1/auth/me`);
      const user = await readJson(response);
      if (user.role !== "client") return;
      await showAccount(user);
    } catch (_) {
      // Keep the login form visible when this tab's session is expired or belongs to another portal.
    }
  }

  initialize();
})();
