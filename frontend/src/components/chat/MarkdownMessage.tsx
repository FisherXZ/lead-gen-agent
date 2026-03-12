"use client";

import { Streamdown } from "streamdown";
import { code } from "@streamdown/code";
import "streamdown/styles.css";

interface MarkdownMessageProps {
  content: string;
  isStreaming: boolean;
}

const plugins = { code };

const components = {
  table: ({ children, ...props }: React.ComponentProps<"table">) => (
    <div className="overflow-x-auto my-2 rounded-lg border border-slate-200">
      <table {...props} className="min-w-full">
        {children}
      </table>
    </div>
  ),
  a: ({ children, ...props }: React.ComponentProps<"a">) => (
    <a {...props} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
};

export default function MarkdownMessage({
  content,
  isStreaming,
}: MarkdownMessageProps) {
  if (!content || content.trim() === "") {
    return null;
  }

  return (
    <div className="prose prose-slate max-w-none prose-headings:font-semibold prose-headings:text-slate-800 prose-p:leading-relaxed prose-a:text-blue-600 prose-a:no-underline hover:prose-a:underline prose-code:rounded prose-code:bg-slate-100 prose-code:px-1 prose-code:py-0.5 prose-code:text-sm prose-code:before:content-none prose-code:after:content-none prose-pre:bg-slate-900 prose-pre:rounded-lg prose-th:text-left prose-th:font-medium prose-th:border prose-th:border-slate-200 prose-th:px-3 prose-td:border prose-td:border-slate-200 prose-td:px-3 prose-td:py-1.5 prose-th:py-1.5">
      <Streamdown
        animated
        plugins={plugins}
        components={components}
        isAnimating={isStreaming}
      >
        {content}
      </Streamdown>
    </div>
  );
}
