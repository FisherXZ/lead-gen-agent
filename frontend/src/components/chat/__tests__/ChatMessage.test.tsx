import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import ChatMessage from '../ChatMessage';

// Mock child components with complex dependencies
vi.mock('../MarkdownMessage', () => ({
  default: ({ content }: { content: string }) => (
    <div data-testid="markdown">{content}</div>
  ),
}));

vi.mock('../ToolPart', () => ({
  default: () => <div data-testid="tool-part" />,
}));

vi.mock('../ResearchTimeline', () => ({
  default: () => <div data-testid="timeline" />,
}));

vi.mock('../SourceSummaryBar', () => ({
  default: () => null,
}));

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function makeToolPart(toolCallId: string, toolName: string): any {
  return {
    type: 'tool-invocation',
    toolCallId,
    toolName,
    state: 'done',
    input: {},
    output: { projects: [] },
  };
}

describe('ChatMessage', () => {
  it('renders text before tools as visible response text (not hidden in accordion)', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const message: any = {
      id: 'test-1',
      role: 'assistant',
      parts: [
        { type: 'text', text: 'Let me check the data for you.' },
        makeToolPart('call-1', 'search_projects'),
        { type: 'text', text: 'Here are the results.' },
      ],
    };

    render(<ChatMessage message={message} />);

    // Pre-tool text should be visible in the document
    expect(screen.getByText('Let me check the data for you.')).toBeInTheDocument();

    // It should NOT be inside an element with aria-label "Agent reasoning"
    const accordions = document.querySelectorAll('[aria-label="Agent reasoning"]');
    expect(accordions.length).toBe(0);
  });

  it('does not render any ThinkingAccordion element', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const message: any = {
      id: 'test-2',
      role: 'assistant',
      parts: [
        { type: 'text', text: 'I am thinking about this problem...' },
        makeToolPart('call-2', 'search_projects'),
      ],
    };

    render(<ChatMessage message={message} />);

    // No ThinkingAccordion should be rendered (aria-label comes from ThinkingAccordion)
    const accordions = document.querySelectorAll('[aria-label="Agent reasoning"]');
    expect(accordions.length).toBe(0);
  });

  it('renders response text after tools as visible', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const message: any = {
      id: 'test-3',
      role: 'assistant',
      parts: [
        makeToolPart('call-3', 'search_projects'),
        { type: 'text', text: 'Here are the results.' },
      ],
    };

    render(<ChatMessage message={message} />);

    // Post-tool text should be visible
    expect(screen.getByText('Here are the results.')).toBeInTheDocument();
  });
});
