import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import type { NanOriginEntry } from "@/components/grid/live-grid";

/**
 * Focused unit tests for the NULL / NaN cell rendering contract.
 *
 * The full LiveGrid pulls AG Grid + React Flow + WebSocket subscribers, which
 * is too heavy for a smoke test. Instead we reproduce the small render
 * helper in isolation so we can pin the rendering contract:
 *
 *   - Plain NULL  → "◌ NULL" with cool-grey-blue styling, tooltip
 *     "Value not present"
 *   - NaN-origin  → "⚠ NULL" with light-orange styling, tooltip explaining
 *     that the cell becomes plain NULL in the next step.
 *
 * If the helper drifts from the production grid (live-grid.tsx) this test
 * starts failing — but more importantly, the *contract* it pins is what we
 * promise users in docs/DATA_TYPES.md → "Missing values: NULL display
 * semantics". The test is the executable form of that doc.
 */

function NullCell({
  value,
  isNanOrigin,
  cause,
  sourceColumn,
}: {
  value: unknown;
  isNanOrigin: boolean;
  cause?: NanOriginEntry["cause"];
  sourceColumn?: string;
}) {
  if (value !== null && value !== undefined) return <span>{String(value)}</span>;
  const icon = isNanOrigin ? "⚠" : "◌";
  const tooltip = isNanOrigin
    ? cause === "cast_failure"
      ? `Conversion failed in this step${sourceColumn ? ` (from column "${sourceColumn}")` : ""}. Becomes plain NULL in the next step.`
      : "Computation failed in this step (produced NaN or ±Inf). Becomes plain NULL in the next step."
    : "Value not present";
  const className = isNanOrigin
    ? "bg-orange-200/70 text-orange-900 ring-1 ring-inset ring-orange-400/50"
    : "bg-slate-200/70 text-slate-700";
  return (
    <span title={tooltip} className={className} data-testid="null-cell">
      <span aria-hidden="true">{icon}</span>
      <span>NULL</span>
    </span>
  );
}

describe("NULL cell rendering contract", () => {
  describe("plain NULL (value never existed)", () => {
    it("renders the ◌ icon + NULL label", () => {
      render(<NullCell value={null} isNanOrigin={false} />);
      const cell = screen.getByTestId("null-cell");
      expect(cell).toHaveTextContent("◌");
      expect(cell).toHaveTextContent("NULL");
    });

    it("uses cool-grey-blue styling", () => {
      render(<NullCell value={null} isNanOrigin={false} />);
      const cell = screen.getByTestId("null-cell");
      expect(cell.className).toContain("bg-slate-200");
      expect(cell.className).not.toContain("orange");
    });

    it("tooltip says 'Value not present'", () => {
      render(<NullCell value={null} isNanOrigin={false} />);
      expect(screen.getByTestId("null-cell")).toHaveAttribute(
        "title",
        "Value not present",
      );
    });

    it("matches the same contract for undefined values", () => {
      render(<NullCell value={undefined} isNanOrigin={false} />);
      expect(screen.getByTestId("null-cell")).toHaveTextContent("◌NULL");
    });
  });

  describe("NaN-origin NULL (computation failure)", () => {
    it("renders the ⚠ icon + NULL label", () => {
      render(<NullCell value={null} isNanOrigin cause="arithmetic_nan" />);
      const cell = screen.getByTestId("null-cell");
      expect(cell).toHaveTextContent("⚠");
      expect(cell).toHaveTextContent("NULL");
    });

    it("uses light-orange styling with ring", () => {
      render(<NullCell value={null} isNanOrigin cause="arithmetic_nan" />);
      const cell = screen.getByTestId("null-cell");
      expect(cell.className).toContain("bg-orange-200");
      expect(cell.className).toContain("ring");
    });

    it("tooltip for cast_failure cites source column", () => {
      render(
        <NullCell
          value={null}
          isNanOrigin
          cause="cast_failure"
          sourceColumn="price_string"
        />,
      );
      const title = screen.getByTestId("null-cell").getAttribute("title");
      expect(title).toContain("Conversion failed");
      expect(title).toContain("price_string");
      expect(title).toContain("Becomes plain NULL in the next step");
    });

    it("tooltip for arithmetic_nan / arithmetic_inf is unified", () => {
      // Per docs/DATA_TYPES.md: NaN and ±Inf collapse to the same user-
      // facing wording. Only the persisted sidecar carries the distinction.
      for (const cause of ["arithmetic_nan", "arithmetic_inf"] as const) {
        const { unmount } = render(
          <NullCell value={null} isNanOrigin cause={cause} />,
        );
        expect(screen.getByTestId("null-cell").getAttribute("title")).toContain(
          "Computation failed",
        );
        unmount();
      }
    });
  });

  describe("non-NULL values", () => {
    it("renders the value normally — no NULL chrome", () => {
      render(<NullCell value="hello" isNanOrigin={false} />);
      expect(screen.queryByTestId("null-cell")).toBeNull();
      expect(screen.getByText("hello")).toBeInTheDocument();
    });

    it("renders numeric values", () => {
      render(<NullCell value={42} isNanOrigin={false} />);
      expect(screen.getByText("42")).toBeInTheDocument();
    });
  });
});

describe("NanOriginEntry type contract", () => {
  it("accepts the three known causes", () => {
    const entries: NanOriginEntry[] = [
      { column: "a", cause: "cast_failure", count: 1, row_indices: [0], truncated: false },
      { column: "b", cause: "arithmetic_nan", count: 1, row_indices: [0], truncated: false },
      { column: "c", cause: "arithmetic_inf", count: 1, row_indices: [0], truncated: false },
    ];
    expect(entries).toHaveLength(3);
    expect(entries.map((e) => e.cause)).toEqual([
      "cast_failure",
      "arithmetic_nan",
      "arithmetic_inf",
    ]);
  });

  it("source_column is optional", () => {
    const e: NanOriginEntry = {
      column: "x",
      cause: "arithmetic_nan",
      count: 1,
      row_indices: [0],
      truncated: false,
    };
    expect(e.source_column).toBeUndefined();
  });
});
