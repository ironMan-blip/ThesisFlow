import { useCallback, useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api, download } from "../api/client";
import { Alerts, DecideButtons, EmptyState, ICONS, PageHeader, Person, Skeleton, ThesisBadge, VersionInfo } from "../components/ui";
import { personName } from "../format";
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
            <Person user={r.student}> · asks you to be {r.slot === "supervisor" ? "supervisor" : "co-supervisor"}</Person>
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
  const isFaculty = user.role === "faculty";
  const [theses, setTheses] = useState(null);
  const [requests, setRequests] = useState([]);
  const { busy, error, notice, setError, run } = useAction();

  const load = useCallback(async () => {
    setTheses(await api("/theses"));
    if (isFaculty) setRequests(await api("/theses/requests"));
  }, [isFaculty]);

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, [load, setError]);

  const decide = (r, accept) => run(r.id, async () => {
    await api(`/theses/requests/${r.id}/${accept ? "accept" : "decline"}`, { method: "POST" });
    await load();
    refreshCounts();
    return `${r.student.full_name}: request ${accept ? "accepted" : "declined"}.`;
  });

  const defer = (t, on) => run(`defer-${t.id}`, async () => {
    await api(`/theses/${t.id}/defer`, { method: "PUT", body: { defer: on } });
    await load();
    return on
      ? `${t.code} will be deferred at the end of the semester.`
      : `${t.code} will be completed at the end of the semester.`;
  });

  const get = (v) => download(v.download_path, v.original_filename).catch((err) => setError(err.message));

  return (
    <div className="space-y-8">
      <PageHeader
        title="Theses"
        intro={isFaculty
          ? "Students who asked you to supervise them, and the theses you supervise with every proposal version."
          : "Every thesis group, archived ones included. After a P3 submission you can defer a thesis: once means P3 again next semester, twice freezes the student. Theses not deferred are completed when you start the next semester."}
      />

      <Alerts error={error} notice={notice} />

      {isFaculty && <Requests requests={requests} decide={decide} busy={busy} />}

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
                  <h2 className="text-lg font-semibold tabular-nums">{t.code}</h2>
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
                <div><dt className="text-zinc-500">Co-supervisor</dt><dd className="font-medium">{t.co_supervisor_accepted ? fullName(t.co_supervisor) : "None"}</dd></div>
              </dl>
              {t.versions.length > 0 ? (
                <ul className="mt-5 divide-y divide-zinc-100 border-t border-zinc-100">
                  {t.versions.map((v) => (
                    <li key={v.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                      <VersionInfo v={v} />
                      <button onClick={() => get(v)} className="btn-secondary px-3 py-1.5">Download</button>
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
    </div>
  );
}
