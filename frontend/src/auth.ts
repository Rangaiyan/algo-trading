// Access token for the backend. When the backend has APP_ACCESS_TOKEN set (required before it is reachable from other
// devices), every API request must carry it. The token is kept in this browser only.
const KEY = "rinz.accessToken";

export function getToken(): string {
  try { return localStorage.getItem(KEY) ?? ""; } catch { return ""; }
}

export function setToken(t: string): void {
  try { if (t) localStorage.setItem(KEY, t); else localStorage.removeItem(KEY); } catch { /* storage blocked */ }
}

/** Add the token to every request to the backend; announce a 401 so the app can ask for the token. */
export function installAuth(apiBase: string): void {
  const original = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (!url.startsWith(apiBase)) return original(input, init);
    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
    const token = getToken();
    if (token && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${token}`);
    const res = await original(input, { ...init, headers });
    if (res.status === 401) window.dispatchEvent(new CustomEvent("rinz:auth-required"));
    return res;
  };
}

/** For plain links (file downloads) that cannot send headers. */
export function withToken(url: string): string {
  const t = getToken();
  return t ? `${url}${url.includes("?") ? "&" : "?"}access_token=${encodeURIComponent(t)}` : url;
}
