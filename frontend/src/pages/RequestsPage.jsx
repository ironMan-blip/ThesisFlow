import { useEffect, useState } from "react";
import { api } from "../api/client";
import { when } from "../format";

// Coordinator inbox of requests to approve or reject; FacultyRequestsPage and DeletionRequestsPage configure it.
function RequestsPage({ path, title, intro, approved, rejected, dateField }) {
  const [requests, setRequests] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(null); // id of the request being decided

  useEffect(() => {
    api(path).then(setRequests).catch((err) => setError(err.message));
  }, [path]);

  const decide = async (r, approve) => {
    setError(null);
    setNotice(null);
    setBusy(r.id);
    try {
      await api(`${path}/${r.id}${approve ? "/approve" : ""}`, { method: approve ? "POST" : "DELETE" });
      setRequests((rs) => rs.filter((x) => x.id !== r.id));
      setNotice(`${r.full_name} ${approve ? approved : rejected}.`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold">{title}</h1>
        <p className="mt-2 max-w-prose text-zinc-600">{intro}</p>
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
                <p className="text-sm text-zinc-600">{r.email} · requested {when(r[dateField])}</p>
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

export const FacultyRequestsPage = () => (
  <RequestsPage
    path="/auth/faculty-requests"
    title="Faculty requests"
    intro="Faculty who registered wait here until you approve them. Please review each request within 48 hours."
    approved="was approved and can now log in"
    rejected="was rejected"
    dateField="created_at"
  />
);

export const DeletionRequestsPage = () => (
  <RequestsPage
    path="/auth/deletion-requests"
    title="Deletion requests"
    intro="Users who asked to delete their account. Approving deletes the account and its proposal for good. A request you do not approve within 48 hours lapses and the account is kept."
    approved="was deleted"
    rejected="keeps their account"
    dateField="deletion_requested_at"
  />
);
