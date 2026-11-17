import { useEffect, useState } from "react";
import { api, download, upload } from "../api/client";
import { Alerts, EmptyState, Icon, ICONS, PageHeader, Skeleton, VersionInfo } from "../components/ui";
import { when } from "../format";
import { useAction } from "../useAction";

export default function ProposalPage() {
  const [proposal, setProposal] = useState(null);
  const [fileName, setFileName] = useState("");
  const [progress, setProgress] = useState(0); // share of the file sent, 0 to 1
  const { busy, error, notice, setError, run } = useAction();

  useEffect(() => {
    api("/proposals/mine").then(setProposal).catch((err) => setError(err.message));
  }, [setError]);

  const submit = (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    setProgress(0);
    run("upload", async () => {
      setProposal(await upload("/proposals/mine/versions", new FormData(form), setProgress));
      form.reset();
      setFileName("");
      return "Upload complete. Your new version is at the top of the list.";
    });
  };

  const get = (v) => download(v.download_path, v.original_filename).catch((err) => setError(err.message));

  const saving = busy === "upload";

  return (
    <div className="space-y-8">
      <PageHeader title="Proposal" intro="Upload a new version of your proposal and see everything you have handed in." help={[
        "Each upload is saved as a new version of your current phase, under your thesis ID. Every version is kept.",
        "Your latest upload when the phase closes is your final submission. Versions can't be deleted.",
      ]} />

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
            <p role="status" className="alert border-amber-200 bg-amber-50 text-amber-900">
              <Icon className="mt-px size-4">{ICONS.alert}</Icon><span>{proposal.upload_block}.</span>
            </p>
          )}
          {proposal?.freeze_at && (
            <p role="alert" className="alert-error">
              <Icon className="mt-px size-4">{ICONS.alert}</Icon>
              <span>You haven't submitted {proposal.phase} yet. Upload before {when(proposal.freeze_at)} or your account will be frozen.</span>
            </p>
          )}
          {proposal?.title && (
            <p className="text-sm text-zinc-500">Your first upload set the title and abstract. Every upload must use them exactly.</p>
          )}
          {/* Fields stay visible but locked while uploads are blocked, so nobody fills a form they can't send. */}
          <fieldset disabled={!!proposal?.upload_block} className="space-y-5">
          <label className="label">
            Title
            <input key={`t-${proposal?.title}`} name="title" required maxLength={255} defaultValue={proposal?.title ?? ""}
              placeholder="Working title of your thesis" className="input" />
          </label>
          <label className="label">
            Abstract
            <textarea key={`a-${proposal?.abstract}`} name="abstract" required maxLength={proposal?.max_abstract_chars} rows={5}
              defaultValue={proposal?.abstract ?? ""} placeholder="A short summary of the problem and approach" className="input resize-y" />
          </label>
          <div>
            <span className="label">PDF file</span>
            {/* The real input covers the box, so click and drag-and-drop both work natively. */}
            <div className={`relative mt-1.5 flex flex-col items-center rounded-xl border-2 border-dashed px-4 py-6 text-center transition
              focus-within:border-teal-600 focus-within:ring-3 focus-within:ring-teal-600/15 hover:border-teal-500 hover:bg-teal-50/40
              has-disabled:border-zinc-200 has-disabled:bg-zinc-50 has-disabled:opacity-60 has-disabled:pointer-events-none ${
                fileName ? "border-teal-300 bg-teal-50/40" : "border-zinc-300"
              }`}>
              <span className="grid size-10 place-items-center rounded-lg bg-white text-teal-700 shadow-xs ring-1 ring-zinc-200">
                <Icon>{fileName ? ICONS.file : ICONS.upload}</Icon>
              </span>
              <p className="mt-3 max-w-full truncate text-sm font-medium text-zinc-800">{fileName || "Click to choose or drag a PDF here"}</p>
              <p className="mt-0.5 text-xs text-zinc-500">{fileName ? "Click to choose a different file" : <>PDF only{proposal && `, up to ${proposal.max_upload_mb} MB`}</>}</p>
              <input name="file" type="file" accept="application/pdf" required aria-label="PDF file"
                onChange={(e) => setFileName(e.target.files[0]?.name ?? "")}
                className="absolute inset-0 cursor-pointer opacity-0 disabled:cursor-not-allowed" />
            </div>
          </div>
          </fieldset>
          <Alerts error={error} notice={notice} />
          <button disabled={saving || !proposal || !!proposal.upload_block} className="btn-primary w-full">
            {/* After the last byte the server still scans and checks the file, so say so instead of sitting at 100%. */}
            {!saving ? "Upload version" : progress < 1 ? `Uploading… ${Math.round(progress * 100)}%` : "Checking the file…"}
          </button>
          {saving && (
            <div role="progressbar" aria-label="Upload progress" aria-valuemin={0} aria-valuemax={100}
              aria-valuenow={Math.round(progress * 100)} className="-mt-3 h-1.5 overflow-hidden rounded-full bg-zinc-100">
              <div className={`h-full rounded-full bg-teal-600 transition-[width] duration-200 ${progress >= 1 ? "animate-pulse" : ""}`}
                style={{ width: `${Math.max(progress, 0.02) * 100}%` }} />
            </div>
          )}
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
                    <button onClick={() => get(v)} className="btn-secondary px-3 py-1.5">Download</button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {proposal?.title && <TitleChange proposal={proposal} setProposal={setProposal} />}

    </div>
  );
}

const CHANGE_BADGE = {
  pending: ["Waiting for your supervisor", "bg-amber-50 text-amber-800 ring-amber-600/20"],
  approved: ["Approved", "bg-teal-50 text-teal-800 ring-teal-600/20"],
  rejected: ["Rejected by your supervisor", "bg-zinc-50 text-zinc-700 ring-zinc-200"],
  expired: ["Expired: not accepted in time", "bg-zinc-50 text-zinc-700 ring-zinc-200"],
};

function TitleChange({ proposal, setProposal }) {
  const { busy, error, notice, run } = useAction();
  const change = proposal.title_change;
  const submit = (e) => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(e.currentTarget));
    run("title", async () => {
      setProposal(await api("/proposals/mine/title-change", { method: "POST", body }));
      return `Change requested. Your supervisor has ${proposal.title_change_days} days to accept it.`;
    });
  };
  const [label, tone] = change ? CHANGE_BADGE[change.status] : [];
  return (
    <section className="card space-y-5 p-6">
      <div>
        <h2 className="font-semibold">Change title or abstract</h2>
        <p className="mt-1 text-sm text-zinc-500">
          You can change them once. Your supervisor must accept the request within {proposal.title_change_days} days; then upload with the new title and abstract.
        </p>
      </div>
      {change && (
        <div className="space-y-1 rounded-lg bg-zinc-50 px-4 py-3 text-sm ring-1 ring-zinc-200/70 ring-inset">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">Your request: "{change.title}"</span>
            <span className={`badge ${tone}`}>{label}</span>
          </div>
          {change.status === "pending" && <p className="text-zinc-500">Your supervisor must accept by {when(change.expires_at)}.</p>}
          <p className="whitespace-pre-line break-words text-zinc-600">{change.abstract}</p>
        </div>
      )}
      {proposal.can_request_title_change ? (
        <form onSubmit={submit} className="space-y-4">
          <label className="label">
            New title
            <input name="title" required maxLength={255} defaultValue={proposal.title} className="input" />
          </label>
          <label className="label">
            New abstract
            <textarea name="abstract" required maxLength={proposal.max_abstract_chars} rows={4} defaultValue={proposal.abstract} className="input resize-y" />
          </label>
          <button disabled={!!busy} className="btn-secondary">{busy ? "Sending…" : "Ask supervisor to change"}</button>
        </form>
      ) : change?.status === "approved" && (
        <p className="text-sm text-zinc-500">You have used your one change.</p>
      )}
      <Alerts error={error} notice={notice} />
    </section>
  );
}
