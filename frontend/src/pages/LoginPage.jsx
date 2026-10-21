import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api/client";

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
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-3 rounded border bg-white p-6">
        <h1 className="text-xl font-semibold">Log in to ThesisFlow</h1>
        <label className="block text-sm">
          Email
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded border px-2 py-1" />
        </label>
        <label className="block text-sm">
          Password
          <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded border px-2 py-1" />
        </label>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button disabled={loading} className="w-full rounded bg-black py-2 text-white disabled:opacity-50">
          {loading ? "Logging in..." : "Log in"}
        </button>
      </form>
    </div>
  );
}
