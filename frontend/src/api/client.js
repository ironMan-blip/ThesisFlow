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

// Brief outages (backend restarting, database blip) are retried for reads, so pages don't fail on them.
const RETRY_DELAYS_MS = [1000, 2000, 4000];
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
export const isOutage = (err) => err instanceof ApiError && (err.status === 0 || (err.status >= 502 && err.status <= 504));

async function request(path, options = {}) {
  // Only reads: retrying a POST/PUT/DELETE could apply it twice.
  const retries = !options.method || options.method === "GET" ? RETRY_DELAYS_MS : [];
  for (const delay of retries) {
    try {
      return await send(path, options);
    } catch (err) {
      if (!isOutage(err)) throw err;
      await sleep(err.retryAfterMs ? Math.min(err.retryAfterMs, 5000) : delay);
    }
  }
  return send(path, options);
}

// Sends the request with the JWT; throws ApiError with the backend's detail on non-2xx.
async function send(path, { body, headers, ...options } = {}) {
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
  endIfSignedOut(res.status, token, path);
  if (!res.ok) throw toError(res.status, await res.json().catch(() => null), res.headers.get("Retry-After"));
  return res;
}

function endIfSignedOut(status, token, path) {
  if (status === 401 && token && path !== "/auth/login") {
    // Session ended (logout on another device, password change, expiry): back to login from any page.
    clearToken();
    window.location.replace("/login");
  }
}

function toError(status, data, retryAfter) {
  // 502/504 come from the proxy when the backend is down, with no JSON detail.
  const fallback = status >= 502 && status <= 504 ? UNAVAILABLE : "Something went wrong";
  const err = new ApiError(status, typeof data?.detail === "string" ? data.detail : fallback);
  err.retryAfterMs = Number(retryAfter) * 1000 || 0;
  return err;
}

// POST a form and report upload progress (0 to 1) as it goes: fetch can't, so this uses XMLHttpRequest.
export function upload(path, form, onProgress) {
  return new Promise((resolve, reject) => {
    const token = getToken();
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api${path}`);
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onerror = () => reject(new ApiError(0, UNAVAILABLE));
    xhr.onload = () => {
      endIfSignedOut(xhr.status, token, path);
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response);
      else reject(toError(xhr.status, xhr.response, xhr.getResponseHeader("Retry-After")));
    };
    xhr.send(form);
  });
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
