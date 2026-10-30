import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Alerts, PageHeader } from "../components/ui";
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
        <span key={u} className="min-w-11 rounded-lg bg-zinc-900 px-1.5 py-1 text-center text-white" aria-hidden="true">
          <span className="block text-sm font-semibold leading-tight tabular-nums">{v}</span>
          <span className="block text-[10px] uppercase tracking-wide text-zinc-400">{u}</span>
        </span>
      ))}
    </span>
  );
}

// ISO string -> value for <input type="datetime-local"> in the browser's time zone.
const toLocalInput = (iso) => {
  const d = new Date(iso);
  return new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};

export default function DeadlinePage() {
  const [data, setData] = useState(null);
  const [offset, setOffset] = useState(0); // server clock minus browser clock
  const [now, setNow] = useState(Date.now());
  const { busy: saving, error, notice, setError, run } = useAction(); // busy key is the phase being saved

  const show = (res) => {
    setData(res);
    setOffset(new Date(res.now) - Date.now());
  };

  useEffect(() => {
    const load = () => api("/milestones").then(show).catch((err) => setError(err.message));
    load();
    // Status and late days come from the server, so refresh them now and then.
    const refresh = setInterval(load, 60000);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      clearInterval(refresh);
      clearInterval(tick);
    };
  }, [setError]);

  const save = (e, phase) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    run(phase, async () => {
      show(
        await api(`/milestones/${phase}`, {
          method: "PUT",
          body: {
            due_at: new Date(f.get("due_at")).toISOString(),
            grace_minutes: Number(f.get("grace_minutes")),
            penalty_per_day: Number(f.get("penalty_per_day")),
          },
        }),
      );
      return `${phase} deadline saved.`;
    });
  };

  const serverNow = now + offset;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Deadlines"
        intro="Each phase has a due date and a grace time. Work handed in after the grace time loses marks for every late day."
      />

      <Alerts error={error} notice={notice} />

      {!data ? (
        <div className="space-y-4" aria-hidden="true">
          {[0, 1, 2].map((i) => <div key={i} className="h-36 animate-pulse rounded-xl bg-zinc-100" />)}
        </div>
      ) : (
        <ol className="relative space-y-4 border-l border-zinc-200 pl-6">
          {data.milestones.map((m) => {
            const [label, tone, dot] = STATUS[m.status];
            return (
              <li key={m.phase} className="card relative p-6">
                <span className={`absolute -left-[31px] top-8 size-3 rounded-full ring-4 ring-zinc-50 ${dot}`} aria-hidden="true" />
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-semibold">{m.phase}</h2>
                    <span className={`badge ${tone}`}>{label}</span>
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
                    <div><dt className="text-zinc-500">Grace time</dt><dd className="font-medium tabular-nums">{m.grace_minutes} min</dd></div>
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
                    <label className="label sm:col-span-2">
                      Due date
                      <input name="due_at" type="datetime-local" required defaultValue={m.due_at ? toLocalInput(m.due_at) : ""} className="input" />
                    </label>
                    <label className="label">
                      Grace (min)
                      <input name="grace_minutes" type="number" min={0} max={data.max_grace_minutes} required defaultValue={m.grace_minutes} className="input" />
                    </label>
                    <label className="label">
                      Penalty (%/day)
                      <input name="penalty_per_day" type="number" min={0} max={data.max_penalty_per_day} required defaultValue={m.penalty_per_day} className="input" />
                    </label>
                    <button disabled={saving === m.phase} className="btn-primary sm:col-span-4 sm:justify-self-end">
                      {saving === m.phase ? "Saving..." : `Save ${m.phase}`}
                    </button>
                  </form>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
