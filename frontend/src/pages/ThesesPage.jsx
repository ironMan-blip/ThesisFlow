import { useCallback, useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api, download } from "../api/client";
import { Alerts, DecideButtons, EmptyState, ICONS, PageHeader, Person, ReasonDialog, Skeleton, ThesisBadge, VersionInfo } from "../components/ui";
import { personName, when } from "../format";
import { useAction } from "../useAction";

const fullName = (p) => (p ? personName(p) : "Account deleted");

function Requests({ requests, decide, busy }) {
  if (!requests.length) return null;
  return (
    <section className="card overflow-hidden">
      <p className="border-b border-zinc-200 px-4 py-3 text-sm font-medium tabular-nums text-zinc-700 sm:px-6">
        {requests.length} supervision {requests.length === 1 ? "request" : "requests"}
      </p>
      <ul className="divide-y divide-zinc-100">
        {requests.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
            <Person user={r.student}>
              {" "}· {r.slot === "supervisor"
                ? "asks you to be their supervisor (accepting forms the group)"
                : r.slot === "co_supervisor"
                  ? `asks you to be co-supervisor of ${r.code ?? "their thesis"} (you join once ${fullName(r.supervisor)} also accepts)`
                  : `wants ${fullName(r.co_supervisor)} as co-supervisor of ${r.code ?? "their thesis"} (they join once you both accept)`}
            </Person>
            <DecideButtons busy={busy === r.id} onReject={() => decide(r, false)} onApprove={() => decide(r, true)}
              reject="Decline" approve="Accept" />
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function ThesesPage() {
  const { user, refreshCounts } = useOutletContext();
  const [theses, setTheses] = useState(null);
  const [requests, setRequests] = useState([]);
  const { busy, error, notice, setError, run, clear } = useAction();
  const [deleting, setDeleting] = useState(null); // version whose delete reason is being written

  const load = useCallback(async () => {
    setTheses(await api("/theses"));
    setRequests(await api("/theses/requests"));
  }, []);

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, [load, setError]);

  const decide = (r, accept) => run(r.id, async () => {
    // Names the co-supervisor shown here, so a swap made meanwhile is refused instead of approved unseen.
    const co = r.co_supervisor ? `?co_supervisor_id=${r.co_supervisor.id}` : "";
    try {
      await api(`/theses/requests/${r.id}/${accept ? "accept" : "decline"}${co}`, { method: "POST" });
    } finally {
      await load(); // a refused, stale request shows its current state
    }
    refreshCounts();
    return `${r.student.full_name}: request ${accept ? "accepted" : "declined"}.`;
  });

  const defer = (t, on) => run(`defer-${t.id}`, async () => {
    await api(`/theses/${t.id}/defer`, { method: "PUT", body: { defer: on } });
    await load();
    return on
      ? `${t.code ?? "The thesis"} will be deferred at the end of the semester.`
      : `${t.code ?? "The thesis"} will be completed at the end of the semester.`;
  });

  const get = (v) => download(v.download_path, v.original_filename).catch((err) => setError(err.message));

  const scheduleDelete = (reason) => {
    const v = deleting;
    run("delete", async () => {
      await api(`/proposals/versions/${v.id}/deletion`, { method: "POST", body: { reason } });
      await load();
      setDeleting(null);
      return `v${v.version_no} will be deleted in ${user.deletion_days} days. The student is told, with your reason; you can still cancel it.`;
    });
  };

  // The student's request: approve (starts the 7 days) or reject. A scheduled delete: cancel.
  const decideDelete = (v, approve) => run(`del-${v.id}`, async () => {
    const url = `/proposals/delete-requests/${v.id}`;
    await api(approve ? `${url}/approve` : url, { method: approve ? "POST" : "DELETE" });
    await load();
    refreshCounts();
    return approve
      ? `v${v.version_no} will be deleted in ${user.deletion_days} days unless you cancel it.`
      : v.delete_executes_at ? `The delete of v${v.version_no} is cancelled; it stays.` : `Request rejected: v${v.version_no} stays.`;
  });

  return (
    <div className="space-y-8">
      <PageHeader
        title="Theses"
        intro="Supervision requests, and every thesis you supervise or co-supervise."
        help={[
          "As the supervisor, you approve or reject a student's request to delete a proposal version.",
          "You can also delete a version yourself, with a reason. A phase's final version can't be deleted.",
          `Any delete runs ${user.deletion_days} days later. Until then you can cancel it.`,
          "After the P3 submission you can defer a thesis: once means P3 again next semester, twice freezes the student.",
        ]}
      />

      <Alerts error={deleting ? null : error} notice={notice} floating onDismiss={clear} />

      <Requests requests={requests} decide={decide} busy={busy} />

      {!theses ? (
        <Skeleton rows={3} row="h-28 rounded-xl" className="space-y-4" />
      ) : !theses.length ? (
        <section className="card"><EmptyState icon={ICONS.file} title="No theses yet">Thesis groups appear here once a supervisor accepts them.</EmptyState></section>
      ) : (
        <ul className="space-y-4">
          {theses.map((t) => (
            <li key={t.id} className="card p-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-lg font-semibold tabular-nums">{t.code ?? "Not registered for P1"}</h2>
                  <ThesisBadge status={t.status} />
                  {t.deferrals > 0 && <span className="badge bg-amber-50 text-amber-800 ring-amber-600/20">Deferred {t.deferrals}x</span>}
                  {t.defer_pending && <span className="badge bg-red-50 text-red-800 ring-red-600/20">Deferral at semester end</span>}
                </div>
                {t.can_defer && (
                  <button onClick={() => defer(t, !t.defer_pending)} disabled={busy === `defer-${t.id}`}
                    className={t.defer_pending ? "btn-secondary px-3 py-1.5" : "btn-ghost-danger px-3 py-1.5"}>
                    {t.defer_pending ? "Undo defer" : "Defer thesis"}
                  </button>
                )}
              </div>
              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
                <div><dt className="text-zinc-500">Student</dt><dd className="font-medium">{t.student ? `${t.student.full_name} · ID ${t.student.id_number}` : "Account deleted"}</dd></div>
                <div><dt className="text-zinc-500">Supervisor</dt><dd className="font-medium">{fullName(t.supervisor)}</dd></div>
                <div><dt className="text-zinc-500">Co-supervisor</dt><dd className="font-medium">
                  {!t.co_supervisor ? "None" : t.co_supervisor_joined ? fullName(t.co_supervisor) : `${fullName(t.co_supervisor)} (not joined yet)`}
                </dd></div>
              </dl>
              {t.versions.length > 0 ? (
                <ul className="mt-5 divide-y divide-zinc-100 border-t border-zinc-100">
                  {t.versions.map((v) => (
                    <li key={v.id} className="space-y-2 py-3">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                      <VersionInfo v={v} />
                      <div className="flex flex-wrap items-center gap-2">
                        {v.delete_pending && (
                          <span className="badge bg-amber-50 text-amber-800 ring-amber-600/20">
                            {v.delete_executes_at ? `Deletes on ${when(v.delete_executes_at)}` : "Delete requested by the student"}
                          </span>
                        )}
                        <button onClick={() => get(v)} className="btn-secondary px-3 py-1.5">Download</button>
                        {t.is_supervisor && v.delete_pending && (v.delete_executes_at ? (
                          <button onClick={() => decideDelete(v, false)} disabled={busy === `del-${v.id}`} className="btn-secondary px-3 py-1.5">Cancel delete</button>
                        ) : (
                          <DecideButtons busy={busy === `del-${v.id}`} onReject={() => decideDelete(v, false)} onApprove={() => decideDelete(v, true)}
                            approve="Approve delete" />
                        ))}
                        {v.can_schedule_delete && (
                          <button onClick={() => { setError(null); setDeleting(v); }} aria-label={`Delete v${v.version_no}`}
                            className="btn-ghost-danger px-3 py-1.5">Delete</button>
                        )}
                      </div>
                      </div>
                      {v.delete_pending && v.delete_reason && (
                        <p className="whitespace-pre-line break-words rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-amber-600/20 ring-inset">
                          Reason{v.delete_by_staff ? (t.is_supervisor ? " (yours)" : " from the supervisor") : " from the student"}: {v.delete_reason}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-4 text-sm text-zinc-500">No proposal versions yet.</p>
              )}
            </li>
          ))}
        </ul>
      )}

      <ReasonDialog open={!!deleting} title={`Delete v${deleting?.version_no}?`} confirm="Schedule delete" busy={busy === "delete"}
        error={error} min={user.min_reason_chars} max={user.max_reason_chars} onCancel={() => setDeleting(null)} onSubmit={scheduleDelete}>
        The version and its PDF are deleted {user.deletion_days} days from now and later versions are renumbered. The student
        sees your reason and can contact you; you can cancel it until then. A phase's final version can't be deleted.
      </ReasonDialog>
    </div>
  );
}
