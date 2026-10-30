// Small pieces every page shares.

export function Logo() {
  return (
    <span className="flex items-center gap-2 font-semibold tracking-tight">
      <span className="grid size-8 place-items-center rounded-lg bg-teal-700 text-sm font-bold text-white">T</span>
      ThesisFlow
    </span>
  );
}

export function PageHeader({ title, intro, children }) {
  return (
    <div>
      <h1 className="text-3xl font-semibold">{title}</h1>
      {intro && <p className="mt-2 max-w-prose text-zinc-600">{intro}</p>}
      {children}
    </div>
  );
}

export function Alerts({ error, notice }) {
  return (
    <>
      {error && <p role="alert" className="alert-error">{error}</p>}
      {notice && <p role="status" className="alert-success">{notice}</p>}
    </>
  );
}

// Live pending-request count, shown as a "3 pending" pill with a pulsing dot.
export function CountBadge({ count, className = "" }) {
  if (!count) return null;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800 ring-1 ring-amber-600/20 ring-inset ${className}`}>
      <span className="relative flex size-2" aria-hidden="true">
        <span className="absolute inline-flex size-full rounded-full bg-amber-400 opacity-75 motion-safe:animate-ping" />
        <span className="relative inline-flex size-2 rounded-full bg-amber-500" />
      </span>
      <span className="tabular-nums">{count > 99 ? "99+" : count}</span> pending
    </span>
  );
}
