import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, login } from "../api/client";
import { Logo } from "../components/Layout";

export default function LoginPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState("login"); // or "register"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("student");
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [loading, setLoading] = useState(false);

  const registering = mode === "register";

  const switchMode = () => {
    setMode(registering ? "login" : "register");
    setError(null);
    setNotice(null);
  };

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      if (registering) {
        const user = await api("/auth/register", { method: "POST", body: { email, password, full_name: fullName, role } });
        if (!user.approved) {
          setMode("login");
          setNotice("Request sent. The coordinator will review your faculty account within 48 hours. You can log in once it is approved.");
          return;
        }
      }
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
            <h1 className="text-xl font-semibold">{registering ? "Create an account" : "Log in"}</h1>
            <p className="mt-1 text-sm text-zinc-600">Use your university email to continue.</p>
          </div>
          {registering && (
            <>
              <fieldset>
                <legend className="label">I am a</legend>
                <div className="mt-1.5 grid grid-cols-2 gap-2">
                  {["student", "faculty"].map((r) => (
                    <label key={r} className={`btn cursor-pointer capitalize ring-1 ${role === r ? "bg-teal-50 text-teal-800 ring-teal-600" : "bg-white text-zinc-700 ring-zinc-300"}`}>
                      <input type="radio" name="role" value={r} checked={role === r} onChange={() => setRole(r)} className="sr-only" />
                      {r}
                    </label>
                  ))}
                </div>
                {role === "faculty" && (
                  <p className="mt-2 text-xs text-zinc-500">Faculty accounts need coordinator approval (within 48 hours) before you can log in.</p>
                )}
              </fieldset>
              <label className="label">
                Full name
                <input required autoComplete="name" value={fullName} onChange={(e) => setFullName(e.target.value)} className="input" />
              </label>
            </>
          )}
          <label className="label">
            Email
            <input type="email" required autoComplete="email" placeholder="you@university.edu" value={email}
              onChange={(e) => setEmail(e.target.value)} className="input" />
          </label>
          <label className="label">
            Password
            <input type="password" required minLength={registering ? 8 : undefined}
              autoComplete={registering ? "new-password" : "current-password"} value={password}
              onChange={(e) => setPassword(e.target.value)} className="input" />
          </label>
          {error && <p role="alert" className="alert-error">{error}</p>}
          {notice && <p role="status" className="rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 text-sm text-teal-800">{notice}</p>}
          <button disabled={loading} className="btn-primary w-full py-2.5">
            {loading ? "Please wait..." : registering ? "Register" : "Log in"}
          </button>
          <p className="text-center text-sm text-zinc-600">
            {registering ? "Already have an account?" : "New here?"}{" "}
            <button type="button" onClick={switchMode} className="font-medium text-teal-700 hover:underline">
              {registering ? "Log in" : "Register"}
            </button>
          </p>
        </form>
      </div>
    </div>
  );
}
