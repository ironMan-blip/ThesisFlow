import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api/client";
import { Logo } from "../components/Layout";

export default function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-[radial-gradient(ellipse_at_top,var(--color-teal-50),transparent_60%)] p-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center"><Logo /></div>
        <form onSubmit={submit} className="card space-y-5 p-7">
          <div>
            <h1 className="text-xl font-semibold">Log in</h1>
            <p className="mt-1 text-sm text-zinc-600">Use your university email to continue.</p>
          </div>
          <label className="label">
            Email
            <input type="email" required autoComplete="email" placeholder="you@university.edu" value={email}
              onChange={(e) => setEmail(e.target.value)} className="input" />
          </label>
          <label className="label">
            Password
            <input type="password" required autoComplete="current-password" value={password}
              onChange={(e) => setPassword(e.target.value)} className="input" />
          </label>
          {error && <p role="alert" className="alert-error">{error}</p>}
          <button disabled={loading} className="btn-primary w-full py-2.5">
            {loading ? "Logging in..." : "Log in"}
          </button>
        </form>
      </div>
    </div>
  );
}
