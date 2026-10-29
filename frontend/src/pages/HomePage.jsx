import { Link, useOutletContext } from "react-router-dom";

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
        {user.role === "student" && (
          <Link to="/proposal" className="card group p-5 transition hover:-translate-y-0.5 hover:shadow-md hover:ring-teal-600/40">
            <span className="grid size-10 place-items-center rounded-lg bg-teal-50 text-teal-700">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" className="size-5" aria-hidden="true">
                <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M12 18v-6M9 15l3-3 3 3" />
              </svg>
            </span>
            <h2 className="mt-4 font-semibold">Proposal</h2>
            <p className="mt-1 text-sm text-zinc-600">Upload a new version and see your past submissions.</p>
            <p className="mt-4 text-sm font-medium text-teal-700">Open <span className="inline-block transition group-hover:translate-x-0.5">→</span></p>
          </Link>
        )}
        <div className="rounded-xl border border-dashed border-zinc-300 p-5 text-sm text-zinc-500">
          More tools will show up here as they are added.
        </div>
      </div>
    </div>
  );
}
