import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Alerts, Icon, ICONS, PageHeader, Person, Skeleton } from "../components/ui";
import { when } from "../format";
import { useAction } from "../useAction";

const STATUS = {
  pending: ["Waiting for supervisor", "bg-amber-50 text-amber-800 ring-amber-600/20"],
  active: ["Active", "bg-teal-50 text-teal-800 ring-teal-600/20"],
  completed: ["Completed", "bg-teal-50 text-teal-800 ring-teal-600/20"],
  dropped: ["Archived", "bg-zinc-100 text-zinc-700 ring-zinc-300"],
};

const name = (f) => `${f.full_name}${f.initials ? ` (${f.initials})` : ""}`;

export default function ThesisPage() {
  const [state, setState] = useState(null);
  const [faculty, setFaculty] = useState([]);
  const [supervisor, setSupervisor] = useState("");
  const { busy, error, notice, setError, run } = useAction();

  useEffect(() => {
    api("/theses/mine").then(setState).catch((err) => setError(err.message));
    api("/theses/faculty").then(setFaculty).catch((err) => setError(err.message));
  }, [setError]);

  const submit = (e) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    run("ask", async () => {
      const co = f.get("co_supervisor_id");
      setState(await api("/theses/mine", {
        method: "POST",
        body: { supervisor_id: Number(f.get("supervisor_id")), co_supervisor_id: co ? Number(co) : null },
      }));
      return "Request sent. Your thesis ID is created when your supervisor accepts.";
    });
  };

  const cancel = () => run("cancel", async () => {
    setState(await api("/theses/mine", { method: "DELETE" }));
    return "Request cancelled. You can choose a supervisor again.";
  });

  const register = () => run("register", async () => {
    setState(await api("/theses/mine/register", { method: "POST" }));
    return "Your group is registered for P1 this semester.";
  });

  const restart = () => run("restart", async () => {
    await api("/auth/me/restart-request", { method: "POST" });
    setState(await api("/theses/mine"));
    return "Restart requested. The coordinator will review it.";
  });

  const t = state?.thesis;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Thesis group"
        intro="You need a thesis group to upload proposals: you, a supervisor and, if you like, a co-supervisor. Every proposal version is kept under your thesis ID."
      />

      <Alerts error={error} notice={notice} />

      {!state ? (
        <Skeleton rows={2} row="h-28 rounded-xl" className="space-y-4" />
      ) : (
        <>
          <section className="card flex flex-wrap items-center justify-between gap-4 p-6">
            <div>
              <p className="text-sm text-zinc-500">Current phase</p>
              <p className="mt-1 text-2xl font-semibold">{state.phase ?? "Thesis complete"}</p>
            </div>
            {t?.code && (
              <div className="text-right">
                <p className="text-sm text-zinc-500">Thesis ID</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums">{t.code}</p>
              </div>
            )}
          </section>

          {state.frozen_reason && (
            <section role="alert" className="card space-y-3 bg-red-50/60 p-6 ring-red-200">
              <p className="flex items-start gap-2 font-medium text-red-800">
                <Icon className="mt-0.5 size-5">{ICONS.alert}</Icon>
                {state.frozen_reason}, so your account is frozen.
              </p>
              <p className="text-sm text-red-900/80">
                You can still log in and see your work, but you can't upload. Ask the coordinator to let you start again at P1.
                If approved, you start fresh at P1 next semester: your current thesis will be archived and your new group gets a new thesis ID.
              </p>
              {state.restart_approved ? (
                <p className="text-sm font-medium text-red-900">Restart approved. You start fresh at P1 next semester.</p>
              ) : state.restart_pending ? (
                <p className="text-sm font-medium text-red-900">Restart requested. Waiting for the coordinator.</p>
              ) : (
                <button onClick={restart} disabled={busy === "restart"} className="btn-danger">
                  {busy === "restart" ? "Sending…" : "Request restart at P1"}
                </button>
              )}
            </section>
          )}

          {t && (
            <section className="card space-y-5 p-6">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="font-semibold">Your group</h2>
                <span className={`badge ${STATUS[t.status][1]}`}>{STATUS[t.status][0]}</span>
              </div>
              {t.deferrals > 0 && t.status === "active" && !state.frozen_reason && (
                <p className="alert-error">
                  <Icon className="mt-px size-4">{ICONS.alert}</Icon>
                  <span>Your thesis was deferred. Submit P3 again this semester. Another deferral freezes your account.</span>
                </p>
              )}
              <div className="space-y-4">
                <div>
                  <p className="mb-2 text-sm text-zinc-500">Supervisor</p>
                  {t.supervisor && <Person user={t.supervisor} />}
                </div>
                {t.co_supervisor && (
                  <div>
                    <p className="mb-2 text-sm text-zinc-500">
                      Co-supervisor{!t.co_supervisor_accepted && " (waiting to accept)"}
                    </p>
                    <Person user={t.co_supervisor} />
                  </div>
                )}
              </div>
              {t.status === "pending" && (
                <button onClick={cancel} disabled={busy === "cancel"} className="btn-secondary">
                  {busy === "cancel" ? "Cancelling…" : "Cancel request"}
                </button>
              )}
            </section>
          )}

          {state.phase === "P1" && t?.status === "active" && !state.frozen_reason && (
            <section className="card flex flex-wrap items-center justify-between gap-4 p-6">
              <div className="max-w-prose">
                <h2 className="font-semibold">P1 registration</h2>
                <p className="mt-1 text-sm text-zinc-600">
                  {t.p1_registered
                    ? "Your group is registered for P1 this semester."
                    : state.registration_open
                      ? <>Register your group to work on P1 this semester. Open until <span className="font-medium tabular-nums">{when(state.registration_closes_at)}</span>.</>
                      : "P1 registration is closed. Your group can register in the first week of next semester; nothing is due for you until then."}
                </p>
              </div>
              {state.can_register && (
                <button onClick={register} disabled={busy === "register"} className="btn-primary">
                  {busy === "register" ? "Registering…" : "Register for P1"}
                </button>
              )}
            </section>
          )}

          {state.can_form_group && (
            <form onSubmit={submit} className="card max-w-xl space-y-5 p-6">
              <h2 className="font-semibold">Form your thesis group</h2>
              <label className="label">
                Supervisor
                <select name="supervisor_id" required value={supervisor} onChange={(e) => setSupervisor(e.target.value)} className="input">
                  <option value="" disabled>Choose a faculty member</option>
                  {faculty.map((f) => <option key={f.id} value={f.id}>{name(f)}</option>)}
                </select>
              </label>
              <label className="label">
                Co-supervisor (optional)
                <select name="co_supervisor_id" defaultValue="" className="input">
                  <option value="">None</option>
                  {faculty.filter((f) => String(f.id) !== supervisor).map((f) => <option key={f.id} value={f.id}>{name(f)}</option>)}
                </select>
              </label>
              <button disabled={busy === "ask" || !faculty.length} className="btn-primary w-full">
                {busy === "ask" ? "Sending…" : "Send request"}
              </button>
            </form>
          )}
        </>
      )}
    </div>
  );
}
