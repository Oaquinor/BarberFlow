const APP_CONFIG = window.KINGFLOW_CONFIG || {};
const API_ROOT = (APP_CONFIG.apiBaseUrl || window.location.origin).replace(/\/$/, '');
const API_BASE = `${API_ROOT}/api/v1`;
let shopCurrency = 'USD';
let shopTimezone = 'UTC';
let availableSlots = [];
let serviceCatalog = [];
let publicFavorites = new Map();
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
    return `${escapeHtml(shopCurrency)} ${((Number(cents) || 0) / 100).toFixed(2)}`;
  }
}

function trustedShopImage(value) {
  if (typeof value !== 'string' || !value.trim()) return '';
  try {
    const url = new URL(value, API_ROOT);
    return url.origin === new URL(API_ROOT).origin && ['http:', 'https:'].includes(url.protocol) &&
      !url.username && !url.password ? url.href : '';
  } catch (_) {
    return '';
  }
}

function renderServiceCards() {
  const container = document.getElementById('publicServices');
  if (!container) return;
  if (!serviceCatalog.length) {
    container.textContent = 'Esta barbería aún no ha publicado servicios.';
    return;
  }
  container.replaceChildren();
  serviceCatalog.forEach((service) => {
    const card = document.createElement('article');
    card.className = 'service-card';
    card.dataset.serviceId = String(Number(service.id));
    const selectButton = document.createElement('button');
    selectButton.type = 'button';
    selectButton.className = 'service-select-trigger';
    selectButton.setAttribute('aria-label', `Elegir ${service.name}`);
    const category = document.createElement('span');
    category.className = 'service-category';
    category.textContent = service.category || 'Servicio';
    const title = document.createElement('h3');
    title.textContent = service.name;
    const description = document.createElement('p');
    description.textContent = service.description || 'Un servicio preparado con atención al detalle.';
    const bottom = document.createElement('span');
    bottom.className = 'service-bottom';
    const price = document.createElement('strong');
    price.textContent = formatMoney(service.price_cents);
    const duration = document.createElement('span');
    duration.textContent = `${Number(service.duration_minutes)} min`;
    bottom.append(price, duration);
    const imageUrl = trustedShopImage(service.image_url);
    if (imageUrl) {
      const image = document.createElement('img');
      image.src = imageUrl;
      image.alt = '';
      image.loading = 'lazy';
      image.className = 'service-photo';
      selectButton.append(image);
    } else {
      const visual = document.createElement('span');
      visual.className = 'service-visual';
      visual.setAttribute('aria-hidden', 'true');
      visual.innerHTML = '<svg viewBox="0 0 48 48"><path d="M9 9l30 30M39 9 9 39"/><circle cx="10" cy="10" r="5"/><circle cx="38" cy="38" r="5"/><path d="m28 12 8 8m-13 13 8 8"/></svg><span>ELIGE TU ESTILO</span>';
      selectButton.append(visual);
    }
    selectButton.append(category, title, description, bottom);
    const favorite = favoriteButton('service', service.id, service.name);
    card.append(favorite, selectButton);
    selectButton.addEventListener('click', () => {
      serviceSelect.value = String(Number(service.id));
      serviceSelect.dispatchEvent(new Event('change', { bubbles: true }));
      container.querySelectorAll('.service-card').forEach((item) => item.classList.remove('selected'));
      card.classList.add('selected');
      document.getElementById('reserva')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    container.append(card);
  });
}

function renderPublicTeam(team) {
  const container = document.getElementById('publicTeam');
  if (!container) return;
  const members = Array.isArray(team) ? team : [];
  container.replaceChildren();
  if (!members.length) {
    const empty = document.createElement('article');
    empty.className = 'team-empty';
    empty.innerHTML = '<span class="team-empty-mark" aria-hidden="true">KF</span><div><strong>Atención personal en cada cita</strong><p>El equipo te ayudará a elegir el estilo que mejor se adapte a ti.</p></div>';
    container.append(empty);
    return;
  }
  members.forEach((member) => {
    const card = document.createElement('article');
    card.className = 'team-card';
    const avatarUrl = trustedShopImage(member.avatar_url);
    if (avatarUrl) {
      const avatar = document.createElement('img');
      avatar.className = 'team-avatar';
      avatar.src = avatarUrl;
      avatar.alt = `Foto de ${member.name}`;
      avatar.loading = 'lazy';
      card.append(avatar);
    } else {
      const monogram = document.createElement('span');
      monogram.className = 'team-avatar team-monogram';
      monogram.setAttribute('aria-hidden', 'true');
      monogram.textContent = String(member.name || 'KF').split(/\s+/).slice(0, 2).map(part => part[0]).join('').toUpperCase();
      card.append(monogram);
    }
    const name = document.createElement('h3');
    name.textContent = member.name || 'Barbero';
    const bio = document.createElement('p');
    bio.textContent = member.bio || 'Especialista en cortes y cuidado personal.';
    const action = document.createElement('button');
    action.type = 'button';
    action.className = 'team-book-button';
    action.dataset.barberId = String(Number(member.id));
    action.textContent = 'Reservar con esta persona';
    card.append(name, bio, action, favoriteButton('barber', member.id, member.name || 'Barbero'));
    container.append(card);
  });
}

function favoriteButton(type, id, label) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'public-favorite-button';
  button.dataset.favoriteType = type;
  button.dataset.favoriteId = String(Number(id));
  button.setAttribute('aria-label', `Guardar ${label} en favoritos`);
  button.setAttribute('aria-pressed', publicFavorites.has(`${type}:${Number(id)}`) ? 'true' : 'false');
  button.textContent = publicFavorites.has(`${type}:${Number(id)}`) ? '♥ Guardado' : '♡ Guardar';
  return button;
}

async function loadPublicFavorites() {
  if (!shopSlug || !sessionStorage.getItem('token')) return;
  try {
    const response = await window.KingFlowAuth.fetch(`${API_BASE}/client-account/favorites`);
    if (!response.ok) return;
    const data = await response.json();
    publicFavorites = new Map((data.items || []).filter(item => item.barbershop_slug === shopSlug)
      .map(item => [`${item.target_type}:${Number(item.target_id)}`, Number(item.favorite_id)]));
    renderServiceCards();
    const shop = window.__kingflowLoadedShop;
    if (shop) renderPublicTeam(shop.team);
  } catch (_) { /* Favorites are optional; keep public booking available. */ }
}

document.getElementById('publicServices')?.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-favorite-type]');
  if (button) await togglePublicFavorite(button);
});
document.getElementById('publicTeam')?.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-favorite-type]');
  if (button) { event.stopPropagation(); await togglePublicFavorite(button); }
});

async function togglePublicFavorite(button) {
  if (!sessionStorage.getItem('token')) {
    bookResult.textContent = 'Inicia sesión para guardar favoritos.';
    const link = document.createElement('a');
    link.href = '/client-account.html';
    link.textContent = ' Abrir mi cuenta';
    bookResult.append(link);
    return;
  }
  button.disabled = true;
  const type = button.dataset.favoriteType;
  const id = Number(button.dataset.favoriteId);
  const key = `${type}:${id}`;
  try {
    if (publicFavorites.has(key)) {
      const response = await window.KingFlowAuth.fetch(`${API_BASE}/client-account/favorites/${publicFavorites.get(key)}`, { method: 'DELETE' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'No se pudo quitar el favorito.');
      publicFavorites.delete(key);
    } else {
      const response = await window.KingFlowAuth.fetch(`${API_BASE}/client-account/favorites`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ barbershop_slug: shopSlug, target_type: type, target_id: id }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'No se pudo guardar el favorito.');
      publicFavorites.set(key, Number(data.favorite_id));
    }
    if (type === 'service') renderServiceCards();
    else renderPublicTeam(window.__kingflowLoadedShop?.team);
    bookResult.textContent = publicFavorites.has(key) ? 'Guardado en tus favoritos.' : 'Eliminado de tus favoritos.';
  } catch (error) { bookResult.textContent = error.message; }
  finally { button.disabled = false; }
}

function renderPublicGallery(images) {
  const section = document.getElementById('galeria');
  const container = document.getElementById('publicGallery');
  const trustedImages = (Array.isArray(images) ? images : []).map(trustedShopImage).filter(Boolean).slice(0, 8);
  if (!section || !container) return;
  section.hidden = false;
  container.replaceChildren();
  container.classList.toggle('gallery-grid-single', trustedImages.length === 1);
  if (!trustedImages.length) {
    const empty = document.createElement('div');
    empty.className = 'gallery-empty';
    empty.innerHTML = '<span class="gallery-empty-mark" aria-hidden="true"><svg viewBox="0 0 48 48"><rect x="5" y="8" width="38" height="32" rx="5"/><circle cx="17" cy="19" r="4"/><path d="m9 35 11-10 7 6 5-5 7 9"/></svg></span><div><p class="eyebrow">PORTAFOLIO</p><h3>El próximo estilo puede ser tuyo.</h3><p>Estamos preparando una selección de nuestros cortes. Mientras tanto, conoce los servicios y cuéntanos qué tienes en mente.</p><a href="#reserva" class="gallery-empty-link">Explorar servicios <span aria-hidden="true">→</span></a></div>';
    container.append(empty);
    return;
  }
  trustedImages.forEach((src, index) => {
    const image = document.createElement('img');
    image.src = src;
    image.alt = `Trabajo de la barbería, imagen ${index + 1}`;
    image.loading = 'lazy';
    image.className = 'gallery-image';
    container.append(image);
  });
}

async function loadShop() {
  if (!shopSlug) {
    shopNameEl.textContent = 'Falta identificar la barbería';
    return;
  }
  const retryButton = document.getElementById('retryShopBtn');
  if (retryButton) retryButton.disabled = true;
  try {
    const res = await fetch(`${API_BASE}/public/${shopSlug}`);
    if (!res.ok) {
      shopNameEl.textContent = 'Barbería no disponible';
      if (retryButton) retryButton.hidden = false;
      return;
    }

    const shop = await res.json();
    window.__kingflowLoadedShop = shop;
    shopCurrency = shop.currency || 'USD';
    shopTimezone = shop.timezone || 'UTC';
    const cancellationHours = Math.max(0, Number(shop.cancellation_window_hours) || 0);
    const cancellationNotice = document.getElementById('cancellationPolicyNotice');
    if (cancellationNotice) cancellationNotice.textContent = cancellationHours
      ? `Puedes cancelar o reprogramar hasta ${cancellationHours} ${cancellationHours === 1 ? 'hora' : 'horas'} antes de tu cita. Después, contacta a la barbería.`
      : 'Puedes cancelar o reprogramar tu cita en cualquier momento antes de que comience.';
    shopNameEl.textContent = shop.name;
    const savedTheme = localStorage.getItem(`kingflow-theme:${shop.slug}`);
    applyPublicTheme(savedTheme || shop.public_theme || 'light');
    const location = [shop.address_line1, [shop.city, shop.state].filter(Boolean).join(', ')].filter(Boolean).join(' · ');
    const address = document.getElementById('shopAddress');
    if (address) address.textContent = location || 'Consulta la ubicación al reservar';
    const hours = document.getElementById('shopHours');
    if (hours) hours.textContent = shop.opening_time && shop.closing_time
      ? `${String(shop.opening_time).slice(0, 5)} — ${String(shop.closing_time).slice(0, 5)}`
      : 'Consulta los horarios disponibles';
    const phone = document.getElementById('shopPhone');
    if (phone && shop.phone) {
      phone.href = `tel:${String(shop.phone).replace(/[^+\d]/g, '')}`;
      phone.textContent = shop.phone;
    }
    const description = document.getElementById('shopDescription');
    if (description && shop.description) description.textContent = shop.description;
    const coverUrl = trustedShopImage(shop.cover_image_url);
    const coverImage = document.getElementById('shopCover');
    if (coverImage && coverUrl) {
      coverImage.src = coverUrl;
      coverImage.alt = `Foto de portada de ${shop.name}`;
    }
    document.title = `${shop.name} - Cliente`;
    if (retryButton) retryButton.hidden = true;

    const brandColorPattern = /^#[0-9a-f]{6}$/i;
    if (brandColorPattern.test(shop.primary_color || '')) {
      document.documentElement.style.setProperty('--brand-primary', shop.primary_color);
    }
    if (brandColorPattern.test(shop.secondary_color || '')) {
      document.documentElement.style.setProperty('--brand-secondary', shop.secondary_color);
    }
    updateBrandForeground(shop.primary_color);
    const logoUrl = trustedShopImage(shop.logo_url);
    if (logoUrl) {
      const logo = document.getElementById('shopLogo');
      if (logo) {
        logo.src = logoUrl;
        logo.alt = `Logo de ${shop.name}`;
        logo.referrerPolicy = 'no-referrer';
        logo.hidden = false;
        if (initial) initial.hidden = true;
      }
    }

    const sres = await fetch(`${API_BASE}/public/${shopSlug}/services`);
    if (!sres.ok) throw new Error('No se pudieron cargar los servicios.');
    serviceCatalog = await sres.json();
    if (!Array.isArray(serviceCatalog)) throw new Error('Respuesta de servicios inválida.');

    serviceSelect.innerHTML = serviceCatalog
      .map(s => `<option value="${Number(s.id)}">${escapeHtml(s.name)} - ${formatMoney(s.price_cents)} (${Number(s.duration_minutes)} min)</option>`)
      .join('');
    renderServiceCards();
    renderPublicGallery(shop.gallery_images);
    renderPublicTeam(shop.team);
    await loadPublicFavorites();
    renderCustomBookingQuestions(shop.booking_questions);
    if (serviceCatalog[0]) {
      document.querySelector(`.service-card[data-service-id="${Number(serviceCatalog[0].id)}"]`)?.classList.add('selected');
    }

    await loadSlots(selectedServiceDuration());
  } catch (_) {
    shopNameEl.textContent = 'No se pudo cargar la barbería. Comprueba tu conexión e inténtalo de nuevo.';
    if (retryButton) retryButton.hidden = false;
  } finally {
    if (retryButton) retryButton.disabled = false;
  }
}

function applyPublicTheme(theme) {
  if (!document.documentElement) return;
  const normalized = theme === 'dark' ? 'dark' : 'light';
  document.documentElement.dataset.theme = normalized;
  const button = document.getElementById('themeToggle');
  if (button) {
    const label = button.querySelector('span');
    if (label) label.textContent = normalized === 'dark' ? 'Tema claro' : 'Tema oscuro';
    button.setAttribute('aria-label', normalized === 'dark' ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro');
  }
}

function renderCustomBookingQuestions(questions) {
  const container = document.getElementById('customBookingQuestions');
  if (!container) return;
  const prompts = (Array.isArray(questions) ? questions : [])
    .filter(question => typeof question === 'string' && question.trim()).slice(0, 5);
  container.replaceChildren();
  container.hidden = prompts.length === 0;
  if (!prompts.length) return;
  const heading = document.createElement('h4');
  heading.textContent = 'Un detalle para preparar tu visita';
  const intro = document.createElement('p');
  intro.textContent = 'La barbería comparte estas preguntas para adaptar mejor tu servicio.';
  container.append(heading, intro);
  prompts.forEach((prompt, index) => {
    const field = document.createElement('label');
    field.className = 'field';
    field.htmlFor = `customBookingQuestion-${index}`;
    field.append(document.createTextNode(prompt));
    const answer = document.createElement('textarea');
    answer.id = `customBookingQuestion-${index}`;
    answer.dataset.bookingQuestion = prompt;
    answer.maxLength = 100;
    answer.placeholder = 'Tu respuesta (opcional)';
    field.append(answer);
    container.append(field);
  });
}

applyPublicTheme('light');

function updateBrandForeground(color) {
  if (!/^#[0-9a-f]{6}$/i.test(color || '')) return;
  const values = color.slice(1).match(/../g).map(value => parseInt(value, 16) / 255);
  const luminance = values.map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4)
    .reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index], 0);
  document.documentElement.style.setProperty('--brand-on-primary', luminance > 0.1791 ? '#161713' : '#ffffff');
}

const themeToggle = document.getElementById('themeToggle');
if (themeToggle?.addEventListener) themeToggle.addEventListener('click', () => {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  applyPublicTheme(next);
  if (shopSlug) localStorage.setItem(`kingflow-theme:${shopSlug}`, next);
});

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
['stylePreference', 'hairLength', 'finishPreference', 'clientNotes'].forEach((id) => {
  document.getElementById(id)?.addEventListener('input', () => {
    const summary = document.getElementById('consultationSummary');
    if (!summary) return;
    const selected = [
      document.getElementById('stylePreference')?.value,
      document.getElementById('hairLength')?.value,
      document.getElementById('finishPreference')?.value,
    ].filter(Boolean);
    summary.textContent = selected.length
      ? `Prepararemos la cita considerando: ${selected.join(' · ')}. Tus respuestas se compartirán con el barbero.`
      : 'Tus preferencias se compartirán con el barbero para preparar la cita.';
  });
});
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
document.getElementById('publicTeam')?.addEventListener('click', (event) => {
  const button = event.target.closest('[data-barber-id]');
  if (!button) return;
  const select = document.getElementById('barberSelect');
  const option = [...(select?.options || [])].find(item => item.value === button.dataset.barberId);
  if (option) {
    select.value = option.value;
    select.dispatchEvent(new Event('change', { bubbles: true }));
  }
  document.getElementById('reserva')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

async function bookAppointment() {
  const client_name = document.getElementById('clientName').value.trim();
  const phone = document.getElementById('clientPhone').value.trim();
  const service_id = Number(serviceSelect.value);
  const slot = availableSlots.find(item => Number(item.availability_id) === Number(scheduledTimeSelect.value));
  const dt = slot?.slot_start;
  const notes = document.getElementById('clientNotes').value.trim();
  const preferences = [
    ['Estilo buscado', document.getElementById('stylePreference')?.value],
    ['Largo actual', document.getElementById('hairLength')?.value],
    ['Acabado preferido', document.getElementById('finishPreference')?.value],
    ['Referencia del cliente', notes],
  ].filter(([, value]) => value).map(([label, value]) => `${label}: ${value}`);
  document.querySelectorAll('[data-booking-question]').forEach((answer) => {
    const value = answer.value.trim();
    if (value) preferences.push(`${answer.dataset.bookingQuestion}: ${value}`);
  });

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
    notes: preferences.length ? preferences.join('\n').slice(0, 1000) : null,
  };

  bookBtn.disabled = true;
  try {
    const res = await window.KingFlowAuth.fetch(`${API_BASE}/public/${shopSlug}/appointments`, {
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
    bookResult.append(document.createTextNode(`Cita creada (ID ${Number(data.appointment_id)}). `));
    if (data.saved_to_account) bookResult.append(document.createTextNode('Guardada en tu cuenta. '));
    const link = document.createElement('a');
    const trackingUrl = trustedTrackingUrl(data.tracking_link);
    if (!trackingUrl) {
      bookResult.textContent = 'Cita creada. No fue posible abrir el enlace de seguimiento.';
      return;
    }
    link.href = trackingUrl.href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Abrir seguimiento privado';
    bookResult.append(link);
    const trackingToken = trackingUrl.searchParams.get('track_token');
    if (trackingToken && !data.saved_to_account) {
      const accountLink = document.createElement('a');
      accountLink.href = `/client-account.html#claim=${encodeURIComponent(trackingToken)}`;
      accountLink.textContent = 'Guardar cita en mi cuenta';
      accountLink.className = 'booking-account-link';
      bookResult.append(document.createTextNode(' · '), accountLink);
    }
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
      ? `Solicitud #${Number(data.ticket_id)} recibida; se envió un aviso al equipo.`
      : `Solicitud #${Number(data.ticket_id)} recibida y guardada. El aviso por correo no está disponible ahora.`;
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

  if (sessionStorage.getItem('token')) {
    try {
      const response = await window.KingFlowAuth.fetch(`${API_BASE}/auth/me`);
      if (response.ok) {
        const user = await response.json();
        if (user.role === 'client' && user.barbershop_id === null && user.is_verified) {
          document.getElementById('clientName').value = user.full_name || '';
          document.getElementById('clientPhone').value = user.phone || '';
        }
      }
    } catch (_) {
      // Keep guest booking available when the optional client session is unavailable.
    }
  }

  const trackingToken = q('track_token');
  if (trackingToken) document.getElementById('trackToken').value = trackingToken;

  if (trackingToken) {
    showPanel('track');
    await trackAppointments();
  }
});
