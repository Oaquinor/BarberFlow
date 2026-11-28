/**
 * KingFlow Barber - Panel Admin
 *
 * Consume los endpoints /api/v1/admin/* (solo accesibles para role=super_admin).
 */

const APP_CONFIG = window.KINGFLOW_CONFIG || {};
const API_ROOT = (APP_CONFIG.apiBaseUrl || window.location.origin).replace(/\/$/, '');

let accessToken = sessionStorage.getItem('token');
let currentTenants = [];
let tenantsRequestSequence = 0;
let supportTicketsOffset = 0;
let latestOpenSupportTicketId = null;
let supportAlertsInitialized = false;
let supportAlertsRefreshing = false;
const SUPPORT_TICKETS_PAGE_SIZE = 50;
let usersOffset = 0;
let usersRequestSequence = 0;
const USERS_PAGE_SIZE = 50;

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[char]);
}

function authHeaders() {
    return { 'Authorization': `Bearer ${accessToken}` };
}

function showGate() {
    document.getElementById('gateContainer').style.display = 'block';
    document.getElementById('adminContainer').style.display = 'none';
}

function showAdmin(email) {
    document.getElementById('gateContainer').style.display = 'none';
    document.getElementById('adminContainer').style.display = 'block';
    document.getElementById('adminEmail').textContent = email || '';
}

async function fetchJson(path, options = {}) {
    const response = await KingFlowAuth.fetch(`${API_ROOT}${path}`, {
        ...options,
        headers: { ...(options.headers || {}), ...authHeaders() },
    });

    if (response.status === 401 || response.status === 403) {
        showGate();
        throw new Error('No autorizado');
    }

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.detail || 'Error de solicitud');
    }
    return data;
}

function renderTenantPill(active) {
    return active
        ? '<span class="pill active">Activo</span>'
        : '<span class="pill inactive">Inactivo</span>';
}

async function loadOverview() {
    const result = document.getElementById('overviewResult');
    if (result) result.textContent = 'Cargando…';
    try {
        const data = await fetchJson('/api/v1/admin/overview');
        document.getElementById('overviewPeriod').textContent = `Desde ${data.period_start} (UTC)`;
        document.getElementById('overviewTenants').textContent = `${data.active_tenant_count} / ${data.tenant_count}`;
        document.getElementById('overviewSubscriptions').textContent = String(data.active_subscription_count);
        document.getElementById('overviewUsers').textContent = String(data.active_user_count);
        document.getElementById('overviewAppointments').textContent = `${data.appointments_created_this_month} / ${data.appointments_completed_this_month}`;
        const revenues = (data.collected_this_month_by_currency || []).map(item =>
            formatAffiliateMoney(item.amount_cents, item.currency)
        );
        document.getElementById('overviewRevenue').textContent = `Cobros de citas registrados este mes: ${revenues.join(' · ') || 'Sin cobros'}`;
        if (result) result.textContent = '';
    } catch (error) {
        if (result) result.textContent = error.message;
    }
}

async function loadPlatformSettings() {
    const result = document.getElementById('platformSettingsResult');
    if (result) result.textContent = 'Cargando…';
    try {
        const data = await fetchJson('/api/v1/admin/settings');
        document.getElementById('registrationsEnabled').checked = data.registrations_enabled;
        document.getElementById('freePeriodDays').value = String(data.free_period_days);
        if (result) result.textContent = '';
    } catch (error) {
        if (result) result.textContent = error.message;
    }
}

document.getElementById('platformSettingsForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const result = document.getElementById('platformSettingsResult');
    const days = Number(document.getElementById('freePeriodDays').value);
    if (!Number.isInteger(days) || days < 1 || days > 365) {
        result.textContent = 'El periodo debe estar entre 1 y 365 días.';
        return;
    }
    result.textContent = 'Guardando…';
    try {
        const data = await fetchJson('/api/v1/admin/settings', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                registrations_enabled: document.getElementById('registrationsEnabled').checked,
                free_period_days: days,
            }),
        });
        document.getElementById('registrationsEnabled').checked = data.registrations_enabled;
        document.getElementById('freePeriodDays').value = String(data.free_period_days);
        result.textContent = 'Configuración de plataforma guardada y auditada.';
    } catch (error) {
        result.textContent = error.message;
    }
});

async function loadTenants() {
    const requestSequence = ++tenantsRequestSequence;
    try {
        const data = await fetchJson('/api/v1/admin/tenants');
        if (requestSequence !== tenantsRequestSequence) return;
        currentTenants = data.items || [];

        const body = document.getElementById('tenantsBody');
        const empty = document.getElementById('tenantsEmpty');
        const filter = document.getElementById('tenantFilter');

        document.getElementById('tenantsCount').textContent = `${currentTenants.length} barbería(s)`;

        if (!currentTenants.length) {
            body.innerHTML = '';
            empty.style.display = 'block';
        } else {
            empty.style.display = 'none';
            body.innerHTML = currentTenants.map((t) => `
                <tr>
                    <td data-label="Barbería">${escapeHtml(t.barbershop_name)} <span class="text-stone-500">(${escapeHtml(t.slug)})</span></td>
                    <td data-label="Owner">${escapeHtml(t.owner_email || '—')}</td>
                    <td data-label="Plan">${t.plan ? `<span class="pill plan">${escapeHtml(t.plan)}</span>` : '—'}</td>
                    <td data-label="Estado suscripción">${escapeHtml(t.subscription_status || '—')}</td>
                    <td data-label="Estado tenant">${renderTenantPill(t.active)}</td>
                    <td data-label="Acciones"><button class="toggle-btn ${t.active ? 'on' : 'off'}" data-action="tenant_status" data-tenant="${t.barbershop_id}" data-value="${t.active}">${t.active ? 'Desactivar' : 'Activar'}</button></td>
                </tr>
            `).join('');
        }

        const syncTenantOptions = (select, placeholder) => {
            const selected = select.value;
            select.replaceChildren(new Option(placeholder, ''));
            currentTenants.forEach((tenant) => {
                select.add(new Option(tenant.barbershop_name, String(tenant.barbershop_id)));
            });
            if (currentTenants.some((tenant) => String(tenant.barbershop_id) === selected)) {
                select.value = selected;
            }
        };
        syncTenantOptions(filter, 'Todas las barberías');
        syncTenantOptions(document.getElementById('subscriptionTenantSelect'), 'Selecciona una barbería...');
        syncTenantOptions(document.getElementById('auditTenantFilter'), 'Todas las barberías');
        updateSubscriptionPaymentCurrency();
    } catch (error) {
        if (requestSequence !== tenantsRequestSequence) return;
        console.error('Error cargando tenants:', error);
    }
}

function updateSubscriptionPaymentCurrency() {
    const currencyLabel = document.getElementById('subscriptionPaymentCurrency');
    const tenantSelect = document.getElementById('subscriptionTenantSelect');
    if (!currencyLabel || !tenantSelect) return;

    const tenant = currentTenants.find((item) => String(item.barbershop_id) === tenantSelect.value);
    currencyLabel.textContent = tenant?.currency || 'moneda del negocio';
}

function renderToggle(userId, enabled, action) {
    const label = enabled ? 'Activado' : 'Desactivado';
    const cls = enabled ? 'on' : 'off';
    return `<button class="toggle-btn ${cls}" data-user="${userId}" data-action="${action}" data-value="${enabled}">${label}</button>`;
}

async function loadAuditLogs() {
    const result = document.getElementById('auditResult');
    const body = document.getElementById('auditBody');
    result.textContent = 'Cargando…';
    const tenant = document.getElementById('auditTenantFilter').value;
    const query = new URLSearchParams({ limit: '50' });
    if (tenant) query.set('barbershop_id', tenant);
    try {
        const data = await fetchJson(`/api/v1/admin/audit-logs?${query.toString()}`);
        const items = data.items || [];
        body.innerHTML = items.map((row) => `
            <tr><td data-label="Fecha">${escapeHtml(new Date(row.occurred_at).toLocaleString())}</td>
                <td data-label="Barbería">${escapeHtml(row.barbershop_id ?? 'Plataforma')}</td>
                <td data-label="Usuario">${escapeHtml(row.actor_user_id ?? 'Sistema / cliente')}</td>
                <td data-label="Acción">${escapeHtml(row.action)}</td>
                <td data-label="Elemento">${escapeHtml(row.entity_type)} ${escapeHtml(row.entity_id ?? '')}</td>
                <td data-label="Datos">${escapeHtml(JSON.stringify(row.details || {}))}</td></tr>`).join('');
        result.textContent = `${items.length} registro(s)`;
    } catch (error) {
        result.textContent = error.message;
    }
}

async function refreshOpenSupportTicketCount(notifyNew = false) {
    if (supportAlertsRefreshing) return;
    supportAlertsRefreshing = true;
    const counter = document.getElementById('supportOpenCount');
    try {
        const data = await fetchJson('/api/v1/admin/support/tickets?status=open&limit=1&offset=0');
        const count = Number(data.total || 0);
        const latestId = Number(data.items?.[0]?.id) || null;
        if (counter) counter.textContent = `Solicitudes abiertas: ${count}`;

        const isNew = notifyNew && supportAlertsInitialized && latestId !== null
            && latestId > (latestOpenSupportTicketId || 0);
        latestOpenSupportTicketId = latestId;
        supportAlertsInitialized = true;
        if (isNew) {
            showToast('Llegó una nueva solicitud a la bandeja de soporte.');
            if (document.getElementById('supportTicketFilter')?.value === 'open') {
                supportTicketsOffset = 0;
                await loadSupportTickets();
            }
        }
    } catch (error) {
        if (counter) counter.textContent = `No se pudo consultar soporte: ${error.message}`;
    } finally {
        supportAlertsRefreshing = false;
    }
}

async function loadSupportTickets() {
    const result = document.getElementById('supportTicketsResult');
    const body = document.getElementById('supportTicketsBody');
    if (!result || !body) return;
    result.textContent = 'Cargando…';
    const status = document.getElementById('supportTicketFilter').value;
    const query = new URLSearchParams({
        limit: String(SUPPORT_TICKETS_PAGE_SIZE), offset: String(supportTicketsOffset),
    });
    if (status) query.set('status', status);
    try {
        const data = await fetchJson(`/api/v1/admin/support/tickets?${query.toString()}`);
        const items = data.items || [];
        if (!items.length && supportTicketsOffset > 0 && supportTicketsOffset >= Number(data.total || 0)) {
            supportTicketsOffset = Math.max(0, Math.ceil(Number(data.total || 0) / SUPPORT_TICKETS_PAGE_SIZE - 1) * SUPPORT_TICKETS_PAGE_SIZE);
            return loadSupportTickets();
        }
        const statusLabels = { open: 'Abierto', in_progress: 'En curso', resolved: 'Resuelto', closed: 'Cerrado' };
        body.innerHTML = items.map((ticket) => `
            <tr><td data-label="Fecha">${escapeHtml(new Date(ticket.created_at).toLocaleString('es-DO'))}</td>
                <td data-label="Barbería">${escapeHtml(ticket.barbershop_name)}</td>
                <td data-label="Contacto">${escapeHtml(ticket.name)}<br>${escapeHtml(ticket.email || '—')}<br>${escapeHtml(ticket.phone || '—')}</td>
                <td data-label="Mensaje"><details><summary>Ver solicitud</summary><p>${escapeHtml(ticket.message).replace(/\n/g, '<br>')}</p></details></td>
                <td data-label="Aviso por correo">${ticket.notification_sent ? 'Enviado' : 'No enviado'}</td>
                <td data-label="Estado">${escapeHtml(statusLabels[ticket.status] || ticket.status)}</td>
                <td data-label="Acción"><select class="support-ticket-next-status" data-id="${Number(ticket.id)}" aria-label="Nuevo estado de solicitud">
                    ${Object.entries(statusLabels).map(([value, label]) => `<option value="${value}" ${ticket.status === value ? 'selected' : ''}>${label}</option>`).join('')}
                </select><button class="save-support-ticket-status" type="button" data-id="${Number(ticket.id)}">Guardar</button></td></tr>
        `).join('');
        result.textContent = `${items.length} de ${Number(data.total || 0)} solicitud(es)`;
        document.getElementById('previousSupportTicketsBtn').disabled = supportTicketsOffset === 0;
        document.getElementById('nextSupportTicketsBtn').disabled = supportTicketsOffset + items.length >= Number(data.total || 0);
    } catch (error) {
        body.textContent = '';
        result.textContent = error.message;
        document.getElementById('previousSupportTicketsBtn').disabled = true;
        document.getElementById('nextSupportTicketsBtn').disabled = true;
    }
}

document.getElementById('supportTicketsBody')?.addEventListener('click', async (event) => {
    const button = event.target.closest('.save-support-ticket-status');
    if (!button) return;
    const ticketId = Number(button.dataset.id);
    const status = document.querySelector(`.support-ticket-next-status[data-id="${ticketId}"]`)?.value;
    button.disabled = true;
    const result = document.getElementById('supportTicketsResult');
    try {
        await fetchJson(`/api/v1/admin/support/tickets/${ticketId}/status`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status }),
        });
        await loadSupportTickets();
    } catch (error) {
        result.textContent = error.message;
        button.disabled = false;
    }
});

function formatAffiliateMoney(cents, currency) {
    try {
        return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(Number(cents || 0) / 100);
    } catch (_) {
        return `${escapeHtml(currency)} ${(Number(cents || 0) / 100).toFixed(2)}`;
    }
}

async function loadAffiliates() {
    const body = document.getElementById('affiliatesBody');
    const select = document.getElementById('affiliateCommissionSelect');
    const result = document.getElementById('affiliateFormResult');
    try {
        const data = await fetchJson('/api/v1/admin/affiliates');
        const affiliates = data.items || [];
        body.innerHTML = affiliates.map(affiliate => {
            const totals = (affiliate.commission_totals_by_currency || []).map(total =>
                `${escapeHtml(total.currency)}: ${formatAffiliateMoney(total.earned_cents, total.currency)} earned / ${formatAffiliateMoney(total.paid_cents, total.currency)} pagado`
            ).join('<br>') || '—';
            return `<tr><td data-label="Afiliado">${escapeHtml(affiliate.name)}<br>${escapeHtml(affiliate.email)}</td>
                <td data-label="Código"><code>${escapeHtml(affiliate.code)}</code></td><td data-label="Estado">${affiliate.is_active ? 'Activo' : 'Inactivo'}</td>
                <td data-label="Referidos">${Number(affiliate.total_referrals || 0)} total / ${Number(affiliate.active_referrals || 0)} activos</td>
                <td data-label="Comisiones por moneda">${totals}</td><td data-label="Acciones"><button type="button" class="toggle-btn ${affiliate.is_active ? 'on' : 'off'} affiliate-status" data-id="${Number(affiliate.id)}" data-active="${affiliate.is_active}">${affiliate.is_active ? 'Desactivar' : 'Activar'}</button></td></tr>`;
        }).join('');
        const current = select.value;
        select.replaceChildren(new Option('Selecciona afiliado para ver comisiones', ''));
        affiliates.forEach(affiliate => select.add(new Option(`${affiliate.name} · ${affiliate.code}`, String(affiliate.id))));
        if (affiliates.some(affiliate => String(affiliate.id) === current)) select.value = current;
        result.textContent = `${affiliates.length} afiliado(s)`;
    } catch (error) {
        result.textContent = error.message;
    }
}

async function loadAffiliateCommissions() {
    const affiliateId = document.getElementById('affiliateCommissionSelect').value;
    const body = document.getElementById('affiliateCommissionsBody');
    const result = document.getElementById('affiliateCommissionResult');
    if (!affiliateId) {
        result.textContent = 'Selecciona un afiliado.';
        return;
    }
    try {
        const data = await fetchJson(`/api/v1/admin/affiliates/${encodeURIComponent(affiliateId)}/commissions`);
        const items = data.items || [];
        body.innerHTML = items.map(commission => {
            const action = commission.status === 'pending'
                ? `<button type="button" data-action="approve" data-id="${Number(commission.id)}">Aprobar</button>`
                : commission.status === 'approved'
                    ? `<div class="commission-payment-controls">
                        <label>Método<select class="commission-payment-method" aria-label="Método de pago de comisión">
                            <option value="bank_transfer">Transferencia</option><option value="cash">Efectivo</option>
                            <option value="card">Tarjeta</option><option value="other">Otro</option>
                        </select></label>
                        <label>Referencia<input class="commission-payment-reference" maxlength="100" aria-label="Referencia del pago"></label>
                        <button type="button" data-action="pay" data-id="${Number(commission.id)}">Registrar pago</button>
                    </div>` : '';
            return `<tr><td data-label="Barbería">${escapeHtml(commission.barbershop_name || commission.barbershop_id)}</td>
                <td data-label="Importe">${formatAffiliateMoney(commission.amount_cents, commission.currency)} (${Number(commission.commission_rate_percent)}%)</td>
                <td data-label="Periodo">${escapeHtml(commission.period_start.slice(0, 10))} — ${escapeHtml(commission.period_end.slice(0, 10))}</td>
                <td data-label="Estado">${escapeHtml(commission.status)}</td><td data-label="Referencia de pago">${escapeHtml(commission.payment_reference || '—')}</td><td data-label="Acciones">${action}</td></tr>`;
        }).join('');
        result.textContent = `${items.length} comisión(es)`;
    } catch (error) {
        result.textContent = error.message;
    }
}

document.getElementById('affiliateForm')?.addEventListener('submit', async event => {
    event.preventDefault();
    const result = document.getElementById('affiliateFormResult');
    const payload = {
        first_name: document.getElementById('affiliateFirstName').value.trim(),
        last_name: document.getElementById('affiliateLastName').value.trim(),
        email: document.getElementById('affiliateEmail').value.trim(),
        phone: document.getElementById('affiliatePhone').value.trim() || null,
        commission_rate: Number(document.getElementById('affiliateRate').value) / 100,
    };
    try {
        const affiliate = await fetchJson('/api/v1/admin/affiliates', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
        event.currentTarget.reset();
        document.getElementById('affiliateRate').value = '15';
        result.textContent = `Afiliado creado. Código para compartir: ${affiliate.code}`;
        await loadAffiliates();
    } catch (error) {
        result.textContent = error.message;
    }
});

document.getElementById('affiliatesBody')?.addEventListener('click', async event => {
    const button = event.target.closest('.affiliate-status');
    if (!button) return;
    try {
        await fetchJson(`/api/v1/admin/affiliates/${Number(button.dataset.id)}/status`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: button.dataset.active !== 'true' }),
        });
        await loadAffiliates();
    } catch (error) {
        document.getElementById('affiliateFormResult').textContent = error.message;
    }
});

document.getElementById('affiliateCommissionsBody')?.addEventListener('click', async event => {
    const button = event.target.closest('button[data-action]');
    if (!button) return;
    const id = Number(button.dataset.id);
    button.disabled = true;
    try {
        if (button.dataset.action === 'approve') {
            await fetchJson(`/api/v1/admin/commissions/${id}/approve`, { method: 'POST' });
        } else {
            const row = button.closest('tr');
            const method = row?.querySelector('.commission-payment-method')?.value;
            const reference = row?.querySelector('.commission-payment-reference')?.value.trim() || null;
            if (!['bank_transfer', 'cash', 'card', 'other'].includes(method)) {
                throw new Error('Selecciona un método de pago válido.');
            }
            await fetchJson(`/api/v1/admin/commissions/${id}/pay`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ payment_method: method, payment_reference: reference }),
            });
        }
        await loadAffiliateCommissions();
        await loadAffiliates();
    } catch (error) {
        document.getElementById('affiliateCommissionResult').textContent = error.message;
        button.disabled = false;
    }
});

document.getElementById('loadAffiliateCommissionsBtn')?.addEventListener('click', loadAffiliateCommissions);

async function loadUsers() {
    const requestSequence = ++usersRequestSequence;
    const tenantId = document.getElementById('tenantFilter').value;
    const search = document.getElementById('userSearch').value.trim();
    const params = new URLSearchParams({ limit: String(USERS_PAGE_SIZE), offset: String(usersOffset) });
    if (tenantId) params.set('barbershop_id', tenantId);
    if (search) params.set('search', search);

    try {
        const data = await fetchJson(`/api/v1/admin/users?${params.toString()}`);
        if (requestSequence !== usersRequestSequence) return;
        const users = data.items || [];

        const body = document.getElementById('usersBody');
        const empty = document.getElementById('usersEmpty');
        const start = data.total ? data.offset + 1 : 0;
        const end = Math.min(data.offset + users.length, data.total);
        document.getElementById('usersCount').textContent = `${start}–${end} de ${data.total} usuario(s)`;
        document.getElementById('previousUsersBtn').disabled = data.offset <= 0;
        document.getElementById('nextUsersBtn').disabled = data.offset + users.length >= data.total;

        if (!users.length) {
            body.innerHTML = '';
            empty.style.display = 'block';
            return;
        }

        empty.style.display = 'none';
        body.innerHTML = users.map((u) => {
            const tenant = currentTenants.find((t) => t.barbershop_id === u.barbershop_id);
            const supportEligible = ['super_admin', 'barbershop_owner', 'barber'].includes(u.role);
            const brandingEligible = ['barber', 'barbershop_owner'].includes(u.role);

            return `
                <tr>
                    <td data-label="Usuario">${escapeHtml(u.full_name)}<br><span class="text-sm text-stone-500">${escapeHtml(u.email)}</span></td>
                    <td data-label="Rol">${escapeHtml(u.role)}</td>
                    <td data-label="Barbería">${escapeHtml(tenant ? tenant.barbershop_name : '—')}</td>
                    <td data-label="Estado">${renderTenantPill(u.is_active)}</td>
                    <td data-label="Acceso"><button class="toggle-btn ${u.is_active ? 'on' : 'off'}" data-action="account_status" data-user="${Number(u.id)}" data-value="${u.is_active}">${u.is_active ? 'Desactivar' : 'Activar'}</button></td>
                    <td data-label="Soporte por correo">${supportEligible ? renderToggle(u.id, u.support_contact_enabled, 'support') : '—'}</td>
                    <td data-label="Branding automático" title="Cuando se activa, usa en el portal los colores configurados por esta barbería.">${brandingEligible ? renderToggle(u.id, u.feature_flags?.branding_auto === true, 'branding_auto') : '—'}</td>
                </tr>
            `;
        }).join('');
    } catch (error) {
        if (requestSequence !== usersRequestSequence) return;
        console.error('Error cargando usuarios:', error);
        document.getElementById('usersCount').textContent = `Error: ${error.message}`;
    }
}

async function toggleSupport(userId, nextValue) {
    await fetchJson(`/api/v1/admin/users/${userId}/support`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ support_contact_enabled: nextValue }),
    });
}

async function toggleFeature(userId, featureKey, nextValue) {
    await fetchJson(`/api/v1/admin/users/${userId}/features`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feature_key: featureKey, enabled: nextValue }),
    });
}

document.getElementById('usersBody')?.addEventListener('click', async (event) => {
    const btn = event.target.closest('.toggle-btn');
    if (!btn) return;

    const userId = Number(btn.dataset.user);
    const action = btn.dataset.action;
    const nextValue = btn.dataset.value !== 'true';

    try {
        if (action === 'account_status') {
            await fetchJson(`/api/v1/admin/users/${userId}/status`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_active: nextValue }),
            });
        } else if (action === 'support') {
            await toggleSupport(userId, nextValue);
        } else {
            await toggleFeature(userId, action, nextValue);
        }
        await loadUsers();
    } catch (error) {
        showToast(` ${error.message}`);
    }
});

document.getElementById('tenantsBody')?.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-action="tenant_status"]');
    if (!button) return;
    const tenantId = Number(button.dataset.tenant);
    const nextValue = button.dataset.value !== 'true';
    try {
        await fetchJson(`/api/v1/admin/tenants/${tenantId}/status`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: nextValue }),
        });
        await loadTenants();
    } catch (error) {
        showToast(` ${error.message}`);
    }
});

async function loadSubscription() {
    const tenantId = document.getElementById('subscriptionTenantSelect').value;
    const resultEl = document.getElementById('subscriptionResult');
    const panel = document.getElementById('subscriptionPanel');
    resultEl.textContent = '';

    if (!tenantId) {
        showToast('Selecciona una barbería primero');
        return;
    }

    try {
        const sub = await fetchJson(`/api/v1/admin/tenants/${tenantId}/subscription`);
        panel.style.display = 'block';
        document.getElementById('subPlan').value = sub.plan;
        document.getElementById('subStatus').value = sub.status;
        document.getElementById('subscriptionPaymentStart').value = (sub.current_period_start || '').slice(0, 10);
        document.getElementById('subscriptionPaymentEnd').value = (sub.current_period_end || '').slice(0, 10);
        document.getElementById('subPeriodEnd').value = (sub.current_period_end || '').slice(0, 10);
        resultEl.textContent = `Suscripción #${sub.subscription_id} · Límites: ${sub.max_barbers ?? '∞'} barberos, ${sub.max_appointments_per_month ?? '∞'} citas/mes, ${sub.max_clients ?? '∞'} clientes.`;
    } catch (error) {
        if (error.message && error.message.toLowerCase().includes('no tiene una suscripci')) {
            // Sin suscripción todavía: permitir crear una desde cero.
            panel.style.display = 'block';
            document.getElementById('subPlan').value = 'free';
            document.getElementById('subStatus').value = 'active';
            document.getElementById('subscriptionPaymentStart').value = '';
            document.getElementById('subscriptionPaymentEnd').value = '';
            document.getElementById('subPeriodEnd').value = '';
            resultEl.textContent = 'Esta barbería no tiene suscripción aún. Guarda para crear una.';
        } else {
            resultEl.textContent = ` ${error.message}`;
        }
    }
}

async function saveSubscription() {
    const tenantId = document.getElementById('subscriptionTenantSelect').value;
    const resultEl = document.getElementById('subscriptionResult');

    if (!tenantId) {
        showToast('Selecciona una barbería primero');
        return;
    }

    const periodEndValue = document.getElementById('subPeriodEnd').value;
    const payload = {
        plan: document.getElementById('subPlan').value,
        status: document.getElementById('subStatus').value,
    };
    if (periodEndValue) {
        // The selected date is the final calendar day of the period. Store its
        // last second in UTC, matching the received-payment period form below.
        payload.current_period_end = `${periodEndValue}T23:59:59Z`;
    }

    try {
        const sub = await fetchJson(`/api/v1/admin/tenants/${tenantId}/subscription`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        resultEl.textContent = ` Guardado. Plan: ${sub.plan} · Estado: ${sub.status} · Fin del periodo: ${(sub.current_period_end || '').slice(0, 10)} · El cobro se registra manualmente.`;
        await loadTenants();
    } catch (error) {
        resultEl.textContent = ` ${error.message}`;
    }
}

document.getElementById('subscriptionPaymentForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const tenantId = document.getElementById('subscriptionTenantSelect').value;
    const result = document.getElementById('subscriptionPaymentResult');
    if (!tenantId) {
        result.textContent = 'Selecciona una barbería primero.';
        return;
    }
    if (!document.getElementById('subscriptionPaymentConfirmed').checked) {
        result.textContent = 'Confirma que el pago externo ya fue recibido.';
        return;
    }
    const amount = Number(document.getElementById('subscriptionPaymentAmount').value);
    const startDate = document.getElementById('subscriptionPaymentStart').value;
    const endDate = document.getElementById('subscriptionPaymentEnd').value;
    if (!Number.isFinite(amount) || amount <= 0 || !startDate || !endDate) {
        result.textContent = 'Completa un importe y periodo válidos.';
        return;
    }
    const payload = {
        amount_cents: Math.round(amount * 100),
        method: document.getElementById('subscriptionPaymentMethod').value,
        reference: document.getElementById('subscriptionPaymentReference').value.trim() || null,
        period_start: `${startDate}T00:00:00Z`,
        period_end: `${endDate}T23:59:59Z`,
    };
    result.textContent = 'Registrando pago confirmado…';
    try {
        const payment = await fetchJson(`/api/v1/admin/tenants/${tenantId}/subscription/payments`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
        result.textContent = payment.commission_id
            ? `Cobro ${payment.payment_id} registrado. Comisión afiliada ${payment.commission_id} creada.`
            : `Cobro ${payment.payment_id} registrado. No hay afiliado asociado.`;
        document.getElementById('subscriptionPaymentForm').reset();
        document.getElementById('subscriptionPaymentConfirmed').checked = false;
        await loadTenants();
        await loadSubscription();
    } catch (error) {
        result.textContent = error.message;
    }
});

document.getElementById('loadSubscriptionBtn')?.addEventListener('click', loadSubscription);
document.getElementById('saveSubscriptionBtn')?.addEventListener('click', saveSubscription);
document.getElementById('subscriptionTenantSelect')?.addEventListener('change', updateSubscriptionPaymentCurrency);

document.getElementById('refreshTenantsBtn')?.addEventListener('click', loadTenants);
document.getElementById('refreshOverviewBtn')?.addEventListener('click', loadOverview);
document.getElementById('refreshUsersBtn')?.addEventListener('click', loadUsers);
document.getElementById('loadAuditBtn')?.addEventListener('click', loadAuditLogs);
document.getElementById('tenantFilter')?.addEventListener('change', () => {
    usersOffset = 0;
    loadUsers();
});
document.getElementById('userSearchBtn')?.addEventListener('click', () => {
    usersOffset = 0;
    loadUsers();
});
document.getElementById('userSearch')?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
        event.preventDefault();
        usersOffset = 0;
        loadUsers();
    }
});
document.getElementById('previousUsersBtn')?.addEventListener('click', () => {
    usersOffset = Math.max(0, usersOffset - USERS_PAGE_SIZE);
    loadUsers();
});
document.getElementById('nextUsersBtn')?.addEventListener('click', () => {
    usersOffset += USERS_PAGE_SIZE;
    loadUsers();
});
document.getElementById('refreshSupportTicketsBtn')?.addEventListener('click', async () => {
    await loadSupportTickets();
    await refreshOpenSupportTicketCount();
});
document.getElementById('previousSupportTicketsBtn')?.addEventListener('click', () => {
    supportTicketsOffset = Math.max(0, supportTicketsOffset - SUPPORT_TICKETS_PAGE_SIZE);
    loadSupportTickets();
});
document.getElementById('nextSupportTicketsBtn')?.addEventListener('click', () => {
    supportTicketsOffset += SUPPORT_TICKETS_PAGE_SIZE;
    loadSupportTickets();
});
document.getElementById('supportTicketFilter')?.addEventListener('change', () => {
    supportTicketsOffset = 0;
    loadSupportTickets();
});

document.getElementById('logoutBtn')?.addEventListener('click', () => {
    KingFlowAuth.logout();
    localStorage.removeItem('userEmail');
    window.location.href = '/index.html';
});

async function init() {
    if (!accessToken) {
        showGate();
        return;
    }

    try {
        const me = await fetchJson('/api/v1/auth/me');
        if (me.role !== 'super_admin') {
            showGate();
            return;
        }
        showAdmin(me.email);
        await loadOverview();
        await loadPlatformSettings();
        await loadTenants();
        await loadUsers();
        await loadAffiliates();
        await loadSupportTickets();
        await refreshOpenSupportTicketCount();
        window.setInterval(() => {
            if (document.visibilityState === 'visible') void refreshOpenSupportTicketCount(true);
        }, 60_000);
    } catch (error) {
        console.error(error);
        showGate();
    }
}

init();
