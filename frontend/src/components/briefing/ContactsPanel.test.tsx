// frontend/src/components/briefing/ContactsPanel.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ContactsPanel, {
  NeedContactsItem,
  CrmReadyItem,
} from "./ContactsPanel";

vi.mock("@/lib/agent-fetch", () => ({
  agentFetch: vi.fn(),
}));

import { agentFetch } from "@/lib/agent-fetch";
const mockAgentFetch = vi.mocked(agentFetch);

const mockNeedContacts: NeedContactsItem[] = [
  {
    discovery_id: "d1",
    entity_id: "e1",
    epc_contractor: "McCarthy Building",
    project_name: "Solar Alpha",
    project_id: "p1",
  },
  {
    discovery_id: "d2",
    entity_id: "e2",
    epc_contractor: "Blattner Energy",
    project_name: "Solar Beta",
    project_id: "p2",
  },
];

const mockCrmReady: CrmReadyItem[] = [
  {
    discovery_id: "d3",
    project_id: "p3",
    epc_contractor: "Mortenson",
    project_name: "Solar Gamma",
    contact_count: 3,
  },
];

describe("ContactsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders CRM-ready items before need-contacts items", () => {
    render(
      <ContactsPanel
        needContacts={mockNeedContacts}
        crmReady={mockCrmReady}
      />
    );
    const names = screen.getAllByText(/McCarthy|Blattner|Mortenson/);
    expect(names[0]).toHaveTextContent("Mortenson");
    expect(names[1]).toHaveTextContent("McCarthy");
    expect(names[2]).toHaveTextContent("Blattner");
  });

  it("shows contact count badge for CRM-ready items", () => {
    render(
      <ContactsPanel
        needContacts={mockNeedContacts}
        crmReady={mockCrmReady}
      />
    );
    expect(screen.getByText("3 contacts")).toBeInTheDocument();
  });

  it("shows 0 contacts badge for need-contacts items", () => {
    render(
      <ContactsPanel
        needContacts={mockNeedContacts}
        crmReady={mockCrmReady}
      />
    );
    expect(screen.getAllByText("0 contacts")).toHaveLength(2);
  });

  it("renders Push to HS button for CRM-ready items", () => {
    render(
      <ContactsPanel
        needContacts={mockNeedContacts}
        crmReady={mockCrmReady}
      />
    );
    expect(screen.getByText("Push to HS")).toBeInTheDocument();
  });

  it("renders Find button for need-contacts items", () => {
    render(
      <ContactsPanel
        needContacts={mockNeedContacts}
        crmReady={mockCrmReady}
      />
    );
    expect(screen.getAllByText("Find")).toHaveLength(2);
  });

  it("shows total count badge", () => {
    render(
      <ContactsPanel
        needContacts={mockNeedContacts}
        crmReady={mockCrmReady}
      />
    );
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("shows Synced after successful HubSpot push", async () => {
    mockAgentFetch.mockResolvedValueOnce({ ok: true } as Response);

    render(
      <ContactsPanel
        needContacts={[]}
        crmReady={mockCrmReady}
      />
    );

    fireEvent.click(screen.getByText("Push to HS"));

    await waitFor(() => {
      expect(screen.getByText("Synced")).toBeInTheDocument();
    });

    expect(mockAgentFetch).toHaveBeenCalledWith(
      "/api/hubspot/push",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ project_id: "p3" }),
      })
    );
  });

  it("shows Found after successful contact discovery", async () => {
    mockAgentFetch.mockResolvedValueOnce({ ok: true } as Response);

    render(
      <ContactsPanel
        needContacts={mockNeedContacts}
        crmReady={[]}
      />
    );

    fireEvent.click(screen.getAllByText("Find")[0]);

    await waitFor(() => {
      expect(screen.getByText("Found")).toBeInTheDocument();
    });

    expect(mockAgentFetch).toHaveBeenCalledWith(
      "/api/contacts/discover",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ entity_id: "e1" }),
      })
    );
  });

  it("shows error on failed push", async () => {
    mockAgentFetch.mockResolvedValueOnce({ ok: false } as Response);

    render(
      <ContactsPanel
        needContacts={[]}
        crmReady={mockCrmReady}
      />
    );

    fireEvent.click(screen.getByText("Push to HS"));

    await waitFor(() => {
      expect(screen.getByText("HubSpot push failed.")).toBeInTheDocument();
    });
  });

  it("shows empty state when no items", () => {
    render(<ContactsPanel needContacts={[]} crmReady={[]} />);
    expect(
      screen.getByText("No contacts needed right now.")
    ).toBeInTheDocument();
  });

  it("renders Actions link", () => {
    render(
      <ContactsPanel
        needContacts={mockNeedContacts}
        crmReady={mockCrmReady}
      />
    );
    const link = screen.getByText("Actions →");
    expect(link.closest("a")).toHaveAttribute("href", "/actions");
  });
});
