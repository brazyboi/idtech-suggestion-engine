import { Link } from "react-router-dom";

export default function PromptManager() {
  return (
    <div className="flex flex-col gap-4 text-black">
      <div>
        <h1 className="text-2xl font-semibold">Prompt Manager</h1>
        <p className="text-sm text-gray-600">
          Prompt management routes are available, but the authoring UI still needs implementation.
        </p>
      </div>
      <Link to="/admin" className="text-sm font-medium text-[#01784B] underline">
        Back to Dashboard
      </Link>
    </div>
  );
}
