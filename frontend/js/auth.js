"use strict";

(() => {
    const config = window.KINGFLOW_CONFIG || {};
    const apiRoot = (config.apiBaseUrl || window.location.origin).replace(/\/$/, "");
    let refreshInFlight = null;

    // Tokens are scoped to this browser tab and are cleared when its session ends.
    localStorage.removeItem("token");
    localStorage.removeItem("refresh_token");

    function setTokens(accessToken, refreshToken) {
        sessionStorage.setItem("token", accessToken);
        sessionStorage.setItem("refresh_token", refreshToken);
    }

    function clearTokens() {
        sessionStorage.removeItem("token");
        sessionStorage.removeItem("refresh_token");
    }

    async function rotateRefreshToken() {
        const refreshToken = sessionStorage.getItem("refresh_token");
        if (!refreshToken) return false;
        const response = await fetch(`${apiRoot}/api/v1/auth/refresh`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!response.ok) {
            if (response.status !== 401 && response.status !== 403) return false;
            // A concurrent local credential update wins over this stale response.
            if (sessionStorage.getItem("refresh_token") !== refreshToken) return true;
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
            const accessToken = sessionStorage.getItem("token");
            if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
            return fetch(input, { ...options, headers });
        };

        const response = await request();
        if (response.status !== 401 || !sessionStorage.getItem("refresh_token")) return response;

        if (!refreshInFlight) {
            refreshInFlight = rotateRefreshToken().finally(() => { refreshInFlight = null; });
        }
        if (!(await refreshInFlight)) return response;
        return request();
    }

    async function logout() {
        const refreshToken = sessionStorage.getItem("refresh_token");
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
