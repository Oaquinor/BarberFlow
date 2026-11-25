"use strict";

(() => {
  const apiRoot = (window.KINGFLOW_CONFIG?.apiBaseUrl || window.location.origin).replace(/\/$/, "");
  const api = `${apiRoot}/api/v1/client-account`;
  const status = document.getElementById("accountStatus");
  const authPanel = document.getElementById("authPanel");
  const customerPanel = document.getElementById("customerPanel");
  const verifyPanel = document.getElementById("verifyPanel");
  const appointmentsList = document.getElementById("appointmentsList");
  const favoritesList = document.getElementById("favoritesList");
  const stylePassportList = document.getElementById("stylePassportList");
  const stylePassportForm = document.getElementById("stylePassportForm");
  let appointmentItems = [];
  let stylePassportItems = [];
  let stylePhotoObjectUrl = null;
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
    const date = parseAppointmentDate(value);
    return Number.isNaN(date.getTime()) ? "Fecha por confirmar" : new Intl.DateTimeFormat("es-DO", { dateStyle: "medium", timeStyle: "short" }).format(date);
  }

  function parseAppointmentDate(value) {
    return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
  }

  function trustedFavoriteImage(value) {
    if (typeof value !== "string" || !value.trim()) return "";
    try {
      const url = new URL(value, apiRoot);
      return url.origin === new URL(apiRoot).origin && ["http:", "https:"].includes(url.protocol) &&
        !url.username && !url.password ? url.href : "";
    } catch (_) { return ""; }
  }

  function renderNextAppointment(items) {
    const container = document.getElementById("nextAppointmentContent");
    container.replaceChildren();
    const now = Date.now();
    const upcoming = items
      .filter((item) => ["pending", "confirmed"].includes(item.status))
      .map((item) => ({ item, date: parseAppointmentDate(item.scheduled_time) }))
      .filter(({ date }) => !Number.isNaN(date.getTime()) && date.getTime() > now)
      .sort((left, right) => left.date - right.date)[0];
    if (!upcoming) {
      const empty = document.createElement("p");
      empty.textContent = "No tienes citas próximas. Cuando reserves, la verás aquí.";
      container.append(empty);
      return;
    }

    const { item, date } = upcoming;
    const shop = document.createElement("p");
    shop.className = "next-appointment-shop";
    shop.textContent = item.barbershop || "Barbería";
    const service = document.createElement("p");
    service.textContent = item.service || "Servicio";
    const scheduled = document.createElement("time");
    scheduled.dateTime = date.toISOString();
    scheduled.textContent = formatAppointmentDate(item.scheduled_time);
    const barber = document.createElement("p");
    barber.textContent = `Con ${item.barber || "el equipo"}`;
    const hoursRemaining = Math.floor((date.getTime() - now) / 3600000);
    const remaining = document.createElement("p");
    remaining.className = "next-appointment-countdown";
    if (hoursRemaining < 1) remaining.textContent = "Tu cita es en menos de una hora";
    else if (hoursRemaining < 24) remaining.textContent = `Faltan ${hoursRemaining} ${hoursRemaining === 1 ? "hora" : "horas"}`;
    else {
      const days = Math.floor(hoursRemaining / 24);
      remaining.textContent = `Faltan ${days} ${days === 1 ? "día" : "días"}`;
    }
    const details = document.createElement("button");
    details.type = "button";
    details.className = "button-secondary next-appointment-action";
    details.textContent = "Ver detalles de la cita";
    details.addEventListener("click", () => {
      const card = document.getElementById(`appointment-${item.appointment_id}`);
      card?.scrollIntoView({ behavior: "smooth", block: "center" });
      card?.querySelector("h3")?.focus();
    });
    container.append(shop, service, scheduled, barber, remaining, details);
  }

  function renderAppointments(items) {
    appointmentsList.replaceChildren();
    renderNextAppointment(items);
    if (!items.length) {
      const empty = document.createElement("p");
      empty.textContent = "Aún no hay citas vinculadas. Puedes añadir una con el código privado de seguimiento.";
      appointmentsList.append(empty);
      return;
    }
    items.forEach((item) => {
      const card = document.createElement("article");
      card.className = "appointment-card";
      card.id = `appointment-${Number(item.appointment_id)}`;
      const title = document.createElement("h3");
      title.tabIndex = -1;
      title.textContent = item.barbershop || "Barbería";
      const details = document.createElement("p");
      details.textContent = `${item.service} · ${labels[item.status] || item.status}`;
      const date = document.createElement("p");
      date.textContent = formatAppointmentDate(item.scheduled_time);
      const barber = document.createElement("p");
      barber.textContent = `Atiende: ${item.barber || "Equipo"}`;
      card.append(title, details, date, barber);
      if (item.status === "completed") {
        const saveStyle = document.createElement("button");
        saveStyle.type = "button";
        saveStyle.className = "button-secondary style-appointment-action";
        saveStyle.dataset.action = "add-style-passport";
        saveStyle.dataset.appointmentId = String(item.appointment_id);
        saveStyle.textContent = "Guardar detalles de este corte";
        card.append(saveStyle);
      }
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
    appointmentItems = data.items || [];
    renderAppointments(appointmentItems);
    return appointmentItems;
  }

  function styleField(label, value) {
    if (!value) return null;
    const row = document.createElement("div");
    const term = document.createElement("dt");
    term.textContent = label;
    const detail = document.createElement("dd");
    detail.textContent = value;
    row.append(term, detail);
    return row;
  }

  function applyStyleEntryButtons() {
    const savedAppointments = new Set(stylePassportItems.map((item) => Number(item.appointment_id)));
    appointmentsList.querySelectorAll('[data-action="add-style-passport"]').forEach((button) => {
      button.hidden = savedAppointments.has(Number(button.dataset.appointmentId));
    });
  }

  function fillStyleAppointmentSelect(selectedAppointmentId = "", entry = null) {
    const select = document.getElementById("stylePassportAppointment");
    const savedAppointments = new Set(stylePassportItems.map((item) => Number(item.appointment_id)));
    select.replaceChildren(new Option("Selecciona una visita completada", ""));
    appointmentItems.filter((item) => item.status === "completed").forEach((item) => {
      if (savedAppointments.has(Number(item.appointment_id)) &&
          Number(item.appointment_id) !== Number(entry?.appointment_id)) return;
      select.add(new Option(
        `${item.barbershop} · ${item.service} · ${formatAppointmentDate(item.scheduled_time)}`,
        String(item.appointment_id),
      ));
    });
    if (entry && ![...select.options].some((option) => option.value === String(entry.appointment_id))) {
      select.add(new Option(
        `${entry.barbershop_name} · ${entry.service} · ${formatAppointmentDate(entry.service_date)}`,
        String(entry.appointment_id),
      ));
    }
    select.value = selectedAppointmentId ? String(selectedAppointmentId) : "";
    select.disabled = Boolean(entry);
  }

  function clearStylePassportForm() {
    stylePassportForm.reset();
    document.getElementById("stylePassportEntryId").value = "";
    document.getElementById("stylePassportAppointment").disabled = false;
    document.getElementById("stylePassportFormTitle").textContent = "Guarda una visita completada";
    document.getElementById("stylePassportFormResult").textContent = "";
    stylePassportForm.hidden = true;
  }

  function openStylePassportForm(appointmentId = "", entry = null) {
    stylePassportForm.reset();
    document.getElementById("stylePassportEntryId").value = entry ? String(entry.id) : "";
    document.getElementById("stylePassportFormTitle").textContent = entry
      ? "Actualiza los detalles de tu corte" : "Guarda una visita completada";
    document.getElementById("stylePassportHaircut").value = entry?.haircut_type || "";
    document.getElementById("stylePassportFade").value = entry?.fade_style || "";
    document.getElementById("stylePassportTop").value = entry?.top_length || "";
    document.getElementById("stylePassportSides").value = entry?.sides_length || "";
    document.getElementById("stylePassportBeard").value = entry?.beard_style || "";
    document.getElementById("stylePassportProducts").value = entry?.products_used || "";
    document.getElementById("stylePassportPreferences").value = entry?.preferences || "";
    document.getElementById("stylePassportShare").checked = Boolean(entry?.share_with_shop);
    document.getElementById("stylePassportReferencePhotos").value = "";
    document.getElementById("stylePassportResultPhotos").value = "";
    document.getElementById("stylePassportFormResult").textContent = "";
    fillStyleAppointmentSelect(appointmentId || entry?.appointment_id || "", entry);
    stylePassportForm.hidden = false;
    stylePassportForm.scrollIntoView({ behavior: "smooth", block: "center" });
    (entry ? document.getElementById("stylePassportHaircut") : document.getElementById("stylePassportAppointment")).focus();
  }

  function renderStylePassport(items) {
    stylePassportItems = Array.isArray(items) ? items : [];
    stylePassportList.replaceChildren();
    if (!stylePassportItems.length) {
      const empty = document.createElement("p");
      empty.textContent = "Tus cortes guardados aparecerán aquí después de cada visita completada.";
      stylePassportList.append(empty);
    }
    stylePassportItems.forEach((entry) => {
      const card = document.createElement("article");
      card.className = "style-passport-card";
      const title = document.createElement("h3");
      title.textContent = entry.haircut_type || entry.service || "Corte guardado";
      const meta = document.createElement("p");
      meta.className = "style-card-meta";
      meta.textContent = `${entry.barbershop_name} · ${entry.service} · ${formatAppointmentDate(entry.service_date)}`;
      const facts = document.createElement("dl");
      facts.className = "style-card-facts";
      [
        ["Fade", entry.fade_style], ["Largo superior", entry.top_length],
        ["Lados", entry.sides_length], ["Barba", entry.beard_style],
        ["Productos", entry.products_used], ["Preferencias", entry.preferences],
        ["Nota del barbero", entry.barber_notes], ["Recomendación", entry.recommendations],
      ].map(([label, value]) => styleField(label, value)).filter(Boolean)
        .forEach((row) => facts.append(row));
      const consent = document.createElement("p");
      consent.className = "style-card-meta";
      consent.textContent = entry.share_with_shop
        ? "Compartido con el equipo de esta barbería"
        : "Privado: solo tú puedes verlo";
      card.append(title, meta, facts, consent);

      if ((entry.photos || []).length) {
        const photoList = document.createElement("div");
        photoList.className = "style-photo-list";
        entry.photos.forEach((photo) => {
          const view = document.createElement("button");
          view.type = "button";
          view.dataset.action = "view-style-photo";
          view.dataset.photoId = String(photo.id);
          view.dataset.entryId = String(entry.id);
          view.textContent = photo.kind === "reference" ? "Ver referencia" : "Ver resultado";
          const remove = document.createElement("button");
          remove.type = "button";
          remove.dataset.action = "delete-style-photo";
          remove.dataset.photoId = String(photo.id);
          remove.dataset.entryId = String(entry.id);
          remove.textContent = photo.kind === "reference" ? "Quitar referencia" : "Quitar resultado";
          photoList.append(view, remove);
        });
        card.append(photoList);
      }

      const actions = document.createElement("div");
      actions.className = "style-card-actions";
      const edit = document.createElement("button");
      edit.type = "button";
      edit.className = "button-secondary";
      edit.dataset.action = "edit-style-passport";
      edit.dataset.entryId = String(entry.id);
      edit.textContent = "Editar registro";
      actions.append(edit);
      if (entry.barbershop_slug && entry.service_id) {
        const repeat = document.createElement("a");
        repeat.className = "button-secondary";
        const params = new URLSearchParams({
          shop: entry.barbershop_slug,
          service_id: String(entry.service_id),
        });
        if (entry.barber_id) params.set("barber_id", String(entry.barber_id));
        repeat.href = `/client.html?${params.toString()}`;
        repeat.textContent = "Repetir este corte";
        actions.append(repeat);
      }
      card.append(actions);
      const deleteDetails = document.createElement("details");
      deleteDetails.className = "style-card-delete";
      const summary = document.createElement("summary");
      summary.textContent = "Eliminar este registro";
      const removeEntry = document.createElement("button");
      removeEntry.type = "button";
      removeEntry.dataset.action = "delete-style-passport";
      removeEntry.dataset.entryId = String(entry.id);
      removeEntry.textContent = "Eliminar el registro y sus fotos";
      deleteDetails.append(summary, removeEntry);
      card.append(deleteDetails);
      stylePassportList.append(card);
    });
    const available = appointmentItems.some((item) => item.status === "completed" &&
      !stylePassportItems.some((entry) => Number(entry.appointment_id) === Number(item.appointment_id)));
    document.getElementById("newStylePassportButton").disabled = !available;
    applyStyleEntryButtons();
  }

  async function loadStylePassport() {
    const data = await readJson(await window.KingFlowAuth.fetch(`${api}/style-passport`));
    renderStylePassport(data.items || []);
  }

  async function uploadStylePhotos(entryId) {
    for (const [inputId, kind] of [
      ["stylePassportReferencePhotos", "reference"],
      ["stylePassportResultPhotos", "result"],
    ]) {
      const input = document.getElementById(inputId);
      const files = [...input.files];
      if (files.length > 2) throw new Error("Puedes subir hasta dos fotos por categoría.");
      for (const file of files) {
        const form = new FormData();
        form.append("file", file);
        const result = await readJson(await window.KingFlowAuth.fetch(
          `${api}/style-passport/${encodeURIComponent(entryId)}/photos?photo_kind=${kind}`,
          { method: "POST", body: form },
        ));
        if (!result.id) throw new Error("No se pudo guardar una de las fotografías.");
      }
      input.value = "";
    }
  }

  async function showStylePhoto(entryId, photoId) {
    const response = await window.KingFlowAuth.fetch(
      `${api}/style-passport/${encodeURIComponent(entryId)}/photos/${encodeURIComponent(photoId)}`,
    );
    if (!response.ok) throw new Error("No se pudo abrir la foto privada.");
    const blob = await response.blob();
    if (stylePhotoObjectUrl) URL.revokeObjectURL(stylePhotoObjectUrl);
    stylePhotoObjectUrl = URL.createObjectURL(blob);
    document.getElementById("stylePassportPhotoPreview").src = stylePhotoObjectUrl;
    document.getElementById("stylePassportPhotoDialog").showModal();
  }

  async function loadFavorites() {
    const data = await readJson(await window.KingFlowAuth.fetch(`${api}/favorites`));
    favoritesList.replaceChildren();
    if (!(data.items || []).length) {
      const empty = document.createElement("p");
      empty.textContent = "Aún no guardas servicios ni barberos. Puedes hacerlo desde la página de cada barbería.";
      favoritesList.append(empty);
      return;
    }
    data.items.forEach((item) => {
      const card = document.createElement("article");
      card.className = "favorite-card";
      const title = document.createElement("h3");
      title.textContent = item.name;
      const imageUrl = trustedFavoriteImage(item.image_url);
      if (imageUrl) {
        const image = document.createElement("img");
        image.className = "favorite-image";
        image.src = imageUrl;
        image.alt = item.name;
        image.loading = "lazy";
        card.append(image);
      }
      const description = document.createElement("p");
      const targetLabel = { service: "Servicio", barber: "Barbero", barbershop: "Barbería" }[item.target_type] || "Favorito";
      description.textContent = item.target_type === "barbershop" ? targetLabel : `${targetLabel} · ${item.barbershop}`;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "account-action";
      remove.textContent = "Quitar de favoritos";
      remove.addEventListener("click", async () => {
        remove.disabled = true;
        try {
          await readJson(await window.KingFlowAuth.fetch(`${api}/favorites/${encodeURIComponent(item.favorite_id)}`, { method: "DELETE" }));
          message("Se quitó de tus favoritos.");
          await loadFavorites();
        } catch (error) { message(error.message); remove.disabled = false; }
      });
      const visit = document.createElement("a");
      visit.className = "button-secondary favorite-visit";
      visit.href = `/client.html?shop=${encodeURIComponent(item.barbershop_slug)}`;
      visit.textContent = item.target_type === "barbershop" ? "Volver a esta barbería" : "Ver barbería";
      card.append(title, description, remove, visit);
      favoritesList.append(card);
    });
  }

  appointmentsList.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    if (button.dataset.action === "add-style-passport") {
      openStylePassportForm(button.dataset.appointmentId);
      return;
    }
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

  document.getElementById("newStylePassportButton").addEventListener("click", () => {
    openStylePassportForm();
  });
  document.getElementById("cancelStylePassportEdit").addEventListener("click", clearStylePassportForm);
  stylePassportForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = stylePassportForm.querySelector('button[type="submit"]');
    const result = document.getElementById("stylePassportFormResult");
    const entryIdField = document.getElementById("stylePassportEntryId");
    const entryId = entryIdField.value;
    const appointmentId = document.getElementById("stylePassportAppointment").value;
    if (!entryId && !appointmentId) {
      result.textContent = "Selecciona una visita completada para guardar el corte.";
      return;
    }
    const payload = {
      haircut_type: document.getElementById("stylePassportHaircut").value.trim() || null,
      fade_style: document.getElementById("stylePassportFade").value.trim() || null,
      top_length: document.getElementById("stylePassportTop").value.trim() || null,
      sides_length: document.getElementById("stylePassportSides").value.trim() || null,
      beard_style: document.getElementById("stylePassportBeard").value.trim() || null,
      products_used: document.getElementById("stylePassportProducts").value.trim() || null,
      preferences: document.getElementById("stylePassportPreferences").value.trim() || null,
      share_with_shop: document.getElementById("stylePassportShare").checked,
    };
    if (!entryId) payload.appointment_id = Number(appointmentId);
    button.disabled = true;
    result.textContent = "Guardando tu Style Passport…";
    try {
      const saved = await readJson(await window.KingFlowAuth.fetch(
        entryId ? `${api}/style-passport/${encodeURIComponent(entryId)}` : `${api}/style-passport`,
        {
          method: entryId ? "PATCH" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      ));
      entryIdField.value = String(saved.id);
      await uploadStylePhotos(saved.id);
      await loadStylePassport();
      clearStylePassportForm();
      message("Tu corte quedó guardado en el Style Passport.");
    } catch (error) {
      result.textContent = `${error.message} Si el registro ya se guardó, puedes editarlo para completar las fotos.`;
    } finally {
      button.disabled = false;
    }
  });

  stylePassportList.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const entryId = Number(button.dataset.entryId);
    const entry = stylePassportItems.find((item) => Number(item.id) === entryId);
    if (button.dataset.action === "edit-style-passport") {
      if (entry) openStylePassportForm(entry.appointment_id, entry);
      return;
    }
    button.disabled = true;
    try {
      if (button.dataset.action === "view-style-photo") {
        await showStylePhoto(entryId, Number(button.dataset.photoId));
        return;
      }
      if (button.dataset.action === "delete-style-photo") {
        await readJson(await window.KingFlowAuth.fetch(
          `${api}/style-passport/${entryId}/photos/${Number(button.dataset.photoId)}`,
          { method: "DELETE" },
        ));
        message("La foto privada se eliminó.");
      } else if (button.dataset.action === "delete-style-passport") {
        await readJson(await window.KingFlowAuth.fetch(
          `${api}/style-passport/${entryId}`,
          { method: "DELETE" },
        ));
        clearStylePassportForm();
        message("Se eliminaron el registro y sus fotos privadas.");
      }
      await loadStylePassport();
    } catch (error) {
      message(error.message);
    } finally {
      button.disabled = false;
    }
  });

  document.getElementById("closeStylePassportPhoto").addEventListener("click", () => {
    document.getElementById("stylePassportPhotoDialog").close();
  });
  document.getElementById("stylePassportPhotoDialog").addEventListener("close", () => {
    const preview = document.getElementById("stylePassportPhotoPreview");
    preview.removeAttribute("src");
    if (stylePhotoObjectUrl) URL.revokeObjectURL(stylePhotoObjectUrl);
    stylePhotoObjectUrl = null;
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
    try { await loadStylePassport(); } catch (error) { message(error.message); }
    try { await loadFavorites(); } catch (error) { message(error.message); }
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
      await loadStylePassport();
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

  document.getElementById("exportDataButton").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      const data = await readJson(await window.KingFlowAuth.fetch(`${api}/export`));
      const file = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const objectUrl = URL.createObjectURL(file);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = "kingflow-mis-datos.json";
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      message("Tu archivo con los datos de tu cuenta está listo.");
    } catch (error) {
      message(error.message);
    } finally {
      button.disabled = false;
    }
  });

  document.getElementById("logoutButton").addEventListener("click", async () => {
    await window.KingFlowAuth.logout();
    document.getElementById("stylePassportPhotoDialog").close();
    stylePassportItems = [];
    appointmentItems = [];
    appointmentsList.replaceChildren();
    favoritesList.replaceChildren();
    stylePassportList.replaceChildren();
    document.getElementById("profileEmail").value = "";
    document.getElementById("profileFirstName").value = "";
    document.getElementById("profileLastName").value = "";
    document.getElementById("profilePhone").value = "";
    clearStylePassportForm();
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
