import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Alerts, EmptyState, Icon, ICONS, PageHeader, Person, Skeleton } from "../components/ui";
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

      <section className="card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3 sm:px-6">
          <div role="tablist" aria-label="Account type" className="inline-flex rounded-lg bg-zinc-100 p-1">
            {Object.entries(TABS).map(([r, t]) => (
              <button key={r} role="tab" aria-selected={role === r} onClick={() => { setRole(r); setConfirming(null); }}
                className={`rounded-md px-3.5 py-1.5 text-sm font-medium capitalize transition focus-visible:ring-3 focus-visible:ring-teal-600/30 focus-visible:outline-none ${
                  role === r ? "bg-white text-zinc-900 shadow-sm" : "text-zinc-600 hover:text-zinc-900"
                }`}>{t}</button>
            ))}
          </div>
          <div className="relative w-full sm:w-64">
            <Icon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-zinc-400">{ICONS.search}</Icon>
            <input type="search" inputMode="numeric" aria-label="Search by ID" placeholder="Search by ID"
              value={query} onChange={(e) => setQuery(e.target.value.trim())} className="input mt-0 pl-9" />
          </div>
        </div>

        {!accounts ? (
          <Skeleton rows={3} />
        ) : accounts.length === 0 ? (
          <EmptyState icon={query ? ICONS.search : undefined} title={query ? "No matches" : `No ${tab} yet`}>
            {query ? `No account in ${tab} matches ID "${query}".` : `Approved ${tab} will show up here.`}
          </EmptyState>
        ) : (
          <ul className="divide-y divide-zinc-100">
            {accounts.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center justify-between gap-4 px-4 py-4 transition hover:bg-zinc-50/60 sm:px-6">
                <Person user={a}>
                  {a.deletion_pending && <> · <span className="font-medium text-amber-700">deletion requested</span></>}
                </Person>
                {confirming === a.id ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-red-700">Delete permanently? This can't be undone.</span>
                    <button onClick={() => setConfirming(null)} disabled={busy === a.id} className="btn-secondary px-3 py-1.5">Cancel</button>
                    <button onClick={() => remove(a)} disabled={busy === a.id} className="btn-danger px-3 py-1.5">
                      {busy === a.id ? "Deleting..." : "Yes, delete"}
                    </button>
                  </div>
                ) : (
                  <button onClick={() => setConfirming(a.id)} aria-label={`Delete ${a.full_name}`} className="btn-ghost-danger px-3 py-1.5">Delete</button>
                )}
              </li>
            ))}
          </ul>
        )}
        {accounts?.length > 0 && (
          <p className="border-t border-zinc-100 px-4 py-3 text-xs tabular-nums text-zinc-500 sm:px-6">
            {accounts.length} {accounts.length === 1 ? "account" : "accounts"}
          </p>
        )}
      </section>
    </div>
  );
}
