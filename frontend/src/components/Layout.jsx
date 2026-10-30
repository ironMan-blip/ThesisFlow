import { useEffect, useState } from "react";
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api, clearToken, getToken } from "../api/client";
import { TOOLS } from "../tools";

export function Logo() {
  return (
    <span className="flex items-center gap-2 font-semibold tracking-tight">
      <span className="grid size-8 place-items-center rounded-lg bg-teal-700 text-sm font-bold text-white">T</span>
      ThesisFlow
    </span>
  );
}

const navClass = ({ isActive }) =>
  `shrink-0 rounded-md px-3 py-1.5 text-sm font-medium transition focus-visible:ring-3 focus-visible:ring-teal-600/30 focus-visible:outline-none ${
    isActive ? "bg-zinc-100 text-zinc-900" : "text-zinc-600 hover:text-zinc-900"
  }`;

// Loads the current user, guards child routes, and shows the top bar.
// Child pages get the user via useOutletContext().
export default function Layout() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [user, setUser] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const tool = Object.values(TOOLS).find((t) => t.to === pathname);
    document.title = `${tool ? tool.title : pathname === "/" ? "Dashboard" : "Not found"} · ThesisFlow`;
  }, [pathname]);

  useEffect(() => {
    if (!getToken()) return;
    api("/auth/me")
      .then(setUser)
      .catch((err) => {
        if (err.status === 401) {
          clearToken();
          navigate("/login");
        } else {
          setError(err.message);
        }
      });
  }, [navigate]);

  if (!getToken()) return <Navigate to="/login" replace />;
  if (error)
    return (
      <div className="grid min-h-dvh place-items-center p-4">
        <div className="card max-w-sm p-6 text-center">
          <h1 className="font-semibold">We couldn't load your account</h1>
          <p className="mt-1 text-sm text-zinc-600">{error}</p>
          <button onClick={() => window.location.reload()} className="btn-primary mt-4">Try again</button>
        </div>
      </div>
    );
  if (!user)
    return (
      <div className="grid min-h-dvh place-items-center" role="status">
        <span className="size-6 animate-spin rounded-full border-2 border-zinc-300 border-t-teal-700" />
        <span className="sr-only">Loading</span>
      </div>
    );

  const logout = () => {
    clearToken();
    navigate("/login");
  };

  const initials = user.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();

  const links = (
    <>
      <NavLink to="/" end className={navClass}>Dashboard</NavLink>
      {user.tools.map((key) => (
        <NavLink key={key} to={TOOLS[key].to} className={navClass}>{TOOLS[key].title}</NavLink>
      ))}
    </>
  );

  return (
    <div className="min-h-dvh">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-20 focus:rounded-lg focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:shadow-md">
        Skip to content
      </a>
      <header className="sticky top-0 z-10 border-b border-zinc-200 bg-white/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
          <div className="flex items-center gap-6">
            <Link to="/" aria-label="ThesisFlow dashboard"><Logo /></Link>
            <nav aria-label="Main" className="hidden items-center gap-1 sm:flex">{links}</nav>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-medium leading-tight">{user.full_name}</p>
              <p className="text-xs capitalize text-zinc-500">{user.role}</p>
            </div>
            <span className="grid size-9 place-items-center rounded-lg bg-teal-50 text-sm font-semibold text-teal-800">
              {initials}
            </span>
            <button onClick={logout} className="btn-secondary px-3 py-1.5">Log out</button>
          </div>
        </div>
        {/* Phones: same links in a scrollable row under the bar. */}
        <nav aria-label="Main" className="flex gap-1 overflow-x-auto border-t border-zinc-100 px-4 py-2 sm:hidden">{links}</nav>
      </header>
      <main id="main" className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
        <Outlet context={{ user }} />
      </main>
    </div>
  );
}
