"use client";

import { useMemo, useState } from "react";
import { Project, ScrapeRun, Filters } from "@/lib/types";
import StatsCards from "./StatsCards";
import FilterBar from "./FilterBar";
import ProjectsTable, { SortField } from "./ProjectsTable";

const PAGE_SIZE = 25;

const DEFAULT_FILTERS: Filters = {
  iso_region: "",
  state: "",
  status: "",
  fuel_type: "",
  mw_min: 0,
  mw_max: 0,
  cod_year_min: 0,
  cod_year_max: 0,
  construction_status: "",
  search: "",
};

interface DashboardProps {
  initialProjects: Project[];
  lastRuns: ScrapeRun[];
}

export default function Dashboard({ initialProjects, lastRuns }: DashboardProps) {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [sortField, setSortField] = useState<SortField>("lead_score");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(0);

  // Unique states for filter dropdown
  const states = useMemo(() => {
    const set = new Set<string>();
    for (const p of initialProjects) {
      if (p.state) set.add(p.state);
    }
    return Array.from(set).sort();
  }, [initialProjects]);

  // Filter
  const filtered = useMemo(() => {
    const searchLower = filters.search.toLowerCase();
    return initialProjects.filter((p) => {
      if (filters.iso_region && p.iso_region !== filters.iso_region) return false;
      if (filters.state && (p.state || "").toLowerCase() !== filters.state.toLowerCase()) return false;
      if (filters.status && !(p.status || "").toLowerCase().includes(filters.status.toLowerCase())) return false;
      if (filters.fuel_type && !(p.fuel_type || "").toLowerCase().includes(filters.fuel_type.toLowerCase())) return false;
      if (filters.construction_status && (p.construction_status || "unknown") !== filters.construction_status) return false;
      if (filters.mw_min && (p.mw_capacity || 0) < filters.mw_min) return false;
      if (filters.mw_max && (p.mw_capacity || 0) > filters.mw_max) return false;
      if (filters.cod_year_min || filters.cod_year_max) {
        const codYear = p.expected_cod ? new Date(p.expected_cod).getFullYear() : null;
        if (!codYear) return false;
        if (filters.cod_year_min && codYear < filters.cod_year_min) return false;
        if (filters.cod_year_max && codYear > filters.cod_year_max) return false;
      }
      if (
        searchLower &&
        !(p.project_name || "").toLowerCase().includes(searchLower) &&
        !(p.developer || "").toLowerCase().includes(searchLower) &&
        !(p.epc_company || "").toLowerCase().includes(searchLower) &&
        !(p.county || "").toLowerCase().includes(searchLower) &&
        !(p.state || "").toLowerCase().includes(searchLower)
      )
        return false;
      return true;
    });
  }, [initialProjects, filters]);

  // Sort
  const sorted = useMemo(() => {
    const arr = [...filtered];
    arr.sort((a, b) => {
      const aVal = a[sortField];
      const bVal = b[sortField];
      if (aVal == null && bVal == null) return 0;
      if (aVal == null) return 1;
      if (bVal == null) return -1;
      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortDir === "asc" ? aVal - bVal : bVal - aVal;
      }
      const cmp = String(aVal).localeCompare(String(bVal));
      return sortDir === "asc" ? cmp : -cmp;
    });
    return arr;
  }, [filtered, sortField, sortDir]);

  function handleSort(field: SortField) {
    if (field === sortField) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir(field === "lead_score" || field === "mw_capacity" ? "desc" : "asc");
    }
    setPage(0);
  }

  function handleFilterChange(newFilters: Filters) {
    setFilters(newFilters);
    setPage(0);
  }

  return (
    <div className="flex flex-col gap-6">
      <StatsCards projects={filtered} lastRuns={lastRuns} />
      <FilterBar filters={filters} onChange={handleFilterChange} states={states} />
      <ProjectsTable
        projects={sorted}
        sortField={sortField}
        sortDir={sortDir}
        onSort={handleSort}
        page={page}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
      />
    </div>
  );
}
