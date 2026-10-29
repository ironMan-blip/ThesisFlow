import { Link, useOutletContext } from "react-router-dom";

export default function HomePage() {
  const { user } = useOutletContext();
  return (
    <div>
      <h1 className="text-2xl font-semibold">Welcome, {user.full_name}</h1>
      <p className="mt-2 text-gray-600">Feature pages go here.</p>
      {user.role === "student" && (
        <Link to="/proposal" className="mt-4 inline-block underline">Proposal upload</Link>
      )}
    </div>
  );
}
