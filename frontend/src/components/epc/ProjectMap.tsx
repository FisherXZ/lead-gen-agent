"use client";

import { useMemo } from "react";
import Link from "next/link";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { Project, EpcDiscovery } from "@/lib/types";

interface ProjectMapProps {
  projects: Project[];
  discoveries: EpcDiscovery[];
}

// Build a lookup: project_id → latest discovery
function buildDiscoveryMap(discoveries: EpcDiscovery[]) {
  const map = new Map<string, EpcDiscovery>();
  for (const d of discoveries) {
    if (!map.has(d.project_id)) {
      map.set(d.project_id, d);
    }
  }
  return map;
}

function getMarkerColor(project: Project, discovery: EpcDiscovery | undefined): string {
  if (discovery && discovery.epc_contractor !== "Unknown") {
    // EPC found — color by confidence
    switch (discovery.confidence) {
      case "confirmed": return "#10b981"; // emerald-500
      case "likely":    return "#34d399"; // emerald-400
      case "possible":  return "#fbbf24"; // amber-400
      default:          return "#94a3b8"; // slate-400
    }
  }
  if (project.epc_company) {
    return "#10b981"; // emerald-500
  }
  return "#64748b"; // slate-500 — no EPC yet
}

function getMarkerRadius(mw: number | null): number {
  if (!mw) return 4;
  if (mw >= 500) return 12;
  if (mw >= 200) return 9;
  if (mw >= 100) return 7;
  if (mw >= 50)  return 5;
  return 4;
}

export default function ProjectMap({ projects, discoveries }: ProjectMapProps) {
  const discoveryMap = useMemo(() => buildDiscoveryMap(discoveries), [discoveries]);

  const mappable = useMemo(
    () => projects.filter((p) => p.latitude != null && p.longitude != null),
    [projects]
  );

  const stats = useMemo(() => {
    const withEpc = mappable.filter(
      (p) => p.epc_company || discoveryMap.has(p.id)
    ).length;
    return { total: mappable.length, withEpc, withoutEpc: mappable.length - withEpc };
  }, [mappable, discoveryMap]);

  // US center
  const center: [number, number] = [39.0, -98.0];

  return (
    <div className="flex flex-col gap-4">
      {/* Legend + stats */}
      <div className="flex flex-wrap items-center gap-6 text-sm text-slate-600">
        <span>{stats.total} projects mapped</span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded-full bg-emerald-500" />
          EPC found ({stats.withEpc})
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded-full bg-slate-500" />
          Needs research ({stats.withoutEpc})
        </span>
        <span className="text-slate-400">Circle size = MW capacity</span>
      </div>

      {/* Map */}
      <div className="h-[calc(100vh-220px)] min-h-[500px] overflow-hidden rounded-lg border border-slate-200">
        <MapContainer
          center={center}
          zoom={5}
          className="h-full w-full"
          scrollWheelZoom={true}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {mappable.map((project) => {
            const discovery = discoveryMap.get(project.id);
            const color = getMarkerColor(project, discovery);
            const radius = getMarkerRadius(project.mw_capacity);
            const epc = discovery?.epc_contractor ?? project.epc_company;

            return (
              <CircleMarker
                key={project.id}
                center={[project.latitude!, project.longitude!]}
                radius={radius}
                pathOptions={{
                  color: color,
                  fillColor: color,
                  fillOpacity: 0.7,
                  weight: 1,
                }}
              >
                <Popup>
                  <div className="min-w-[200px] text-sm">
                    <p className="font-semibold text-slate-900">
                      {project.project_name || project.queue_id}
                    </p>
                    {project.developer && (
                      <p className="text-slate-600">Developer: {project.developer}</p>
                    )}
                    {epc && epc !== "Unknown" && (
                      <p className="text-emerald-700 font-medium">EPC: {epc}</p>
                    )}
                    {discovery && (
                      <p className="text-slate-500">
                        Confidence: {discovery.confidence}
                      </p>
                    )}
                    <p className="text-slate-500">
                      {project.mw_capacity ? `${project.mw_capacity} MW` : ""}
                      {project.state ? ` · ${project.state}` : ""}
                      {project.county ? `, ${project.county}` : ""}
                    </p>
                    <p className="text-slate-400">
                      {project.iso_region} · Score: {project.lead_score}
                    </p>
                    <Link
                      href={`/projects/${project.id}`}
                      className="mt-1 inline-block text-blue-600 hover:underline"
                    >
                      View details
                    </Link>
                  </div>
                </Popup>
              </CircleMarker>
            );
          })}
        </MapContainer>
      </div>
    </div>
  );
}
