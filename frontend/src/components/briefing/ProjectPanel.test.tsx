import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ProjectPanel } from './ProjectPanel';

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

// Mock Supabase
vi.mock('@supabase/ssr', () => ({
  createBrowserClient: () => ({
    from: (table: string) => {
      if (table === 'projects') {
        return {
          select: () => ({
            eq: () => ({
              single: () => Promise.resolve({
                data: {
                  id: 'proj-1',
                  project_name: 'Sunflower Solar',
                  developer: 'NextEra',
                  mw_capacity: 350,
                  iso_region: 'ERCOT',
                  state: 'Texas',
                  county: 'Travis',
                  latitude: 30.27,
                  longitude: -97.74,
                  lead_score: 85,
                  construction_status: 'pre_construction',
                  expected_cod: '2027-Q2',
                  fuel_type: 'Solar',
                  queue_id: 'Q-123',
                },
              }),
            }),
          }),
        };
      }
      // epc_discoveries
      return {
        select: () => ({
          eq: () => ({
            order: () => ({
              limit: () => ({
                maybeSingle: () => Promise.resolve({
                  data: {
                    id: 'disc-1',
                    epc_contractor: 'McCarthy Building',
                    confidence: 'confirmed',
                    review_status: 'accepted',
                  },
                }),
              }),
            }),
          }),
        }),
      };
    },
  }),
}));

describe('ProjectPanel', () => {
  beforeEach(() => {
    mockPush.mockClear();
  });

  it('renders nothing when projectId is null', () => {
    const { container } = render(<ProjectPanel projectId={null} onClose={() => {}} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders project name when projectId provided', async () => {
    render(<ProjectPanel projectId="proj-1" onClose={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('Sunflower Solar')).toBeInTheDocument();
    });
  });

  it('renders project details', async () => {
    render(<ProjectPanel projectId="proj-1" onClose={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('NextEra')).toBeInTheDocument();
      expect(screen.getByText('ERCOT')).toBeInTheDocument();
      expect(screen.getByText(/350 MW/)).toBeInTheDocument();
    });
  });

  it('renders EPC discovery details', async () => {
    render(<ProjectPanel projectId="proj-1" onClose={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('McCarthy Building')).toBeInTheDocument();
    });
  });

  it('renders back button', async () => {
    render(<ProjectPanel projectId="proj-1" onClose={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText(/Back to Briefing/)).toBeInTheDocument();
    });
  });

  it('calls onClose when back button clicked', async () => {
    const onClose = vi.fn();
    render(<ProjectPanel projectId="proj-1" onClose={onClose} />);
    await waitFor(() => {
      expect(screen.getByText(/Back to Briefing/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText(/Back to Briefing/));
    expect(onClose).toHaveBeenCalled();
  });

  it('calls onClose when backdrop clicked', async () => {
    const onClose = vi.fn();
    render(<ProjectPanel projectId="proj-1" onClose={onClose} />);
    await waitFor(() => {
      expect(screen.getByText('Sunflower Solar')).toBeInTheDocument();
    });
    // Click the backdrop (first fixed div)
    const backdrop = document.querySelector('.fixed.inset-0');
    if (backdrop) fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalled();
  });

  it('renders Investigate in Chat button', async () => {
    render(<ProjectPanel projectId="proj-1" onClose={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('Investigate in Chat')).toBeInTheDocument();
    });
  });

  it('navigates to agent with context when investigate clicked', async () => {
    render(<ProjectPanel projectId="proj-1" onClose={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText('Investigate in Chat')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Investigate in Chat'));
    expect(mockPush).toHaveBeenCalledWith(expect.stringContaining('/agent?context='));
  });

  it('renders location details', async () => {
    render(<ProjectPanel projectId="proj-1" onClose={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText(/Travis/)).toBeInTheDocument();
      expect(screen.getByText(/View on Google Maps/)).toBeInTheDocument();
    });
  });
});
