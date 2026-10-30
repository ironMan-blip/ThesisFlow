import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="py-16 text-center">
      <p className="text-sm font-semibold tabular-nums text-teal-700">404</p>
      <h1 className="mt-2 text-3xl font-semibold">Page not found</h1>
      <p className="mx-auto mt-2 max-w-prose text-zinc-600">This page does not exist or you do not have access to it.</p>
      <Link to="/" className="btn-primary mt-6">Back to dashboard</Link>
    </div>
  );
}
