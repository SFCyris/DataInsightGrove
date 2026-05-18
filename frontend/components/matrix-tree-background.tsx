"use client";

import { useEffect, useRef } from "react";

/**
 * Canvas backdrop: a procedurally-drawn tree silhouette filled with
 * Matrix-style cascading green digits, in varying shades. Pure decoration,
 * pointer-events: none, aria-hidden. Respects prefers-reduced-motion.
 *
 * `dimmed` (optional): when true the backdrop fades to ~30% opacity via CSS
 * — used to calm the matrix during a long-running action (e.g. sample
 * import) so the foreground "⏳ Importing…" UI gets visual focus.
 */
export function MatrixTreeBackground({
  className = "fixed inset-0 -z-10 pointer-events-none",
  dimmed = false,
}: { className?: string; dimmed?: boolean }) {
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
    const cell = 14; // CSS px per character
    let cols = 0;
    let rows = 0;
    let mask = new Uint8Array(0);
    let drops: number[] = [];
    let speeds: number[] = [];

    const buildMask = () => {
      cols = Math.floor(W / cell);
      rows = Math.floor(H / cell);
      // Guard against zero-sized canvas — happens when the component mounts
      // before layout (e.g. headless / preview / hidden iframe) or during
      // a transient resize to a 0-px viewport. getImageData on a 0×0 canvas
      // throws IndexSizeError.
      if (cols <= 0 || rows <= 0) {
        mask = new Uint8Array(0);
        drops = [];
        speeds = [];
        return;
      }
      const off = document.createElement("canvas");
      off.width = cols;
      off.height = rows;
      const oc = off.getContext("2d");
      if (!oc) return;
      oc.fillStyle = "white";

      const cx = cols / 2;
      const trunkW = Math.max(3, cols * 0.045);
      const trunkH = rows * 0.22;

      // Trunk
      oc.fillRect(cx - trunkW / 2, rows - trunkH, trunkW, trunkH);

      // Canopy: stacked ovals, pinched top + bottom for an organic blob shape
      const layers = 9;
      for (let i = 0; i < layers; i++) {
        const t = i / (layers - 1);
        const widthScale = Math.sin(Math.PI * (0.18 + 0.7 * t));
        const radius = Math.min(cols, rows) * 0.32 * widthScale;
        const yPos = rows * 0.07 + rows * 0.7 * t;
        oc.beginPath();
        oc.ellipse(cx, yPos, radius, radius * 0.55, 0, 0, Math.PI * 2);
        oc.fill();
      }

      // A few "branch" rectangles peeking out for character
      const branchN = 6;
      for (let b = 0; b < branchN; b++) {
        const t = b / (branchN - 1);
        const angle = Math.PI * (0.85 - 0.7 * t);
        const len = cols * (0.18 + Math.random() * 0.05);
        const x0 = cx;
        const y0 = rows - trunkH * (0.2 + 0.6 * t);
        const x1 = x0 + Math.cos(angle) * len;
        const y1 = y0 - Math.sin(angle) * len;
        oc.strokeStyle = "white";
        oc.lineWidth = Math.max(2, trunkW * 0.4 * (1 - t * 0.5));
        oc.beginPath();
        oc.moveTo(x0, y0);
        oc.lineTo(x1, y1);
        oc.stroke();

        // Mirror to the left
        const x2 = x0 - Math.cos(angle) * len * (0.85 + Math.random() * 0.2);
        const y2 = y0 - Math.sin(angle) * len * (0.9 + Math.random() * 0.1);
        oc.beginPath();
        oc.moveTo(x0, y0);
        oc.lineTo(x2, y2);
        oc.stroke();
      }

      const data = oc.getImageData(0, 0, cols, rows).data;
      mask = new Uint8Array(cols * rows);
      for (let i = 0; i < cols * rows; i++) {
        mask[i] = data[i * 4 + 3] > 64 ? 1 : 0;
      }

      drops = new Array(cols).fill(0).map(() => Math.random() * -rows);
      speeds = new Array(cols).fill(0).map(() => 0.35 + Math.random() * 0.7);
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
      ctx.font = `bold ${cell - 2}px ui-monospace, "Geist Mono", "SF Mono", Menlo, monospace`;
      ctx.textBaseline = "alphabetic";
      // Initial fill is translucent so the layer behind us (NumberTree3D at
      // -z-[25]) bleeds through. The matrix rain still reads as foreground
      // because each digit is drawn at high opacity below.
      ctx.fillStyle = "rgba(2, 9, 7, 0.55)";
      ctx.fillRect(0, 0, W, H);
      buildMask();
    };

    const draw = () => {
      // Trail-fade overlay — light enough that the 3D tree behind stays
      // visible while old characters still fade out smoothly.
      ctx.fillStyle = "rgba(2, 12, 8, 0.05)";
      ctx.fillRect(0, 0, W, H);

      for (let c = 0; c < cols; c++) {
        const py = Math.floor(drops[c]);
        const x = c * cell + cell / 2;

        if (py >= 0 && py < rows && mask[py * cols + c] === 1) {
          const ch = Math.floor(Math.random() * 10).toString();
          // Bright leading character: white-green
          ctx.fillStyle = "rgba(220, 255, 230, 0.95)";
          ctx.fillText(ch, x - cell / 4, py * cell + cell - 2);
        }
        // Mid-tail: a couple of cells back, vary green shade
        const mid = py - 2;
        if (mid >= 0 && mid < rows && mask[mid * cols + c] === 1) {
          const greenShade = 160 + Math.floor(Math.random() * 80);
          ctx.fillStyle = `rgba(40, ${greenShade}, 80, 0.85)`;
          const ch = Math.floor(Math.random() * 10).toString();
          ctx.fillText(ch, x - cell / 4, mid * cell + cell - 2);
        }

        drops[c] += speeds[c];
        if (drops[c] > rows + 30) drops[c] = -Math.random() * 30;
      }

      raf = requestAnimationFrame(draw);
    };

    // Round-4 UX#1 finding: `reduce` was read once on mount. If the
    // operator flipped their OS reduced-motion setting mid-session the
    // rain kept cascading. Capture the MediaQueryList so we can swap
    // behaviour live via the `change` event below.
    const reduceMql = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    let reduce = !!reduceMql?.matches;

    const drawStatic = () => {
      // Static fallback also stays translucent so the 3D tree behind shows.
      ctx.fillStyle = "rgba(2, 9, 7, 0.55)";
      ctx.fillRect(0, 0, W, H);
      for (let c = 0; c < cols; c++) {
        for (let r = 0; r < rows; r++) {
          if (mask[r * cols + c] === 1) {
            const greenShade = 160 + Math.floor(Math.random() * 70);
            ctx.fillStyle = `rgba(40, ${greenShade}, 80, 0.6)`;
            ctx.fillText(
              Math.floor(Math.random() * 10).toString(),
              c * cell + cell / 4,
              r * cell + cell - 2,
            );
          }
        }
      }
    };

    resize();
    window.addEventListener("resize", resize);

    // Pause when tab not visible — battery + CPU.
    const onVisibility = () => {
      if (reduce) return;
      if (document.hidden) {
        if (raf !== 0) { cancelAnimationFrame(raf); raf = 0; }
      } else if (raf === 0) {
        raf = requestAnimationFrame(draw);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    if (reduce) {
      drawStatic();
    } else {
      raf = requestAnimationFrame(draw);
    }

    const onReduceChange = (e: MediaQueryListEvent) => {
      reduce = e.matches;
      if (reduce) {
        if (raf !== 0) { cancelAnimationFrame(raf); raf = 0; }
        drawStatic();
      } else if (raf === 0 && !document.hidden) {
        raf = requestAnimationFrame(draw);
      }
    };
    reduceMql?.addEventListener?.("change", onReduceChange);

    return () => {
      if (raf !== 0) cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibility);
      reduceMql?.removeEventListener?.("change", onReduceChange);
    };
  }, []);

  return (
    <canvas
      ref={ref}
      className={`${className} transition-opacity duration-700 ease-out`}
      style={{ opacity: dimmed ? 0.32 : 1 }}
      aria-hidden
    />
  );
}
