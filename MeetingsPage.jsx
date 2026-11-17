import { useCallback, useEffect, useRef, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api } from "../api/client";
import { Alerts, ConfirmDialog, EmptyState, Skeleton, PageHeader } from "../components/ui";
import { fromDhakaInput, personName, toDhakaInput, when } from "../format";
import { TOOLS } from "../tools";
import { useAction } from "../useAction";

const todayDhaka = () => toDhakaInput(new Date().toISOString()).slice(0, 10);
const dueToIso = (local) => {
  const [date, time] = local.split("T");
  return fromDhakaInput(date, time);
};

function Attendance({ m, thesis }) {
  const people = [
    ["Supervisor", m.supervisor_attended],
    ["Student", m.student_attended],
    ...(thesis?.co_supervisor_accepted ? [["Co-supervisor", m.co_supervisor_attended]] : []),
  ];
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Attendance">
      {people.map(([label, came]) => (
        <li key={label} className={`badge ${came ? "bg-teal-50 text-teal-800 ring-teal-600/20" : "bg-zinc-50 text-zinc-500 ring-zinc-200"}`}>
          {label}: {came ? "came" : "absent"}
        </li>
      ))}
    </ul>
  );
}

function MeetingCard({ m, data, canEdit, busy, onEdit, onRemove, onToggle }) {
  return (
    <li className="px-6 py-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-medium">{when(m.held_at)}</h3>
          {m.recorded_by && <p className="mt-0.5 text-xs text-zinc-500">Recorded by {personName(m.recorded_by)}</p>}
        </div>
        {canEdit && (
          <div className="flex gap-2">
            <button onClick={() => onEdit(m)} className="btn-secondary px-3 py-1.5">Edit</button>
            <button onClick={() => onRemove(m)} className="btn-ghost-danger px-3 py-1.5">Remove</button>
          </div>
        )}
      </div>
      <div className="mt-3"><Attendance m={m} thesis={data.thesis} /></div>
      <p className="mt-3 whitespace-pre-wrap break-words text-sm text-zinc-700">{m.notes}</p>
      {m.tasks.length > 0 && (
        <div className="mt-4">
          <p className="text-sm font-medium text-zinc-700">Tasks</p>
          <ul className="mt-1 space-y-1.5">
            {m.tasks.map((t) => (
              <li key={t.id} className="flex items-start gap-2.5 text-sm">
                <input type="checkbox" checked={t.done} disabled={!canEdit || busy === `task-${t.id}`}
                  onChange={(e) => onToggle(t, e.target.checked)} aria-label={`Done: ${t.description}`}
                  className="mt-0.5 size-4 rounded border-zinc-300 text-teal-700 focus:ring-teal-600" />
                <span className={t.done ? "text-zinc-400 line-through" : "text-zinc-800"}>
                  {t.description}
                  {t.due_at && <span className="ml-2 text-xs text-zinc-500">due {when(t.due_at)}</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </li>
  );
}

// Log a new meeting, or edit one (`meeting` set). The page remounts it with a new key after each save.
function MeetingForm({ data, meeting, saving, onSubmit, onCancel }) {
  const nextKey = useRef(0);
  const [tasks, setTasks] = useState(() =>
    (meeting?.tasks ?? []).map((t) => ({ key: `t${t.id}`, id: t.id, description: t.description, due: t.due_at ? toDhakaInput(t.due_at) : "" })),
  );
  const held = meeting ? toDhakaInput(meeting.held_at) : "";
  const patch = (key, change) => setTasks((ts) => ts.map((t) => (t.key === key ? { ...t, ...change } : t)));
  const hasCo = data.thesis?.co_supervisor_accepted;

  const submit = (e) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    onSubmit({
      held_at: fromDhakaInput(f.get("held_date"), f.get("held_time")),
      notes: f.get("notes"),
      supervisor_attended: f.has("supervisor_attended"),
      student_attended: f.has("student_attended"),
      co_supervisor_attended: hasCo && f.has("co_supervisor_attended"),
      tasks: tasks
        .filter((t) => t.description.trim())
        .map((t) => ({ id: t.id, description: t.description, due_at: t.due ? dueToIso(t.due) : null })),
    });
  };

  const check = (name, label, on) => (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" name={name} defaultChecked={on} className="size-4 rounded border-zinc-300 text-teal-700 focus:ring-teal-600" />
      {label}
    </label>
  );

  return (
    <form onSubmit={submit} className="card space-y-5 p-6 lg:col-span-2">
      <h2 className="font-semibold">{meeting ? "Edit meeting" : "Log a meeting"}</h2>
      <div className="grid grid-cols-2 gap-3">
        <label className="label">
          Date
          <input name="held_date" type="date" required max={todayDhaka()} defaultValue={held.slice(0, 10)} className="input" />
        </label>
        <label className="label">
          Time
          <input name="held_time" type="time" required defaultValue={held.slice(11)} className="input" />
        </label>
      </div>
      <fieldset>
        <legend className="label">Who came</legend>
        <div className="mt-1.5 space-y-1.5">
          {check("supervisor_attended", "Supervisor", meeting?.supervisor_attended ?? true)}
          {check("student_attended", "Student", meeting?.student_attended ?? true)}
          {hasCo && check("co_supervisor_attended", "Co-supervisor", meeting?.co_supervisor_attended ?? false)}
        </div>
      </fieldset>
      <label className="label">
        Notes
        <textarea name="notes" required rows={5} maxLength={data.max_notes_chars} defaultValue={meeting?.notes}
          placeholder="What was discussed and decided" className="input resize-y" />
      </label>
      <div>
        <span className="label">Tasks for the student</span>
        <ul className="mt-1.5 space-y-2">
          {tasks.map((t) => (
            <li key={t.key} className="space-y-1.5 rounded-lg bg-zinc-50 p-3 ring-1 ring-zinc-200/70 ring-inset">
              <input value={t.description} onChange={(e) => patch(t.key, { description: e.target.value })}
                maxLength={data.max_task_chars} aria-label="Task" placeholder="What to do" className="input" />
              <div className="flex items-center gap-2">
                <input type="datetime-local" value={t.due} onChange={(e) => patch(t.key, { due: e.target.value })}
                  aria-label="Task due date (optional)" className="input" />
                <button type="button" onClick={() => setTasks((ts) => ts.filter((x) => x.key !== t.key))}
                  className="btn-ghost-danger shrink-0 px-3 py-1.5">Remove</button>
              </div>
            </li>
          ))}
        </ul>
        {tasks.length < data.max_tasks && (
          <button type="button" className="btn-secondary mt-2 px-3 py-1.5"
            onClick={() => setTasks((ts) => [...ts, { key: `n${nextKey.current++}`, id: null, description: "", due: "" }])}>
            Add a task
          </button>
        )}
      </div>
      <div className="flex gap-2">
        {meeting && <button type="button" onClick={onCancel} className="btn-secondary flex-1">Cancel</button>}
        <button disabled={saving} className="btn-primary flex-1">{saving ? "Saving…" : meeting ? "Save changes" : "Log meeting"}</button>
      </div>
    </form>
  );
}

export default function MeetingsPage() {
  const { user } = useOutletContext();
  const isStudent = user.role === "student";
  const [theses, setTheses] = useState(null); // faculty and coordinator pick a thesis; students only have their own
  const [thesisId, setThesisId] = useState(null);
  const [data, setData] = useState(null);
  const [editing, setEditing] = useState(null);
  const [removing, setRemoving] = useState(null);
  const [formKey, setFormKey] = useState(0);
  const { busy, error, notice, setError, run } = useAction();

  const fetchList = useCallback((id) => api(isStudent ? "/meetings/mine" : `/meetings/thesis/${id}`), [isStudent]);

  useEffect(() => {
    if (isStudent) return;
    api("/theses")
      .then((rows) => {
        setTheses(rows);
        setThesisId((rows.find((t) => t.status === "active") ?? rows[0])?.id ?? null);
      })
      .catch((err) => setError(err.message));
  }, [isStudent, setError]);

  useEffect(() => {
    if (!isStudent && thesisId === null) return;
    let stale = false;
    setData(null);
    setEditing(null);
    fetchList(thesisId)
      .then((res) => !stale && setData(res))
      .catch((err) => !stale && setError(err.message));
    return () => {
      stale = true;
    };
  }, [isStudent, thesisId, fetchList, setError]);

  const reload = async () => setData(await fetchList(thesisId));

  const save = (payload) =>
    run("save", async () => {
      if (editing) await api(`/meetings/${editing.id}`, { method: "PUT", body: payload });
      else await api(`/meetings/thesis/${thesisId}`, { method: "POST", body: payload });
      const wasEditing = !!editing;
      setEditing(null);
      setFormKey((k) => k + 1);
      await reload();
      return wasEditing ? "Meeting updated." : "Meeting logged.";
    });

  const confirmRemove = () => {
    const m = removing;
    setRemoving(null);
    run("remove", async () => {
      await api(`/meetings/${m.id}`, { method: "DELETE" });
      if (editing?.id === m.id) setEditing(null);
      await reload();
      return "Meeting removed.";
    });
  };

  const toggle = (t, done) =>
    run(`task-${t.id}`, async () => {
      await api(`/meetings/tasks/${t.id}`, { method: "PUT", body: { done } });
      await reload();
      return null;
    });

  const noTheses = !isStudent && theses && !theses.length;
  const canEdit = !!data?.can_edit;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Meetings"
        intro={isStudent
          ? "Your supervisor records each meeting with you here, with who came, what was decided and the tasks you agreed on."
          : user.role === "faculty"
            ? "Record each meeting with your thesis groups: who came, what was discussed and the tasks set. The log is read-only once a thesis is completed or archived."
            : "Every thesis group's meeting log. Supervisors write it; you can read it."}
      />

      {!isStudent && theses?.length > 0 && (
        <label className="label block max-w-md">
          Thesis
          <select value={thesisId ?? ""} onChange={(e) => setThesisId(Number(e.target.value))} className="input">
            {theses.map((t) => (
              <option key={t.id} value={t.id}>
                {t.code} · {t.student ? t.student.full_name : "Account deleted"}{t.status !== "active" ? ` (${t.status === "dropped" ? "archived" : t.status})` : ""}
              </option>
            ))}
          </select>
        </label>
      )}

      <Alerts error={error} notice={notice} />
      {data?.log_block && <p className="rounded-lg bg-zinc-50 px-3 py-2 text-sm text-zinc-700 ring-1 ring-zinc-200/70 ring-inset">{data.log_block}.</p>}

      {noTheses ? (
        <section className="card"><EmptyState icon={TOOLS.meetings.icon} title="No theses yet">Thesis groups appear here once a supervisor accepts them.</EmptyState></section>
      ) : (
        <div className="grid items-start gap-6 lg:grid-cols-5">
          {canEdit && (
            <MeetingForm key={`${editing?.id ?? "new"}-${formKey}`} data={data} meeting={editing} saving={busy === "save"}
              onSubmit={save} onCancel={() => setEditing(null)} />
          )}
          <section className={`card ${canEdit ? "lg:col-span-3" : "lg:col-span-5"}`}>
            <div className="flex items-center justify-between border-b border-zinc-200 px-6 py-4">
              <h2 className="font-semibold">Meeting log</h2>
              {data?.meetings.length > 0 && <span className="text-sm tabular-nums text-zinc-500">{data.meetings.length} total</span>}
            </div>
            {!data ? (
              <Skeleton row="h-20 rounded-lg" />
            ) : !data.meetings.length ? (
              <EmptyState icon={TOOLS.meetings.icon} title="No meetings logged yet">
                {isStudent ? "Meetings with your supervisor will appear here." : "Logged meetings will appear here, newest first."}
              </EmptyState>
            ) : (
              <ul className="divide-y divide-zinc-100">
                {data.meetings.map((m) => (
                  <MeetingCard key={m.id} m={m} data={data} canEdit={canEdit} busy={busy} onEdit={setEditing}
                    onRemove={setRemoving} onToggle={toggle} />
                ))}
              </ul>
            )}
          </section>
        </div>
      )}

      <ConfirmDialog open={!!removing} title="Remove this meeting?" confirm="Yes, remove" danger
        onCancel={() => setRemoving(null)} onConfirm={confirmRemove}>
        This permanently deletes the meeting and its tasks. It cannot be undone.
      </ConfirmDialog>
    </div>
  );
}