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

export async function api(path, { body, headers, ...options } = {}) {
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
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    const detail = typeof data?.detail === "string" ? data.detail : "Something went wrong";
    throw new ApiError(res.status, detail);
  }
  return data;
}

export async function login(email, password) {
  const form = new URLSearchParams({ username: email, password });
  const { access_token } = await api("/auth/login", { method: "POST", body: form });
  setToken(access_token);
}
