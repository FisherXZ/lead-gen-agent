import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { AlertCard } from './AlertCard';
import { NewProjectEvent, StatusChangeEvent } from '@/lib/briefing-types';

vi.mock('@/lib/agent-fetch', () => ({
  agentFetch: vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ plan: 'test plan' }) })),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const newProjectEvent: NewProjectEvent = {
  id: 'project-1',
  type: 'new_project',
  priority: 3,
  created_at: '2026-04-05T10:00:00Z',
  dismissed: false,
  project_id: 'proj-3',
  project_name: 'Mesa Verde Solar',
  developer: 'Invenergy',
  mw_capacity: 500,
  iso_region: 'MISO',
  state: 'Indiana',
  status: 'Active',
};

const statusChangeEvent: StatusChangeEvent = {
  id: 'status-1',
  type: 'status_change',
  priority: 4,
  created_at: '2026-04-05T10:00:00Z',
  dismissed: false,
  project_id: 'proj-4',
  project_name: 'Red Rock Solar',
  previous_status: 'pre_construction',
  new_status: 'under_construction',
  expected_cod: '2027-Q3',
};

describe('AlertCard - New Project', () => {
  it('renders New Project badge', () => {
    render(<AlertCard event={newProjectEvent} onExpand={() => {}} onDismiss={() => {}} />);
    expect(screen.getByText('New Project')).toBeInTheDocument();
  });

  it('renders project name and details', () => {
    render(<AlertCard event={newProjectEvent} onExpand={() => {}} onDismiss={() => {}} />);
    expect(screen.getByText('Mesa Verde Solar')).toBeInTheDocument();
    expect(screen.getByText(/Invenergy/)).toBeInTheDocument();
    expect(screen.getByText(/500 MW/)).toBeInTheDocument();
  });

  it('renders Research EPC button', () => {
    render(<AlertCard event={newProjectEvent} onExpand={() => {}} onDismiss={() => {}} />);
    expect(screen.getByText('Research EPC')).toBeInTheDocument();
  });

  it('renders Dismiss button', () => {
    render(<AlertCard event={newProjectEvent} onExpand={() => {}} onDismiss={() => {}} />);
    expect(screen.getByText('Dismiss')).toBeInTheDocument();
  });

  it('calls onDismiss when Dismiss clicked', () => {
    const onDismiss = vi.fn();
    render(<AlertCard event={newProjectEvent} onExpand={() => {}} onDismiss={onDismiss} />);
    fireEvent.click(screen.getByText('Dismiss'));
    expect(onDismiss).toHaveBeenCalledWith('project-1');
  });
});

describe('AlertCard - Status Change', () => {
  it('renders Status Change badge', () => {
    render(<AlertCard event={statusChangeEvent} onExpand={() => {}} onDismiss={() => {}} />);
    expect(screen.getByText('Status Change')).toBeInTheDocument();
  });

  it('renders project name', () => {
    render(<AlertCard event={statusChangeEvent} onExpand={() => {}} onDismiss={() => {}} />);
    expect(screen.getByText('Red Rock Solar')).toBeInTheDocument();
  });

  it('renders status transition', () => {
    render(<AlertCard event={statusChangeEvent} onExpand={() => {}} onDismiss={() => {}} />);
    expect(screen.getByText(/Pre-Construction/)).toBeInTheDocument();
    expect(screen.getByText(/Under Construction/)).toBeInTheDocument();
  });

  it('renders Details button', () => {
    render(<AlertCard event={statusChangeEvent} onExpand={() => {}} onDismiss={() => {}} />);
    expect(screen.getByText('Details')).toBeInTheDocument();
  });

  it('calls onExpand when Details clicked', () => {
    const onExpand = vi.fn();
    render(<AlertCard event={statusChangeEvent} onExpand={onExpand} onDismiss={() => {}} />);
    fireEvent.click(screen.getByText('Details'));
    expect(onExpand).toHaveBeenCalledWith('proj-4');
  });
});
