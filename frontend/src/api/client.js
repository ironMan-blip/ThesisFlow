// Small fetch wrapper. Adds the JWT and throws on non-2xx responses.

const TOKEN_KEY = "token";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (token) => localStorage.setItem(TOKEN_KEY, token);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

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
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new ApiError(res.status, typeof data?.detail === "string" ? data.detail : "Something went wrong");
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
  a.click();
  URL.revokeObjectURL(url);
}

export async function login(email, password) {
  const form = new URLSearchParams({ username: email, password });
  const { access_token } = await api("/auth/login", { method: "POST", body: form });
  setToken(access_token);
}
