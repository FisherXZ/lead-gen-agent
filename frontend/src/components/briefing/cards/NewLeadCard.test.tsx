import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { NewLeadCard } from './NewLeadCard';
import { NewLeadEvent } from '@/lib/briefing-types';

// Mock agentFetch to avoid real API calls
vi.mock('@/lib/agent-fetch', () => ({
  agentFetch: vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) })),
}));

// Mock sonner toast
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const mockEvent: NewLeadEvent = {
  id: 'lead-1',
  type: 'new_lead',
  priority: 1,
  created_at: '2026-04-05T10:00:00Z',
  dismissed: false,
  project_id: 'proj-1',
  project_name: 'Sunflower Solar',
  developer: 'NextEra Energy',
  mw_capacity: 350,
  iso_region: 'ERCOT',
  state: 'Texas',
  lead_score: 85,
  epc_contractor: 'McCarthy Building',
  confidence: 'confirmed',
  discovery_id: 'disc-1',
  entity_id: 'ent-1',
  contacts: [
    {
      id: 'c-1',
      full_name: 'John Smith',
      title: 'VP of Solar',
      linkedin_url: 'https://linkedin.com/in/jsmith',
      outreach_context: null,
    },
  ],
  outreach_context: 'McCarthy was just awarded the 350MW Sunflower project in ERCOT.',
};

describe('NewLeadCard', () => {
  it('renders EPC contractor name as heading', () => {
    render(<NewLeadCard event={mockEvent} onExpand={() => {}} onDismiss={() => {}} />);
    expect(screen.getByText('McCarthy Building')).toBeInTheDocument();
  });

  it('renders project details', () => {
    render(<NewLeadCard event={mockEvent} onExpand={() => {}} onDismiss={() => {}} />);
    expect(screen.getByText(/Sunflower Solar/)).toBeInTheDocument();
    expect(screen.getByText(/350 MW/)).toBeInTheDocument();
    expect(screen.getByText(/Texas/)).toBeInTheDocument();
  });

  it('renders lead score', () => {
    render(<NewLeadCard event={mockEvent} onExpand={() => {}} onDismiss={() => {}} />);
    expect(screen.getByText('85')).toBeInTheDocument();
  });

  it('renders outreach context', () => {
    render(<NewLeadCard event={mockEvent} onExpand={() => {}} onDismiss={() => {}} />);
    expect(screen.getByText(/McCarthy was just awarded/)).toBeInTheDocument();
  });

  it('renders contacts', () => {
    render(<NewLeadCard event={mockEvent} onExpand={() => {}} onDismiss={() => {}} />);
    expect(screen.getByText('John Smith')).toBeInTheDocument();
    expect(screen.getByText('VP of Solar')).toBeInTheDocument();
    expect(screen.getByText('LinkedIn')).toBeInTheDocument();
  });

  it('renders action buttons', () => {
    render(<NewLeadCard event={mockEvent} onExpand={() => {}} onDismiss={() => {}} />);
    expect(screen.getByText('Push to HubSpot')).toBeInTheDocument();
    expect(screen.getByText('Copy Outreach')).toBeInTheDocument();
    expect(screen.getByText('Details')).toBeInTheDocument();
  });

  it('calls onExpand when Details clicked', () => {
    const onExpand = vi.fn();
    render(<NewLeadCard event={mockEvent} onExpand={onExpand} onDismiss={() => {}} />);
    fireEvent.click(screen.getByText('Details'));
    expect(onExpand).toHaveBeenCalledWith('proj-1');
  });

  it('renders New Lead badge', () => {
    render(<NewLeadCard event={mockEvent} onExpand={() => {}} onDismiss={() => {}} />);
    expect(screen.getByText('New Lead')).toBeInTheDocument();
  });

  it('renders region label', () => {
    render(<NewLeadCard event={mockEvent} onExpand={() => {}} onDismiss={() => {}} />);
    expect(screen.getByText('ERCOT')).toBeInTheDocument();
  });
});
