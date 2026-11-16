// Small fetch wrapper. Adds the JWT and throws on non-2xx responses.

const TOKEN_KEY = "token";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
const setToken = (token) => localStorage.setItem(TOKEN_KEY, token);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

const UNAVAILABLE = "ThesisFlow can't reach the server right now. Try again in a moment.";

// Sends the request with the JWT; throws ApiError with the backend's detail on non-2xx.
async function request(path, { body, headers, ...options } = {}) {
  const token = getToken();
  const isForm = body instanceof FormData || body instanceof URLSearchParams;
  const res = await fetch(`/api${path}`, {
    ...options,
    headers: {
      ...(body && !isForm ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: body && !isForm ? JSON.stringify(body) : body,
  }).catch(() => {
    throw new ApiError(0, UNAVAILABLE); // network down or the dev server stopped
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    // 502/504 come from the proxy when the backend is down, with no JSON detail.
    const fallback = res.status >= 502 && res.status <= 504 ? UNAVAILABLE : "Something went wrong";
    throw new ApiError(res.status, typeof data?.detail === "string" ? data.detail : fallback);
  }
  return res;
}

export async function api(path, options) {
  const res = await request(path, options);
  return res.status === 204 ? null : res.json().catch(() => null);
}

// Links can't send the JWT header, so fetch the file and hand it to the browser.
export async function download(path, filename) {
  const res = await request(path);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.append(a);
  a.click();
  a.remove();
  // Revoking right away can cancel the download in Safari.
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export async function login(idNumber, password) {
  const form = new URLSearchParams({ username: idNumber, password });
  const { access_token } = await api("/auth/login", { method: "POST", body: form });
  setToken(access_token);
}
