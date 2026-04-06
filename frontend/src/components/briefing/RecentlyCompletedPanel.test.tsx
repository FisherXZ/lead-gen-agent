// frontend/src/components/briefing/RecentlyCompletedPanel.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import RecentlyCompletedPanel, { CompletedItem } from "./RecentlyCompletedPanel";

const now = new Date().toISOString();
const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();

const mockItems: CompletedItem[] = [
  {
    discovery_id: "d1",
    project_id: "p1",
    epc_contractor: "McCarthy Building",
    project_name: "Solar Alpha",
    mw_capacity: 200,
    contact_count: 3,
    has_hubspot_sync: true,
    completed_at: now,
  },
  {
    discovery_id: "d2",
    project_id: "p2",
    epc_contractor: "Blattner Energy",
    project_name: "Solar Beta",
    mw_capacity: 150,
    contact_count: 0,
    has_hubspot_sync: false,
    completed_at: twoHoursAgo,
  },
];

describe("RecentlyCompletedPanel", () => {
  it("renders EPC names", () => {
    render(<RecentlyCompletedPanel items={mockItems} />);
    expect(screen.getByText("McCarthy Building")).toBeInTheDocument();
    expect(screen.getByText("Blattner Energy")).toBeInTheDocument();
  });

  it("shows In HubSpot badge for synced items", () => {
    render(<RecentlyCompletedPanel items={mockItems} />);
    expect(screen.getByText("In HubSpot")).toBeInTheDocument();
  });

  it("shows Accepted badge for non-synced items", () => {
    render(<RecentlyCompletedPanel items={mockItems} />);
    expect(screen.getByText("Accepted")).toBeInTheDocument();
  });

  it("shows count badge in header", () => {
    render(<RecentlyCompletedPanel items={mockItems} />);
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("renders links to project detail pages", () => {
    render(<RecentlyCompletedPanel items={mockItems} />);
    const links = screen.getAllByRole("link");
    expect(links[0]).toHaveAttribute("href", "/projects/p1");
    expect(links[1]).toHaveAttribute("href", "/projects/p2");
  });

  it("shows project context with MW and contacts", () => {
    render(<RecentlyCompletedPanel items={mockItems} />);
    expect(
      screen.getByText(/Solar Alpha · 200MW · 3 contacts/)
    ).toBeInTheDocument();
  });

  it("shows empty state when no items", () => {
    render(<RecentlyCompletedPanel items={[]} />);
    expect(
      screen.getByText("No completed actions yet.")
    ).toBeInTheDocument();
  });

  it("renders green dots for each item", () => {
    const { container } = render(
      <RecentlyCompletedPanel items={mockItems} />
    );
    const dots = container.querySelectorAll(".bg-status-green.rounded-full.h-1\\.5");
    expect(dots.length).toBe(2);
  });
});
