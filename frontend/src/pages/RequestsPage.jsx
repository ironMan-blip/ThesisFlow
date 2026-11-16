import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api, download } from "../api/client";
import { Alerts, DecideButtons, EmptyState, ICONS, PageHeader, Person, Skeleton, VersionInfo } from "../components/ui";
import { when } from "../format";
import { useAction } from "../useAction";

// Coordinator inbox of requests to approve or reject; the pages exported below configure it.
// person(r): who asked (the row itself for account requests); details(r): extra content under the person.
// executesAt(r): for deletions only. Null means waiting for approval (approve or reject); a date means approved, so
// it runs by itself then and the coordinator can only cancel it.
function RequestsPage({ path, title, intro, approved, rejected, dateField, person = (r) => r, details, executesAt }) {
  const [requests, setRequests] = useState(null);
  const { user, refreshCounts } = useOutletContext();
  const { busy, error, notice, setError, run } = useAction(); // busy key is the request id being decided

  useEffect(() => {
    api(path).then(setRequests).catch((err) => setError(err.message));
  }, [path, setError]);

  const decide = (r, approve) =>
    run(r.id, async () => {
      await api(`${path}/${r.id}${approve ? "/approve" : ""}`, { method: approve ? "POST" : "DELETE" });
      // An approved deletion stays listed (it can still be cancelled), so reload instead of dropping the row.
      if (approve && executesAt) setRequests(await api(path));
      else setRequests((rs) => rs.filter((x) => x.id !== r.id));
      refreshCounts();
      return `${person(r).full_name} ${approve ? approved : rejected}.`;
    });

  return (
    <div className="space-y-8">
      <PageHeader title={title} intro={intro(user)} />

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
                  <div className="min-w-0 space-y-3">
                    <Person user={person(r)}> · requested {when(r[dateField])}</Person>
                    {details?.(r, setError)}
                  </div>
                  {executesAt?.(r) ? (
                    <button onClick={() => decide(r, false)} disabled={busy === r.id} className="btn-secondary px-3 py-1.5">
                      {busy === r.id ? "Saving…" : "Cancel deletion"}
                    </button>
                  ) : (
                    <DecideButtons busy={busy === r.id} onReject={() => decide(r, false)} onApprove={() => decide(r, true)} />
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}

// When a scheduled delete runs, who asked, and why.
function ScheduledDelete({ executesAt, by, reason }) {
  return (
    <div className="rounded-lg bg-amber-50 px-3 py-2.5 text-sm text-amber-900 ring-1 ring-amber-600/20 ring-inset">
      <p className="font-medium">
        {executesAt ? `Approved: deletes on ${when(executesAt)}` : "Waiting for your decision"} · asked by {by}
      </p>
      <p className="mt-1 whitespace-pre-line break-words text-amber-800">{reason}</p>
    </div>
  );
}

export const RegistrationRequestsPage = () => (
  <RequestsPage
    path="/auth/registration-requests"
    title="Registration requests"
    intro={(u) => `Students and faculty who registered wait here until you approve them. Please review each request within ${u.review_hours} hours.`}
    approved="was approved and can now log in"
    rejected="was rejected"
    dateField="created_at"
  />
);

export const DeletionRequestsPage = () => (
  <RequestsPage
    path="/auth/deletion-requests"
    title="Deletion requests"
    intro={(u) => `Account deletions, each with its reason. Approve or reject a request. An approved account is deleted ${u.deletion_days} days after you approve it, unless you cancel it here before then; nobody else can. The thesis and every proposal version are kept as an archive. If a faculty member takes on a thesis meanwhile, their deletion is dropped.`}
    approved="will be deleted after the waiting period"
    rejected="keeps their account"
    dateField="deletion_requested_at"
    executesAt={(r) => r.deletion_executes_at}
    details={(r) => (
      <ScheduledDelete executesAt={r.deletion_executes_at} by={r.deletion_by_coordinator ? "the coordinator" : "the account owner"} reason={r.deletion_reason} />
    )}
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

export const VersionDeleteRequestsPage = () => (
  <RequestsPage
    path="/proposals/delete-requests"
    title="Version delete requests"
    intro={(u) => `Proposal versions students asked to delete, each with its reason. Approve or reject a request. An approved version and its PDF are deleted ${u.deletion_days} days after you approve it (later versions are renumbered), unless you cancel it here before then; nobody else can. If the phase closes first, the version is a final submission and is kept.`}
    approved="will have the version deleted after the waiting period"
    rejected="keeps the version"
    dateField="delete_requested_at"
    person={(r) => r.student}
    executesAt={(r) => r.delete_executes_at}
    details={(r, setError) => (
      <div className="space-y-2">
      <ScheduledDelete executesAt={r.delete_executes_at} by="the student" reason={r.delete_reason} />
      <div className="flex flex-wrap items-start gap-3 rounded-lg bg-zinc-50 p-3 ring-1 ring-zinc-200/70 ring-inset">
        <VersionInfo v={r} />
        <button onClick={() => download(r.download_path, r.original_filename).catch((err) => setError(err.message))}
          className="btn-secondary px-3 py-1.5">Download</button>
        {r.thesis_code && <span className="badge bg-white font-semibold tabular-nums text-zinc-700 ring-zinc-200">{r.thesis_code}</span>}
      </div>
      </div>
    )}
  />
);
