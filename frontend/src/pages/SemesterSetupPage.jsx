import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { Alerts, ConfirmDialog, PageHeader, Skeleton } from "../components/ui";
import { when } from "../format";
import { useAction } from "../useAction";

const DEFAULT_STEPS = [
  { key: "form_group", label: "Form Group", defaultOpen: true },
  { key: "pick_supervisor", label: "Pick Supervisor", defaultOpen: true },
  { key: "P1", label: "Pre-Thesis 1 (P1)", defaultOpen: true },
  { key: "P2", label: "Pre-Thesis 2 (P2)", defaultOpen: true },
  { key: "P3", label: "Final Thesis (P3)", defaultOpen: true },
  { key: "defense", label: "Final Defense", defaultOpen: false },
];

export default function SemesterSetupPage() {
  const [current, setCurrent] = useState(null);
  const [history, setHistory] = useState([]);
  const [pendingCreate, setPendingCreate] = useState(null);
  const { busy, error, notice, setError, run, clear } = useAction();

  const load = useCallback(async () => {
    const [cur, list] = await Promise.all([
      api("/semesters/current"),
      api("/semesters"),
    ]);
    setCurrent(cur);
    setHistory(list);
  }, []);

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, [load, setError]);

  const toggleStep = (step) => {
    const nextState = !step.is_open;
    run(`step-${step.key}`, async () => {
      const updated = await api(`/semesters/current/steps/${step.key}`, {
        method: "PATCH",
        body: { is_open: nextState },
      });
      setCurrent(updated);
      setHistory((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
      return `${step.label} is now ${nextState ? "open" : "closed"}.`;
    });
  };

  const setAllSteps = (isOpen) => {
    run("bulk-steps", async () => {
      const updated = await api("/semesters/current/steps", {
        method: "PATCH",
        body: {
          form_group: isOpen,
          pick_supervisor: isOpen,
          P1: isOpen,
          P2: isOpen,
          P3: isOpen,
          defense: isOpen,
        },
      });
      setCurrent(updated);
      setHistory((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
      return `All semester steps are now ${isOpen ? "open" : "closed"}.`;
    });
  };

  const handleCreateSubmit = (e) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const payload = {
      name: f.get("name"),
      registration_opens_local: f.get("registration_opens_local") || null,
      registration_closes_local: f.get("registration_closes_local") || null,
      form_group_open: f.has("step_form_group"),
      pick_supervisor_open: f.has("step_pick_supervisor"),
      p1_open: f.has("step_P1"),
      p2_open: f.has("step_P2"),
      p3_open: f.has("step_P3"),
      defense_open: f.has("step_defense"),
    };

    // A new semester always rolls groups over, so always confirm first.
    setPendingCreate({ payload, form: e.currentTarget });
  };

  const executeCreate = (payload, form) => {
    setPendingCreate(null);
    run("create", async () => {
      const created = await api("/semesters", {
        method: "POST",
        body: payload,
      });
      form?.reset();
      await load();
      if (created.rollover_summary) {
        const r = created.rollover_summary;
        return `Created "${created.name}" and rolled over students (${r.advanced} advanced, ${r.completed} completed, ${r.deferred} deferred, ${r.frozen} frozen, ${r.restarted} restarted).`;
      }
      return `Created new semester "${created.name}".`;
    });
  };

  return (
    <div className="space-y-8">
      <PageHeader
        title="Semester setup"
        intro="Create a semester and open or close each step of the thesis workflow (group formation, supervisor selection, P1, P2, P3, and defense)."
        help={[
          "Only one semester is active at a time (the most recently created semester).",
          "Closing a step immediately prevents students or faculty from performing actions in that stage.",
          "Enable 'Advance active groups from previous semester' when starting a new term after all grace periods end.",
        ]}
      />

      <Alerts error={error} notice={notice} floating onDismiss={clear} />

      {!current ? (
        <Skeleton rows={3} row="h-28 rounded-xl" className="space-y-4" />
      ) : (
        <>
          <section className="card p-6">
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-100 pb-5">
              <div>
                <div className="flex items-center gap-2.5">
                  <h2 className="text-xl font-semibold">{current.name}</h2>
                  <span className="badge bg-teal-50 text-teal-800 ring-teal-600/20">Active semester</span>
                </div>
                <p className="mt-1 text-sm text-zinc-500">
                  Started {when(current.started_at)}
                  {current.registration_opens_at && current.registration_closes_at && (
                    <> · P1 registration: {when(current.registration_opens_at)} to {when(current.registration_closes_at)}</>
                  )}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setAllSteps(true)}
                  disabled={busy === "bulk-steps"}
                  className="btn-secondary px-3 py-1.5"
                >
                  Open all steps
                </button>
                <button
                  type="button"
                  onClick={() => setAllSteps(false)}
                  disabled={busy === "bulk-steps"}
                  className="btn-ghost-danger px-3 py-1.5"
                >
                  Close all steps
                </button>
              </div>
            </div>

            <div className="mt-5">
              <h3 className="text-sm font-medium text-zinc-700">Step controls</h3>
              <ul className="mt-3 divide-y divide-zinc-100">
                {current.steps.map((step) => (
                  <li key={step.key} className="flex flex-wrap items-center justify-between gap-4 py-3.5">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-zinc-900">{step.label}</span>
                        <span
                          className={`badge ${
                            step.is_open
                              ? "bg-teal-50 text-teal-800 ring-teal-600/20"
                              : "bg-zinc-100 text-zinc-700 ring-zinc-300"
                          }`}
                        >
                          {step.is_open ? "Open" : "Closed"}
                        </span>
                      </div>
                      <p className="mt-0.5 text-sm text-zinc-500">{step.description}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => toggleStep(step)}
                      disabled={busy === `step-${step.key}`}
                      className={step.is_open ? "btn-secondary px-3.5 py-1.5" : "btn-primary px-3.5 py-1.5"}
                    >
                      {busy === `step-${step.key}`
                        ? "Saving…"
                        : step.is_open
                          ? "Close step"
                          : "Open step"}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </section>

          <form onSubmit={handleCreateSubmit} className="card space-y-5 p-6">
            <div>
              <h2 className="text-lg font-semibold">Create new semester</h2>
              <p className="mt-1 text-sm text-zinc-600">
                Start a new semester term and configure which steps open immediately.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              <label className="label">
                Semester name
                <input
                  name="name"
                  required
                  maxLength={80}
                  placeholder="e.g. Spring 2027"
                  className="input"
                />
              </label>
              <label className="label">
                P1 registration opens (Dhaka, optional)
                <input name="registration_opens_local" type="datetime-local" className="input" />
              </label>
              <label className="label">
                P1 registration closes (Dhaka, optional)
                <input name="registration_closes_local" type="datetime-local" className="input" />
              </label>
            </div>

            <div>
              <span className="label">Initial open steps</span>
              <div className="mt-2 grid gap-2.5 sm:grid-cols-3">
                {DEFAULT_STEPS.map((s) => (
                  <label
                    key={s.key}
                    className="flex items-center gap-2.5 rounded-lg bg-zinc-50 px-3 py-2 text-sm text-zinc-800 ring-1 ring-zinc-200/70 ring-inset"
                  >
                    <input
                      type="checkbox"
                      name={`step_${s.key}`}
                      defaultChecked={s.defaultOpen}
                      className="size-4 accent-teal-700"
                    />
                    {s.label}
                  </label>
                ))}
              </div>
            </div>

            <p className="rounded-lg bg-amber-50/70 px-3.5 py-3 text-sm text-amber-950 ring-1 ring-amber-600/20 ring-inset">
              <span className="font-medium">Active groups from the previous semester move on</span>
              <span className="block text-xs text-amber-800">
                Moves submitted groups to their next phase and freezes groups that missed a closed deadline. Deadlines are kept: groups still working to an open deadline carry on with it.
              </span>
            </p>

            <div className="flex justify-end">
              <button disabled={busy === "create"} className="btn-primary">
                {busy === "create" ? "Creating…" : "Create semester"}
              </button>
            </div>
          </form>

          {history.length > 1 && (
            <section className="card overflow-hidden">
              <div className="border-b border-zinc-200 px-6 py-4">
                <h2 className="font-semibold">Previous semesters</h2>
              </div>
              <ul className="divide-y divide-zinc-100">
                {history.slice(1).map((sem) => (
                  <li key={sem.id} className="flex flex-wrap items-center justify-between gap-3 px-6 py-3.5 text-sm">
                    <span className="font-medium text-zinc-800">{sem.name}</span>
                    <span className="text-zinc-500">Started {when(sem.started_at)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      <ConfirmDialog
        open={!!pendingCreate}
        title="Create semester and advance students?"
        confirm="Yes, create & advance"
        onCancel={() => setPendingCreate(null)}
        onConfirm={() => executeCreate(pendingCreate.payload, pendingCreate.form)}
      >
        This will advance submitted thesis groups to their next phase, freeze groups that missed a closed deadline, keep every deadline, and start "{pendingCreate?.payload.name}". This cannot be undone.
      </ConfirmDialog>
    </div>
  );
}