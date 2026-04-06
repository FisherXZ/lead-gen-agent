import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ResearchTimeline from "../ResearchTimeline";

describe("ResearchTimeline", () => {
  it("renders stage name with uppercase class", () => {
    render(
      <ResearchTimeline
        stages={[{ name: "research", status: "complete", children: [] }]}
      />
    );
    // CSS text-transform: uppercase renders the text visually uppercase.
    // The element containing the stage name should have the 'uppercase' class.
    const el = screen.getByText("Research");
    expect(el).toHaveClass("uppercase");
  });

  it("renders stage name with tertiary text color", () => {
    render(
      <ResearchTimeline
        stages={[{ name: "research", status: "complete", children: [] }]}
      />
    );
    const el = screen.getByText("Research");
    expect(el).toHaveClass("text-text-tertiary");
  });

  it("renders active stage with amber pulsing dot", () => {
    render(
      <ResearchTimeline
        stages={[{ name: "research", status: "active", children: [] }]}
      />
    );
    const dot = document.querySelector(".animate-timeline-pulse");
    expect(dot).toBeInTheDocument();
  });

  it("renders complete stage with green checkmark icon", () => {
    render(
      <ResearchTimeline
        stages={[{ name: "research", status: "complete", children: [] }]}
      />
    );
    const icon = document.querySelector(".text-status-green");
    expect(icon).toBeInTheDocument();
  });
});
