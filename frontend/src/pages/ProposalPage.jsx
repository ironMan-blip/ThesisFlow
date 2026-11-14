import { useEffect, useState } from "react";
import { api, download } from "../api/client";
import { Alerts, ConfirmDialog, EmptyState, Icon, ICONS, PageHeader, Skeleton, VersionInfo } from "../components/ui";
import { when } from "../format";
import { useAction } from "../useAction";

export default function ProposalPage() {
  const [proposal, setProposal] = useState(null);
  const [pending, setPending] = useState(null);
  const [fileName, setFileName] = useState("");
  const { busy, error, notice, setError, run } = useAction();

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

  return (
    <div className="space-y-8">
      <PageHeader title="Proposal" intro="Each upload is saved as a new version of your current phase, under your thesis ID. You can remove a version until the phase closes; after that it is your final submission." />

      <div className="grid items-start gap-6 lg:grid-cols-5">
        <form onSubmit={submit} className="card space-y-5 p-6 lg:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">Upload a new version</h2>
            {proposal && (
              <div className="flex gap-2">
                {proposal.thesis_code && <span className="badge bg-zinc-50 font-semibold tabular-nums text-zinc-700 ring-zinc-200">{proposal.thesis_code}</span>}
                {proposal.phase && <span className="badge bg-teal-50 text-teal-800 ring-teal-600/20">{proposal.phase}</span>}
              </div>
            )}
          </div>
          {proposal?.upload_block && (
            <p className="rounded-lg bg-zinc-50 px-3 py-2 text-sm text-zinc-700 ring-1 ring-zinc-200/70 ring-inset">{proposal.upload_block}.</p>
          )}
          {proposal?.freeze_at && (
            <p role="alert" className="alert-error">
              <Icon className="mt-px size-4">{ICONS.alert}</Icon>
              <span>You haven't submitted {proposal.phase} yet. Upload before {when(proposal.freeze_at)} or your account will be frozen.</span>
            </p>
          )}
          <label className="label">
            Title
            <input name="title" required maxLength={255} placeholder="Working title of your thesis" className="input" />
          </label>
          <label className="label">
            Abstract
            <textarea name="abstract" required maxLength={proposal?.max_abstract_chars} rows={5} placeholder="A short summary of the problem and approach" className="input resize-y" />
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
          <button disabled={saving || !proposal || !!proposal.upload_block} className="btn-primary w-full">
            {saving ? "Uploading…" : "Upload version"}
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
            <Skeleton row="h-16 rounded-lg" />
          ) : !proposal.versions.length ? (
            <EmptyState icon={ICONS.file} title="No uploads yet">Your first version will appear here after you upload it.</EmptyState>
          ) : (
            <ul className="divide-y divide-zinc-100">
              {proposal.versions.map((v) => (
                <li key={v.id} className="flex flex-col gap-3 px-6 py-4 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
                  <VersionInfo v={v} abstract />
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

      <ConfirmDialog open={!!pending} title={`Remove v${pending?.version_no}?`} confirm="Yes, remove" danger
        onCancel={() => setPending(null)} onConfirm={confirmRemove}>
        This permanently deletes the version and its PDF. It cannot be undone.
        Later versions will be renumbered to fill the gap.
      </ConfirmDialog>
    </div>
  );
}
