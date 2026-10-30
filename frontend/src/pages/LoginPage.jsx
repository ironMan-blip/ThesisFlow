import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, login } from "../api/client";
import { Alerts, Logo } from "../components/ui";
import { useAction } from "../useAction";

export default function LoginPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState("login"); // or "register"
  const [email, setEmail] = useState("");
  const [idNumber, setIdNumber] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("student");
  const [initials, setInitials] = useState("");
  const { busy, error, notice, setError, setNotice, run } = useAction();
  const [showPassword, setShowPassword] = useState(false);

  const registering = mode === "register";

  useEffect(() => {
    document.title = `${registering ? "Register" : "Log in"} · ThesisFlow`;
  }, [registering]);

  const switchMode = () => {
    setMode(registering ? "login" : "register");
    setError(null);
    setNotice(null);
  };

  const submit = (e) => {
    e.preventDefault();
    run("submit", async () => {
      // Every sign-up waits for coordinator approval, so registering never logs in.
      if (registering) {
        await api("/auth/register", { method: "POST", body: { email, id_number: idNumber, password, full_name: fullName, role, initials: role === "faculty" ? initials : null } });
        setMode("login");
        return "Request sent. The coordinator will review your account within 48 hours. You can log in once it is approved.";
      }
      await login(idNumber, password);
      navigate("/");
    });
  };

  const loading = busy === "submit";

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-[radial-gradient(ellipse_at_top,var(--color-teal-50),transparent_60%)] p-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center"><Logo /></div>
        <form onSubmit={submit} className="card space-y-5 p-7">
          <div>
            <h1 className="text-xl font-semibold">{registering ? "Create an account" : "Log in"}</h1>
            <p className="mt-1 text-sm text-zinc-600">Use your 8-digit university ID to continue.</p>
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
                <p className="mt-2 text-xs text-zinc-500">New accounts need coordinator approval (within 48 hours) before you can log in.</p>
              </fieldset>
              <label className="label">
                Full name
                <input required autoComplete="name" value={fullName} onChange={(e) => setFullName(e.target.value)} className="input" />
              </label>
              {role === "faculty" && (
                <label className="label">
                  Initials
                  <input required pattern="[A-Z]{1,10}" maxLength={10} title="Capital letters only" placeholder="ABC" value={initials}
                    onChange={(e) => setInitials(e.target.value.toUpperCase())} className="input" />
                </label>
              )}
              <label className="label">
                Email
                <input type="email" required autoComplete="email" placeholder="you@university.edu" value={email}
                  onChange={(e) => setEmail(e.target.value)} className="input" />
              </label>
            </>
          )}
          <label className="label">
            ID number
            <input required inputMode="numeric" pattern="[0-9]{8}" maxLength={8} title="Exactly 8 digits" autoComplete="username"
              placeholder="12345678" value={idNumber} onChange={(e) => setIdNumber(e.target.value)} className="input" />
          </label>
          <div>
            <div className="flex items-center justify-between">
              <label htmlFor="password" className="label">Password</label>
              <button type="button" onClick={() => setShowPassword((s) => !s)} aria-controls="password"
                className="text-xs font-medium text-teal-700 hover:underline">
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
            <input id="password" type={showPassword ? "text" : "password"} required minLength={registering ? 8 : undefined}
              autoComplete={registering ? "new-password" : "current-password"} value={password}
              onChange={(e) => setPassword(e.target.value)} aria-describedby={registering ? "password-hint" : undefined} className="input" />
            {registering && <p id="password-hint" className="mt-1 text-xs text-zinc-500">At least 8 characters, with an uppercase letter, a lowercase letter and a number. No spaces.</p>}
          </div>
          <Alerts error={error} notice={notice} />
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
