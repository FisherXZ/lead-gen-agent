// frontend/src/components/briefing/QuickNav.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import QuickNav from "./QuickNav";

describe("QuickNav", () => {
  it("renders all 5 navigation links", () => {
    render(<QuickNav />);
    expect(screen.getByText("Pipeline →")).toBeInTheDocument();
    expect(screen.getByText("Review Queue →")).toBeInTheDocument();
    expect(screen.getByText("Actions →")).toBeInTheDocument();
    expect(screen.getByText("Map →")).toBeInTheDocument();
    expect(screen.getByText("Solarina →")).toBeInTheDocument();
  });

  it("links point to correct pages", () => {
    render(<QuickNav />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(5);
    expect(links[0]).toHaveAttribute("href", "/projects");
    expect(links[1]).toHaveAttribute("href", "/review");
    expect(links[2]).toHaveAttribute("href", "/actions");
    expect(links[3]).toHaveAttribute("href", "/map");
    expect(links[4]).toHaveAttribute("href", "/agent");
  });
});
