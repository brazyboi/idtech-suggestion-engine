import { Link } from "react-router-dom";

export default function DocManager() {
  return (
    <div className="flex flex-col gap-4 text-black">
      <div>
        <h1 className="text-2xl font-semibold">Doc Manager</h1>
        <p className="text-sm text-gray-600">
          Documentation management routes are wired in, but the editor UI has not been implemented yet.
        </p>
      </div>
      <Link to="/admin" className="text-sm font-medium text-[#01784B] underline">
        Back to Dashboard
      </Link>
    </div>
  );
}
