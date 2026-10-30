import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Alerts, PageHeader } from "../components/ui";
import { useAction } from "../useAction";

// Coordinator's list of every approved account; any account but the coordinator's can be deleted.
export default function AccountsPage() {
  const [accounts, setAccounts] = useState(null);
  const [confirming, setConfirming] = useState(null); // id of the account awaiting "Yes, delete"
  const { busy, error, notice, setError, run } = useAction(); // busy key is the account id being deleted

  useEffect(() => {
    api("/auth/accounts").then(setAccounts).catch((err) => setError(err.message));
  }, [setError]);

  const remove = (a) =>
    run(a.id, async () => {
      await api(`/auth/accounts/${a.id}`, { method: "DELETE" });
      setAccounts((as) => as.filter((x) => x.id !== a.id));
      setConfirming(null);
      return `${a.full_name}'s account was deleted.`;
    });

  return (
    <div className="space-y-8">
      <PageHeader title="Accounts" intro="Every approved account. Deleting an account also deletes its proposal for good." />

      <Alerts error={error} notice={notice} />

      {!accounts ? (
        <div className="h-24 animate-pulse rounded-xl bg-zinc-100" aria-hidden="true" />
      ) : (
        <ul className="space-y-3">
          {accounts.map((a) => (
            <li key={a.id} className="card flex flex-wrap items-center justify-between gap-4 p-5">
              <div>
                <p className="font-medium">{a.full_name}{a.initials && ` (${a.initials})`} <span className="text-sm font-normal capitalize text-zinc-500">· {a.role}</span></p>
                <p className="text-sm text-zinc-600">ID {a.id_number} · {a.email}{a.deletion_pending && " · deletion requested"}</p>
              </div>
              {a.role === "coordinator" ? null : confirming === a.id ? (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-red-700">Delete permanently? This can't be undone.</span>
                  <button onClick={() => setConfirming(null)} disabled={busy === a.id} className="btn-secondary">Cancel</button>
                  <button onClick={() => remove(a)} disabled={busy === a.id} className="btn bg-red-600 text-white shadow-sm hover:bg-red-700">
                    {busy === a.id ? "Deleting..." : "Yes, delete"}
                  </button>
                </div>
              ) : (
                <button onClick={() => setConfirming(a.id)} className="btn-secondary text-red-700 hover:text-red-800">Delete</button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
