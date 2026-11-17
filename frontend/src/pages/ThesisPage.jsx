import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { Alerts, Icon, ICONS, PageHeader, Person, Skeleton, ThesisBadge } from "../components/ui";
import { memberNames, personName, when } from "../format";
import { useAction } from "../useAction";
import GroupSection from "./GroupSection";

export default function ThesisPage() {
  const [state, setState] = useState(null);
  const [supervisor, setSupervisor] = useState("");
  const { busy, error, notice, setError, run, clear } = useAction();

  const load = useCallback(() => api("/theses/mine").then(setState).catch((err) => setError(err.message)), [setError]);
  useEffect(() => { load(); }, [load]);
  // Bumped after registering for P1, which locks the group: remounting GroupSection fetches its new state.
  const [groupKey, setGroupKey] = useState(0);

  const submit = (e) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    run("ask", async () => {
      setState(await api("/theses/mine", { method: "POST", body: { supervisor_id: Number(f.get("supervisor_id")) } }));
      return "Request sent. Your group is formed, with its thesis ID, when your supervisor accepts. You can add a co-supervisor after that.";
    });
  };

  const addCo = (e) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    run("co", async () => {
      setState(await api("/theses/mine/co-supervisor", { method: "POST", body: { co_supervisor_id: Number(f.get("co_supervisor_id")) } }));
      return "Co-supervisor asked. They join your group once both they and your supervisor accept.";
    });
  };

  const cancelCo = () => run("cancel-co", async () => {
    setState(await api("/theses/mine/co-supervisor", { method: "DELETE" }));
    return "Co-supervisor request withdrawn.";
  });

  const cancel = () => run("cancel", async () => {
    setState(await api("/theses/mine", { method: "DELETE" }));
    return "Request cancelled. You can choose a supervisor again.";
  });

  const register = () => run("register", async () => {
    setState(await api("/theses/mine/register", { method: "POST" }));
    setGroupKey((k) => k + 1);
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
        intro="Form your group with other students, then choose a supervisor. You need both before you can upload proposals."
        help={[
          "Create a group or accept an invitation. Invite teammates from Find teammates.",
          "Once your group has at least 3 members, any member can choose a supervisor and send the request. The thesis belongs to the whole group, and it forms when the supervisor accepts.",
          "After that any member can add a co-supervisor. They join when both they and your supervisor accept.",
          "Students can join or leave until your group registers for P1. After that, the group is fixed.",
          "Every proposal version is kept under your thesis ID.",
        ]}
      />

      <Alerts error={error} notice={notice} floating onDismiss={clear} />

      {/* Where the student stands comes first; the steps to get further follow below. */}
      {state && (
        <section className="card flex flex-wrap items-center justify-between gap-4 p-6">
          <div>
            <p className="text-sm text-zinc-500">Current phase</p>
            <p className="mt-1 text-2xl font-semibold">{state.phase ?? (t?.status === "completed" ? "Thesis complete" : "No thesis yet")}</p>
          </div>
          {t?.code && (
            <div className="text-right">
              <p className="text-sm text-zinc-500">Thesis ID</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">{t.code}</p>
            </div>
          )}
        </section>
      )}

      <GroupSection key={groupKey} onChange={load} />

      {!state ? (
        <Skeleton rows={2} row="h-28 rounded-xl" className="space-y-4" />
      ) : (
        <>

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
                <ThesisBadge status={t.status} />
              </div>
              {state.show_deferral_warning && (
                <p className="alert-error">
                  <Icon className="mt-px size-4">{ICONS.alert}</Icon>
                  <span>Your thesis was deferred. Submit P3 again this semester. Another deferral freezes your account.</span>
                </p>
              )}
              <div className="space-y-4">
                <div>
                  <p className="mb-2 text-sm text-zinc-500">Students</p>
                  <p className="font-medium">{memberNames(t)}</p>
                </div>
                <div>
                  <p className="mb-2 text-sm text-zinc-500">
                    Supervisor{t.status === "pending" && " (waiting to accept)"}
                  </p>
                  {t.supervisor && <Person user={t.supervisor} />}
                </div>
                {t.co_supervisor && (
                  <div>
                    <p className="mb-2 text-sm text-zinc-500">
                      Co-supervisor
                      {!t.co_supervisor_joined &&
                        ` (waiting for ${[!t.co_supervisor_accepted && "them", !t.co_supervisor_approved && "your supervisor"].filter(Boolean).join(" and ")} to accept)`}
                    </p>
                    <Person user={t.co_supervisor} />
                  </div>
                )}
              </div>
              {state.can_cancel && (
                <button onClick={cancel} disabled={busy === "cancel"} className="btn-secondary">
                  {busy === "cancel" ? "Cancelling…" : "Cancel request"}
                </button>
              )}
              {state.can_cancel_co_supervisor && (
                <button onClick={cancelCo} disabled={busy === "cancel-co"} className="btn-secondary">
                  {busy === "cancel-co" ? "Withdrawing…" : "Withdraw co-supervisor request"}
                </button>
              )}
              {state.can_add_co_supervisor && (
                <form onSubmit={addCo} className="flex flex-wrap items-end gap-3 border-t border-zinc-100 pt-5">
                  <label className="label min-w-56 flex-1">
                    Add a co-supervisor (optional)
                    <select name="co_supervisor_id" required defaultValue="" className="input">
                      <option value="" disabled>Choose a faculty member</option>
                      {state.faculty_choices.map((f) => <option key={f.id} value={f.id}>{personName(f)}</option>)}
                    </select>
                  </label>
                  <button disabled={busy === "co"} className="btn-secondary">{busy === "co" ? "Sending…" : "Ask"}</button>
                </form>
              )}
            </section>
          )}

          {state.show_p1_registration && (
            <section className="card flex flex-wrap items-center justify-between gap-4 p-6">
              <div className="max-w-prose">
                <h2 className="font-semibold">P1 registration</h2>
                <p className="mt-1 text-sm text-zinc-600">
                  {t.p1_registered
                    ? "Your group is registered for P1 this semester."
                    : state.registration_open
                      ? <>Register your group to work on P1 this semester. Open until <span className="font-medium tabular-nums">{when(state.registration_closes_at)}</span>. After that, nobody can join or leave the group.</>
                      : "P1 registration is closed. Your group can register in the first week of next semester; nothing is due for you until then."}
                </p>
                {state.registration_open && state.register_block && !t.p1_registered && (
                  <p className="mt-2 text-sm font-medium text-amber-800">{state.register_block}.</p>
                )}
              </div>
              {state.can_register && (
                <button onClick={register} disabled={busy === "register"} className="btn-primary">
                  {busy === "register" ? "Registering…" : "Register for P1"}
                </button>
              )}
            </section>
          )}

          {(state.can_form_group || state.form_group_block) && (
            <form onSubmit={submit} className="card space-y-5 p-6">
              <div>
                <h2 className="font-semibold">Choose a supervisor</h2>
                <p className="mt-1 text-sm text-zinc-500">
                  Any member can send the request for the whole group. Your group is formed once the supervisor accepts.
                </p>
              </div>
              {state.form_group_block && (
                <p role="status" className="alert border-amber-200 bg-amber-50 text-amber-900">
                  <Icon className="mt-px size-4">{ICONS.alert}</Icon><span>{state.form_group_block}.</span>
                </p>
              )}
              <fieldset disabled={!state.can_form_group} className="flex flex-wrap items-end gap-3">
                <label className="label min-w-56 flex-1">
                  Supervisor
                  <select name="supervisor_id" required value={supervisor} onChange={(e) => setSupervisor(e.target.value)} className="input">
                    <option value="" disabled>Choose a faculty member</option>
                    {state.faculty_choices.map((f) => <option key={f.id} value={f.id}>{personName(f)}</option>)}
                  </select>
                </label>
                <button disabled={busy === "ask" || !state.faculty_choices.length} className="btn-primary">
                  {busy === "ask" ? "Sending…" : "Send request"}
                </button>
              </fieldset>
              {state.can_form_group && !state.faculty_choices.length && <p className="text-sm text-zinc-500">No faculty members are available yet.</p>}
            </form>
          )}
        </>
      )}
    </div>
  );
}
