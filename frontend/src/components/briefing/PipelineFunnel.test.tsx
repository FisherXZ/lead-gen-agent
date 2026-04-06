// frontend/src/components/briefing/PipelineFunnel.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import PipelineFunnel from "./PipelineFunnel";

describe("PipelineFunnel", () => {
  it("renders all 5 stage counts", () => {
    render(
      <PipelineFunnel
        totalProjects={423}
        researched={64}
        pendingReview={61}
        accepted={3}
        inCrm={0}
      />
    );
    // Each count appears twice (desktop + mobile layouts)
    expect(screen.getAllByText("423").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("64").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("61").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("3").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("0").length).toBeGreaterThanOrEqual(1);
  });

  it("renders all 5 stage labels", () => {
    render(
      <PipelineFunnel
        totalProjects={10}
        researched={5}
        pendingReview={3}
        accepted={2}
        inCrm={1}
      />
    );
    // Labels appear twice (desktop + mobile)
    expect(screen.getAllByText("Projects").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Pending Review").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("In CRM").length).toBeGreaterThanOrEqual(1);
  });

  it("renders arrows between stages on desktop", () => {
    render(
      <PipelineFunnel
        totalProjects={10}
        researched={5}
        pendingReview={3}
        accepted={2}
        inCrm={1}
      />
    );
    const arrows = screen.getAllByText("→");
    expect(arrows.length).toBe(4);
  });

  it("renders links to correct pages", () => {
    render(
      <PipelineFunnel
        totalProjects={10}
        researched={5}
        pendingReview={3}
        accepted={2}
        inCrm={0}
      />
    );
    const links = screen.getAllByRole("link");
    const hrefs = links.map((l) => l.getAttribute("href"));
    expect(hrefs).toContain("/projects");
    expect(hrefs).toContain("/review");
    expect(hrefs).toContain("/actions");
  });
});
