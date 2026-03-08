"use client";

import { Filters } from "@/lib/types";

interface FilterBarProps {
  filters: Filters;
  onChange: (filters: Filters) => void;
  states: string[];
}

export default function FilterBar({ filters, onChange, states }: FilterBarProps) {
  const update = (partial: Partial<Filters>) =>
    onChange({ ...filters, ...partial });

  return (
    <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4">
      {/* Source */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-slate-500">Source</label>
        <select
          className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900"
          value={filters.iso_region}
          onChange={(e) => update({ iso_region: e.target.value })}
        >
          <option value="">All Sources</option>
          <option value="MISO">MISO</option>
          <option value="ERCOT">ERCOT</option>
          <option value="CAISO">CAISO</option>
          <option value="GEM">GEM Tracker</option>
        </select>
      </div>

      {/* State */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-slate-500">State</label>
        <select
          className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900"
          value={filters.state}
          onChange={(e) => update({ state: e.target.value })}
        >
          <option value="">All</option>
          {states.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {/* Status */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-slate-500">Status</label>
        <select
          className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900"
          value={filters.status}
          onChange={(e) => update({ status: e.target.value })}
        >
          <option value="">All</option>
          <option value="Active">Active</option>
          <option value="Completed">Completed</option>
          <option value="Withdrawn">Withdrawn</option>
        </select>
      </div>

      {/* Fuel Type */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-slate-500">Fuel Type</label>
        <select
          className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900"
          value={filters.fuel_type}
          onChange={(e) => update({ fuel_type: e.target.value })}
        >
          <option value="">All</option>
          <option value="Solar">Solar</option>
          <option value="Solar+Storage">Solar+Storage</option>
        </select>
      </div>

      {/* Construction Status */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-slate-500">Construction</label>
        <select
          className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900"
          value={filters.construction_status}
          onChange={(e) => update({ construction_status: e.target.value })}
        >
          <option value="">All</option>
          <option value="pre_construction">Pre-Construction</option>
          <option value="under_construction">Under Construction</option>
          <option value="completed">Completed</option>
          <option value="cancelled">Cancelled</option>
          <option value="unknown">Unknown</option>
        </select>
      </div>

      {/* COD Year Range */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-slate-500">COD From</label>
        <select
          className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900"
          value={filters.cod_year_min || ""}
          onChange={(e) => update({ cod_year_min: Number(e.target.value) || 0 })}
        >
          <option value="">Any</option>
          {[2024, 2025, 2026, 2027, 2028, 2029, 2030].map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-slate-500">COD To</label>
        <select
          className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900"
          value={filters.cod_year_max || ""}
          onChange={(e) => update({ cod_year_max: Number(e.target.value) || 0 })}
        >
          <option value="">Any</option>
          {[2024, 2025, 2026, 2027, 2028, 2029, 2030].map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
      </div>

      {/* MW Range */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-slate-500">MW Min</label>
        <input
          type="number"
          className="h-9 w-24 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900"
          placeholder="20"
          value={filters.mw_min || ""}
          onChange={(e) => update({ mw_min: Number(e.target.value) || 0 })}
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-slate-500">MW Max</label>
        <input
          type="number"
          className="h-9 w-24 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900"
          placeholder="Any"
          value={filters.mw_max || ""}
          onChange={(e) => update({ mw_max: Number(e.target.value) || 0 })}
        />
      </div>

      {/* Search */}
      <div className="flex min-w-[200px] flex-1 flex-col gap-1">
        <label className="text-xs font-medium text-slate-500">Search</label>
        <input
          type="text"
          className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900"
          placeholder="Name, developer, EPC, county, state..."
          value={filters.search}
          onChange={(e) => update({ search: e.target.value })}
        />
      </div>
    </div>
  );
}
