import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api } from "../api/client";
import { Avatar, PageHeader, ReasonDialog } from "../components/ui";
import { when } from "../format";
import { useAction } from "../useAction";

export default function AccountPage() {
  const { user } = useOutletContext();
  const [me, setMe] = useState(user); // refreshed after asking, so the scheduled date shows at once
  const [asking, setAsking] = useState(false);
  const { busy, error, setError, run } = useAction();

  const requestDeletion = (reason) =>
    run("delete", async () => {
      setMe(await api("/auth/me/deletion-request", { method: "POST", body: { reason } }));
      setAsking(false);
    });

  return (
    <div className="space-y-8">
      <PageHeader title="Account" intro="Your details as the university has them. Contact the coordinator if something is wrong." />

      <section className="card max-w-2xl" aria-labelledby="profile-heading">
        <div className="flex items-center gap-4 border-b border-zinc-200 p-6">
          <Avatar user={user} className="size-14 text-lg" />
          <div>
            <h2 id="profile-heading" className="text-lg font-semibold">{user.full_name}</h2>
            <p className="text-sm capitalize text-zinc-500">{user.role}</p>
          </div>
        </div>
        <dl className="grid gap-x-6 gap-y-4 p-6 text-sm sm:grid-cols-2">
          {[
            ["ID number", user.id_number],
            ["Email", user.email],
            user.initials && ["Initials", user.initials],
          ].filter(Boolean).map(([k, v]) => (
            <div key={k}><dt className="text-zinc-500">{k}</dt><dd className="mt-0.5 break-words font-medium tabular-nums">{v}</dd></div>
          ))}
        </dl>
      </section>

      <section className="card max-w-2xl space-y-3 p-6 ring-red-200" aria-labelledby="delete-heading">
        <h2 id="delete-heading" className="font-semibold text-red-800">Delete account</h2>
        <p className="text-sm text-zinc-600">
          Tell us why. The coordinator decides; if they approve, your account is deleted for good {user.deletion_days} days
          later. You can't take the request back: only the coordinator can reject or cancel it. Your thesis and proposal versions stay archived.
        </p>

        {me.deletion_pending ? (
          <div role="status" className="space-y-1 rounded-lg bg-amber-50 px-3 py-2.5 text-sm text-amber-900 ring-1 ring-amber-600/20 ring-inset">
            <p className="font-medium">
              {me.deletion_executes_at
                ? `${me.deletion_by_coordinator ? "The coordinator scheduled your account for deletion" : "Approved: your account will be deleted"} on ${when(me.deletion_executes_at)}.`
                : "Deletion requested. Waiting for the coordinator to decide."}
            </p>
            <p>Only the coordinator can {me.deletion_executes_at ? "cancel it before then" : "reject it"}.</p>
            {me.coordinator_contact && (
              <p>If you have a problem with it, contact the coordinator at <a href={`mailto:${me.coordinator_contact}`} className="font-medium underline">{me.coordinator_contact}</a> before then.</p>
            )}
            <p className="whitespace-pre-line text-amber-800">Reason: {me.deletion_reason}</p>
          </div>
        ) : (
          <button onClick={() => { setError(null); setAsking(true); }} className="btn-secondary text-red-700 hover:bg-red-50 hover:text-red-800">
            Request account deletion
          </button>
        )}
      </section>

      <ReasonDialog open={asking} title="Delete your account?" confirm="Request deletion" busy={busy === "delete"} error={error}
        min={user.min_reason_chars} max={user.max_reason_chars} onCancel={() => setAsking(false)} onSubmit={requestDeletion}>
        <strong className="text-red-800">This can't be undone once it runs.</strong> If the coordinator approves, your account is
        deleted {user.deletion_days} days after that, unless they cancel it. You can keep using it until then.
      </ReasonDialog>
    </div>
  );
}
