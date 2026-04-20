import React from "react";
import Link from "next/link";
import { LayoutDashboard, Wrench, Eye, Settings } from "lucide-react";

const Sidebar: React.FC = () => {
  return (
    <aside
      className="relative w-46 h-full overflow-hidden border-r border-white/10 text-white bg-fixed bg-cover bg-center bg-no-repeat"
      style={{ backgroundImage: "url('/header-dashboard.jpg')" }}
    >
      {/* Dark overlay */}
      <div className="absolute inset-0 bg-black/30" />

      {/* Content */}
      <nav className="relative z-10 p-3">
        <ul className="space-y-2">
          <li>
            <Link
              href="/dashboard"
              className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-[#0a0e27] hover:brightness-110 transition-all shadow-sm"
              style={{ backgroundColor: "rgba(255,255,255,0.55)" }}
            >
              <LayoutDashboard className="h-3.5 w-3.5" />
              Overview
            </Link>
          </li>
          <li>
            <Link
              href="/dashboard/tools"
              className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-[#0a0e27] hover:brightness-110 transition-all shadow-sm"
              style={{ backgroundColor: "rgba(255,255,255,0.55)" }}
            >
              <Wrench className="h-3.5 w-3.5" />
              Manage Tools
            </Link>
          </li>
          <li>
            <Link
              href="/dashboard/visualizations"
              className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-[#0a0e27] hover:brightness-110 transition-all shadow-sm"
              style={{ backgroundColor: "rgba(255,255,255,0.55)" }}
            >
              <Eye className="h-3.5 w-3.5" />
              Visualization
            </Link>
          </li>
          <li>
            <Link
              href="/dashboard/settings"
              className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-[#0a0e27] hover:brightness-110 transition-all shadow-sm"
              style={{ backgroundColor: "rgba(255,255,255,0.55)" }}
            >
              <Settings className="h-3.5 w-3.5" />
              Platform Settings
            </Link>
          </li>
        </ul>
      </nav>
    </aside>
  );
};

export default Sidebar;
