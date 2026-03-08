"use client";

import dynamic from "next/dynamic";
import type { Project, EpcDiscovery } from "@/lib/types";

const ProjectMap = dynamic(() => import("./ProjectMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[calc(100vh-220px)] min-h-[500px] items-center justify-center rounded-lg border border-slate-200 bg-slate-50">
      <p className="text-slate-400">Loading map...</p>
    </div>
  ),
});

interface Props {
  projects: Project[];
  discoveries: EpcDiscovery[];
}

export default function ProjectMapLoader({ projects, discoveries }: Props) {
  return <ProjectMap projects={projects} discoveries={discoveries} />;
}
