import { useEffect, useRef, useState } from "react";
import { api, download } from "../api/client";
import { Alerts, EmptyState, Icon, ICONS, PageHeader } from "../components/ui";
import { when } from "../format";
import { useAction } from "../useAction";

export default function ProposalPage() {
  const [proposal, setProposal] = useState(null);
  const [pending, setPending] = useState(null);
  const [fileName, setFileName] = useState("");
  const { busy, error, notice, setError, run } = useAction();
  const dialog = useRef(null);

  useEffect(() => {
    api("/proposals/mine").then(setProposal).catch((err) => setError(err.message));
  }, [setError]);

  const submit = (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    run("upload", async () => {
      setProposal(await api("/proposals/mine/versions", { method: "POST", body: new FormData(form) }));
      form.reset();
      setFileName("");
      return "Upload complete. Your new version is at the top of the list.";
    });
  };

  const get = (v) => download(v.download_path, v.original_filename).catch((err) => setError(err.message));

  const confirmRemove = () => {
    const v = pending;
    setPending(null);
    run("remove", async () => {
      setProposal(await api(`/proposals/versions/${v.id}`, { method: "DELETE" }));
      return `v${v.version_no} was removed.`;
    });
  };

  const saving = busy === "upload";

  useEffect(() => {
    if (pending) dialog.current.showModal();
    else dialog.current.close();
  }, [pending]);

  return (
    <div className="space-y-8">
      <PageHeader title="Proposal" intro="Each upload is saved as a new version. Older versions stay available until you remove them." />

      <div className="grid items-start gap-6 lg:grid-cols-5">
        <form onSubmit={submit} className="card space-y-5 p-6 lg:col-span-2">
          <h2 className="font-semibold">Upload a new version</h2>
          <label className="label">
            Phase
            <select name="phase" required className="input">
              {proposal?.phases.map((p) => <option key={p}>{p}</option>)}
            </select>
            {proposal?.missed_notice ? (
              <span className="mt-1 block text-xs font-normal text-red-700">{proposal.missed_notice}.</span>
            ) : proposal?.phases.length === 0 && (
              <span className="mt-1 block text-xs font-normal text-zinc-500">No phase is open for uploads right now.</span>
            )}
          </label>
          <label className="label">
            Title
            <input name="title" required maxLength={255} placeholder="Working title of your thesis" className="input" />
          </label>
          <label className="label">
            Abstract
            <textarea name="abstract" required rows={5} placeholder="A short summary of the problem and approach" className="input resize-y" />
          </label>
          <div>
            <span className="label">PDF file</span>
            {/* The real input covers the box, so click and drag-and-drop both work natively. */}
            <div className={`relative mt-1.5 flex flex-col items-center rounded-xl border-2 border-dashed px-4 py-6 text-center transition
              focus-within:border-teal-600 focus-within:ring-3 focus-within:ring-teal-600/15 hover:border-teal-500 hover:bg-teal-50/40 ${
                fileName ? "border-teal-300 bg-teal-50/40" : "border-zinc-300"
              }`}>
              <span className="grid size-10 place-items-center rounded-lg bg-white text-teal-700 shadow-xs ring-1 ring-zinc-200">
                <Icon>{fileName ? ICONS.file : ICONS.upload}</Icon>
              </span>
              <p className="mt-3 max-w-full truncate text-sm font-medium text-zinc-800">{fileName || "Click to choose or drag a PDF here"}</p>
              <p className="mt-0.5 text-xs text-zinc-500">{fileName ? "Click to choose a different file" : <>PDF only{proposal && `, up to ${proposal.max_upload_mb} MB`}</>}</p>
              <input name="file" type="file" accept="application/pdf" required aria-label="PDF file"
                onChange={(e) => setFileName(e.target.files[0]?.name ?? "")}
                className="absolute inset-0 cursor-pointer opacity-0" />
            </div>
          </div>
          <Alerts error={error} notice={notice} />
          <button disabled={saving || !proposal?.phases.length} className="btn-primary w-full">
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
            <EmptyState icon={ICONS.file} title="No uploads yet">Your first version will appear here after you upload it.</EmptyState>
          ) : (
            <ul className="divide-y divide-zinc-100">
              {proposal.versions.map((v) => (
                <li key={v.id} className="flex flex-col gap-3 px-6 py-4 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="badge bg-zinc-50 font-semibold tabular-nums text-zinc-700 ring-zinc-200">v{v.version_no}</span>
                      <span className="badge bg-zinc-50 text-zinc-700 ring-zinc-200">{v.phase}</span>
                      {v.is_latest && <span className="badge bg-teal-50 text-teal-800 ring-teal-600/20">Latest</span>}
                      <p className="truncate font-medium">{v.title}</p>
                    </div>
                    <p className="mt-1.5 line-clamp-2 text-sm text-zinc-600">{v.abstract}</p>
                    <p className="mt-1.5 break-words text-xs text-zinc-500">
                      {v.original_filename} · {v.size_label} · {when(v.created_at)}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <button onClick={() => get(v)} className="btn-secondary px-3 py-1.5">Download</button>
                    {v.can_delete && (
                      <button onClick={() => setPending(v)} aria-label={`Remove v${v.version_no}`}
                        className="btn-ghost-danger px-3 py-1.5">Remove</button>
                    )}
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
          <button onClick={confirmRemove} className="btn-danger">Yes, remove</button>
        </div>
      </dialog>
    </div>
  );
}
