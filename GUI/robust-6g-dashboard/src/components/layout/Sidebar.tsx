"use client";

import React from "react";
import { usePathname, useRouter } from "next/navigation";
import { LayoutDashboard, Wrench, Eye, Settings } from "lucide-react";

const Sidebar: React.FC = () => {
  const router = useRouter();
  const pathname = usePathname();
  const noAction = () => undefined;

  const scrollToDashboardSection = (sectionId: string) => {
    if (pathname !== "/dashboard") {
      router.push(`/dashboard#${sectionId}`);
      return;
    }

    const section = document.getElementById(sectionId);
    section?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

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
            <button
              type="button"
              onClick={() => scrollToDashboardSection("dashboard-top")}
              className="w-full flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-[#0a0e27] hover:brightness-110 transition-all shadow-sm"
              style={{ backgroundColor: "rgba(255,255,255,0.55)" }}
            >
              <LayoutDashboard className="h-3.5 w-3.5" />
              Overview
            </button>
          </li>
          <li>
            <button
              type="button"
              onClick={() =>
                scrollToDashboardSection("monitoring-tool-configuration")
              }
              className="w-full flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-[#0a0e27] hover:brightness-110 transition-all shadow-sm"
              style={{ backgroundColor: "rgba(255,255,255,0.55)" }}
            >
              <Wrench className="h-3.5 w-3.5" />
              Manage Tools
            </button>
          </li>
          <li>
            <button
              type="button"
              onClick={noAction}
              className="w-full flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-[#0a0e27] hover:brightness-110 transition-all shadow-sm"
              style={{ backgroundColor: "rgba(255,255,255,0.55)" }}
            >
              <Eye className="h-3.5 w-3.5" />
              Visualization
            </button>
          </li>
          <li>
            <button
              type="button"
              onClick={noAction}
              className="w-full flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-[#0a0e27] hover:brightness-110 transition-all shadow-sm"
              style={{ backgroundColor: "rgba(255,255,255,0.55)" }}
            >
              <Settings className="h-3.5 w-3.5" />
              Platform Settings
            </button>
          </li>
        </ul>
      </nav>
    </aside>
  );
};

export default Sidebar;
