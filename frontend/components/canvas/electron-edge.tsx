"use client";

import { useMemo } from "react";
import { BaseEdge, getBezierPath, type EdgeProps } from "@xyflow/react";
import { useReducedMotion } from "motion/react";

/**
 * Electron-flow edge — ported from the SoniqBoom circuit-board effect.
 *
 * Glowing emerald "electrons" (a bright core in a soft halo, SoniqBoom's
 * signature look) stream ALONG the edge from source → target, so the eye
 * reads the direction information flows through the pipeline (dataset →
 * step → output) at a glance — not just which nodes are wired, but which
 * way the data moves.
 *
 * Implementation notes:
 *  - SVG <animateMotion path=…> moves each electron along the exact bezier
 *    the edge already draws. The path is generated source→target, so the
 *    motion direction IS the data-flow direction — no extra bookkeeping.
 *  - Constant visual speed: the animation duration scales with the edge's
 *    endpoint distance (px / SPEED), so electrons travel at the same px/s
 *    on a short hop and a long sweep alike (matches SoniqBoom's feel).
 *  - Electrons are evenly distributed via negative `begin` offsets, so a
 *    fresh edge shows a full stream immediately rather than one lonely dot.
 *  - prefers-reduced-motion → no electrons (the arrowhead marker still
 *    shows direction). Same posture as SoniqBoom, which hides its electron
 *    canvas under reduced-motion.
 *  - SMIL animations auto-throttle when the tab is hidden, so there's no
 *    explicit visibility pause to wire up.
 */

// Constant electron speed in px/s (in flow coordinates). Tuned to read as
// a deliberate, calm flow rather than a frantic blur.
const SPEED_PX_PER_S = 90;
// Electrons per edge. Small — enough to read as a stream, cheap enough to
// run dozens of edges of SMIL animation without jank.
const N_ELECTRONS = 3;

export function ElectronEdge({
  id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition,
  markerEnd, style,
}: EdgeProps) {
  const reduce = useReducedMotion();

  // Memoize on geometry only. The edge component re-renders often for
  // reasons unrelated to its shape (selection, run metrics, freshness
  // halos) — recomputing `edgePath`/`dur` on those frames would re-parse
  // <animateMotion> and restart every electron mid-flow (flicker). A real
  // geometry change (node drag) still re-tunes both, which is correct:
  // constant px/s means a longer edge legitimately gets a longer dur.
  const { edgePath, dur } = useMemo(() => {
    const [path] = getBezierPath({
      sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition,
    });
    // Duration from straight-line endpoint distance keeps a constant px/s
    // through the mid-range; the clamp trades exact speed for sanity at the
    // extremes (a tiny edge isn't a strobe, a huge one isn't glacial).
    const dist = Math.hypot(targetX - sourceX, targetY - sourceY) || 1;
    return { edgePath: path, dur: Math.max(0.9, Math.min(6, dist / SPEED_PX_PER_S)) };
  }, [sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition]);

  return (
    <>
      <BaseEdge id={id} path={edgePath} markerEnd={markerEnd} style={style} />
      {!reduce && (
        // Each electron is one emerald circle; the group's stacked
        // drop-shadows add the soft halo = SoniqBoom's glowing-electron
        // look, one animated element apiece (cheap). The core uses
        // --ring (DIG's theme-adaptive emerald: darker on the light
        // canvas, brighter on dark) so the dot reads on both themes —
        // a white core would vanish on DIG's near-white canvas.
        // aria-hidden: purely decorative, keep it out of the a11y tree.
        <g
          aria-hidden="true"
          style={{
            filter:
              "drop-shadow(0 0 2px var(--color-emerald-400)) drop-shadow(0 0 5px var(--color-emerald-500))",
            pointerEvents: "none",
          }}
        >
          {Array.from({ length: N_ELECTRONS }).map((_, i) => (
            <circle key={i} r={3} fill="var(--ring)">
              <animateMotion
                dur={`${dur}s`}
                begin={`-${((i * dur) / N_ELECTRONS).toFixed(3)}s`}
                repeatCount="indefinite"
                path={edgePath}
              />
            </circle>
          ))}
        </g>
      )}
    </>
  );
}
