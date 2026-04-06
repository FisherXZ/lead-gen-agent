import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import CollapsibleToolCard from '../CollapsibleToolCard';

describe('CollapsibleToolCard', () => {
  it('shows amber pulsing dot when status is running', () => {
    const { container } = render(
      <CollapsibleToolCard
        label="Searching ERCOT queue"
        status="running"
        defaultExpanded={false}
      />
    );

    // Amber pulsing dot must exist
    const dot = container.querySelector('.animate-timeline-pulse');
    expect(dot).not.toBeNull();

    // Old spinner must NOT exist
    const spinner = container.querySelector('.animate-spin');
    expect(spinner).toBeNull();
  });

  it('shows green checkmark when status is done', () => {
    const { container } = render(
      <CollapsibleToolCard
        label="Done task"
        status="done"
        defaultExpanded={false}
      />
    );

    // Green checkmark element
    const green = container.querySelector('.text-status-green');
    expect(green).not.toBeNull();

    // No pulsing dot
    const dot = container.querySelector('.animate-timeline-pulse');
    expect(dot).toBeNull();
  });

  it('shows red X when status is error', () => {
    const { container } = render(
      <CollapsibleToolCard
        label="Failed task"
        status="error"
        defaultExpanded={false}
      />
    );

    const red = container.querySelector('.text-status-red');
    expect(red).not.toBeNull();
  });

  it('renders label text', () => {
    render(
      <CollapsibleToolCard
        label="Searching ERCOT queue"
        status="running"
        defaultExpanded={false}
      />
    );

    expect(screen.getByText('Searching ERCOT queue')).toBeInTheDocument();
  });

  it('does not render card border chrome', () => {
    const { container } = render(
      <CollapsibleToolCard
        label="Some tool"
        status="done"
        defaultExpanded={false}
      />
    );

    // No border-border-subtle on any element (card chrome removed)
    const bordered = container.querySelector('.border-border-subtle');
    expect(bordered).toBeNull();
  });

  it('expands children on click when children provided', () => {
    render(
      <CollapsibleToolCard
        label="Tool with children"
        status="done"
        defaultExpanded={false}
      >
        <div>Child content here</div>
      </CollapsibleToolCard>
    );

    // Children are rendered in a collapsed grid — find the header row
    const header = screen.getByText('Tool with children').closest('div[class*="flex"]') as HTMLElement ||
      screen.getByText('Tool with children').parentElement as HTMLElement;

    // Click on the label text's parent (the clickable header row)
    fireEvent.click(screen.getByText('Tool with children'));

    // After click, child content should be present in the DOM
    expect(screen.getByText('Child content here')).toBeInTheDocument();
  });
});
