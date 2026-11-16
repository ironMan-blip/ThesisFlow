import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api, download } from "../api/client";
import { Alerts, EmptyState, Icon, ICONS, PageHeader, ReasonDialog, Skeleton, VersionInfo } from "../components/ui";
import { when } from "../format";
import { useAction } from "../useAction";

export default function ProposalPage() {
  const { user } = useOutletContext();
  const [proposal, setProposal] = useState(null);
  const [fileName, setFileName] = useState("");
  const [asking, setAsking] = useState(null); // version the student is asking to delete
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

  const askDelete = (reason) => {
    const v = asking;
    run("ask", async () => {
      const res = await api(`/proposals/versions/${v.id}/delete-request`, { method: "POST", body: { reason } });
      setProposal(res);
      setAsking(null);
      return `Delete requested for v${v.version_no}. The coordinator decides; if approved it is deleted ${user.deletion_days} days later.`;
    });
  };

  const saving = busy === "upload";

  return (
    <div className="space-y-8">
      <PageHeader title="Proposal" intro={`Each upload is saved as a new version of your current phase, under your thesis ID. Every version is kept. To delete one, give a reason: if the coordinator approves, it is deleted ${user.deletion_days} days later unless they cancel it, and only if the phase is still open then. Your latest upload when the phase closes is your final submission.`} />

      {proposal?.versions.filter((v) => v.delete_by_staff && v.delete_pending).map((v) => (
        // A supervisor or the coordinator scheduled this: the student must get the chance to object in time.
        <div key={v.id} role="alert" className="alert-error">
          <Icon className="mt-px size-4">{ICONS.alert}</Icon>
          <div className="space-y-1">
            <p className="font-medium">v{v.version_no} ("{v.title}") is scheduled for deletion on {when(v.delete_executes_at)}.</p>
            <p className="whitespace-pre-line break-words">Reason: {v.delete_reason}</p>
            <p>
              If this is a mistake or you have a problem with it, contact the coordinator at{" "}
              <a href={`mailto:${proposal.coordinator_contact}`} className="font-medium underline">{proposal.coordinator_contact}</a>{" "}
              before then. Only the coordinator can cancel it.
            </p>
          </div>
        </div>
      ))}

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
                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                    {v.delete_pending && <span className="badge bg-amber-50 text-amber-800 ring-amber-600/20">{v.delete_executes_at ? `Deletes on ${when(v.delete_executes_at)}` : "Delete requested"}</span>}
                    {v.delete_rejected && <span className="badge bg-zinc-50 text-zinc-700 ring-zinc-200">Delete request rejected</span>}
                    <button onClick={() => get(v)} className="btn-secondary px-3 py-1.5">Download</button>
                    {v.can_request_delete && (
                      <button onClick={() => { setError(null); setAsking(v); }} disabled={busy === "ask"} aria-label={`Ask to delete v${v.version_no}`}
                        className="btn-ghost-danger px-3 py-1.5">Ask to delete</button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <ReasonDialog open={!!asking} title={`Delete v${asking?.version_no}?`} confirm="Schedule delete" busy={busy === "ask"} error={error}
        min={user.min_reason_chars} max={user.max_reason_chars} onCancel={() => setAsking(null)} onSubmit={askDelete}>
        If the coordinator approves, the version and its PDF are deleted {user.deletion_days} days after that, and later versions are
        renumbered. You can't take this back: only the coordinator can reject or cancel it. If the phase closes first, the version is kept as a final submission.
      </ReasonDialog>

    </div>
  );
}
