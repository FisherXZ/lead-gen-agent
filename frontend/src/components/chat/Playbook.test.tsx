import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import Playbook from "./Playbook";

const mockStats = {
  awaiting_review: 61,
  new_projects_this_week: 3,
  epcs_need_contacts: 5,
  leads_ready_for_crm: 8,
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("Playbook", () => {
  it("renders the Solarina header", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => mockStats,
    } as Response);

    render(<Playbook onSelect={() => {}} />);
    expect(screen.getByText("Solarina")).toBeInTheDocument();
  });

  it("renders dynamic nudges when stats are non-zero", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => mockStats,
    } as Response);

    render(<Playbook onSelect={() => {}} />);

    await waitFor(() => {
      expect(screen.getByText("61")).toBeInTheDocument();
    });
    expect(screen.getByText("awaiting review")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("new projects this week")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
  });

  it("hides nudges with zero count", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        ...mockStats,
        epcs_need_contacts: 0,
        leads_ready_for_crm: 0,
      }),
    } as Response);

    render(<Playbook onSelect={() => {}} />);

    await waitFor(() => {
      expect(screen.getByText("61")).toBeInTheDocument();
    });
    expect(screen.queryByText("EPCs need contacts")).not.toBeInTheDocument();
    expect(screen.queryByText("leads ready for CRM")).not.toBeInTheDocument();
  });

  it("shows 'all caught up' when all stats are zero", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        awaiting_review: 0,
        new_projects_this_week: 0,
        epcs_need_contacts: 0,
        leads_ready_for_crm: 0,
      }),
    } as Response);

    render(<Playbook onSelect={() => {}} />);

    await waitFor(() => {
      expect(screen.getByText("You're all caught up")).toBeInTheDocument();
    });
    expect(screen.getByText(/Start batch research/)).toBeInTheDocument();
  });

  it("renders all 5 outcome cards", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => mockStats,
    } as Response);

    render(<Playbook onSelect={() => {}} />);

    expect(screen.getByText("Deep-dive a company")).toBeInTheDocument();
    expect(screen.getByText("Batch research projects")).toBeInTheDocument();
    expect(screen.getByText("Triage the review queue")).toBeInTheDocument();
    expect(screen.getByText("Pipeline intelligence")).toBeInTheDocument();
    expect(screen.getByText("Scout a new region")).toBeInTheDocument();
  });

  it("calls onSelect with prompt when nudge is clicked", async () => {
    const onSelect = vi.fn();
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => mockStats,
    } as Response);

    render(<Playbook onSelect={onSelect} />);

    await waitFor(() => {
      expect(screen.getByText("61")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("61").closest("button")!);
    expect(onSelect).toHaveBeenCalledWith(
      "Let's triage the 61 pending reviews"
    );
  });

  it("calls onSelect with prompt when outcome card is clicked", () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => mockStats,
    } as Response);

    const onSelect = vi.fn();
    render(<Playbook onSelect={onSelect} />);

    fireEvent.click(screen.getByText("Deep-dive a company"));
    expect(onSelect).toHaveBeenCalledWith("I want to deep-dive a company");
  });

  it("calls onSelect when 'all caught up' batch research link is clicked", async () => {
    const onSelect = vi.fn();
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        awaiting_review: 0,
        new_projects_this_week: 0,
        epcs_need_contacts: 0,
        leads_ready_for_crm: 0,
      }),
    } as Response);

    render(<Playbook onSelect={onSelect} />);

    await waitFor(() => {
      expect(screen.getByText(/Start batch research/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText(/Start batch research/));
    expect(onSelect).toHaveBeenCalledWith(
      "Batch research unresearched projects"
    );
  });

  it("handles fetch failure gracefully", async () => {
    vi.spyOn(global, "fetch").mockRejectedValueOnce(new Error("Network error"));

    render(<Playbook onSelect={() => {}} />);

    // Should still render outcome cards (static)
    expect(screen.getByText("Deep-dive a company")).toBeInTheDocument();
    // Stats area stays in loading state (null)
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });
});
