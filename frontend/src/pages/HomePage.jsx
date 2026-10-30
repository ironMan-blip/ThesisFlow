import { Link, useOutletContext } from "react-router-dom";

// Display info only; which tools a user gets comes from the API (user.tools).
const TOOLS = {
  proposal: {
    to: "/proposal", title: "Proposal", text: "Upload a new version and see your past submissions.",
    icon: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M12 18v-6M9 15l3-3 3 3" /></>,
  },
  deadlines: {
    to: "/deadlines", title: "Deadlines", text: "P1, P2 and P3 due dates, grace time and countdowns.",
    icon: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  },
  faculty_requests: {
    to: "/faculty-requests", title: "Faculty requests", text: "Approve or reject faculty who registered.",
    icon: <><circle cx="9" cy="8" r="4" /><path d="M2 21a7 7 0 0 1 14 0M16 11l2 2 4-4" /></>,
  },
};

function ToolCard({ to, icon, title, children }) {
  return (
    <Link to={to} className="card group p-5 transition hover:-translate-y-0.5 hover:shadow-md hover:ring-teal-600/40">
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

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {user.tools.map((key) => {
          const t = TOOLS[key];
          return <ToolCard key={key} to={t.to} title={t.title} icon={t.icon}>{t.text}</ToolCard>;
        })}
        <div className="rounded-xl border border-dashed border-zinc-300 p-5 text-sm text-zinc-500">
          More tools will show up here as they are added.
        </div>
      </div>
    </div>
  );
}
