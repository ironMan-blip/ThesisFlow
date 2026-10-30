import { useEffect, useRef, useState } from "react";
import { api, download } from "../api/client";

export default function ProposalPage() {
  const [proposal, setProposal] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [pending, setPending] = useState(null);
  const dialog = useRef(null);

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

  const get = (v) => download(v.download_path, v.original_filename).catch((err) => setError(err.message));

  const confirmRemove = async () => {
    const v = pending;
    setPending(null);
    setError(null);
    try {
      setProposal(await api(`/proposals/versions/${v.id}`, { method: "DELETE" }));
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    if (pending) dialog.current.showModal();
    else dialog.current.close();
  }, [pending]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold">Proposal</h1>
        <p className="mt-2 max-w-prose text-zinc-600">Each upload is saved as a new version. Older versions stay available until you remove them.</p>
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-5">
        <form onSubmit={submit} className="card space-y-5 p-6 lg:col-span-2">
          <h2 className="font-semibold">Upload a new version</h2>
          <label className="label">
            Phase
            <select name="phase" required defaultValue="P1" className="input">
              <option>P1</option>
              <option>P2</option>
              <option>P3</option>
            </select>
          </label>
          <label className="label">
            Title
            <input name="title" required maxLength={255} placeholder="Working title of your thesis" className="input" />
          </label>
          <label className="label">
            Abstract
            <textarea name="abstract" required rows={5} placeholder="A short summary of the problem and approach" className="input resize-y" />
          </label>
          <label className="label">
            PDF file
            <input name="file" type="file" accept="application/pdf" required
              className="mt-1.5 block w-full cursor-pointer rounded-lg border border-dashed border-zinc-300 p-2 text-sm text-zinc-600
                file:mr-3 file:cursor-pointer file:rounded-md file:border-0 file:bg-teal-50 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-teal-800 hover:file:bg-teal-100" />
            <span className="mt-1 block text-xs font-normal text-zinc-500">PDF only.</span>
          </label>
          {error && <p role="alert" className="alert-error">{error}</p>}
          <button disabled={saving} className="btn-primary w-full">
            {saving ? "Uploading..." : "Upload version"}
          </button>
        </form>

        <section className="card lg:col-span-3">
          <div className="flex items-center justify-between border-b border-zinc-200 px-6 py-4">
            <h2 className="font-semibold">Versions</h2>
            {proposal?.versions.length > 0 && (
              <span className="text-sm tabular-nums text-zinc-500">{proposal.versions.length} total</span>
            )}
          </div>
          {!proposal ? (
            <div className="space-y-3 p-6" aria-hidden="true">
              {[0, 1].map((i) => <div key={i} className="h-16 animate-pulse rounded-lg bg-zinc-100" />)}
            </div>
          ) : !proposal.versions.length ? (
            <div className="px-6 py-14 text-center">
              <p className="font-medium">No uploads yet</p>
              <p className="mt-1 text-sm text-zinc-500">Your first version will appear here after you upload it.</p>
            </div>
          ) : (
            <ul className="divide-y divide-zinc-100">
              {proposal.versions.map((v) => (
                <li key={v.id} className="flex items-start justify-between gap-4 px-6 py-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="rounded-md bg-zinc-100 px-1.5 py-0.5 text-xs font-semibold tabular-nums text-zinc-700">v{v.version_no}</span>
                      <span className="rounded-md bg-zinc-100 px-1.5 py-0.5 text-xs font-medium text-zinc-700">{v.phase}</span>
                      {v.is_latest &&<span className="rounded-md bg-teal-50 px-1.5 py-0.5 text-xs font-medium text-teal-800">Latest</span>}
                      <p className="truncate font-medium">{v.title}</p>
                    </div>
                    <p className="mt-1.5 line-clamp-2 text-sm text-zinc-600">{v.abstract}</p>
                    <p className="mt-1.5 break-words text-xs text-zinc-500">
                      {v.original_filename} · {v.size_label} · {new Date(v.created_at).toLocaleString()}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <button onClick={() => get(v)} className="btn-secondary px-3 py-1.5">Download</button>
                    <button onClick={() => setPending(v)} aria-label={`Remove v${v.version_no}`}
                      className="btn-secondary px-3 py-1.5 text-red-700 hover:bg-red-50">Remove</button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {/* Esc closes the dialog natively; onClose keeps state in sync. */}
      <dialog ref={dialog} onClose={() => setPending(null)} aria-labelledby="remove-title"
        className="card m-auto w-full max-w-md p-6 backdrop:bg-zinc-900/40">
        <h2 id="remove-title" className="font-semibold">Remove v{pending?.version_no}?</h2>
        <p className="mt-2 text-sm text-zinc-600">
          This permanently deletes the version and its PDF. It cannot be undone.
          Later versions will be renumbered to fill the gap.
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <button onClick={() => setPending(null)} autoFocus className="btn-secondary">Cancel</button>
          <button onClick={confirmRemove} className="btn bg-red-700 text-white shadow-sm hover:bg-red-800">Yes, remove</button>
        </div>
      </dialog>
    </div>
  );
}
