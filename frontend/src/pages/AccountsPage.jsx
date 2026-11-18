import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api } from "../api/client";
import { Alerts, EmptyState, Icon, ICONS, PageHeader, Person, ReasonDialog, Skeleton } from "../components/ui";
import { when } from "../format";
import { useAction } from "../useAction";

const TABS = { student: "students", faculty: "faculty" }; // role -> tab label

// Coordinator's list of every approved student and faculty account; any of them can be scheduled for deletion.
export default function AccountsPage() {
  const { user } = useOutletContext();
  const [accounts, setAccounts] = useState(null);
  const [query, setQuery] = useState("");
  const [deleting, setDeleting] = useState(null); // account whose deletion reason is being written
  const { busy, error, notice, setError, run, clear } = useAction(); // busy key is the account id being scheduled

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

  const schedule = (reason) => {
    const a = deleting;
    run(a.id, async () => {
      const updated = await api(`/auth/accounts/${a.id}/deletion`, { method: "POST", body: { reason } });
      setAccounts((as) => as.map((x) => (x.id === a.id ? updated : x)));
      setDeleting(null);
      return `${a.full_name}'s account will be deleted on ${when(updated.deletion_executes_at)}. You can cancel it under Deletion requests until then.`;
    });
  };

  return (
    <div className="space-y-8">
      <PageHeader title="Accounts" intro="Every approved account. Filter by role or search by ID." help={[
        "Deleting an account needs a written reason.",
        `The deletion runs ${user.deletion_days} days later. Until then you can cancel it under Deletion requests.`,
        "The account's thesis and proposal versions are kept as an archive.",
      ]} />

      <Alerts error={deleting ? null : error} notice={notice} floating onDismiss={clear} />

      <section className="card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3 sm:px-6">
          <div role="tablist" aria-label="Account type" className="inline-flex rounded-lg bg-zinc-100 p-1">
            {Object.entries(TABS).map(([r, t]) => (
              <button key={r} role="tab" aria-selected={role === r} onClick={() => setRole(r)}
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
                  {a.deletion_pending && <> · <span className="font-medium text-amber-700">deletes on {when(a.deletion_executes_at)}</span></>}
                </Person>
                {!a.deletion_pending && (
                  <button onClick={() => { setError(null); setDeleting(a); }} aria-label={`Delete ${a.full_name}`} className="btn-ghost-danger px-3 py-1.5">Delete</button>
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

      <ReasonDialog open={!!deleting} title={`Delete ${deleting?.full_name}'s account?`} confirm="Schedule deletion"
        busy={busy === deleting?.id} error={error} min={user.min_reason_chars} max={user.max_reason_chars}
        onCancel={() => setDeleting(null)} onSubmit={schedule}>
        The account is deleted {user.deletion_days} days from now, and can't be recovered after that. Until then it stays
        usable, and you can cancel the deletion. The reason is shown to the account owner.
      </ReasonDialog>
    </div>
  );
}
