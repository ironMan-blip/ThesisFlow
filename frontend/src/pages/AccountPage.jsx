import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api } from "../api/client";
import { Alerts, Avatar, PageHeader } from "../components/ui";
import { useAction } from "../useAction";

export default function AccountPage() {
  const { user } = useOutletContext();
  const [pending, setPending] = useState(user.deletion_pending);
  const [confirming, setConfirming] = useState(false);
  const { busy, error, run } = useAction();

  const requestDeletion = () =>
    run("delete", async () => {
      const me = await api("/auth/me/deletion-request", { method: "POST" });
      setPending(me.deletion_pending);
      setConfirming(false);
    });

  const sending = busy === "delete";

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
          Your request goes to the coordinator. If they approve it within 48 hours, your account and your proposal
          are deleted for good. If they don't, your account is kept and you can ask again.
        </p>

        <Alerts error={error} />

        {pending ? (
          <p role="status" className="alert-success">Deletion requested. Waiting for the coordinator to decide.</p>
        ) : confirming ? (
          <div className="flex flex-wrap items-center gap-2">
            <p role="alert" className="alert-error w-full">
              <strong>Warning: this can't be undone.</strong> If the coordinator approves, your account and your
              proposal will be deleted permanently and cannot be recovered.
            </p>
            <span className="text-sm font-medium">Send the deletion request?</span>
            <button onClick={() => setConfirming(false)} disabled={sending} className="btn-secondary">Cancel</button>
            <button onClick={requestDeletion} disabled={sending} className="btn-danger">
              {sending ? "Sending..." : "Yes, request deletion"}
            </button>
          </div>
        ) : (
          <button onClick={() => setConfirming(true)} className="btn-secondary text-red-700 hover:bg-red-50 hover:text-red-800">
            Request account deletion
          </button>
        )}
      </section>
    </div>
  );
}
