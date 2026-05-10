"use client";

import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";

/**
 * Positive, perception-magic loading state for any in-progress
 * computation in the editor.
 *
 * UX principles applied (Don Norman / Steven Hoober / NN/g RAIL):
 *
 *   1. **No error language.** This is a normal in-progress state, not
 *      a failure. The visual stays warm — never red, yellow, ⚠.
 *   2. **Animated focal point** — emoji rotation gives the eye
 *      something to track before any text registers.
 *   3. **Layered text staircase** matched to the RAIL latency
 *      thresholds (Doherty ~400ms / Response ~2s / Patience ~8s):
 *        - Always: primary line ("Computing…").
 *        - After 1s: elapsed-seconds counter (numbers help patience).
 *        - After 2s: a tip about why it might take a moment.
 *        - After 8s: a longer-task tip with a way to recover.
 *   4. **Indeterminate shimmer** — communicates "we're working" without
 *      lying about completion %. Avoids the false-progress antipattern.
 *   5. **Reduced-motion respected** — when the OS asks for it, we
 *      collapse to a static icon + text.
 *
 * Three preset variants cover the editor's loading needs:
 *
 *   - ``computing``  → 🔬 🧮 ✨   "Computing chart…"  (Polars step → image)
 *   - ``rendering``  → 🔎 ⚙ ✨   "Loading data…"     (any tabular preview)
 *   - ``compiling``  → 🛠 🔌 ⚙   "Compiling…"        (SQL compile path)
 *   - ``thinking``   → ✨ 💭 🧠 🪄  "Thinking…"        (AI / LLM round-trip)
 *
 * Every AI feature in DIG uses ``thinking`` — that's the agreed
 * "we're waiting for the model" affordance. Don't roll your own
 * `animate-pulse` emoji span; it's noisy across the app.
 */
type Variant = "computing" | "rendering" | "compiling" | "thinking";

const PRESETS: Record<
  Variant,
  { emoji: readonly string[]; primary: string; tipShort: string; tipLong: string }
> = {
  computing: {
    emoji: ["🔬", "🧮", "✨"],
    primary: "Computing…",
    tipShort: "First call after a fresh reload can take a moment to warm up.",
    tipLong:
      "Sampling a wide window — backing off to a smaller sample helps.",
  },
  rendering: {
    emoji: ["🔎", "⚙", "✨"],
    primary: "Loading data…",
    tipShort:
      "Routing to the backend for this step — usually under a second.",
    tipLong:
      "If this hangs, check the API status (top-right) and retry.",
  },
  compiling: {
    emoji: ["🛠", "🔌", "⚙"],
    primary: "Compiling…",
    tipShort: "Resolving the DAG and validating params.",
    tipLong:
      "Long compiles usually mean a heavy schema-inference step — try focusing earlier in the chain.",
  },
  thinking: {
    emoji: ["✨", "💭", "🧠", "🪄"],
    primary: "Thinking…",
    tipShort: "Calling the configured AI model — usually 2–5 seconds.",
    tipLong:
      "The model is taking longer than usual — local Ollama models warm up slowly on a cold start. Hang tight, or check Settings → AI.",
  },
};

/**
 * Bar gradient per variant. AI features get a violet→fuchsia shimmer
 * (matches the rest of DIG's "AI surface" colour) so it reads as
 * "model thinking" instead of generic "page loading".
 */
const SHIMMER_BAR_CLS: Record<Variant, string> = {
  computing: "bg-emerald-400/60",
  rendering: "bg-emerald-400/60",
  compiling: "bg-emerald-400/60",
  thinking: "bg-gradient-to-r from-violet-400/70 via-fuchsia-400/70 to-emerald-400/70",
};

export function PositiveLoader({
  variant = "computing",
  primary,
  size = "md",
  showTimer = true,
  showShimmer = true,
}: {
  variant?: Variant;
  /** Override the default primary text for the variant. */
  primary?: string;
  size?: "sm" | "md" | "lg";
  showTimer?: boolean;
  showShimmer?: boolean;
}) {
  const preset = PRESETS[variant];
  const [tickIdx, setTickIdx] = useState(0);
  const [elapsedS, setElapsedS] = useState(0);
  const startedAt = useRef(Date.now());
  const reduce = useReducedMotion();

  useEffect(() => {
    if (reduce) return;
    const i = setInterval(() => setTickIdx((n) => (n + 1) % preset.emoji.length), 700);
    return () => clearInterval(i);
  }, [reduce, preset.emoji.length]);
  useEffect(() => {
    if (!showTimer) return;
    const i = setInterval(() => {
      setElapsedS(Math.floor((Date.now() - startedAt.current) / 1000));
    }, 200);
    return () => clearInterval(i);
  }, [showTimer]);

  const tip = elapsedS >= 8 ? preset.tipLong : elapsedS >= 2 ? preset.tipShort : null;

  const cls = {
    emoji: size === "sm" ? "text-2xl" : size === "lg" ? "text-6xl" : "text-5xl",
    primary: size === "sm" ? "text-xs" : size === "lg" ? "text-base" : "text-sm",
    timer: size === "sm" ? "text-[10px]" : "text-[11px]",
    tip: size === "sm" ? "text-[10px]" : "text-[11px]",
    shimmerW: size === "sm" ? "w-32" : size === "lg" ? "w-64" : "w-48",
    gap: size === "sm" ? "gap-1.5" : "gap-3",
  };

  return (
    <div
      className={`flex flex-col items-center ${cls.gap} text-muted-foreground select-none`}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <motion.div
        key={preset.emoji[tickIdx]}
        initial={reduce ? false : { scale: 0.85, opacity: 0 }}
        animate={
          reduce
            ? { scale: 1, opacity: 1 }
            : variant === "thinking"
            ? {
                // AI: continuous gentle wobble + scale breath between
                // emoji-cycle ticks so the sparkle feels "alive" even
                // mid-tick.
                scale: [1, 1.08, 1],
                rotate: [0, -8, 8, 0],
                opacity: 1,
              }
            : { scale: 1, opacity: 1 }
        }
        exit={reduce ? undefined : { scale: 0.85, opacity: 0 }}
        transition={
          variant === "thinking"
            ? { duration: 1.1, repeat: Infinity, ease: "easeInOut" }
            : { type: "spring", stiffness: 360, damping: 22 }
        }
        className={cls.emoji}
        aria-hidden
      >
        {preset.emoji[tickIdx]}
      </motion.div>
      <div className="text-center">
        <p className={`${cls.primary} font-medium text-foreground`}>{primary ?? preset.primary}</p>
        {showTimer && (
          <p className={`${cls.timer} mt-0.5 tabular-nums`}>
            {elapsedS >= 1 ? `${elapsedS}s elapsed` : "preparing"}
          </p>
        )}
      </div>
      {showShimmer && (
        <div className={`${cls.shimmerW} h-[3px] bg-muted/60 rounded-full overflow-hidden`}>
          {!reduce && (
            <motion.div
              className={`h-full w-1/3 rounded-full ${SHIMMER_BAR_CLS[variant]}`}
              initial={{ x: "-100%" }}
              animate={{ x: "200%" }}
              transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
            />
          )}
        </div>
      )}
      {tip && (
        <p className={`${cls.tip} text-muted-foreground/70 italic max-w-xs text-center leading-snug`}>
          💡 {tip}
        </p>
      )}
    </div>
  );
}

/**
 * Inline / compact variant — single line, just the rotating emoji + text,
 * no timer or shimmer. Use for banner-style loading badges (e.g. the
 * grid's "recomputing…" indicator).
 */
export function PositiveLoaderInline({
  variant = "rendering",
  text,
  /** Visual size — AI thinking banners often want `sm`-but-readable
   *  text; default keeps the original 10px badge size for non-AI
   *  consumers. */
  size = "xs",
}: {
  variant?: Variant;
  text?: string;
  size?: "xs" | "sm";
}) {
  const preset = PRESETS[variant];
  const [tickIdx, setTickIdx] = useState(0);
  const reduce = useReducedMotion();
  useEffect(() => {
    if (reduce) return;
    const i = setInterval(() => setTickIdx((n) => (n + 1) % preset.emoji.length), 700);
    return () => clearInterval(i);
  }, [reduce, preset.emoji.length]);
  const textCls = size === "sm" ? "text-xs" : "text-[10px]";
  return (
    <span
      className={`inline-flex items-center gap-1.5 ${textCls} text-muted-foreground`}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <motion.span
        key={preset.emoji[tickIdx]}
        initial={reduce ? false : { scale: 0.85, opacity: 0 }}
        animate={
          reduce
            ? { scale: 1, opacity: 1 }
            : variant === "thinking"
            ? {
                scale: [1, 1.15, 1],
                rotate: [0, -10, 10, 0],
                opacity: 1,
              }
            : { scale: 1, opacity: 1 }
        }
        transition={
          variant === "thinking"
            ? { duration: 1.1, repeat: Infinity, ease: "easeInOut" }
            : { type: "spring", stiffness: 360, damping: 22 }
        }
        className="inline-block"
        aria-hidden
      >
        {preset.emoji[tickIdx]}
      </motion.span>
      <span>{text ?? preset.primary}</span>
      {/* Tiny travelling-shimmer dot specifically for AI thinking
          (replaces the static `…` ellipsis with motion the eye can
          actually track without being distracting). */}
      {variant === "thinking" && !reduce && (
        <span
          className="inline-block w-6 h-[2px] bg-muted/60 rounded-full overflow-hidden align-middle"
          aria-hidden
        >
          <motion.span
            className="block h-full w-1/2 rounded-full bg-gradient-to-r from-violet-400/70 to-fuchsia-400/70"
            initial={{ x: "-100%" }}
            animate={{ x: "200%" }}
            transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
          />
        </span>
      )}
    </span>
  );
}

/**
 * Tiny pre-built button-label for AI mutations. Replaces the
 * common `⏳ Asking…` static pattern. Use inline:
 *
 *     <Button disabled={ask.isPending}>
 *       {ask.isPending ? <ThinkingLabel text="Asking…" /> : "✨ Suggest fix"}
 *     </Button>
 *
 * The animated emoji + travelling-shimmer ellipsis tells the user
 * the click registered AND something is happening. ⏳ alone is
 * static and reads as "frozen UI".
 */
export function ThinkingLabel({ text = "Thinking…" }: { text?: string }) {
  return <PositiveLoaderInline variant="thinking" text={text} />;
}
