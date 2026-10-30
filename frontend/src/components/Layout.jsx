import { useCallback, useEffect, useState } from "react";
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api, clearToken, getToken } from "../api/client";
import { TOOLS } from "../tools";
import { Avatar, CountBadge, Icon, ICONS, Logo } from "./ui";

const navClass = ({ isActive }) =>
  `flex min-h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium transition focus-visible:ring-3 focus-visible:ring-teal-600/30 focus-visible:outline-none ${
    isActive ? "bg-teal-50 text-teal-900 [&>svg]:text-teal-700" : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 [&>svg]:text-zinc-400"
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

  // Badge counts per tool from the API (empty unless the user has requests to decide);
  // refetched on page change, every 10s, and on tab focus.
  const [counts, setCounts] = useState({});
  const refreshCounts = useCallback(() => {
    if (user) api("/auth/me/counts").then(setCounts).catch(() => {});
  }, [user]);
  useEffect(refreshCounts, [refreshCounts, pathname]);
  const hasCounts = Object.keys(counts).length > 0;
  useEffect(() => {
    if (!hasCounts) return;
    // shortcut: polling, not push; switch to SSE/WebSocket if many coordinators are online at once.
    const id = setInterval(() => document.visibilityState === "visible" && refreshCounts(), 10000);
    window.addEventListener("focus", refreshCounts);
    return () => {
      clearInterval(id);
      window.removeEventListener("focus", refreshCounts);
    };
  }, [hasCounts, refreshCounts]);

  // Phone drawer; closes whenever the page changes.
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => setMenuOpen(false), [pathname]);
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e) => e.key === "Escape" && setMenuOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

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

  // Same sidebar on desktop (fixed) and phones (drawer).
  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex h-16 shrink-0 items-center justify-between px-5">
        <Link to="/" aria-label="ThesisFlow dashboard"><Logo /></Link>
        <button onClick={() => setMenuOpen(false)} aria-label="Close menu" className="btn -mr-2 size-10 p-0 text-zinc-500 hover:bg-zinc-100 lg:hidden">
          <Icon>{ICONS.close}</Icon>
        </button>
      </div>
      <nav aria-label="Main" className="flex-1 space-y-1 overflow-y-auto px-3 py-2">
        <NavLink to="/" end className={navClass}><Icon>{ICONS.home}</Icon>Dashboard</NavLink>
        {user.tools.map((key) => (
          <NavLink key={key} to={TOOLS[key].to} className={navClass}>
            <Icon>{TOOLS[key].icon}</Icon>
            <span className="flex-1 truncate">{TOOLS[key].title}</span>
            <CountBadge count={counts[key]} compact />
          </NavLink>
        ))}
      </nav>
      <div className="flex items-center gap-3 border-t border-zinc-200 p-4">
        <Avatar user={user} className="size-9 text-sm" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium leading-tight">{user.full_name}</p>
          <p className="text-xs capitalize text-zinc-500">{user.role}</p>
        </div>
        <button onClick={logout} aria-label="Log out" title="Log out" className="btn size-9 p-0 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900">
          <Icon className="size-[18px]">{ICONS.logout}</Icon>
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-dvh">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:shadow-md">
        Skip to content
      </a>

      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-zinc-200 bg-white lg:block">{sidebar}</aside>

      {/* Phones and tablets: top bar + slide-in drawer. Rendered only when open, so it is out of the tab order otherwise. */}
      <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-zinc-200 bg-white/85 px-4 backdrop-blur lg:hidden">
        <Link to="/" aria-label="ThesisFlow dashboard"><Logo /></Link>
        <button onClick={() => setMenuOpen(true)} aria-label="Open menu" aria-expanded={menuOpen} className="btn -mr-2 size-10 p-0 text-zinc-600 hover:bg-zinc-100">
          <Icon>{ICONS.menu}</Icon>
        </button>
      </header>
      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="absolute inset-0 bg-zinc-900/40 backdrop-blur-[2px]" onClick={() => setMenuOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 max-w-[85vw] bg-white shadow-xl">{sidebar}</aside>
        </div>
      )}

      <main id="main" className="lg:pl-64">
        <div className="mx-auto max-w-5xl px-4 py-8 sm:px-8 sm:py-10">
          <Outlet context={{ user, counts, refreshCounts }} />
        </div>
      </main>
    </div>
  );
}
