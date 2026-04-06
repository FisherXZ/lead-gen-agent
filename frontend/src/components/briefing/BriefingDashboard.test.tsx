// frontend/src/components/briefing/BriefingDashboard.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import BriefingDashboard, {
  BriefingDashboardProps,
} from "./BriefingDashboard";

// Mock all child panels to isolate the shell
vi.mock("./PipelineFunnel", () => ({
  default: (props: any) => (
    <div data-testid="pipeline-funnel">
      Funnel: {props.totalProjects}/{props.pendingReview}
    </div>
  ),
}));

vi.mock("./QuickNav", () => ({
  default: () => <div data-testid="quick-nav">QuickNav</div>,
}));

vi.mock("./NeedsReviewPanel", () => ({
  default: (props: any) => (
    <div data-testid="needs-review">
      Review: {props.discoveries.length} items
    </div>
  ),
}));

vi.mock("./NeedsInvestigationPanel", () => ({
  default: (props: any) => (
    <div data-testid="needs-investigation">
      Investigation: {props.projects.length} items
    </div>
  ),
}));

vi.mock("./ContactsPanel", () => ({
  default: (props: any) => (
    <div data-testid="contacts-panel">
      Contacts: {props.needContacts.length + props.crmReady.length} items
    </div>
  ),
}));

vi.mock("./RecentlyCompletedPanel", () => ({
  default: (props: any) => (
    <div data-testid="recently-completed">
      Completed: {props.items.length} items
    </div>
  ),
}));

const mockProps: BriefingDashboardProps = {
  funnel: {
    totalProjects: 423,
    researched: 64,
    pendingReview: 61,
    accepted: 3,
    inCrm: 0,
  },
  pendingDiscoveries: [
    {
      id: "d1",
      epc_contractor: "McCarthy",
      confidence: "confirmed",
      reasoning_summary: "test",
      project_id: "p1",
      project_name: "Solar A",
      mw_capacity: 200,
      iso_region: "ERCOT",
    },
  ],
  totalPending: 61,
  unresearchedProjects: [
    {
      id: "p2",
      project_name: "Solar B",
      iso_region: "CAISO",
      state: "CA",
      lead_score: 80,
    },
  ],
  totalUnresearched: 350,
  needContacts: [
    {
      discovery_id: "d2",
      entity_id: "e1",
      epc_contractor: "Blattner",
      project_name: "Solar C",
      project_id: "p3",
    },
  ],
  crmReady: [],
  recentlyCompleted: [
    {
      discovery_id: "d3",
      project_id: "p4",
      epc_contractor: "Mortenson",
      project_name: "Solar D",
      mw_capacity: 300,
      contact_count: 2,
      has_hubspot_sync: false,
      completed_at: new Date().toISOString(),
    },
  ],
};

describe("BriefingDashboard", () => {
  it("renders all 6 sub-components", () => {
    render(<BriefingDashboard {...mockProps} />);
    expect(screen.getByTestId("pipeline-funnel")).toBeInTheDocument();
    expect(screen.getByTestId("quick-nav")).toBeInTheDocument();
    expect(screen.getByTestId("needs-review")).toBeInTheDocument();
    expect(screen.getByTestId("needs-investigation")).toBeInTheDocument();
    expect(screen.getByTestId("contacts-panel")).toBeInTheDocument();
    expect(screen.getByTestId("recently-completed")).toBeInTheDocument();
  });

  it("passes funnel counts to PipelineFunnel", () => {
    render(<BriefingDashboard {...mockProps} />);
    expect(screen.getByTestId("pipeline-funnel")).toHaveTextContent(
      "Funnel: 423/61"
    );
  });

  it("passes correct item counts to panels", () => {
    render(<BriefingDashboard {...mockProps} />);
    expect(screen.getByTestId("needs-review")).toHaveTextContent("1 items");
    expect(screen.getByTestId("needs-investigation")).toHaveTextContent(
      "1 items"
    );
    expect(screen.getByTestId("contacts-panel")).toHaveTextContent("1 items");
    expect(screen.getByTestId("recently-completed")).toHaveTextContent(
      "1 items"
    );
  });
});
