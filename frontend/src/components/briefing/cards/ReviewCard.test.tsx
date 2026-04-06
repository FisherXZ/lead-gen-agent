import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ReviewCard } from './ReviewCard';
import { ReviewEvent } from '@/lib/briefing-types';

// Mock agentFetch
vi.mock('@/lib/agent-fetch', () => ({
  agentFetch: vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) })),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockEvent: ReviewEvent = {
  id: 'review-1',
  type: 'review',
  priority: 2,
  created_at: '2026-04-05T10:00:00Z',
  dismissed: false,
  project_id: 'proj-2',
  project_name: 'Desert Sun Project',
  mw_capacity: 200,
  iso_region: 'CAISO',
  epc_contractor: 'Blattner Energy',
  confidence: 'likely',
  discovery_id: 'disc-2',
  reasoning_summary: 'Found in press release from developer announcing financial close.',
  source_url: 'https://example.com/source',
};

describe('ReviewCard', () => {
  it('renders EPC contractor name', () => {
    render(<ReviewCard event={mockEvent} onDismiss={() => {}} />);
    expect(screen.getByText('Blattner Energy')).toBeInTheDocument();
  });

  it('renders project name and capacity', () => {
    render(<ReviewCard event={mockEvent} onDismiss={() => {}} />);
    expect(screen.getByText(/Desert Sun Project/)).toBeInTheDocument();
    expect(screen.getByText(/200 MW/)).toBeInTheDocument();
  });

  it('renders Needs Review badge', () => {
    render(<ReviewCard event={mockEvent} onDismiss={() => {}} />);
    expect(screen.getByText('Needs Review')).toBeInTheDocument();
  });

  it('renders confidence level', () => {
    render(<ReviewCard event={mockEvent} onDismiss={() => {}} />);
    expect(screen.getByText(/likely/i)).toBeInTheDocument();
  });

  it('renders reasoning summary', () => {
    render(<ReviewCard event={mockEvent} onDismiss={() => {}} />);
    expect(screen.getByText(/Found in press release/)).toBeInTheDocument();
  });

  it('renders source link', () => {
    render(<ReviewCard event={mockEvent} onDismiss={() => {}} />);
    expect(screen.getByText('Source')).toBeInTheDocument();
  });

  it('renders approve and reject buttons', () => {
    render(<ReviewCard event={mockEvent} onDismiss={() => {}} />);
    expect(screen.getByText('Approve')).toBeInTheDocument();
    expect(screen.getByText('Reject')).toBeInTheDocument();
  });

  it('renders investigate button', () => {
    render(<ReviewCard event={mockEvent} onDismiss={() => {}} />);
    expect(screen.getByText('Investigate')).toBeInTheDocument();
  });

  it('navigates to agent with context when investigate clicked', () => {
    render(<ReviewCard event={mockEvent} onDismiss={() => {}} />);
    fireEvent.click(screen.getByText('Investigate'));
    expect(mockPush).toHaveBeenCalledWith(expect.stringContaining('/agent?context='));
    expect(mockPush).toHaveBeenCalledWith(expect.stringContaining('Blattner'));
  });
});
