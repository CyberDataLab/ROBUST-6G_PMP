"use client";

import React from "react";
import { signOut } from "next-auth/react";
import { LogOut } from "lucide-react";

const Header: React.FC = () => {
  return (
    <header
      className="relative overflow-visible border-b border-white/10 text-white py-4 px-6 bg-fixed bg-cover bg-center bg-no-repeat min-h-[92px]"
      style={{ backgroundImage: "url('/header-dashboard.jpg')" }}
    >
      {/* Dark overlay */}
      <div className="absolute inset-0 bg-black/40" />

      {/* Content */}
      <div className="relative z-10 flex w-full items-center">
        <img
          src="/robust-6g.jpg"
          alt="ROBUST-6G"
          className="h-14 object-contain"
        />
        <button
          onClick={() => signOut({ callbackUrl: "/login", redirect: true })}
          className="ml-auto flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-[#0a0e27] hover:brightness-110 transition-all shadow-sm"
          style={{ backgroundColor: "rgba(255,255,255,0.55)" }}
        >
          <LogOut className="h-3.5 w-3.5" />
          Sign Out
        </button>
      </div>
    </header>
  );
};

export default Header;
