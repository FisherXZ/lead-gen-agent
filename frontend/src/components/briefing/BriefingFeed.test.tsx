import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { BriefingFeed } from './BriefingFeed';
import { AnyBriefingEvent, BriefingStats, NewLeadEvent, ReviewEvent, NewProjectEvent } from '@/lib/briefing-types';

// Mock child components to isolate BriefingFeed logic
vi.mock('./cards/NewLeadCard', () => ({
  NewLeadCard: ({ event }: any) => <div data-testid={`new-lead-${event.id}`}>NewLead: {event.epc_contractor}</div>,
}));

vi.mock('./cards/ReviewCard', () => ({
  ReviewCard: ({ event }: any) => <div data-testid={`review-${event.id}`}>Review: {event.epc_contractor}</div>,
}));

vi.mock('./cards/AlertCard', () => ({
  AlertCard: ({ event }: any) => <div data-testid={`alert-${event.id}`}>Alert: {event.project_name}</div>,
}));

vi.mock('./cards/DigestCard', () => ({
  DigestCard: ({ event }: any) => <div data-testid={`digest-${event.id}`}>Digest</div>,
}));

vi.mock('./ProjectPanel', () => ({
  ProjectPanel: ({ projectId }: any) => projectId ? <div data-testid="project-panel">Panel: {projectId}</div> : null,
}));

const now = new Date().toISOString();
const lastWeek = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(); // 3 days ago

const mockEvents: AnyBriefingEvent[] = [
  {
    id: 'lead-1', type: 'new_lead', priority: 1, created_at: now, dismissed: false,
    project_id: 'p1', project_name: 'Solar A', developer: null, mw_capacity: 100,
    iso_region: 'ERCOT', state: 'TX', lead_score: 90, epc_contractor: 'McCarthy',
    confidence: 'confirmed', discovery_id: 'd1', entity_id: null, contacts: [],
    outreach_context: 'test',
  } as NewLeadEvent,
  {
    id: 'review-1', type: 'review', priority: 2, created_at: now, dismissed: false,
    project_id: 'p2', project_name: 'Solar B', mw_capacity: 200,
    iso_region: 'CAISO', epc_contractor: 'Blattner', confidence: 'likely',
    discovery_id: 'd2', reasoning_summary: 'test', source_url: null,
  } as ReviewEvent,
  {
    id: 'project-1', type: 'new_project', priority: 3, created_at: now, dismissed: false,
    project_id: 'p3', project_name: 'Solar C', developer: 'Dev', mw_capacity: 300,
    iso_region: 'ERCOT', state: 'TX', status: 'Active',
  } as NewProjectEvent,
];

const mockStats: BriefingStats = {
  new_leads_this_week: 5,
  awaiting_review: 2,
  total_epcs_discovered: 30,
};

describe('BriefingFeed', () => {
  it('renders the StatBar with stats', () => {
    render(<BriefingFeed events={mockEvents} stats={mockStats} />);
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText(/new leads this week/i)).toBeInTheDocument();
  });

  it('renders QuickFilters', () => {
    render(<BriefingFeed events={mockEvents} stats={mockStats} />);
    expect(screen.getByText('All Regions')).toBeInTheDocument();
    expect(screen.getByText('This Week')).toBeInTheDocument();
  });

  it('renders all event cards', () => {
    render(<BriefingFeed events={mockEvents} stats={mockStats} />);
    expect(screen.getByTestId('new-lead-lead-1')).toBeInTheDocument();
    expect(screen.getByTestId('review-review-1')).toBeInTheDocument();
    expect(screen.getByTestId('alert-project-1')).toBeInTheDocument();
  });

  it('sorts cards by priority (new_lead before review before project)', () => {
    render(<BriefingFeed events={mockEvents} stats={mockStats} />);
    const cards = screen.getAllByTestId(/^(new-lead|review|alert)-/);
    expect(cards[0]).toHaveAttribute('data-testid', 'new-lead-lead-1');
    expect(cards[1]).toHaveAttribute('data-testid', 'review-review-1');
    expect(cards[2]).toHaveAttribute('data-testid', 'alert-project-1');
  });

  it('filters by region when chip clicked', () => {
    render(<BriefingFeed events={mockEvents} stats={mockStats} />);
    fireEvent.click(screen.getByText('CAISO'));
    // Only CAISO event should show
    expect(screen.queryByTestId('new-lead-lead-1')).not.toBeInTheDocument(); // ERCOT
    expect(screen.getByTestId('review-review-1')).toBeInTheDocument(); // CAISO
    expect(screen.queryByTestId('alert-project-1')).not.toBeInTheDocument(); // ERCOT
  });

  it('shows empty state when no events match filter', () => {
    render(<BriefingFeed events={mockEvents} stats={mockStats} />);
    fireEvent.click(screen.getByText('MISO'));
    expect(screen.getByText(/all caught up/i)).toBeInTheDocument();
  });

  it('shows all events when All Regions selected', () => {
    render(<BriefingFeed events={mockEvents} stats={mockStats} />);
    fireEvent.click(screen.getByText('CAISO'));
    fireEvent.click(screen.getByText('All Regions'));
    expect(screen.getByTestId('new-lead-lead-1')).toBeInTheDocument();
    expect(screen.getByTestId('review-review-1')).toBeInTheDocument();
    expect(screen.getByTestId('alert-project-1')).toBeInTheDocument();
  });
});
