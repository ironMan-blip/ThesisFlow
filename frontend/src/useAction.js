import { useState } from "react";

// Runs a page's API calls: tracks which one is busy and keeps its error or success message.
// run(key, fn): fn may return the success message to show.
export function useAction() {
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  const run = async (key, fn) => {
    setError(null);
    setNotice(null);
    setBusy(key);
    try {
      setNotice((await fn()) ?? null);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  return { busy, error, notice, setError, setNotice, run };
}
