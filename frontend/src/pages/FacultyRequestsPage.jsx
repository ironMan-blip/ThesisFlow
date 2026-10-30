import { useEffect, useState } from "react";
import { api } from "../api/client";
import { when } from "../format";

export default function FacultyRequestsPage() {
  const [requests, setRequests] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(null); // id of the request being decided

  useEffect(() => {
    api("/auth/faculty-requests").then(setRequests).catch((err) => setError(err.message));
  }, []);

  const decide = async (r, approve) => {
    setError(null);
    setNotice(null);
    setBusy(r.id);
    try {
      await api(`/auth/faculty-requests/${r.id}${approve ? "/approve" : ""}`, { method: approve ? "POST" : "DELETE" });
      setRequests((rs) => rs.filter((x) => x.id !== r.id));
      setNotice(`${r.full_name} was ${approve ? "approved and can now log in" : "rejected"}.`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold">Faculty requests</h1>
        <p className="mt-2 max-w-prose text-zinc-600">
          Faculty who registered wait here until you approve them. Please review each request within 48 hours.
        </p>
      </div>

      {error && <p role="alert" className="alert-error">{error}</p>}
      {notice && <p role="status" className="alert-success">{notice}</p>}

      {!requests ? (
        <div className="h-24 animate-pulse rounded-xl bg-zinc-100" aria-hidden="true" />
      ) : requests.length === 0 ? (
        <p className="rounded-xl border border-dashed border-zinc-300 p-5 text-sm text-zinc-500">No pending requests.</p>
      ) : (
        <ul className="space-y-3">
          {requests.map((r) => (
            <li key={r.id} className="card flex flex-wrap items-center justify-between gap-4 p-5">
              <div>
                <p className="font-medium">{r.full_name}</p>
                <p className="text-sm text-zinc-600">{r.email} · requested {when(r.created_at)}</p>
              </div>
              <div className="flex gap-2">
                <button onClick={() => decide(r, false)} disabled={busy === r.id} className="btn-secondary">Reject</button>
                <button onClick={() => decide(r, true)} disabled={busy === r.id} className="btn-primary">
                  {busy === r.id ? "Saving..." : "Approve"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
