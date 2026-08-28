import { NavLink, Outlet } from "react-router-dom";
import "./admin.css";
import IDTechLogo from "./components/IDTechLogo";

const navLinks = [
  { to: "/admin", label: "Dashboard", end: true },
  { to: "/admin/leads", label: "Leads" },
  { to: "/admin/hardware", label: "Hardware" },
  { to: "/admin/software", label: "Software" },
  { to: "/admin/categories", label: "Categories" },
  { to: "/admin/use-cases", label: "Use Cases" },
];

export default function AdminLayout() {
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
