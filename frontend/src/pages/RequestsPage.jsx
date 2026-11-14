import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api } from "../api/client";
import { Alerts, DecideButtons, EmptyState, ICONS, PageHeader, Person, Skeleton } from "../components/ui";
import { when } from "../format";
import { useAction } from "../useAction";

// Coordinator inbox of requests to approve or reject; the pages exported below configure it.
function RequestsPage({ path, title, intro, approved, rejected, dateField }) {
  const [requests, setRequests] = useState(null);
  const { user, refreshCounts } = useOutletContext();
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
      <PageHeader title={title} intro={intro(user.review_hours)} />

      <Alerts error={error} notice={notice} />

      <section className="card overflow-hidden">
        {!requests ? (
          <Skeleton />
        ) : requests.length === 0 ? (
          <EmptyState icon={ICONS.check} title="You're all caught up">No pending requests right now. New ones appear here automatically.</EmptyState>
        ) : (
          <>
            <p className="border-b border-zinc-200 px-4 py-3 text-sm font-medium tabular-nums text-zinc-700 sm:px-6">
              {requests.length} pending {requests.length === 1 ? "request" : "requests"}
            </p>
            <ul className="divide-y divide-zinc-100">
              {requests.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
                  <Person user={r}> · requested {when(r[dateField])}</Person>
                  <DecideButtons busy={busy === r.id} onReject={() => decide(r, false)} onApprove={() => decide(r, true)} />
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}

export const RegistrationRequestsPage = () => (
  <RequestsPage
    path="/auth/registration-requests"
    title="Registration requests"
    intro={(h) => `Students and faculty who registered wait here until you approve them. Please review each request within ${h} hours.`}
    approved="was approved and can now log in"
    rejected="was rejected"
    dateField="created_at"
  />
);

export const DeletionRequestsPage = () => (
  <RequestsPage
    path="/auth/deletion-requests"
    title="Deletion requests"
    intro={(h) => `Users who asked to delete their account. Approving deletes the account. Its thesis and every proposal version are kept as an archive. A request you do not approve within ${h} hours lapses and the account is kept.`}
    approved="was deleted"
    rejected="keeps their account"
    dateField="deletion_requested_at"
  />
);

export const RestartRequestsPage = () => (
  <RequestsPage
    path="/auth/restart-requests"
    title="Restart requests"
    intro={() => "Students whose account froze after a missed deadline or a second deferral. Approving moves them back to P1 at the next semester rollover, fully fresh: their old thesis is archived with all its versions, and their next group gets a new thesis ID."}
    approved="restarts at P1 next semester"
    rejected="stays frozen"
    dateField="restart_requested_at"
  />
);
