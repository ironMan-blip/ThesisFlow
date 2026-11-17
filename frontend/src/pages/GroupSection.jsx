import { useEffect, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { api } from "../api/client";
import { Alerts, ConfirmDialog, DecideButtons, Icon, ICONS, Person, Skeleton } from "../components/ui";
import { when } from "../format";
import { useAction } from "../useAction";

// Student group (3 to 5 students): shown on the Thesis group page.
export default function GroupSection() {
  const { refreshCounts } = useOutletContext();
  const [state, setState] = useState(null);
  const [leaving, setLeaving] = useState(false);
  const { busy, error, notice, setError, run } = useAction();

  useEffect(() => {
    api("/groups/mine").then(setState).catch((err) => setError(err.message));
  }, [setError]);

  // Every group action returns the fresh state, so the page just shows it.
  const act = (key, path, options, message) =>
    run(key, async () => {
      setState(await api(path, options));
      refreshCounts();
      return message;
    });

  const create = (e) => {
    e.preventDefault();
    const name = new FormData(e.currentTarget).get("name");
    act("create", "/groups/mine", { method: "POST", body: { name } }, "Group created. Invite teammates from Find teammates.");
  };

  const leave = () => {
    setLeaving(false);
    act("leave", "/groups/mine", { method: "DELETE" }, "You left the group.");
  };

  const g = state?.group;

  return (
    <div className="space-y-8">
      {state && (
        <p className="text-sm text-zinc-600">
          A thesis group has {state.min_members} to {state.max_members} students. Invitations expire after {state.invite_days} days.
        </p>
      )}

      <Alerts error={error} notice={notice} />

      {!state ? (
        <Skeleton rows={2} row="h-28 rounded-xl" className="space-y-4" />
      ) : (
        <>
          {state.received_invitations.length > 0 && (
            <section className="card overflow-hidden">
              <p className="border-b border-zinc-200 px-4 py-3 text-sm font-medium tabular-nums text-zinc-700 sm:px-6">
                {state.received_invitations.length} {state.received_invitations.length === 1 ? "invitation" : "invitations"}
              </p>
              <ul className="divide-y divide-zinc-100">
                {state.received_invitations.map((i) => (
                  <li key={i.id} className="flex flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
                    <div className="min-w-0">
                      <p className="font-medium">{i.group_name} <span className="badge bg-zinc-50 font-normal text-zinc-600 ring-zinc-200">{i.member_count} members</span></p>
                      <p className="mt-0.5 text-sm text-zinc-500">
                        {i.invited_by ? `Invited by ${i.invited_by.full_name}` : "Invited"} · expires {when(i.expires_at)}
                      </p>
                    </div>
                    <DecideButtons
                      busy={busy === `inv-${i.id}`}
                      reject="Decline" approve="Accept"
                      onReject={() => act(`inv-${i.id}`, `/groups/invitations/${i.id}/decline`, { method: "POST" }, "Invitation declined.")}
                      onApprove={() => act(`inv-${i.id}`, `/groups/invitations/${i.id}/accept`, { method: "POST" }, `You joined ${i.group_name}.`)}
                    />
                  </li>
                ))}
              </ul>
            </section>
          )}

          {state.can_create && (
            <form onSubmit={create} className="card max-w-xl space-y-5 p-6">
              <h2 className="font-semibold">Create a group</h2>
              <label className="label">
                Group name
                <input name="name" required maxLength={60} placeholder="e.g. Team Nova" className="input" />
              </label>
              <button disabled={busy === "create"} className="btn-primary w-full">{busy === "create" ? "Creating…" : "Create group"}</button>
              <p className="text-xs text-zinc-500">
                You become the leader. You can also wait for an invitation, or <Link to="/teammates" className="font-medium text-teal-700 hover:underline">find teammates</Link> first.
              </p>
            </form>
          )}

          {g && (
            <section className="card space-y-5 p-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-lg font-semibold">{g.name}</h2>
                  <span className={`badge ${g.is_ready ? "bg-teal-50 text-teal-800 ring-teal-600/20" : "bg-amber-50 text-amber-800 ring-amber-600/20"}`}>
                    {g.is_ready ? "Ready" : `Needs ${g.members_needed} more`}
                  </span>
                  <span className="badge bg-zinc-50 tabular-nums text-zinc-700 ring-zinc-200">{g.members.length}/{state.max_members} members</span>
                </div>
                <div className="flex gap-2">
                  {state.can_invite && <Link to="/teammates" className="btn-primary px-3 py-1.5">Invite students</Link>}
                  <button onClick={() => setLeaving(true)} disabled={busy === "leave"} className="btn-ghost-danger px-3 py-1.5">Leave group</button>
                </div>
              </div>

              <ul className="divide-y divide-zinc-100">
                {g.members.map((m) => (
                  <li key={m.id} className="py-3">
                    <Person user={m}>{g.leader?.id === m.id && <> · <span className="font-medium text-teal-700">Leader</span></>}</Person>
                  </li>
                ))}
              </ul>

              {state.sent_invitations.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-zinc-700">Waiting for an answer</h3>
                  <ul className="mt-2 divide-y divide-zinc-100">
                    {state.sent_invitations.map((i) => (
                      <li key={i.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                        <Person user={i.invitee}> · expires {when(i.expires_at)}</Person>
                        {state.is_leader && (
                          <button onClick={() => act(`cancel-${i.id}`, `/groups/mine/invitations/${i.id}`, { method: "DELETE" }, "Invitation cancelled.")}
                            disabled={busy === `cancel-${i.id}`} className="btn-secondary px-3 py-1.5">Cancel</button>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {!state.can_invite && state.is_leader && (
                <p className="alert-success"><Icon className="mt-px size-4">{ICONS.check}</Icon><span>Your group is full, counting invitations still waiting.</span></p>
              )}
            </section>
          )}
        </>
      )}

      <ConfirmDialog open={leaving} title="Leave this group?" confirm="Yes, leave" danger onCancel={() => setLeaving(false)} onConfirm={leave}>
        If you are the leader, the longest-standing member takes over. If you are the last member, the group is removed.
      </ConfirmDialog>
    </div>
  );
}
