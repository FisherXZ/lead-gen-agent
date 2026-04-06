import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { QuickFilters } from './QuickFilters';
import { BriefingFilters } from '@/lib/briefing-types';

describe('QuickFilters', () => {
  const defaultFilters: BriefingFilters = { region: 'all', timeRange: 'this_week' };

  it('renders all region options', () => {
    render(<QuickFilters filters={defaultFilters} onChange={() => {}} />);
    expect(screen.getByText('All Regions')).toBeInTheDocument();
    expect(screen.getByText('ERCOT')).toBeInTheDocument();
    expect(screen.getByText('CAISO')).toBeInTheDocument();
    expect(screen.getByText('MISO')).toBeInTheDocument();
  });

  it('renders all time range options', () => {
    render(<QuickFilters filters={defaultFilters} onChange={() => {}} />);
    expect(screen.getByText('Today')).toBeInTheDocument();
    expect(screen.getByText('This Week')).toBeInTheDocument();
    expect(screen.getByText('This Month')).toBeInTheDocument();
  });

  it('calls onChange with updated region when region chip clicked', () => {
    const onChange = vi.fn();
    render(<QuickFilters filters={defaultFilters} onChange={onChange} />);
    fireEvent.click(screen.getByText('ERCOT'));
    expect(onChange).toHaveBeenCalledWith({ region: 'ERCOT', timeRange: 'this_week' });
  });

  it('calls onChange with updated timeRange when time chip clicked', () => {
    const onChange = vi.fn();
    render(<QuickFilters filters={defaultFilters} onChange={onChange} />);
    fireEvent.click(screen.getByText('Today'));
    expect(onChange).toHaveBeenCalledWith({ region: 'all', timeRange: 'today' });
  });

  it('highlights the active region filter', () => {
    render(<QuickFilters filters={{ region: 'CAISO', timeRange: 'this_week' }} onChange={() => {}} />);
    const caisoButton = screen.getByText('CAISO');
    expect(caisoButton.className).toContain('accent-amber');
  });
});
