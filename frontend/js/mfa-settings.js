"use strict";

(() => {
    const config = window.KINGFLOW_CONFIG || {};
    const apiRoot = (config.apiBaseUrl || window.location.origin).replace(/\/$/, "");
    const h = (tag, attrs = {}, text = "") => {
        const node = document.createElement(tag);
        const shared = {
            button: 'inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-stone-300 bg-white px-4 py-2 text-sm font-semibold hover:bg-stone-100',
            dialog: 'm-auto max-h-[90dvh] w-[min(94vw,36rem)] space-y-5 overflow-y-auto rounded-2xl border border-stone-200 bg-white p-6 text-stone-900 backdrop:bg-black/60 [&_section]:grid [&_section]:gap-3 [&_input]:min-h-11 [&_input]:min-w-0 [&_input]:rounded-lg [&_input]:border [&_input]:border-stone-300 [&_input]:p-3 [&_button]:min-h-11 [&_button]:rounded-lg [&_button]:bg-stone-100 [&_button]:p-3 [&_pre]:overflow-x-auto',
        };
        attrs.class = [attrs.class || '', shared[tag] || ''].join(' ').trim();
        for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
        if (text) node.textContent = text;
        return node;
    };

    function unmount() {
        document.getElementById("mfaManageButton")?.remove();
        document.getElementById("mfaSettingsDialog")?.remove();
    }

    async function api(path, body) {
        const response = await window.KingFlowAuth.fetch(`${apiRoot}/api/v1/auth/mfa/${path}`, {
            method: body ? "POST" : "GET",
            headers: body ? { "Content-Type": "application/json" } : {},
            body: body ? JSON.stringify(body) : undefined,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || "No se pudo completar la acción.");
        return data;
    }

    function mount() {
        if (!window.KingFlowAuth || !sessionStorage.getItem("token")
            || document.getElementById("mfaManageButton")) return;
        void window.KingFlowAuth.fetch(`${apiRoot}/api/v1/auth/me`).then(async (res) => {
            if (!res.ok) return;
            const user = await res.json();
            if (!["barbershop_owner", "super_admin"].includes(user.role)) return;
            if (document.getElementById("mfaManageButton") || !sessionStorage.getItem("token")) return;
            const button = h("button", { type: "button", class: "mfa-manage-button", "aria-haspopup": "dialog" }, "Seguridad de cuenta");
            button.id = "mfaManageButton";
            const dialog = h("dialog", { class: "mfa-settings-dialog", "aria-labelledby": "mfaSettingsTitle" });
            dialog.id = "mfaSettingsDialog";
            dialog.innerHTML = `
                <div class="mfa-settings-head"><div><p class="mfa-eyebrow">SEGURIDAD</p><h2 id="mfaSettingsTitle">Verificación en dos pasos</h2></div><button type="button" class="mfa-close" aria-label="Cerrar">×</button></div>
                <p class="mfa-copy">Protege esta cuenta con una aplicación de autenticación. Los códigos de recuperación se muestran una sola vez.</p>
                <p class="mfa-status" role="status" aria-live="polite"></p>
                <section class="mfa-enable-section"><label for="mfaPassword">Confirma tu contraseña para configurar</label><input id="mfaPassword" type="password" autocomplete="current-password" maxlength="72"><button type="button" class="mfa-action mfa-setup">Configurar autenticador</button></section>
                <section class="mfa-pending" hidden><p>Agrega esta clave manualmente en tu app:</p><code class="mfa-secret"></code><label for="mfaEnableCode">Código de 6 dígitos</label><input id="mfaEnableCode" inputmode="numeric" autocomplete="one-time-code" maxlength="6"><button type="button" class="mfa-action mfa-enable">Verificar y activar</button></section>
                <section class="mfa-codes" hidden><h3>Guarda estos códigos de recuperación</h3><p>No volverán a mostrarse.</p><pre></pre><button type="button" class="mfa-action mfa-codes-done">Ya los guardé</button></section>
                <section class="mfa-maintenance" hidden><label for="mfaActionCode">Código de autenticación o recuperación</label><input id="mfaActionCode" autocomplete="one-time-code" maxlength="32"><button type="button" class="mfa-action mfa-rotate">Generar nuevos códigos</button><label for="mfaDisablePassword">Contraseña para desactivar</label><input id="mfaDisablePassword" type="password" autocomplete="current-password" maxlength="72"><button type="button" class="mfa-action mfa-disable">Desactivar verificación</button></section>
                <div class="mfa-footer"><button type="button" class="mfa-cancel">Cerrar</button></div>`;
            const actionHost = document.querySelector(".header-actions") || document.body;
            actionHost.append(button);
            document.body.append(dialog);
            const status = dialog.querySelector(".mfa-status");
            const report = (error) => { status.textContent = error.message || "No se pudo completar la acción."; };
            const loadStatus = async () => {
                try {
                    const state = await api("status");
                    dialog.querySelector(".mfa-enable-section").hidden = state.enabled;
                    dialog.querySelector(".mfa-maintenance").hidden = !state.enabled;
                    status.textContent = state.enabled ? `MFA activo · ${state.recovery_codes_remaining} códigos disponibles.` : "MFA desactivado para esta cuenta.";
                } catch (error) { report(error); }
            };
            const clearCodes = () => { dialog.querySelector(".mfa-codes").hidden = true; dialog.querySelector(".mfa-codes pre").textContent = ""; };
            const showCodes = (codes) => { dialog.querySelector(".mfa-codes pre").textContent = codes.join("\n"); dialog.querySelector(".mfa-codes").hidden = false; };
            button.addEventListener("click", () => { dialog.showModal(); void loadStatus(); });
            dialog.querySelectorAll(".mfa-close,.mfa-cancel").forEach((item) => item.addEventListener("click", () => dialog.close()));
            dialog.addEventListener("close", () => { dialog.querySelector(".mfa-secret").textContent = ""; dialog.querySelector(".mfa-enable-code").value = ""; clearCodes(); });
            dialog.querySelector(".mfa-setup").addEventListener("click", async () => {
                try {
                    const setup = await api("setup", { password: dialog.querySelector("#mfaPassword").value });
                    dialog.querySelector(".mfa-secret").textContent = setup.secret;
                    dialog.querySelector(".mfa-pending").hidden = false;
                    dialog.querySelector("#mfaPassword").value = "";
                    status.textContent = "Clave temporal válida durante 10 minutos. Agrégala a tu aplicación y verifica el código.";
                } catch (error) { report(error); }
            });
            dialog.querySelector(".mfa-enable").addEventListener("click", async () => {
                try {
                    const result = await api("enable", { code: dialog.querySelector("#mfaEnableCode").value });
                    dialog.querySelector(".mfa-pending").hidden = true;
                    dialog.querySelector(".mfa-secret").textContent = "";
                    showCodes(result.recovery_codes);
                    await loadStatus();
                } catch (error) { report(error); }
            });
            dialog.querySelector(".mfa-codes-done").addEventListener("click", clearCodes);
            dialog.querySelector(".mfa-rotate").addEventListener("click", async () => {
                try { const result = await api("recovery-codes", { code: dialog.querySelector("#mfaActionCode").value }); showCodes(result.recovery_codes); await loadStatus(); }
                catch (error) { report(error); }
            });
            dialog.querySelector(".mfa-disable").addEventListener("click", async () => {
                try { await api("disable", { code: dialog.querySelector("#mfaActionCode").value, password: dialog.querySelector("#mfaDisablePassword").value }); dialog.querySelector("#mfaActionCode").value = ""; dialog.querySelector("#mfaDisablePassword").value = ""; status.textContent = "Verificación en dos pasos desactivada."; await loadStatus(); }
                catch (error) { report(error); }
            });
        }).catch(() => {});
    }

    window.KingFlowMfaSettings = { mount, unmount };
    window.addEventListener("kingflow:session-ended", unmount);
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount, { once: true });
    else mount();
})();
