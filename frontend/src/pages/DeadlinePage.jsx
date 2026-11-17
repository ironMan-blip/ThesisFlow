import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { Alerts, ConfirmDialog, PageHeader, Skeleton } from "../components/ui";
import { when } from "../format";
import { useAction } from "../useAction";

// status -> [label, badge tone, timeline dot]
const STATUS = {
  not_set: ["Not set", "bg-zinc-50 text-zinc-600 ring-zinc-200", "bg-zinc-300"],
  open: ["Open", "bg-teal-50 text-teal-800 ring-teal-600/20", "bg-teal-600"],
  grace: ["Grace time", "bg-amber-50 text-amber-800 ring-amber-600/20", "bg-amber-500"],
  closed: ["Closed", "bg-zinc-100 text-zinc-700 ring-zinc-300", "bg-zinc-400"],
};

const pad = (n) => String(n).padStart(2, "0");

function Countdown({ ms }) {
  const s = Math.max(0, Math.floor(ms / 1000));
  const parts = [[Math.floor(s / 86400), "days"], [pad(Math.floor(s / 3600) % 24), "hrs"], [pad(Math.floor(s / 60) % 60), "min"], [pad(s % 60), "sec"]];
  return (
    <span className="flex gap-1.5">
      <span className="sr-only">{parts.map(([v, u]) => `${v} ${u}`).join(" ")}</span>
      {parts.map(([v, u]) => (
        <span key={u} className="min-w-11 rounded-lg bg-zinc-50 px-1.5 py-1 text-center ring-1 ring-zinc-200 ring-inset" aria-hidden="true">
          <span className="block text-sm font-semibold leading-tight text-zinc-900 tabular-nums">{v}</span>
          <span className="block text-[10px] uppercase tracking-wide text-zinc-500">{u}</span>
        </span>
      ))}
    </span>
  );
}

export default function DeadlinePage() {
  const [data, setData] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [offset, setOffset] = useState(0); // server clock minus browser clock
  const [semesterId, setSemesterId] = useState(null); // coordinator: whose deadlines to show; null = current semester
  const [now, setNow] = useState(Date.now());
  const { busy: saving, error, notice, setError, run, clear } = useAction(); // busy key is the phase being saved

  const show = useCallback((res) => {
    setData(res);
    setOffset(new Date(res.now) - Date.now());
  }, []);

  const load = useCallback(
    () => api(semesterId ? `/milestones?semester_id=${semesterId}` : "/milestones").then(show).catch((err) => setError(err.message)),
    [semesterId, show, setError],
  );

  useEffect(() => {
    load();
    // Status and late days come from the server, so refresh them now and then.
    const refresh = setInterval(load, 60000);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      clearInterval(refresh);
      clearInterval(tick);
    };
  }, [load]);

  const save = (e, phase) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    run(phase, async () => {
      show(
        await api(`/milestones/${phase}`, {
          method: "PUT",
          body: {
            due_local: `${f.get("due_date")}T${f.get("due_time")}`, // Dhaka time; the server converts it
            grace_days: Number(f.get("grace_days")),
            penalty_per_day: Number(f.get("penalty_per_day")),
            semester_id: data.semester_id,
          },
        }),
      );
      return `${phase} deadline saved.`;
    });
  };

  const saveRegistration = (e) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    run("registration", async () => {
      show(
        await api("/milestones/registration", {
          method: "PUT",
          body: { opens_local: f.get("opens_local"), closes_local: f.get("closes_local") }, // Dhaka time
        }),
      );
      return "P1 registration dates saved.";
    });
  };

  const serverNow = now + offset;

  // A countdown hit zero: fetch at once so open -> grace -> closed and late days update without waiting a minute.
  const reachedZero = !!data?.milestones.some((m) => m.countdown_to && new Date(m.countdown_to) <= serverNow);
  useEffect(() => {
    if (reachedZero) load();
  }, [reachedZero, load]);

  const nextSemester = () => {
    setConfirming(false);
    run("semester", async () => {
      const r = await api("/milestones/next-semester", { method: "POST" });
      setSemesterId(null);
      show(await api("/milestones"));
      return `New semester started. Thesis groups: ${r.advanced} moved to the next phase, ${r.completed} completed, ${r.deferred} deferred, ${r.cancelled} cancelled, ${r.frozen} frozen. Students restarted at P1: ${r.restarted}. Set the new deadlines below.`;
    });
  };

  return (
    <div className="space-y-8">
      <PageHeader
        title="Deadlines"
        intro="Each phase has a due date and a grace time. Work handed in during the grace time loses marks for every late day; after it ends, uploads close."
      />

      {data?.can_edit && (
        <section className="card flex flex-wrap items-center justify-between gap-4 p-6">
          <div className="max-w-prose">
            <h2 className="font-semibold">End this semester</h2>
            <p className="mt-1 text-sm text-zinc-600">
              Thesis groups that submitted move to their next phase, P3 theses are completed or deferred (a second deferral
              cancels the thesis), groups that missed a closed deadline are frozen, and approved restarts start fresh.
              Deadlines are kept: groups still working to last semester's deadline carry on with it. Set the new
              semester's deadlines below.
              P1 registration then opens for one week, unless you set other dates below.
            </p>
          </div>
          <button onClick={() => setConfirming(true)} disabled={saving === "semester"} className="btn-primary">
            {saving === "semester" ? "Starting…" : "Start next semester"}
          </button>
        </section>
      )}

      <Alerts error={error} notice={notice} floating onDismiss={clear} />

      {data && (data.can_edit || data.registration_closes_at) && (
        <section className="card p-6">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold">P1 registration</h2>
            {(() => {
              const [label, tone] = data.registration_status === "upcoming" ? ["Not open yet", STATUS.not_set[1]] : STATUS[data.registration_status];
              return <span className={`badge ${tone}`}>{label}</span>;
            })()}
          </div>
          <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
            <div><dt className="text-zinc-500">Opens</dt><dd className="font-medium">{data.registration_opens_at ? when(data.registration_opens_at) : "Not set"}</dd></div>
            <div><dt className="text-zinc-500">Closes</dt><dd className="font-medium">{data.registration_closes_at ? when(data.registration_closes_at) : "Not set"}</dd></div>
          </dl>
          {data.can_edit && (
            <form onSubmit={saveRegistration} className="mt-5 grid items-end gap-3 border-t border-zinc-100 pt-5 sm:grid-cols-3">
              <label className="label">
                Opens (Dhaka)
                <input name="opens_local" type="datetime-local" required defaultValue={data.registration_opens_local ?? ""} className="input" />
              </label>
              <label className="label">
                Closes (Dhaka)
                <input name="closes_local" type="datetime-local" required defaultValue={data.registration_closes_local ?? ""} className="input" />
              </label>
              <button disabled={saving === "registration"} className="btn-primary sm:justify-self-end">
                {saving === "registration" ? "Saving…" : "Save registration"}
              </button>
              <p className="text-sm text-zinc-500 sm:col-span-3">P1 can only be due after registration closes.</p>
            </form>
          )}
        </section>
      )}

      {data?.can_edit && (
        <section className="card flex flex-wrap items-end justify-between gap-4 p-6">
          <p className="max-w-prose text-sm text-zinc-600">
            Each semester has its own deadlines. Groups work to the deadlines of the semester they registered for P1
            in, or moved into their phase in, even after the next semester starts.
          </p>
          <label className="label">
            Deadlines for
            <select value={data.semester_id ?? ""} onChange={(e) => setSemesterId(Number(e.target.value))} className="input">
              {data.semesters.map((s, i) => <option key={s.id} value={s.id}>{s.name}{i === 0 ? " (current)" : ""}</option>)}
            </select>
          </label>
        </section>
      )}

      {!data ? (
        <Skeleton rows={3} row="h-36 rounded-xl" className="space-y-4" />
      ) : (
        <ol className="relative space-y-4 border-l border-zinc-200 pl-6">
          {data.milestones.map((m) => {
            const [label, tone, dot] = STATUS[m.status];
            return (
              <li key={`${data.semester_id}-${m.phase}`} className={`card relative p-6 ${m.mine ? "ring-2 ring-teal-600/40" : ""}`}>
                <span className={`absolute -left-[31px] top-8 size-3 rounded-full ring-4 ring-zinc-50 ${dot}`} aria-hidden="true" />
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-semibold">{m.phase}</h2>
                    <span className={`badge ${tone}`}>{label}</span>
                    {m.semester_name && <span className="badge bg-zinc-100 text-zinc-700 ring-zinc-300">For {m.semester_name}</span>}
                    {m.mine && <span className="badge bg-teal-700 text-white ring-teal-700">Your phase</span>}
                  </div>
                  {m.countdown_to && (
                    <div className="flex items-center gap-3 text-sm text-zinc-600">
                      {m.countdown_label}
                      <Countdown ms={new Date(m.countdown_to) - serverNow} />
                    </div>
                  )}
                </div>

                {m.due_at ? (
                  <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
                    <div><dt className="text-zinc-500">Due</dt><dd className="font-medium">{when(m.due_at)}</dd></div>
                    <div><dt className="text-zinc-500">Grace time</dt><dd className="font-medium tabular-nums">{m.grace_days} {m.grace_days === 1 ? "day" : "days"}</dd></div>
                    <div><dt className="text-zinc-500">Late penalty</dt><dd className="font-medium tabular-nums">{m.penalty_per_day}% per day</dd></div>
                  </dl>
                ) : (
                  <p className="mt-3 text-sm text-zinc-500">The coordinator has not set this deadline yet.</p>
                )}

                {m.submission_status && (
                  <p className="mt-4 rounded-lg bg-zinc-50 px-3 py-2 text-sm ring-1 ring-zinc-200/70 ring-inset">
                    {m.submitted_at ? <>Submitted {when(m.submitted_at)}</> : "Not submitted yet"}
                    {m.submission_status === "late" && (
                      <span className="font-medium text-red-700">
                        {" "}· {m.late_days} late {m.late_days === 1 ? "day" : "days"} · −{m.penalty_percent}%
                      </span>
                    )}
                    {m.submission_status === "on_time" && <span className="font-medium text-teal-800"> · On time</span>}
                  </p>
                )}

                {data.can_edit && (
                  <form onSubmit={(e) => save(e, m.phase)} className="mt-5 grid items-end gap-3 border-t border-zinc-100 pt-5 sm:grid-cols-4">
                    <label className="label">
                      Due date
                      <input name="due_date" type="date" required defaultValue={m.due_date ?? ""} className="input" />
                    </label>
                    <label className="label">
                      Due time (Dhaka)
                      <input name="due_time" type="time" required defaultValue={m.due_time} className="input" />
                    </label>
                    <label className="label">
                      Grace (days)
                      <input name="grace_days" type="number" min={0} max={data.max_grace_days} required defaultValue={m.grace_days} className="input" />
                    </label>
                    <label className="label">
                      Penalty (%/day)
                      <input name="penalty_per_day" type="number" min={0} max={data.max_penalty_per_day} required defaultValue={m.penalty_per_day} className="input" />
                    </label>
                    <button disabled={saving === m.phase} className="btn-primary sm:col-span-4 sm:justify-self-end">
                      {saving === m.phase ? "Saving…" : `Save ${m.phase}`}
                    </button>
                  </form>
                )}
              </li>
            );
          })}
        </ol>
      )}

      <ConfirmDialog open={confirming} title="Start the next semester?" confirm="Yes, start it"
        onCancel={() => setConfirming(false)} onConfirm={nextSemester}>
        This moves every student on. This semester's deadlines are kept for the groups still working to them. It cannot be undone.
      </ConfirmDialog>
    </div>
  );
}
