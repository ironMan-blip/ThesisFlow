import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Alerts, PageHeader, Person } from "../components/ui";
import { useAction } from "../useAction";

const TABS = { student: "students", faculty: "faculties" }; // role -> tab label

// Coordinator's list of every approved student and faculty account, each deletable.
export default function AccountsPage() {
  const [accounts, setAccounts] = useState(null);
  const [query, setQuery] = useState("");
  const [confirming, setConfirming] = useState(null); // id of the account awaiting "Yes, delete"
  const { busy, error, notice, setError, run } = useAction(); // busy key is the account id being deleted

  const [role, setRole] = useState("student");
  const tab = TABS[role];

  // The API filters by role and ID prefix; ignore stale replies when the filter changes mid-request.
  useEffect(() => {
    let current = true;
    api(`/auth/accounts?${new URLSearchParams({ role, id_prefix: query })}`)
      .then((as) => current && setAccounts(as))
      .catch((err) => current && setError(err.message));
    return () => { current = false; };
  }, [role, query, setError]);

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
        <div className="space-y-4">
        <div role="tablist" aria-label="Account type" className="flex gap-2">
          {Object.entries(TABS).map(([r, t]) => (
            <button key={r} role="tab" aria-selected={role === r} onClick={() => { setRole(r); setConfirming(null); }}
              className={`${role === r ? "btn bg-zinc-900 text-white" : "btn-secondary"} capitalize`}>{t}</button>
          ))}
        </div>
        <input type="search" inputMode="numeric" aria-label="Search by ID" placeholder="Search by ID"
          value={query} onChange={(e) => setQuery(e.target.value.trim())} className="input max-w-xs" />
        {accounts.length === 0 && <p className="text-sm text-zinc-600">{query ? `No account in ${tab} matches ID "${query}".` : `No ${tab} accounts yet.`}</p>}
        <ul className="space-y-3">
          {accounts.map((a) => (
            <li key={a.id} className="card flex flex-wrap items-center justify-between gap-4 p-5">
              <Person user={a}>{a.deletion_pending && " · deletion requested"}</Person>
              {confirming === a.id ? (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-red-700">Delete permanently? This can't be undone.</span>
                  <button onClick={() => setConfirming(null)} disabled={busy === a.id} className="btn-secondary">Cancel</button>
                  <button onClick={() => remove(a)} disabled={busy === a.id} className="btn-danger">
                    {busy === a.id ? "Deleting..." : "Yes, delete"}
                  </button>
                </div>
              ) : (
                <button onClick={() => setConfirming(a.id)} className="btn-secondary text-red-700 hover:text-red-800">Delete</button>
              )}
            </li>
          ))}
        </ul>
        </div>
      )}
    </div>
  );
}
