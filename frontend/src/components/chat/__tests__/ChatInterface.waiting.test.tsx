import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import WaitingIndicator from '../WaitingIndicator';

describe('WaitingIndicator', () => {
  it('shows amber pulse dot (animate-timeline-pulse) when rendered', () => {
    render(<WaitingIndicator />);
    const pulseDot = document.querySelector('.animate-timeline-pulse');
    expect(pulseDot).not.toBeNull();
  });

  it('does not use animate-bounce', () => {
    render(<WaitingIndicator />);
    const bounceDots = document.querySelectorAll('.animate-bounce');
    expect(bounceDots.length).toBe(0);
  });

  it('shows "Researching..." text', () => {
    render(<WaitingIndicator />);
    expect(screen.getByText('Researching...')).toBeTruthy();
  });

  it('does not show "Thinking..." text', () => {
    render(<WaitingIndicator />);
    expect(screen.queryByText('Thinking...')).toBeNull();
  });
});
