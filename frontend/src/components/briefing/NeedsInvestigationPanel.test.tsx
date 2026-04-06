// frontend/src/components/briefing/NeedsInvestigationPanel.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import NeedsInvestigationPanel, {
  UnresearchedProject,
} from "./NeedsInvestigationPanel";

vi.mock("@/lib/agent-fetch", () => ({
  agentFetch: vi.fn(),
}));

import { agentFetch } from "@/lib/agent-fetch";
const mockAgentFetch = vi.mocked(agentFetch);

const mockProjects: UnresearchedProject[] = [
  {
    id: "p1",
    project_name: "Solar Ranch Alpha",
    iso_region: "ERCOT",
    state: "TX",
    lead_score: 90,
  },
  {
    id: "p2",
    project_name: "Sunbeam Beta",
    iso_region: "CAISO",
    state: "CA",
    lead_score: 75,
  },
];

describe("NeedsInvestigationPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders project cards with name and context", () => {
    render(
      <NeedsInvestigationPanel projects={mockProjects} totalUnresearched={20} />
    );
    expect(screen.getByText("Solar Ranch Alpha")).toBeInTheDocument();
    expect(screen.getByText("Sunbeam Beta")).toBeInTheDocument();
    expect(screen.getByText("ERCOT · TX · Score 90")).toBeInTheDocument();
  });

  it("renders Research button for each project", () => {
    render(
      <NeedsInvestigationPanel projects={mockProjects} totalUnresearched={20} />
    );
    expect(screen.getAllByText("Research")).toHaveLength(2);
  });

  it("renders View pipeline link", () => {
    render(
      <NeedsInvestigationPanel projects={mockProjects} totalUnresearched={20} />
    );
    const link = screen.getByText("View pipeline →");
    expect(link.closest("a")).toHaveAttribute("href", "/projects");
  });

  it("renders project links to detail pages", () => {
    render(
      <NeedsInvestigationPanel projects={mockProjects} totalUnresearched={20} />
    );
    const links = screen.getAllByRole("link");
    const hrefs = links.map((l) => l.getAttribute("href"));
    expect(hrefs).toContain("/projects/p1");
    expect(hrefs).toContain("/projects/p2");
  });

  it("shows empty state when no projects", () => {
    render(
      <NeedsInvestigationPanel projects={[]} totalUnresearched={0} />
    );
    expect(
      screen.getByText("All projects have been researched.")
    ).toBeInTheDocument();
  });

  it("calls plan then execute on Research click", async () => {
    mockAgentFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ plan: "test-plan" }),
      } as Response)
      .mockResolvedValueOnce({ ok: true } as Response);

    render(
      <NeedsInvestigationPanel projects={mockProjects} totalUnresearched={20} />
    );

    fireEvent.click(screen.getAllByText("Research")[0]);

    await waitFor(() => {
      expect(screen.getByText("Done")).toBeInTheDocument();
    });

    expect(mockAgentFetch).toHaveBeenCalledTimes(2);
    expect(mockAgentFetch).toHaveBeenNthCalledWith(
      1,
      "/api/discover/plan",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ project_id: "p1" }),
      })
    );
    expect(mockAgentFetch).toHaveBeenNthCalledWith(
      2,
      "/api/discover",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ project_id: "p1", plan: "test-plan" }),
      })
    );
  });

  it("shows error when plan step fails", async () => {
    mockAgentFetch.mockResolvedValueOnce({ ok: false } as Response);

    render(
      <NeedsInvestigationPanel projects={mockProjects} totalUnresearched={20} />
    );

    fireEvent.click(screen.getAllByText("Research")[0]);

    await waitFor(() => {
      expect(
        screen.getByText("Failed to generate research plan.")
      ).toBeInTheDocument();
    });
  });

  it("shows + N more footer when there are more projects", () => {
    render(
      <NeedsInvestigationPanel projects={mockProjects} totalUnresearched={50} />
    );
    expect(screen.getByText("Top by lead score · 48 more")).toBeInTheDocument();
  });
});
