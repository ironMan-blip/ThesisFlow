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
