import { useEffect, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { api } from "../api/client";
import { CountBadge, Icon, ICONS } from "../components/ui";
import { when } from "../format";
import { TOOLS } from "../tools";

function ToolCard({ to, icon, title, count, children }) {
  return (
    <Link to={to} className="card group relative flex flex-col p-6 transition duration-200 hover:-translate-y-0.5 hover:shadow-lift hover:ring-teal-600/30 focus-visible:ring-2 focus-visible:ring-teal-600 focus-visible:outline-none">
      <span className="grid size-11 place-items-center rounded-xl bg-teal-50 text-teal-700 ring-1 ring-teal-700/10 transition group-hover:bg-teal-700 group-hover:text-white">
        <Icon>{icon}</Icon>
      </span>
      <CountBadge count={count} className="absolute right-5 top-5" />
      <h2 className="mt-5 font-semibold">{title}</h2>
      <p className="mt-1 flex-1 text-sm text-zinc-600">{children}</p>
      <p className="mt-5 text-sm font-medium text-teal-700">Open <span className="inline-block transition group-hover:translate-x-1">→</span></p>
    </Link>
  );
}

// Whole days left, as the Deadlines countdown shows them; hours on the last day.
const timeLeft = (iso) => {
  const h = Math.max(0, Math.floor((new Date(iso) - Date.now()) / 3600000));
  return h >= 24 ? [Math.floor(h / 24), "day"] : [h, "hour"];
};

// One line at the top saying what matters now: the nearest deadline, or how many requests wait for a decision.
function UpNext({ user, counts }) {
  const [next, setNext] = useState(undefined); // undefined = loading, null = nothing due
  const hasDeadlines = user.tools.includes("deadlines");
  useEffect(() => {
    if (!hasDeadlines) return;
    api("/milestones")
      .then((d) => {
        const due = d.milestones.filter((m) => m.countdown_to);
        // The user's own phase first; else the deadline the server counts down to soonest.
        setNext(due.find((m) => m.mine) ?? due.sort((a, b) => new Date(a.countdown_to) - new Date(b.countdown_to))[0] ?? null);
      })
      .catch(() => setNext(null)); // the panel is a shortcut; the Deadlines page shows any error
  }, [hasDeadlines]);

  const pending = Object.values(counts).reduce((a, b) => a + b, 0);
  if (pending)
    return (
      <Link to={TOOLS[Object.keys(counts).find((k) => counts[k])].to} className="alert border-amber-200 bg-amber-50 text-amber-900 transition hover:bg-amber-100/70 focus-visible:ring-3 focus-visible:ring-amber-600/30 focus-visible:outline-none">
        <Icon className="mt-px size-4 text-amber-600">{ICONS.alert}</Icon>
        <span className="flex-1"><span className="font-medium">{pending} {pending === 1 ? "request waits" : "requests wait"} for your decision.</span> Badges below show where.</span>
        <span className="font-medium">Review →</span>
      </Link>
    );
  if (!hasDeadlines || next === null) return null;
  if (next === undefined) return <div className="h-[74px] animate-pulse rounded-2xl bg-zinc-200/60" aria-hidden="true" />;
  const [n, unit] = timeLeft(next.countdown_to);
  return (
    <Link to="/deadlines" className="card group flex flex-wrap items-center gap-x-6 gap-y-2 p-5 transition hover:ring-teal-600/30 focus-visible:ring-2 focus-visible:ring-teal-600 focus-visible:outline-none">
      <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-teal-700 text-white"><Icon>{TOOLS.deadlines.icon}</Icon></span>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-zinc-500">{next.mine ? "Your next deadline" : "Next deadline"}</p>
        <p className="font-semibold">{next.phase} {next.status === "grace" ? "grace time ends" : "is due"} {when(next.countdown_to)}</p>
      </div>
      <p className="text-right">
        <span className="block text-2xl font-semibold tabular-nums leading-none">{n}</span>
        <span className="text-xs text-zinc-500">{unit}{n === 1 ? "" : "s"} left</span>
      </p>
    </Link>
  );
}

export default function HomePage() {
  const { user, counts } = useOutletContext();
  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm font-medium text-teal-700 first-letter:uppercase">{user.role} dashboard</p>
        <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">Welcome back, {user.first_name}</h1>
        <p className="mt-2 text-zinc-600">{new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</p>
      </div>

      <UpNext user={user} counts={counts} />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {user.tools.map((key) => {
          const t = TOOLS[key];
          return <ToolCard key={key} to={t.to} title={t.title} icon={t.icon} count={counts[key]}>{t.text}</ToolCard>;
        })}
      </div>
    </div>
  );
}
