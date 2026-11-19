"use strict";

(() => {
    const config = window.KINGFLOW_CONFIG || {};
    const apiRoot = (config.apiBaseUrl || window.location.origin).replace(/\/$/, "");
    let refreshInFlight = null;

    function setTokens(accessToken, refreshToken) {
        localStorage.setItem("token", accessToken);
        localStorage.setItem("refresh_token", refreshToken);
    }

    function clearTokens() {
        localStorage.removeItem("token");
        localStorage.removeItem("refresh_token");
    }

    async function rotateRefreshToken() {
        const refreshToken = localStorage.getItem("refresh_token");
        if (!refreshToken) return false;
        const response = await fetch(`${apiRoot}/api/v1/auth/refresh`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!response.ok) {
            // Another browser tab may have rotated the same session already.
            if (localStorage.getItem("refresh_token") !== refreshToken) return true;
            clearTokens();
            window.dispatchEvent(new Event("kingflow:auth-expired"));
            return false;
        }
        const tokens = await response.json();
        setTokens(tokens.access_token, tokens.refresh_token);
        return true;
    }

    async function fetchAuthenticated(input, options = {}) {
        const request = async () => {
            const headers = new Headers(options.headers || {});
            const accessToken = localStorage.getItem("token");
            if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
            return fetch(input, { ...options, headers });
        };

        const response = await request();
        if (response.status !== 401 || !localStorage.getItem("refresh_token")) return response;

        if (!refreshInFlight) {
            refreshInFlight = rotateRefreshToken().finally(() => { refreshInFlight = null; });
        }
        if (!(await refreshInFlight)) return response;
        return request();
    }

    async function logout() {
        const refreshToken = localStorage.getItem("refresh_token");
        clearTokens();
        if (!refreshToken) return;
        try {
            await fetch(`${apiRoot}/api/v1/auth/logout`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ refresh_token: refreshToken }),
            });
        } catch (_) {
            // Local credentials are cleared even if the server is unreachable.
        }
    }

    window.KingFlowAuth = { setTokens, clearTokens, fetch: fetchAuthenticated, logout };
})();
