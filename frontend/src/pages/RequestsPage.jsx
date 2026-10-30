import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api } from "../api/client";
import { Alerts, PageHeader } from "../components/ui";
import { when } from "../format";
import { TOOLS } from "../tools";
import { useAction } from "../useAction";

// Coordinator inbox of requests to approve or reject; RegistrationRequestsPage and DeletionRequestsPage configure it.
function RequestsPage({ path, title, intro, approved, rejected, dateField }) {
  const [requests, setRequests] = useState(null);
  const { refreshCounts } = useOutletContext();
  const { busy, error, notice, setError, run } = useAction(); // busy key is the request id being decided

  useEffect(() => {
    api(path).then(setRequests).catch((err) => setError(err.message));
  }, [path, setError]);

  const decide = (r, approve) =>
    run(r.id, async () => {
      await api(`${path}/${r.id}${approve ? "/approve" : ""}`, { method: approve ? "POST" : "DELETE" });
      setRequests((rs) => rs.filter((x) => x.id !== r.id));
      refreshCounts();
      return `${r.full_name} ${approve ? approved : rejected}.`;
    });

  return (
    <div className="space-y-8">
      <PageHeader title={title} intro={intro} />

      <Alerts error={error} notice={notice} />

      {!requests ? (
        <div className="h-24 animate-pulse rounded-xl bg-zinc-100" aria-hidden="true" />
      ) : requests.length === 0 ? (
        <p className="rounded-xl border border-dashed border-zinc-300 p-5 text-sm text-zinc-500">No pending requests.</p>
      ) : (
        <ul className="space-y-3">
          {requests.map((r) => (
            <li key={r.id} className="card flex flex-wrap items-center justify-between gap-4 p-5">
              <div>
                <p className="font-medium">{r.full_name}{r.initials && ` (${r.initials})`} <span className="text-sm font-normal capitalize text-zinc-500">· {r.role}</span></p>
                <p className="text-sm text-zinc-600">ID {r.id_number} · {r.email} · requested {when(r[dateField])}</p>
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

export const RegistrationRequestsPage = () => (
  <RequestsPage
    path={TOOLS.registration_requests.requests}
    title="Registration requests"
    intro="Students and faculty who registered wait here until you approve them. Please review each request within 48 hours."
    approved="was approved and can now log in"
    rejected="was rejected"
    dateField="created_at"
  />
);

export const DeletionRequestsPage = () => (
  <RequestsPage
    path={TOOLS.deletion_requests.requests}
    title="Deletion requests"
    intro="Users who asked to delete their account. Approving deletes the account and its proposal for good. A request you do not approve within 48 hours lapses and the account is kept."
    approved="was deleted"
    rejected="keeps their account"
    dateField="deletion_requested_at"
  />
);
