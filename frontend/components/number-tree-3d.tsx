"use client";

import { useEffect, useRef } from "react";

/**
 * NumberTree3D — a transparent muted-green 3D tree composed entirely of
 * digits in a terminal monospace font. Designed to sit *behind* the
 * MatrixTreeBackground (which has the cascading rain).
 *
 * Implementation notes:
 *   - Pre-computed point cloud sampled from a tree silhouette (canopy +
 *     trunk + a few branches), with a Z component sampled from a
 *     bell-distribution so points cluster around z=0 (front-back depth).
 *   - Each frame applies a slow Y-axis rotation, projects to screen via a
 *     simple perspective transform, then renders each point as a single
 *     digit with size + opacity scaled by depth.
 *   - Static fallback when prefers-reduced-motion is set.
 *   - Cheap: ~600 points × one fillText each = ~10k ops/frame, well under a
 *     full Matrix-rain render. We also throttle to 30 fps because the
 *     rotation is meant to be subliminal, not snappy.
 */
export function NumberTree3D({
  className = "fixed inset-0 -z-20 pointer-events-none",
  density = 800,
}: {
  className?: string;
  /** Approximate number of digits. Bigger = denser tree. */
  density?: number;
}) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let dpr = Math.min(window.devicePixelRatio || 1, 2);
    let W = window.innerWidth;
    let H = window.innerHeight;
    let last = performance.now();
    const targetFps = 30;
    const frameMs = 1000 / targetFps;

    /** Sample one (x, y, z) point on a unit-tree shape (-1..1 in each axis). */
    const sampleTreePoint = (): [number, number, number] => {
      const r = Math.random();
      // 18% trunk, 82% canopy. Trunk runs y=0..-0.5; canopy around y=-0.45..1.
      if (r < 0.18) {
        // Trunk: thin rectangle.
        const x = (Math.random() - 0.5) * 0.18;
        const y = -1 + Math.random() * 0.55;
        const z = (Math.random() - 0.5) * 0.16;
        return [x, y, z];
      }
      // Canopy: roughly spherical / oblate. Sample inside a ball, weighted
      // toward the surface so the silhouette feels "planted with leaves".
      let x = 0, y = 0, z = 0, mag = 0;
      let tries = 0;
      do {
        x = (Math.random() - 0.5) * 2;
        y = (Math.random() - 0.5) * 2;
        z = (Math.random() - 0.5) * 2;
        mag = Math.hypot(x, y, z);
        tries++;
      } while ((mag > 1 || mag < 0.45) && tries < 6);
      // Pinch the canopy at the top (y > 0) — fewer points up high → conical
      // taper. Push the whole canopy up.
      const taper = 1 - 0.5 * Math.max(0, y);
      x *= taper;
      z *= taper;
      // Map y to canopy region (-0.45..0.95).
      y = -0.45 + (y + 1) * 0.7;
      return [x, y, z];
    };

    let points: Array<[number, number, number, string]> = [];
    const seedPoints = () => {
      points = new Array(density).fill(0).map(() => {
        const [x, y, z] = sampleTreePoint();
        const ch = Math.floor(Math.random() * 10).toString();
        return [x, y, z, ch];
      });
    };

    const resize = () => {
      W = window.innerWidth;
      H = window.innerHeight;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      canvas.style.width = "100%";
      canvas.style.height = "100%";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.textBaseline = "middle";
      ctx.textAlign = "center";
    };

    /** Project (x, y, z) ∈ [-1,1]³ to screen with a slight Y-axis rotation. */
    const project = (
      x: number, y: number, z: number, sin: number, cos: number,
    ): { sx: number; sy: number; depth: number } => {
      // Rotate around Y axis.
      const rx = x * cos + z * sin;
      const rz = -x * sin + z * cos;
      // Tree footprint: ~70% of viewport height, centered horizontally,
      // pulled down a touch so the canopy occupies the upper-middle.
      const treeH = Math.min(H * 0.85, W * 0.95);
      const cx = W * 0.5;
      const cy = H * 0.55;
      // Perspective: closer (rz < 0) appears bigger.
      const persp = 1 / (1.6 + rz * 0.4);
      const sx = cx + rx * (treeH * 0.45) * persp;
      // Y axis points down on screen; tree y=1 (top of canopy) maps to top.
      const sy = cy - y * (treeH * 0.5) * persp;
      // depth: 0 (front) → 1 (back). Used to attenuate alpha + size.
      const depth = (rz + 1) * 0.5;
      return { sx, sy, depth };
    };

    const draw = (now: number) => {
      const dt = now - last;
      raf = requestAnimationFrame(draw);
      if (dt < frameMs) return;
      last = now;

      // Slow rotation: full revolution every ~50 seconds.
      const t = (now / 50_000) * Math.PI * 2;
      const sin = Math.sin(t);
      const cos = Math.cos(t);

      // Clear (transparent — we don't fill the canvas, the page bg / matrix
      // backdrop shows through).
      ctx.clearRect(0, 0, W, H);

      // Sort by depth so back points render first (painter's algorithm).
      const projected = points.map(([x, y, z, ch]) => ({
        ...project(x, y, z, sin, cos),
        ch,
      }));
      projected.sort((a, b) => b.depth - a.depth);

      for (const { sx, sy, depth, ch } of projected) {
        const sizePx = 8 + (1 - depth) * 10;       // 8 (back) → 18 (front)
        const alpha = 0.05 + (1 - depth) * 0.18;   // 0.05 (back) → 0.23 (front)
        // Muted emerald: a deeper hue at the front, paler-green at the back.
        const g = Math.floor(120 + (1 - depth) * 80);
        ctx.font = `${sizePx}px ui-monospace, "Geist Mono", "SF Mono", Menlo, monospace`;
        ctx.fillStyle = `rgba(40, ${g}, 80, ${alpha})`;
        ctx.fillText(ch, sx, sy);
      }
    };

    const drawStatic = () => {
      // Same as one frame of draw() at sin=0, cos=1.
      ctx.clearRect(0, 0, W, H);
      const projected = points.map(([x, y, z, ch]) => ({
        ...project(x, y, z, 0, 1),
        ch,
      }));
      projected.sort((a, b) => b.depth - a.depth);
      for (const { sx, sy, depth, ch } of projected) {
        const sizePx = 8 + (1 - depth) * 10;
        const alpha = 0.05 + (1 - depth) * 0.18;
        const g = Math.floor(120 + (1 - depth) * 80);
        ctx.font = `${sizePx}px ui-monospace, "Geist Mono", "SF Mono", Menlo, monospace`;
        ctx.fillStyle = `rgba(40, ${g}, 80, ${alpha})`;
        ctx.fillText(ch, sx, sy);
      }
    };

    seedPoints();
    resize();
    window.addEventListener("resize", resize);

    const reduce =
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Pause when the tab isn't visible — saves battery + CPU. Browsers
    // throttle rAF to ~1 fps when hidden, but explicit cancel = zero work.
    const onVisibility = () => {
      if (reduce) return;
      if (document.hidden) {
        if (raf !== 0) { cancelAnimationFrame(raf); raf = 0; }
      } else if (raf === 0) {
        last = performance.now();
        raf = requestAnimationFrame(draw);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    if (reduce) {
      drawStatic();
    } else {
      raf = requestAnimationFrame(draw);
    }

    return () => {
      if (raf !== 0) cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [density]);

  return <canvas ref={ref} className={className} aria-hidden />;
}
