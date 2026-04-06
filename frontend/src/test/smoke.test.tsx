import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

function Hello() {
  return <div>Hello, test infrastructure!</div>;
}

describe('Test infrastructure', () => {
  it('renders a React component', () => {
    render(<Hello />);
    expect(screen.getByText('Hello, test infrastructure!')).toBeInTheDocument();
  });
});
