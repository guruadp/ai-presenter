import { Database, FolderOpen, Mic, Settings } from "lucide-react";
import { NavLink } from "react-router-dom";

const nav = [
  { to: "/projects", icon: FolderOpen, label: "Projects" },
  { to: "/kbs", icon: Database, label: "Knowledge Bases" },
];

export default function Sidebar() {
  return (
    <aside className="w-60 shrink-0 h-screen bg-white border-r border-gray-200 flex flex-col">
      {/* Logo */}
      <div className="px-4 py-5 border-b border-gray-100">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center shrink-0">
            <Mic size={15} className="text-white" />
          </div>
          <div>
            <div className="text-sm font-semibold text-gray-900 leading-none">
              Ednex
            </div>
            <div className="text-xs text-gray-400 mt-0.5">AI Presenter</div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 flex flex-col gap-0.5">
        {nav.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? "bg-indigo-50 text-indigo-700 font-medium"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon
                  size={16}
                  className={isActive ? "text-indigo-600" : "text-gray-400"}
                />
                {label}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-3 py-4 border-t border-gray-100">
        <button className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-gray-500 hover:bg-gray-100 hover:text-gray-700 w-full transition-colors">
          <Settings size={16} className="text-gray-400" />
          Settings
        </button>
      </div>
    </aside>
  );
}
