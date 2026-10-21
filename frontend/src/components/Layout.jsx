import { useEffect, useState } from "react";
import { Link, Navigate, Outlet, useNavigate } from "react-router-dom";
import { api, clearToken, getToken } from "../api/client";

// Loads the current user, guards child routes, and shows the top bar.
// Child pages get the user via useOutletContext().
export default function Layout() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [error, setError] = useState(null);

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
  if (error) return <p className="p-4 text-red-600">{error}</p>;
  if (!user) return <p className="p-4">Loading...</p>;

  const logout = () => {
    clearToken();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="flex items-center justify-between border-b bg-white px-4 py-3">
        <Link to="/" className="font-semibold">ThesisFlow</Link>
        <div className="flex items-center gap-3 text-sm">
          <span>{user.full_name} ({user.role})</span>
          <button onClick={logout} className="rounded border px-2 py-1">Log out</button>
        </div>
      </header>
      <main className="mx-auto max-w-5xl p-4">
        <Outlet context={{ user }} />
      </main>
    </div>
  );
}
