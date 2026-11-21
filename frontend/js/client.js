const APP_CONFIG = window.KINGFLOW_CONFIG || {};
const API_ROOT = (APP_CONFIG.apiBaseUrl || window.location.origin).replace(/\/$/, '');
const API_BASE = `${API_ROOT}/api/v1`;
let shopCurrency = 'USD';
let shopTimezone = 'UTC';
let availableSlots = [];
let serviceCatalog = [];
let slotsRequestSequence = 0;

function q(name) {
  return new URLSearchParams(window.location.search).get(name);
}

const shopSlug = q('shop');

function trustedTrackingUrl(value) {
  try {
    const url = new URL(value, window.location.origin);
    const allowedOrigins = new Set([window.location.origin, new URL(API_ROOT).origin]);
    if (!allowedOrigins.has(url.origin) || !['http:', 'https:'].includes(url.protocol) ||
        url.username || url.password || url.pathname !== '/client.html' ||
        url.searchParams.get('shop') !== shopSlug || !url.searchParams.get('track_token') ||
        url.hash) {
      return null;
    }
    return url;
  } catch (_) {
    return null;
  }
}

const shopNameEl = document.getElementById('shopName');
const serviceSelect = document.getElementById('serviceSelect');
const barberSelect = document.getElementById('barberSelect');
const scheduledTimeSelect = document.getElementById('scheduledTime');
const bookBtn = document.getElementById('bookBtn');
const bookResult = document.getElementById('bookResult');
const trackBtn = document.getElementById('trackBtn');
const trackList = document.getElementById('trackList');
const supportBtn = document.getElementById('supportBtn');

const showBookBtn = document.getElementById('showBookBtn');
const showTrackBtn = document.getElementById('showTrackBtn');
const showSupportBtn = document.getElementById('showSupportBtn');

const bookSection = document.getElementById('bookSection');
const trackSection = document.getElementById('trackSection');
const supportSection = document.getElementById('supportSection');

function showPanel(panel) {
  if (bookSection) bookSection.style.display = panel === 'book' ? 'block' : 'none';
  if (trackSection) trackSection.style.display = panel === 'track' ? 'block' : 'none';
  if (supportSection) supportSection.style.display = panel === 'support' ? 'block' : 'none';

  const map = {
    book: showBookBtn,
    track: showTrackBtn,
    support: showSupportBtn,
  };

  [showBookBtn, showTrackBtn, showSupportBtn].forEach((btn) => {
    if (btn) btn.classList.remove('active');
  });

  if (map[panel]) {
    map[panel].classList.add('active');
  }
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
}

function formatMoney(cents) {
  try {
    return new Intl.NumberFormat('es-DO', { style: 'currency', currency: shopCurrency }).format((Number(cents) || 0) / 100);
  } catch (_) {
    return `${shopCurrency} ${((Number(cents) || 0) / 100).toFixed(2)}`;
  }
}

async function loadShop() {
  if (!shopSlug) {
    shopNameEl.textContent = '❌ Falta identificar la barbería';
    return;
  }
  const retryButton = document.getElementById('retryShopBtn');
  if (retryButton) retryButton.disabled = true;
  try {
    const res = await fetch(`${API_BASE}/public/${shopSlug}`);
    if (!res.ok) {
      shopNameEl.textContent = '❌ Barbería no disponible';
      if (retryButton) retryButton.hidden = false;
      return;
    }

    const shop = await res.json();
    shopCurrency = shop.currency || 'USD';
    shopTimezone = shop.timezone || 'UTC';
    shopNameEl.textContent = `💈 ${shop.name}`;
    document.title = `${shop.name} - Cliente`;
    if (retryButton) retryButton.hidden = true;

    const brandColorPattern = /^#[0-9a-f]{6}$/i;
    if (brandColorPattern.test(shop.primary_color || '')) {
      document.documentElement.style.setProperty('--brand-primary', shop.primary_color);
    }
    if (brandColorPattern.test(shop.secondary_color || '')) {
      document.documentElement.style.setProperty('--brand-secondary', shop.secondary_color);
    }
    if (shop.logo_url) {
      try {
        const logoUrl = new URL(shop.logo_url, API_ROOT);
        if (logoUrl.origin === new URL(API_ROOT).origin && ['http:', 'https:'].includes(logoUrl.protocol)) {
          const logo = document.getElementById('shopLogo');
          logo.src = logoUrl.href;
          logo.alt = `Logo de ${shop.name}`;
          logo.referrerPolicy = 'no-referrer';
          logo.hidden = false;
        }
      } catch (_) {
        // Ignore an invalid legacy logo URL and keep the booking page usable.
      }
    }

    const sres = await fetch(`${API_BASE}/public/${shopSlug}/services`);
    if (!sres.ok) throw new Error('No se pudieron cargar los servicios.');
    serviceCatalog = await sres.json();
    if (!Array.isArray(serviceCatalog)) throw new Error('Respuesta de servicios inválida.');

    serviceSelect.innerHTML = serviceCatalog
      .map(s => `<option value="${Number(s.id)}">${escapeHtml(s.name)} - ${formatMoney(s.price_cents)} (${Number(s.duration_minutes)} min)</option>`)
      .join('');

    await loadSlots(selectedServiceDuration());
  } catch (_) {
    shopNameEl.textContent = 'No se pudo cargar la barbería. Comprueba tu conexión e inténtalo de nuevo.';
    if (retryButton) retryButton.hidden = false;
  } finally {
    if (retryButton) retryButton.disabled = false;
  }
}

function selectedServiceDuration() {
  const service = serviceCatalog.find(item => Number(item.id) === Number(serviceSelect.value));
  const duration = Number(service?.duration_minutes);
  return Number.isInteger(duration) && duration > 0 ? duration : null;
}

async function fetchSlots(durationMinutes) {
  const url = new URL(`${API_BASE}/public/${shopSlug}/slots`);
  if (Number.isInteger(Number(durationMinutes)) && Number(durationMinutes) > 0) {
    url.searchParams.set('duration_minutes', String(Number(durationMinutes)));
  }
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    const slots = await res.json();
    return Array.isArray(slots) ? slots : null;
  } catch (_) {
    return null;
  }
}

async function loadSlots(durationMinutes = selectedServiceDuration()) {
  const requestSequence = ++slotsRequestSequence;
  const slots = await fetchSlots(durationMinutes);
  if (requestSequence !== slotsRequestSequence) return;
  if (!Array.isArray(slots)) {
    availableSlots = [];
    if (barberSelect) barberSelect.innerHTML = '<option value="">Cualquier barbero</option>';
    scheduledTimeSelect.innerHTML = '<option value="">No se pudo consultar la disponibilidad</option>';
    return;
  }
  availableSlots = slots;

  const selectedBarberId = barberSelect?.value || '';
  const barbers = new Map(availableSlots.map(slot => [Number(slot.barber_id), slot.barber_name]));
  if (barberSelect) {
    barberSelect.innerHTML = '<option value="">Cualquier barbero</option>' +
      [...barbers.entries()].map(([id, name]) => `<option value="${id}">${escapeHtml(name)}</option>`).join('');
    if (barbers.has(Number(selectedBarberId))) barberSelect.value = selectedBarberId;
  }

  renderAvailableSlots();
}

function renderAvailableSlots() {
  const barberId = barberSelect?.value || '';
  const slots = availableSlots.filter(slot => !barberId || Number(slot.barber_id) === Number(barberId));

  if (!slots.length) {
    scheduledTimeSelect.innerHTML = '<option value="">Sin turnos disponibles</option>';
    return;
  }

  scheduledTimeSelect.innerHTML = slots.map(s => {
    const label = `${new Date(s.slot_start).toLocaleString('es-DO', { timeZone: shopTimezone })} · ${escapeHtml(s.barber_name)}`;
    return `<option value="${Number(s.availability_id)}">${label}</option>`;
  }).join('');
}

serviceSelect.addEventListener('change', () => loadSlots(selectedServiceDuration()));
barberSelect?.addEventListener('change', renderAvailableSlots);
document.getElementById('refreshSlotsBtn')?.addEventListener('click', async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    await loadSlots(selectedServiceDuration());
  } finally {
    button.disabled = false;
  }
});
document.getElementById('retryShopBtn')?.addEventListener('click', loadShop);

async function bookAppointment() {
  const client_name = document.getElementById('clientName').value.trim();
  const phone = document.getElementById('clientPhone').value.trim();
  const service_id = Number(serviceSelect.value);
  const slot = availableSlots.find(item => Number(item.availability_id) === Number(scheduledTimeSelect.value));
  const dt = slot?.slot_start;
  const notes = document.getElementById('clientNotes').value.trim();

  if (!client_name || !phone || !service_id || !dt) {
    bookResult.textContent = 'Completa todos los campos requeridos.';
    return;
  }

  bookResult.textContent = 'Agendando...';

  const payload = {
    client_name,
    phone,
    service_id,
    barber_id: slot.barber_id,
    scheduled_time: dt,
    notes: notes || null,
  };

  bookBtn.disabled = true;
  try {
    const res = await fetch(`${API_BASE}/public/${shopSlug}/appointments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    if (!res.ok) {
      bookResult.textContent = data.detail || 'No fue posible agendar la cita.';
      return;
    }

    bookResult.replaceChildren();
    bookResult.append(document.createTextNode(`✅ Cita creada (ID ${Number(data.appointment_id)}). `));
    const link = document.createElement('a');
    const trackingUrl = trustedTrackingUrl(data.tracking_link);
    if (!trackingUrl) {
      bookResult.textContent = '✅ Cita creada. No fue posible abrir el enlace de seguimiento.';
      return;
    }
    link.href = trackingUrl.href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Abrir seguimiento privado';
    bookResult.append(link);
    await loadSlots();
  } catch (_) {
    bookResult.textContent = 'No pudimos confirmar la respuesta. Revisa tus citas con el código de seguimiento antes de volver a reservar.';
  } finally {
    bookBtn.disabled = false;
  }
}

function statusLabel(status) {
  const map = {
    pending: 'Pendiente',
    confirmed: 'Confirmada',
    in_progress: 'En proceso',
    completed: 'Completada',
    cancelled: 'Cancelada',
    no_show: 'No asistió',
  };
  return map[status] || status;
}

async function trackAppointments() {
  const token = document.getElementById('trackToken').value.trim();

  if (!token) {
    trackList.textContent = 'Ingresa el código privado que recibiste al reservar.';
    return;
  }

  trackList.textContent = 'Consultando...';
  trackBtn.disabled = true;
  try {
    const res = await fetch(`${API_BASE}/public/${shopSlug}/track`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });

    const data = await res.json();
    if (!res.ok) {
      trackList.textContent = data.detail || 'Error de consulta.';
      return;
    }

    if (!data.items || data.items.length === 0) {
      trackList.textContent = 'No se encontró una cita con ese código de seguimiento.';
      return;
    }

    const slotResults = new Map();
    const cards = await Promise.all(data.items.map(async (item) => {
      const d = new Date(item.scheduled_time).toLocaleString('es-DO', { timeZone: shopTimezone });
      const cancelButton = ['pending', 'confirmed'].includes(item.status)
        ? `<button class="secondary cancel-booking" type="button" data-token="${escapeHtml(token)}">Cancelar cita</button>`
        : '';
      const canReschedule = ['pending', 'confirmed'].includes(item.status);
      const duration = Number(item.estimated_duration);
      let availableForService = [];
      if (canReschedule) {
        if (!slotResults.has(duration)) slotResults.set(duration, fetchSlots(duration));
        availableForService = await slotResults.get(duration) || [];
      }
      const rescheduleControls = ['pending', 'confirmed'].includes(item.status) && availableForService.length
        ? `<label class="field">Nuevo turno<select class="reschedule-slot" data-token="${escapeHtml(token)}">${availableForService.map(slot => {
            const label = `${new Date(slot.slot_start).toLocaleString('es-DO', { timeZone: shopTimezone })} · ${escapeHtml(slot.barber_name)}`;
            return `<option value="${Number(slot.availability_id)}">${label}</option>`;
          }).join('')}</select></label><button class="secondary reschedule-booking" type="button" data-token="${escapeHtml(token)}">Reprogramar cita</button>`
        : '';
      return `<div class="item"><strong>ID ${Number(item.appointment_id)}</strong> • ${escapeHtml(statusLabel(item.status))}<br>${escapeHtml(item.service_type)}<br>${escapeHtml(d)}${item.barber_name ? `<br>Barbero: ${escapeHtml(item.barber_name)}` : ''}<br>${rescheduleControls}<br>${cancelButton}</div>`;
    }));
    trackList.innerHTML = cards.join('');
  } catch (_) {
    trackList.textContent = 'No se pudieron consultar tus citas. Comprueba tu conexión e inténtalo de nuevo.';
  } finally {
    trackBtn.disabled = false;
  }
}

trackList.addEventListener('click', async (event) => {
  const rescheduleButton = event.target.closest('.reschedule-booking');
  if (rescheduleButton) {
    const card = rescheduleButton.closest('.item');
    const availabilityId = Number(card?.querySelector('.reschedule-slot')?.value);
    if (!availabilityId) return;
    rescheduleButton.disabled = true;
    try {
      const response = await fetch(`${API_BASE}/public/${shopSlug}/appointments/reschedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: rescheduleButton.dataset.token, availability_id: availabilityId }),
      });
      const data = await response.json();
      if (!response.ok) {
        rescheduleButton.disabled = false;
        showToast(data.detail || 'No se pudo reprogramar la cita.');
        return;
      }
    } catch (_) {
      rescheduleButton.disabled = false;
      showToast('No pudimos confirmar el cambio. Actualiza el seguimiento antes de intentarlo otra vez.');
      return;
    }
    await loadSlots();
    await trackAppointments();
    return;
  }
  const button = event.target.closest('.cancel-booking');
  if (!button || !await showConfirmation('¿Quieres cancelar esta cita?', {
    title: 'Cancelar cita', confirmLabel: 'Cancelar cita', danger: true,
  })) return;
  button.disabled = true;
  try {
    const response = await fetch(`${API_BASE}/public/${shopSlug}/appointments/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: button.dataset.token }),
    });
    const data = await response.json();
    if (!response.ok) {
      button.disabled = false;
      showToast(data.detail || 'No se pudo cancelar la cita.');
      return;
    }
  } catch (_) {
    button.disabled = false;
    showToast('No pudimos confirmar la cancelación. Actualiza el seguimiento antes de intentarlo otra vez.');
    return;
  }
  await loadSlots();
  await trackAppointments();
});

async function sendSupport() {
  const name = document.getElementById('supportName').value.trim();
  const email = document.getElementById('supportEmail').value.trim();
  const phone = document.getElementById('supportPhone').value.trim();
  const message = document.getElementById('supportMessage').value.trim();
  const result = document.getElementById('supportResult');

  if (!name || !message) {
    result.textContent = 'Nombre y mensaje son requeridos.';
    return;
  }

  result.textContent = 'Enviando...';
  supportBtn.disabled = true;
  try {
    const res = await fetch(`${API_BASE}/support/contact`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email: email || null, phone: phone || null, message, barbershop_slug: shopSlug }),
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      result.textContent = data.detail || 'No se pudo enviar soporte.';
      return;
    }

    result.textContent = data.notification_sent
      ? `✅ Solicitud #${Number(data.ticket_id)} recibida; se envió un aviso al equipo.`
      : `✅ Solicitud #${Number(data.ticket_id)} recibida y guardada. El aviso por correo no está disponible ahora.`;
  } catch (_) {
    result.textContent = 'No pudimos confirmar el envío. Espera un momento y consulta con soporte antes de enviar otra solicitud.';
  } finally {
    supportBtn.disabled = false;
  }
}

bookBtn.addEventListener('click', bookAppointment);
trackBtn.addEventListener('click', trackAppointments);
if (supportBtn) supportBtn.addEventListener('click', sendSupport);

if (showBookBtn) showBookBtn.addEventListener('click', () => showPanel('book'));
if (showTrackBtn) showTrackBtn.addEventListener('click', () => showPanel('track'));
if (showSupportBtn) showSupportBtn.addEventListener('click', () => showPanel('support'));

window.addEventListener('DOMContentLoaded', async () => {
  showPanel('book');
  await loadShop();

  const trackingToken = q('track_token');
  if (trackingToken) document.getElementById('trackToken').value = trackingToken;

  if (trackingToken) {
    showPanel('track');
    await trackAppointments();
  }
});
