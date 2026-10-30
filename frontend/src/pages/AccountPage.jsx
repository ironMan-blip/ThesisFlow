import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api } from "../api/client";

export default function AccountPage() {
  const { user } = useOutletContext();
  const [pending, setPending] = useState(user.deletion_pending);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const requestDeletion = async () => {
    setError(null);
    setBusy(true);
    try {
      const me = await api("/auth/me/deletion-request", { method: "POST" });
      setPending(me.deletion_pending);
      setConfirming(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold">Account</h1>
        <dl className="mt-4 grid max-w-md grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
          <dt className="text-zinc-500">Name</dt><dd>{user.full_name}</dd>
          <dt className="text-zinc-500">Email</dt><dd>{user.email}</dd>
          <dt className="text-zinc-500">Role</dt><dd className="capitalize">{user.role}</dd>
        </dl>
      </div>

      <section className="card max-w-xl space-y-3 p-5" aria-labelledby="delete-heading">
        <h2 id="delete-heading" className="font-semibold">Delete account</h2>
        <p className="text-sm text-zinc-600">
          Your request goes to the coordinator. If they approve it within 48 hours, your account and your proposal
          are deleted for good. If they don't, your account is kept and you can ask again.
        </p>

        {error && <p role="alert" className="alert-error">{error}</p>}

        {pending ? (
          <p role="status" className="alert-success">Deletion requested. Waiting for the coordinator to decide.</p>
        ) : confirming ? (
          <div className="flex flex-wrap items-center gap-2">
            <p role="alert" className="alert-error w-full">
              <strong>Warning: this can't be undone.</strong> If the coordinator approves, your account and your
              proposal will be deleted permanently and cannot be recovered.
            </p>
            <span className="text-sm font-medium">Send the deletion request?</span>
            <button onClick={() => setConfirming(false)} disabled={busy} className="btn-secondary">Cancel</button>
            <button onClick={requestDeletion} disabled={busy} className="btn bg-red-600 text-white shadow-sm hover:bg-red-700">
              {busy ? "Sending..." : "Yes, request deletion"}
            </button>
          </div>
        ) : (
          <button onClick={() => setConfirming(true)} className="btn-secondary text-red-700 hover:text-red-800">
            Request account deletion
          </button>
        )}
      </section>
    </div>
  );
}
