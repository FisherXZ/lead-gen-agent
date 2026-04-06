import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { StatBar } from './StatBar';

describe('StatBar', () => {
  const stats = {
    new_leads_this_week: 12,
    awaiting_review: 3,
    total_epcs_discovered: 47,
  };

  it('renders new leads count', () => {
    render(<StatBar stats={stats} />);
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText(/new leads this week/i)).toBeInTheDocument();
  });

  it('renders awaiting review count', () => {
    render(<StatBar stats={stats} />);
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText(/awaiting review/i)).toBeInTheDocument();
  });

  it('renders total EPCs discovered', () => {
    render(<StatBar stats={stats} />);
    expect(screen.getByText('47')).toBeInTheDocument();
    expect(screen.getByText(/EPCs discovered/i)).toBeInTheDocument();
  });

  it('renders zero values correctly', () => {
    render(<StatBar stats={{ new_leads_this_week: 0, awaiting_review: 0, total_epcs_discovered: 0 }} />);
    const zeros = screen.getAllByText('0');
    expect(zeros.length).toBe(3);
  });
});
