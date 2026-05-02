"use client";

import { useEffect, useRef } from "react";
import * as Plot from "@observablehq/plot";
import { motion } from "motion/react";
import type { ColumnInfo } from "@/lib/api/client";

const TYPE_EMOJI: Record<string, string> = {
  integer: "🔢",
  double: "🔢",
  string: "🅰️",
  date: "📅",
  datetime: "📅",
  boolean: "☑️",
  nested: "🧱",
};

function fmtNum(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "number") {
    if (!isFinite(v)) return "—";
    if (Math.abs(v) >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
    if (Number.isInteger(v)) return String(v);
    return v.toLocaleString(undefined, { maximumFractionDigits: 3 });
  }
  return String(v);
}

interface Props {
  column: ColumnInfo;
  index: number;
}

export function ProfileCard({ column, index }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const c = column;

  useEffect(() => {
    if (!ref.current) return;
    ref.current.innerHTML = "";

    let plot: HTMLElement | SVGSVGElement | undefined;
    try {
      if ((c.type === "integer" || c.type === "double") && c.histogram?.length) {
        const data = c.histogram.map((b) => ({
          bin: typeof b.bin === "number" ? b.bin : 0,
          count: typeof b.count === "number" ? b.count : 0,
        }));
        plot = Plot.plot({
          width: 280,
          height: 56,
          margin: 0,
          x: { axis: null },
          y: { axis: null },
          marks: [Plot.rectY(data, { x: "bin", y: "count", fill: "currentColor", fillOpacity: 0.65, inset: 0.5 })],
          style: { background: "transparent", overflow: "visible" },
        });
      } else if (c.topValues?.length) {
        const data = c.topValues.slice(0, 8).map((t) => ({
          label: String(t.value).slice(0, 24),
          count: typeof t.count === "number" ? t.count : 0,
        }));
        plot = Plot.plot({
          width: 280,
          height: 56,
          margin: 0,
          x: { axis: null, label: null },
          y: { axis: null, label: null, domain: data.map((d) => d.label) },
          marks: [Plot.barX(data, { x: "count", y: "label", fill: "currentColor", fillOpacity: 0.65 })],
          style: { background: "transparent", overflow: "visible" },
        });
      }
    } catch (e) {
      console.warn("profile chart failed for", c.name, e);
    }

    if (plot) {
      // Add a screen-reader-accessible name to the SVG so the chart isn't an
      // anonymous blob. Plot returns either an SVG or a wrapping <figure>.
      const svg = plot.tagName === "svg"
        ? plot as SVGElement
        : (plot as HTMLElement).querySelector("svg");
      if (svg) {
        svg.setAttribute("role", "img");
        const what = (c.type === "integer" || c.type === "double")
          ? "Distribution histogram" : "Top values";
        svg.setAttribute("aria-label", `${what} of column "${c.name}"`);
        // Some screen readers prefer a real <title> child over aria-label.
        const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
        title.textContent = `${what} of column "${c.name}"`;
        svg.insertBefore(title, svg.firstChild);
      }
      ref.current.appendChild(plot);
    }
    // Only re-render when the column's *content* changes — not on every parent
    // re-render (which previously rebuilt every plot card on the page on
    // every keystroke). Identity-stable deps via JSON.stringify of just the
    // shape that drives the plot.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    c.name,
    c.type,
    c.histogram ? JSON.stringify(c.histogram) : null,
    c.topValues ? JSON.stringify(c.topValues) : null,
  ]);

  const nullPct =
    c.nullFraction != null ? `${(c.nullFraction * 100).toFixed(c.nullFraction < 0.01 ? 2 : 1)}%` : "—";

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 320, damping: 30, delay: 0.025 * index }}
      className="rounded-lg border border-border bg-card/40 p-3 flex flex-col gap-2 min-w-[260px]"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="text-base select-none" aria-hidden>
            {TYPE_EMOJI[c.type] ?? "❔"}
          </span>
          <p className="text-sm font-medium truncate" title={c.name}>
            {c.name}
          </p>
        </div>
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground shrink-0">
          {c.type}
        </span>
      </div>

      <div ref={ref} className="text-foreground/80 -mx-1 h-[56px] flex items-end" />

      <dl className="grid grid-cols-3 gap-2 text-[10px] text-muted-foreground tabular-nums pt-1 border-t border-border/40">
        <div>
          <dt className="opacity-60 uppercase tracking-wider">Distinct</dt>
          <dd className="font-medium text-foreground">{fmtNum(c.distinctCount)}</dd>
        </div>
        <div>
          <dt className="opacity-60 uppercase tracking-wider">Nulls</dt>
          <dd className="font-medium text-foreground">{nullPct}</dd>
        </div>
        <div>
          {c.type === "integer" || c.type === "double" ? (
            <>
              <dt className="opacity-60 uppercase tracking-wider">Mean</dt>
              <dd className="font-medium text-foreground">{fmtNum(c.mean)}</dd>
            </>
          ) : (
            <>
              <dt className="opacity-60 uppercase tracking-wider">Min/Max</dt>
              <dd className="font-medium text-foreground">
                {fmtNum(c.min)}–{fmtNum(c.max)}
              </dd>
            </>
          )}
        </div>
      </dl>
    </motion.div>
  );
}
