"use client";

/**
 * JoinTypeIcons — horizontal icon-ladder picker for the six join kinds.
 *
 * Replaces the default enum dropdown for the `kind` param when the
 * manifest declares `widget: "join_type_icons"`. Each icon is a small
 * SVG set-diagram showing which rows survive the join — clearer than
 * text labels for new users (the words "left outer" don't convey what
 * happens) and clearer than a Venn diagram for users who already know
 * SQL joins (anti-joins / semi-joins fit naturally as just another
 * configuration of the same two-circle visual).
 */
import type { CSSProperties } from "react";

export type JoinKind =
  | "inner" | "left" | "right" | "full" | "anti_left" | "anti_right";

interface DiagramProps { fill: { left: boolean; right: boolean; both: boolean }; }

/** Two-circle set diagram. We render explicitly which regions are
 *  "kept" vs "discarded" — the `fill` prop maps the three regions
 *  (left-only, right-only, both) to opaque vs faint. */
function SetDiagram({ fill }: DiagramProps) {
  const ON = "currentColor";
  const OFF = "rgb(0 0 0 / 0)";
  // Faint outline always drawn for orientation; fills overlay where
  // the join keeps rows.
  return (
    <svg
      width="32" height="20" viewBox="0 0 32 20"
      aria-hidden
      className="shrink-0"
    >
      {/* Faint outlines */}
      <circle cx="11" cy="10" r="8" fill="none" stroke="currentColor" strokeOpacity="0.35" strokeWidth="1.2" />
      <circle cx="21" cy="10" r="8" fill="none" stroke="currentColor" strokeOpacity="0.35" strokeWidth="1.2" />
      {/* Left-only crescent */}
      <path
        d="M11,2 a8,8 0 1 0 0,16 a8,8 0 0 1 0,-16 z"
        fill={fill.left ? ON : OFF}
        opacity={fill.left ? 0.85 : 0}
        transform="translate(-3 0)"
      />
      {/* Right-only crescent */}
      <path
        d="M21,2 a8,8 0 1 1 0,16 a8,8 0 0 0 0,-16 z"
        fill={fill.right ? ON : OFF}
        opacity={fill.right ? 0.85 : 0}
        transform="translate(3 0)"
      />
      {/* Intersection lens — clip to both circles */}
      {fill.both && (
        <g>
          <defs>
            <clipPath id="lens">
              <circle cx="11" cy="10" r="8" />
            </clipPath>
          </defs>
          <circle
            cx="21" cy="10" r="8"
            fill={ON} opacity="0.85"
            clipPath="url(#lens)"
          />
        </g>
      )}
    </svg>
  );
}

const KINDS: Array<{
  id: JoinKind;
  label: string;
  hint: string;
  fill: { left: boolean; right: boolean; both: boolean };
}> = [
  {
    id: "inner",
    label: "inner",
    hint: "Keep only rows where the keys match on both sides.",
    fill: { left: false, right: false, both: true },
  },
  {
    id: "left",
    label: "left",
    hint: "Keep all rows from the left input. Right columns are NULL where unmatched.",
    fill: { left: true, right: false, both: true },
  },
  {
    id: "right",
    label: "right",
    hint: "Keep all rows from the right input. Left columns are NULL where unmatched.",
    fill: { left: false, right: true, both: true },
  },
  {
    id: "full",
    label: "full",
    hint: "Keep all rows from both inputs. NULLs fill in where unmatched.",
    fill: { left: true, right: true, both: true },
  },
  {
    id: "anti_left",
    label: "anti-L",
    hint: "Rows from the left that did NOT match — set difference (left − right). Useful for finding records missing from the other side.",
    fill: { left: true, right: false, both: false },
  },
  {
    id: "anti_right",
    label: "anti-R",
    hint: "Rows from the right that did NOT match — set difference (right − left).",
    fill: { left: false, right: true, both: false },
  },
];

interface Props {
  value: JoinKind | string;
  onChange: (next: JoinKind) => void;
  disabled?: boolean;
}

export function JoinTypeIcons({ value, onChange, disabled }: Props) {
  return (
    <div
      role="radiogroup"
      aria-label="Join type"
      className="flex flex-wrap gap-1.5"
    >
      {KINDS.map((k) => {
        const selected = value === k.id;
        const style: CSSProperties = selected
          ? { color: "rgb(16 185 129)" }   // emerald-500 to inherit
          : { color: "rgb(107 114 128)" }; // muted gray
        return (
          <button
            key={k.id}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={disabled}
            onClick={() => onChange(k.id)}
            title={k.hint}
            className={[
              "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border text-[11px] font-medium transition-colors",
              selected
                ? "border-emerald-500/70 bg-emerald-50 dark:bg-emerald-900/25 text-emerald-900 dark:text-emerald-100"
                : "border-border hover:border-foreground/30 text-foreground/80",
              disabled && "opacity-50 cursor-not-allowed",
            ].filter(Boolean).join(" ")}
          >
            <span style={style}>
              <SetDiagram fill={k.fill} />
            </span>
            {k.label}
          </button>
        );
      })}
    </div>
  );
}
