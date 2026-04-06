import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { DigestCard } from './DigestCard';
import { DigestEvent } from '@/lib/briefing-types';

const mockEvent: DigestEvent = {
  id: 'digest-1',
  type: 'digest',
  priority: 5,
  created_at: '2026-04-07T08:00:00Z',
  dismissed: false,
  period_start: '2026-03-31',
  period_end: '2026-04-06',
  new_projects_count: 24,
  epcs_discovered_count: 8,
  contacts_found_count: 15,
  top_leads: [
    { project_name: 'Sunflower Solar', epc_contractor: 'McCarthy', lead_score: 92 },
    { project_name: 'Mesa Verde', epc_contractor: 'Blattner', lead_score: 85 },
  ],
};

describe('DigestCard', () => {
  it('renders Weekly Digest badge', () => {
    render(<DigestCard event={mockEvent} />);
    expect(screen.getByText('Weekly Digest')).toBeInTheDocument();
  });

  it('renders project count', () => {
    render(<DigestCard event={mockEvent} />);
    expect(screen.getByText('24')).toBeInTheDocument();
    expect(screen.getByText('New Projects')).toBeInTheDocument();
  });

  it('renders EPCs discovered count', () => {
    render(<DigestCard event={mockEvent} />);
    expect(screen.getByText('8')).toBeInTheDocument();
    expect(screen.getByText('EPCs Discovered')).toBeInTheDocument();
  });

  it('renders contacts found count', () => {
    render(<DigestCard event={mockEvent} />);
    expect(screen.getByText('15')).toBeInTheDocument();
    expect(screen.getByText('Contacts Found')).toBeInTheDocument();
  });

  it('renders top leads', () => {
    render(<DigestCard event={mockEvent} />);
    expect(screen.getByText('McCarthy')).toBeInTheDocument();
    expect(screen.getByText(/Sunflower Solar/)).toBeInTheDocument();
    expect(screen.getByText('92')).toBeInTheDocument();
    expect(screen.getByText('Blattner')).toBeInTheDocument();
  });

  it('renders Top Leads section header', () => {
    render(<DigestCard event={mockEvent} />);
    expect(screen.getByText('Top Leads')).toBeInTheDocument();
  });
});
