import { render, screen, fireEvent, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ReviewQueue from "./ReviewQueue";
import type { PendingDiscoveryWithProject } from "@/lib/types";

vi.mock("@/lib/agent-fetch", () => ({ agentFetch: vi.fn() }));

function makeDiscovery(
  overrides: Partial<PendingDiscoveryWithProject> & {
    project?: Partial<PendingDiscoveryWithProject["project"]>;
  } = {},
): PendingDiscoveryWithProject {
  const { project: projectOverrides, ...rest } = overrides;
  return {
    id: "d1",
    project_id: "p1",
    epc_contractor: "McCarthy Building",
    confidence: "confirmed",
    sources: [],
    reasoning: null,
    related_leads: [],
    review_status: "pending",
    agent_log: [],
    tokens_used: 0,
    created_at: "2026-04-01T00:00:00Z",
    updated_at: "2026-04-01T00:00:00Z",
    project: {
      id: "p1",
      project_name: "Sunstone Solar",
      developer: "Pine Gate",
      mw_capacity: 200,
      state: "TX",
      ...projectOverrides,
    },
    ...rest,
  };
}

const fixtures: PendingDiscoveryWithProject[] = [
  makeDiscovery({
    id: "a",
    epc_contractor: "McCarthy Building",
    confidence: "confirmed",
    created_at: "2026-04-01T00:00:00Z",
    project: {
      id: "pa",
      project_name: "Sunstone Solar",
      state: "TX",
      mw_capacity: 200,
      developer: "Pine Gate",
    },
  }),
  makeDiscovery({
    id: "b",
    epc_contractor: "Blattner Energy",
    confidence: "likely",
    created_at: "2026-04-05T00:00:00Z",
    project: {
      id: "pb",
      project_name: "White Bluff",
      state: "AR",
      mw_capacity: 450,
      developer: "Entergy",
    },
  }),
  makeDiscovery({
    id: "c",
    epc_contractor: "Swinerton Renewable",
    confidence: "possible",
    created_at: "2026-03-12T00:00:00Z",
    project: {
      id: "pc",
      project_name: "Silver Ridge",
      state: "CO",
      mw_capacity: 600,
      developer: "SDGE",
    },
  }),
];

describe("ReviewQueue filters", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders every discovery by default", () => {
    render(<ReviewQueue initialDiscoveries={fixtures} />);
    expect(screen.getByText("Sunstone Solar")).toBeInTheDocument();
    expect(screen.getByText("White Bluff")).toBeInTheDocument();
    expect(screen.getByText("Silver Ridge")).toBeInTheDocument();
  });

  it("filters by state dropdown", () => {
    render(<ReviewQueue initialDiscoveries={fixtures} />);
    fireEvent.change(screen.getByLabelText(/state/i), {
      target: { value: "TX" },
    });
    expect(screen.getByText("Sunstone Solar")).toBeInTheDocument();
    expect(screen.queryByText("White Bluff")).not.toBeInTheDocument();
    expect(screen.queryByText("Silver Ridge")).not.toBeInTheDocument();
  });

  it("filters by confidence dropdown", () => {
    render(<ReviewQueue initialDiscoveries={fixtures} />);
    fireEvent.change(screen.getByLabelText(/confidence/i), {
      target: { value: "likely" },
    });
    expect(screen.getByText("White Bluff")).toBeInTheDocument();
    expect(screen.queryByText("Sunstone Solar")).not.toBeInTheDocument();
  });

  it("filters by free-text search across project, developer, EPC", () => {
    render(<ReviewQueue initialDiscoveries={fixtures} />);
    fireEvent.change(screen.getByPlaceholderText(/search/i), {
      target: { value: "blattner" },
    });
    expect(screen.getByText("White Bluff")).toBeInTheDocument();
    expect(screen.queryByText("Sunstone Solar")).not.toBeInTheDocument();
    expect(screen.queryByText("Silver Ridge")).not.toBeInTheDocument();
  });

  it("state dropdown only lists states present in the data", () => {
    render(<ReviewQueue initialDiscoveries={fixtures} />);
    const stateSelect = screen.getByLabelText(/state/i) as HTMLSelectElement;
    const values = Array.from(stateSelect.options).map((o) => o.value);
    expect(values).toEqual(["", "AR", "CO", "TX"]);
  });
});

describe("ReviewQueue sorting", () => {
  const firstCellText = (row: HTMLElement) =>
    within(row).getAllByRole("cell")[0].textContent;
  const stateCellText = (row: HTMLElement) =>
    within(row).getAllByRole("cell")[3].textContent;
  const epcCellText = (row: HTMLElement) =>
    within(row).getAllByRole("cell")[4].textContent;

  function dataRows() {
    return screen
      .getAllByRole("row")
      .filter((r) => within(r).queryAllByRole("cell").length > 0);
  }

  it("defaults to newest created_at first", () => {
    render(<ReviewQueue initialDiscoveries={fixtures} />);
    const rows = dataRows();
    expect(firstCellText(rows[0])).toContain("White Bluff"); // 2026-04-05
    expect(firstCellText(rows[1])).toContain("Sunstone Solar"); // 2026-04-01
    expect(firstCellText(rows[2])).toContain("Silver Ridge"); // 2026-03-12
  });

  it("clicking the Created header toggles to oldest-first", () => {
    render(<ReviewQueue initialDiscoveries={fixtures} />);
    fireEvent.click(screen.getByRole("columnheader", { name: /created/i }));
    const rows = dataRows();
    expect(firstCellText(rows[0])).toContain("Silver Ridge"); // 2026-03-12
    expect(firstCellText(rows[2])).toContain("White Bluff"); // 2026-04-05
  });

  it("sorts by state alphabetically when State header clicked", () => {
    render(<ReviewQueue initialDiscoveries={fixtures} />);
    fireEvent.click(screen.getByRole("columnheader", { name: /state/i }));
    const rows = dataRows();
    expect(stateCellText(rows[0])).toBe("AR");
    expect(stateCellText(rows[1])).toBe("CO");
    expect(stateCellText(rows[2])).toBe("TX");
  });

  it("sorts confidence with confirmed on top", () => {
    render(<ReviewQueue initialDiscoveries={fixtures} />);
    fireEvent.click(screen.getByRole("columnheader", { name: /confidence/i }));
    const rows = dataRows();
    expect(epcCellText(rows[0])).toBe("McCarthy Building"); // confirmed
    expect(epcCellText(rows[1])).toBe("Blattner Energy"); // likely
    expect(epcCellText(rows[2])).toBe("Swinerton Renewable"); // possible
  });

  it("shows an arrow indicator on the active sort column", () => {
    render(<ReviewQueue initialDiscoveries={fixtures} />);
    const createdHeader = screen.getByRole("columnheader", { name: /created/i });
    expect(createdHeader.textContent).toMatch(/↓/);
    fireEvent.click(createdHeader);
    expect(createdHeader.textContent).toMatch(/↑/);
  });
});

describe("ReviewQueue empty states", () => {
  it("shows 'no pending discoveries' when initial list is empty", () => {
    render(<ReviewQueue initialDiscoveries={[]} />);
    expect(screen.getByText(/no pending discoveries/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/state/i)).not.toBeInTheDocument();
  });

  it("shows 'no discoveries match' when filters exclude all rows, and keeps filters visible", () => {
    render(<ReviewQueue initialDiscoveries={fixtures} />);
    fireEvent.change(screen.getByPlaceholderText(/search/i), {
      target: { value: "zzznomatches" },
    });
    expect(screen.getByText(/no discoveries match/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/state/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /clear filters/i }));
    expect(screen.getByText("Sunstone Solar")).toBeInTheDocument();
  });
});
