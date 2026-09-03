/**
 * KingFlow Barber - Panel Admin
 *
 * Consume los endpoints /api/v1/admin/* (solo accesibles para role=super_admin).
 */

const API_BASE = 'http://127.0.0.1:8000';
const APP_CONFIG = window.KINGFLOW_CONFIG || {};
const API_ROOT = APP_CONFIG.apiBaseUrl || API_BASE;

let accessToken = localStorage.getItem('token');
let currentTenants = [];

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
    const response = await fetch(`${API_ROOT}${path}`, {
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

async function loadTenants() {
    try {
        const data = await fetchJson('/api/v1/admin/tenants');
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
                    <td data-label="Barbería">${t.barbershop_name} <span style="color:#a1a1aa;">(${t.slug})</span></td>
                    <td data-label="Owner">${t.owner_email || '—'}</td>
                    <td data-label="Plan">${t.plan ? `<span class="pill plan">${t.plan}</span>` : '—'}</td>
                    <td data-label="Estado suscripción">${t.subscription_status || '—'}</td>
                    <td data-label="Estado tenant">${renderTenantPill(t.active)}</td>
                </tr>
            `).join('');
        }

        const existingValues = new Set(Array.from(filter.options).map((o) => o.value));
        currentTenants.forEach((t) => {
            const value = String(t.barbershop_id);
            if (!existingValues.has(value)) {
                const opt = document.createElement('option');
                opt.value = value;
                opt.textContent = t.barbershop_name;
                filter.appendChild(opt);
            }
        });
    } catch (error) {
        console.error('Error cargando tenants:', error);
    }
}

function renderToggle(userId, enabled, action) {
    const label = enabled ? 'Activado' : 'Desactivado';
    const cls = enabled ? 'on' : 'off';
    return `<button class="toggle-btn ${cls}" data-user="${userId}" data-action="${action}" data-value="${enabled}">${label}</button>`;
}

async function loadUsers() {
    const tenantId = document.getElementById('tenantFilter').value;
    const query = tenantId ? `?barbershop_id=${encodeURIComponent(tenantId)}` : '';

    try {
        const data = await fetchJson(`/api/v1/admin/users${query}`);
        const users = data.items || [];

        const body = document.getElementById('usersBody');
        const empty = document.getElementById('usersEmpty');
        document.getElementById('usersCount').textContent = `${users.length} usuario(s)`;

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
                    <td data-label="Usuario">${u.full_name}<br><span style="color:#a1a1aa;font-size:.85em;">${u.email}</span></td>
                    <td data-label="Rol">${u.role}</td>
                    <td data-label="Barbería">${tenant ? tenant.barbershop_name : '—'}</td>
                    <td data-label="Estado">${renderTenantPill(u.is_active)}</td>
                    <td data-label="Soporte por correo">${supportEligible ? renderToggle(u.id, u.support_contact_enabled, 'support') : '—'}</td>
                    <td data-label="Branding automático">${brandingEligible ? renderToggle(u.id, false, 'branding_auto') : '—'}</td>
                </tr>
            `;
        }).join('');
    } catch (error) {
        console.error('Error cargando usuarios:', error);
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
        if (action === 'support') {
            await toggleSupport(userId, nextValue);
        } else {
            await toggleFeature(userId, action, nextValue);
        }
        await loadUsers();
    } catch (error) {
        alert(`❌ ${error.message}`);
    }
});

document.getElementById('refreshTenantsBtn')?.addEventListener('click', loadTenants);
document.getElementById('refreshUsersBtn')?.addEventListener('click', loadUsers);
document.getElementById('tenantFilter')?.addEventListener('change', loadUsers);

document.getElementById('logoutBtn')?.addEventListener('click', () => {
    localStorage.removeItem('token');
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
        await loadTenants();
        await loadUsers();
    } catch (error) {
        console.error(error);
        showGate();
    }
}

init();
