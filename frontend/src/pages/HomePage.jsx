import { Link, useOutletContext } from "react-router-dom";
import { CountBadge, Icon } from "../components/ui";
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

export default function HomePage() {
  const { user, counts } = useOutletContext();
  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm font-medium text-teal-700 capitalize">{user.role} dashboard</p>
        <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">Welcome back, {user.first_name}</h1>
        <p className="mt-2 max-w-prose text-zinc-600">Pick up where you left off. Everything you can do is one click away.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {user.tools.map((key) => {
          const t = TOOLS[key];
          return <ToolCard key={key} to={t.to} title={t.title} icon={t.icon} count={counts[key]}>{t.text}</ToolCard>;
        })}
      </div>
    </div>
  );
}
