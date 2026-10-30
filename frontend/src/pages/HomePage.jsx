import { Link, useOutletContext } from "react-router-dom";
import { TOOLS } from "../tools";

function ToolCard({ to, icon, title, children }) {
  return (
    <Link to={to} className="card group p-5 transition hover:-translate-y-0.5 hover:shadow-md hover:ring-teal-600/40 focus-visible:ring-2 focus-visible:ring-teal-600 focus-visible:outline-none">
      <span className="grid size-10 place-items-center rounded-lg bg-teal-50 text-teal-700">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" className="size-5" aria-hidden="true">
          {icon}
        </svg>
      </span>
      <h2 className="mt-4 font-semibold">{title}</h2>
      <p className="mt-1 text-sm text-zinc-600">{children}</p>
      <p className="mt-4 text-sm font-medium text-teal-700">Open <span className="inline-block transition group-hover:translate-x-0.5">→</span></p>
    </Link>
  );
}

export default function HomePage() {
  const { user } = useOutletContext();
  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm font-medium text-teal-700 capitalize">{user.role} dashboard</p>
        <h1 className="mt-1 text-3xl font-semibold">Welcome back, {user.full_name.split(" ")[0]}</h1>
        <p className="mt-2 max-w-prose text-zinc-600">Here is where your thesis work lives.</p>
      </div>

      {user.tools.length ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {user.tools.map((key) => {
            const t = TOOLS[key];
            return <ToolCard key={key} to={t.to} title={t.title} icon={t.icon}>{t.text}</ToolCard>;
          })}
        </div>
      ) : (
        <p className="rounded-xl border border-dashed border-zinc-300 p-5 text-sm text-zinc-500">
          No tools are available for your account yet.
        </p>
      )}
    </div>
  );
}
