import { useEffect, useState } from "react";
import { api, download } from "../api/client";

export default function ProposalPage() {
  const [proposal, setProposal] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api("/proposals/mine").then(setProposal).catch((err) => setError(err.message));
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    setError(null);
    setSaving(true);
    try {
      setProposal(await api("/proposals/mine/versions", { method: "POST", body: new FormData(form) }));
      form.reset();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const get = (v) => download(`/proposals/versions/${v.id}/file`, v.original_filename).catch((err) => setError(err.message));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Proposal</h1>

      <form onSubmit={submit} className="space-y-3 rounded border bg-white p-4">
        <h2 className="font-medium">Upload a new version</h2>
        <label className="block text-sm">
          Title
          <input name="title" required maxLength={255} className="mt-1 w-full rounded border px-2 py-1" />
        </label>
        <label className="block text-sm">
          Abstract
          <textarea name="abstract" required rows={4} className="mt-1 w-full rounded border px-2 py-1" />
        </label>
        <label className="block text-sm">
          PDF file
          <input name="file" type="file" accept="application/pdf" required className="mt-1 block w-full text-sm" />
        </label>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        <button disabled={saving} className="rounded bg-black px-4 py-2 text-white disabled:opacity-50">
          {saving ? "Uploading..." : "Upload"}
        </button>
      </form>

      <section className="rounded border bg-white p-4">
        <h2 className="mb-2 font-medium">Versions</h2>
        {!proposal?.versions.length ? (
          <p className="text-sm text-gray-600">No uploads yet.</p>
        ) : (
          <ul className="divide-y">
            {proposal.versions.map((v) => (
              <li key={v.id} className="flex items-start justify-between gap-4 py-3">
                <div className="min-w-0">
                  <p className="font-medium">v{v.version_no} · {v.title}</p>
                  <p className="text-sm text-gray-600">{v.abstract}</p>
                  <p className="text-xs text-gray-500">
                    {v.original_filename} · {(v.size_bytes / 1024).toFixed(0)} KB · {new Date(v.created_at).toLocaleString()}
                  </p>
                </div>
                <button onClick={() => get(v)} className="shrink-0 rounded border px-2 py-1 text-sm">Download</button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
