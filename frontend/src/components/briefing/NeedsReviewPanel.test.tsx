// frontend/src/components/briefing/NeedsReviewPanel.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import NeedsReviewPanel, { PendingDiscovery } from "./NeedsReviewPanel";

vi.mock("@/lib/agent-fetch", () => ({
  agentFetch: vi.fn(),
}));

import { agentFetch } from "@/lib/agent-fetch";
const mockAgentFetch = vi.mocked(agentFetch);

const mockDiscoveries: PendingDiscovery[] = [
  {
    id: "d1",
    epc_contractor: "McCarthy Building",
    confidence: "confirmed",
    reasoning_summary: "Found on FERC filing",
    project_id: "p1",
    project_name: "Solar Ranch Alpha",
    mw_capacity: 200,
    iso_region: "ERCOT",
  },
  {
    id: "d2",
    epc_contractor: "Blattner Energy",
    confidence: "likely",
    reasoning_summary: "LinkedIn mention",
    project_id: "p2",
    project_name: "Sunbeam Beta",
    mw_capacity: 150,
    iso_region: "CAISO",
  },
];

describe("NeedsReviewPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders discovery cards with EPC name and confidence", () => {
    render(
      <NeedsReviewPanel discoveries={mockDiscoveries} totalPending={10} />
    );
    expect(screen.getByText("McCarthy Building")).toBeInTheDocument();
    expect(screen.getByText("Blattner Energy")).toBeInTheDocument();
    expect(screen.getByText("confirmed")).toBeInTheDocument();
    expect(screen.getByText("likely")).toBeInTheDocument();
  });

  it("renders project context line", () => {
    render(
      <NeedsReviewPanel discoveries={mockDiscoveries} totalPending={10} />
    );
    expect(
      screen.getByText("Solar Ranch Alpha · 200MW · ERCOT")
    ).toBeInTheDocument();
  });

  it("renders approve and reject buttons for each card", () => {
    render(
      <NeedsReviewPanel discoveries={mockDiscoveries} totalPending={10} />
    );
    expect(screen.getAllByText("✓")).toHaveLength(2);
    expect(screen.getAllByText("✕")).toHaveLength(2);
  });

  it("shows total pending count badge", () => {
    render(
      <NeedsReviewPanel discoveries={mockDiscoveries} totalPending={61} />
    );
    expect(screen.getByText("61")).toBeInTheDocument();
  });

  it("shows View all link to /review", () => {
    render(
      <NeedsReviewPanel discoveries={mockDiscoveries} totalPending={10} />
    );
    const viewAll = screen.getByText("View all →");
    expect(viewAll.closest("a")).toHaveAttribute("href", "/review");
  });

  it("shows empty state when no discoveries", () => {
    render(<NeedsReviewPanel discoveries={[]} totalPending={0} />);
    expect(
      screen.getByText("All caught up. No pending reviews.")
    ).toBeInTheDocument();
  });

  it("expands reasoning on card click", () => {
    render(
      <NeedsReviewPanel discoveries={mockDiscoveries} totalPending={10} />
    );
    expect(screen.queryByText("Found on FERC filing")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("McCarthy Building"));
    expect(screen.getByText("Found on FERC filing")).toBeInTheDocument();
  });

  it("removes card on successful approve", async () => {
    mockAgentFetch.mockResolvedValueOnce({ ok: true } as Response);
    const onCountChange = vi.fn();

    render(
      <NeedsReviewPanel
        discoveries={mockDiscoveries}
        totalPending={10}
        onCountChange={onCountChange}
      />
    );

    const approveButtons = screen.getAllByText("✓");
    fireEvent.click(approveButtons[0]);

    await waitFor(() => {
      expect(screen.queryByText("McCarthy Building")).not.toBeInTheDocument();
    });
    expect(onCountChange).toHaveBeenCalledWith(-1);
    expect(mockAgentFetch).toHaveBeenCalledWith(
      "/api/discover/d1/review",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ action: "accepted" }),
      })
    );
  });

  it("removes card on successful reject", async () => {
    mockAgentFetch.mockResolvedValueOnce({ ok: true } as Response);

    render(
      <NeedsReviewPanel discoveries={mockDiscoveries} totalPending={10} />
    );

    const rejectButtons = screen.getAllByText("✕");
    fireEvent.click(rejectButtons[0]);

    await waitFor(() => {
      expect(screen.queryByText("McCarthy Building")).not.toBeInTheDocument();
    });
    expect(mockAgentFetch).toHaveBeenCalledWith(
      "/api/discover/d1/review",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ action: "rejected" }),
      })
    );
  });

  it("shows error on failed action", async () => {
    mockAgentFetch.mockResolvedValueOnce({ ok: false } as Response);

    render(
      <NeedsReviewPanel discoveries={mockDiscoveries} totalPending={10} />
    );

    fireEvent.click(screen.getAllByText("✓")[0]);

    await waitFor(() => {
      expect(
        screen.getByText("Failed to approve. Try again.")
      ).toBeInTheDocument();
    });
    // Card should still be there
    expect(screen.getByText("McCarthy Building")).toBeInTheDocument();
  });
});
