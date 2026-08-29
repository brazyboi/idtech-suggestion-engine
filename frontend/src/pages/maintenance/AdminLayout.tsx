import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import "./admin.css";
import IDTechLogo from "./components/IDTechLogo";
import { adminFetch, clearAdminKey, getAdminKey, setAdminKey } from "../../api/adminAuth";

const navLinks = [
  { to: "/admin", label: "Dashboard", end: true },
  { to: "/admin/leads", label: "Leads" },
  { to: "/admin/hardware", label: "Hardware" },
  { to: "/admin/software", label: "Software" },
  { to: "/admin/categories", label: "Categories" },
  { to: "/admin/use-cases", label: "Use Cases" },
];

type AuthStatus = "checking" | "authed" | "unauthed";

export default function AdminLayout() {
  // Re-verify stored keys before showing the admin UI; the backend remains the real gate.
  const [status, setStatus] = useState<AuthStatus>(() => (getAdminKey() ? "checking" : "unauthed"));

  useEffect(() => {
    if (status !== "checking") {
      return;
    }
    let cancelled = false;
    adminFetch("/api/lead/metrics")
      .then((res) => {
        if (cancelled) return;
        if (res.ok) {
          setStatus("authed");
        } else {
          clearAdminKey();
          setStatus("unauthed");
        }
      })
      .catch(() => {
        if (cancelled) return;
        clearAdminKey();
        setStatus("unauthed");
      });
    return () => {
      cancelled = true;
    };
  }, [status]);

  if (status === "checking") {
    return (
      <div className="flex w-screen h-screen items-center justify-center bg-black">
        <p className="text-white text-sm">Checking admin session...</p>
      </div>
    );
  }

  if (status === "unauthed") {
    return <AdminLogin onAuthed={() => setStatus("authed")} />;
  }

  return (
    <div className="flex bg-black w-screen h-screen overflow-hidden items-center">
      <div className="flex flex-col bg-white h-full flex-1 min-w-0">
        <DashboardNavbar />
        <div id="dashboard-page" className="flex flex-col p-5 bg-white flex-1 min-h-0 overflow-hidden">
          <div className="flex bg-white flex-1 min-h-0 overflow-hidden">
            <Outlet />
          </div>
        </div>
      </div>
      <ChatbotPlaceholder />
    </div>
  );
}

function AdminLogin({ onAuthed }: { onAuthed: () => void }) {
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setChecking(true);
    setError(null);
    setAdminKey(key);
    try {
      const res = await adminFetch("/api/lead/metrics");
      if (!res.ok) {
        throw new Error(res.status === 401 ? "Invalid admin key" : `Server error: ${res.status}`);
      }
      onAuthed();
    } catch (err) {
      // Do not retain a key that failed verification.
      clearAdminKey();
      setError(err instanceof Error ? err.message : "Unable to verify admin key");
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="flex w-screen h-screen items-center justify-center bg-black">
      <form onSubmit={handleSubmit} className="flex flex-col gap-3 bg-white p-8 rounded shadow-md w-80">
        <h1 className="text-xl font-semibold">Admin Login</h1>
        <input
          type="password"
          placeholder="Admin API key"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          className="border rounded px-3 py-2 text-black"
          autoFocus
        />
        {error && <p className="text-red-500 text-sm">{error}</p>}
        <button
          type="submit"
          disabled={checking || !key}
          className="bg-[#02AF6E] text-white rounded px-3 py-2 disabled:opacity-50"
        >
          {checking ? "Checking..." : "Continue"}
        </button>
      </form>
    </div>
  );
}

function DashboardNavbar() {
  return (
    <nav className="flex justify-between pl-5 m-0 pr-5 bg-[#02AF6E] w-full min-h-12 items-center border-b-2 border-[#00955D] shrink-0 gap-4">
      <div className="flex items-center shrink-0">
        <IDTechLogo />
        <h1 className="italic font-semibold text-2xl text-white p-0 pl-3">Admin Portal</h1>
      </div>
      <div className="flex justify-end gap-4 flex-wrap">
        {navLinks.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className={({ isActive }) =>
              `text-xl transition ${isActive ? "text-white font-semibold" : "text-green-100 hover:text-white"}`
            }
          >
            {link.label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}

function ChatbotPlaceholder() {
  return <></>;
}
