// Small pieces every page shares.

// Outline icon in a 24px grid; `children` are the SVG paths (see TOOLS and ICONS).
export function Icon({ children, className = "size-5" }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"
      className={`shrink-0 ${className}`} aria-hidden="true">
      {children}
    </svg>
  );
}

export const ICONS = {
  home: <><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9v11h14V9" /><path d="M10 20v-6h4v6" /></>,
  logout: <><path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" /><path d="M10 16l-4-4 4-4M6 12h10" /></>,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></>,
  check: <><circle cx="12" cy="12" r="9" /><path d="m8 12 3 3 5-6" /></>,
  alert: <><circle cx="12" cy="12" r="9" /><path d="M12 8v5M12 16h.01" /></>,
  inbox: <><path d="M3 13h5l1.5 3h5L16 13h5" /><path d="M5 5h14l2 8v6H3v-6z" /></>,
  upload: <><path d="M12 16V4M7 9l5-5 5 5" /><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" /></>,
  file: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></>,
};

export function Logo({ light = false }) {
  return (
    <span className={`flex items-center gap-2.5 font-semibold tracking-tight ${light ? "text-white" : ""}`}>
      <span className={`grid size-8 place-items-center rounded-lg text-sm font-bold ${light ? "bg-white text-teal-800" : "bg-teal-700 text-white"}`}>T</span>
      ThesisFlow
    </span>
  );
}

export function PageHeader({ title, intro }) {
  return (
    <div>
      <h1 className="text-2xl font-semibold sm:text-3xl">{title}</h1>
      {intro && <p className="mt-2 max-w-prose text-zinc-600">{intro}</p>}
    </div>
  );
}

// Grey placeholder rows while a list loads.
export function Skeleton({ rows = 2, row = "h-14 rounded-lg", className = "space-y-3 p-6" }) {
  return (
    <div className={className} aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => <div key={i} className={`animate-pulse bg-zinc-100 ${row}`} />)}
    </div>
  );
}

export function Alerts({ error, notice }) {
  return (
    <>
      {error && <p role="alert" className="alert-error"><Icon className="mt-px size-4">{ICONS.alert}</Icon><span>{error}</span></p>}
      {notice && <p role="status" className="alert-success"><Icon className="mt-px size-4">{ICONS.check}</Icon><span>{notice}</span></p>}
    </>
  );
}

export function Avatar({ user, className = "size-10 text-sm" }) {
  return (
    <span className={`grid shrink-0 place-items-center rounded-xl bg-teal-50 font-semibold text-teal-800 ring-1 ring-teal-700/10 ${className}`} aria-hidden="true">
      {user.monogram}
    </span>
  );
}

// A user's avatar, name, initials, role, ID and email; children add to the end of the second line.
export function Person({ user, children }) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <Avatar user={user} />
      <div className="min-w-0">
        <p className="font-medium">
          {user.full_name}{user.initials && ` (${user.initials})`}{" "}
          <span className="badge bg-zinc-50 align-middle font-normal capitalize text-zinc-600 ring-zinc-200">{user.role}</span>
        </p>
        <p className="mt-0.5 break-words text-sm text-zinc-500">
          <span className="tabular-nums">ID {user.id_number}</span> · {user.email}{children}
        </p>
      </div>
    </div>
  );
}

export function EmptyState({ icon = ICONS.inbox, title, children }) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      <span className="grid size-12 place-items-center rounded-xl bg-zinc-100 text-zinc-500"><Icon className="size-6">{icon}</Icon></span>
      <p className="mt-4 font-medium">{title}</p>
      {children && <p className="mt-1 max-w-sm text-sm text-zinc-500">{children}</p>}
    </div>
  );
}

// Live pending-request count, shown as a "3 pending" pill with a pulsing dot; `compact` drops the word.
export function CountBadge({ count, compact = false, className = "" }) {
  if (!count) return null;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 ring-1 ring-amber-600/20 ring-inset ${className}`}>
      <span className="relative flex size-2" aria-hidden="true">
        <span className="absolute inline-flex size-full rounded-full bg-amber-400 opacity-75 motion-safe:animate-ping" />
        <span className="relative inline-flex size-2 rounded-full bg-amber-500" />
      </span>
      <span className="tabular-nums">{count > 99 ? "99+" : count}</span>{compact ? <span className="sr-only"> pending</span> : " pending"}
    </span>
  );
}
