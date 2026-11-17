import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Alerts, EmptyState, Icon, ICONS, PageHeader, Person, Skeleton } from "../components/ui";
import { useAction } from "../useAction";

const Tags = ({ items }) => items.map((t) => <span key={t} className="badge bg-zinc-50 text-zinc-700 ring-zinc-200">{t}</span>);
const split = (s) => s.split(",").map((t) => t.trim()).filter(Boolean);

export default function TeammatesPage() {
  const [results, setResults] = useState(null);
  const [profile, setProfile] = useState(null);
  const [query, setQuery] = useState("");
  const [reload, setReload] = useState(0);
  const { busy, error, notice, setError, run } = useAction();

  useEffect(() => {
    api("/groups/profile").then(setProfile).catch((err) => setError(err.message));
  }, [setError]);

  // The API filters; ignore stale replies when the search changes mid-request.
  useEffect(() => {
    let current = true;
    api(`/groups/teammates?${new URLSearchParams({ q: query })}`)
      .then((r) => current && setResults(r))
      .catch((err) => current && setError(err.message));
    return () => { current = false; };
  }, [query, reload, setError]);

  const saveProfile = (e) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    run("profile", async () => {
      setProfile(await api("/groups/profile", {
        method: "PUT",
        body: { interests: split(f.get("interests")), skills: split(f.get("skills")), bio: f.get("bio"), open_to_invites: f.get("open") === "on" },
      }));
      setReload((n) => n + 1);
      return "Profile saved.";
    });
  };

  const invite = (s) =>
    run(s.id, async () => {
      await api("/groups/mine/invitations", { method: "POST", body: { student_id: s.id } });
      setReload((n) => n + 1);
      return `Invitation sent to ${s.full_name}. It expires in 3 days.`;
    });

  return (
    <div className="space-y-8">
      <PageHeader title="Find teammates" intro="Students without a group, searchable by interests and skills. Create a group on Thesis group first, then invite from here." />

      <Alerts error={error} notice={notice} />

      <div className="grid items-start gap-6 lg:grid-cols-5">
        {profile && (
          <form onSubmit={saveProfile} className="card space-y-5 p-6 lg:col-span-2">
            <h2 className="font-semibold">Your profile</h2>
            <label className="label">
              Interests
              <input name="interests" defaultValue={profile.interests.join(", ")} placeholder="nlp, computer vision" className="input" />
            </label>
            <label className="label">
              Skills
              <input name="skills" defaultValue={profile.skills.join(", ")} placeholder="python, react" className="input" />
            </label>
            <label className="label">
              About you
              <textarea name="bio" rows={3} maxLength={profile.max_bio_chars} defaultValue={profile.bio} className="input resize-y" />
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700">
              <input type="checkbox" name="open" defaultChecked={profile.open_to_invites} className="size-4 accent-teal-700" />
              Show me here and let groups invite me
            </label>
            <p className="text-xs text-zinc-500">Separate tags with commas, up to {profile.max_tags} each.</p>
            <button disabled={busy === "profile"} className="btn-primary w-full">{busy === "profile" ? "Saving…" : "Save profile"}</button>
          </form>
        )}

        <section className="card overflow-hidden lg:col-span-3">
          <div className="border-b border-zinc-200 px-4 py-3 sm:px-6">
            <div className="relative">
              <Icon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-zinc-400">{ICONS.search}</Icon>
              <input type="search" aria-label="Search interests and skills" placeholder="Search interests or skills"
                value={query} onChange={(e) => setQuery(e.target.value)} className="input mt-0 pl-9" />
            </div>
          </div>
          {!results ? (
            <Skeleton rows={3} />
          ) : results.length === 0 ? (
            <EmptyState icon={ICONS.search} title="No students found">
              {query ? `Nobody without a group lists "${query}".` : "Every student already has a group."}
            </EmptyState>
          ) : (
            <ul className="divide-y divide-zinc-100">
              {results.map((s) => (
                <li key={s.id} className="flex flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
                  <div className="min-w-0 space-y-2">
                    <Person user={s} />
                    {(s.interests.length > 0 || s.skills.length > 0) && (
                      <div className="flex flex-wrap gap-1.5"><Tags items={s.interests} /><Tags items={s.skills} /></div>
                    )}
                    {s.bio && <p className="line-clamp-2 text-sm text-zinc-600">{s.bio}</p>}
                  </div>
                  {s.invited ? (
                    <span className="badge bg-amber-50 text-amber-800 ring-amber-600/20">Invited</span>
                  ) : s.can_invite ? (
                    <button onClick={() => invite(s)} disabled={busy === s.id} className="btn-primary px-3 py-1.5">
                      {busy === s.id ? "Sending…" : "Invite"}
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
