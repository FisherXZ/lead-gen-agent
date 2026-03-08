"use client";

import { useSidebar } from "./SidebarContext";

export default function MainContent({ children }: { children: React.ReactNode }) {
  const { collapsed } = useSidebar();

  return (
    <div
      className={`min-h-screen pt-12 transition-all duration-200 lg:pt-0 ${
        collapsed ? "lg:ml-16" : "lg:ml-56"
      }`}
    >
      {children}
    </div>
  );
}
