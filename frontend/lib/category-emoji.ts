/**
 * Single source of truth for category emojis used across the editor
 * surfaces (canvas nodes, pipeline strip, quick-add menu, step library).
 *
 * Round-8 fix: previously four separate files maintained their own
 * copy of this map and they had drifted — ``derive`` rendered as ➕ in
 * pipeline-strip and StepNode but 🧮 in quick-add-menu, and the strip
 * was missing entries for ``analyze`` / ``validate`` / ``visualize``
 * entirely so those categories fell back to 🧩.
 *
 * Keep in sync with backend ``CATEGORY_LABELS`` in
 * ``scripts/gen-steps-doc.py``.
 */
export const CATEGORY_EMOJI: Record<string, string> = {
  ingest:    "📥",
  shape:     "✂️",
  clean:     "🧼",
  derive:    "🧮",
  combine:   "🤝",
  aggregate: "📊",
  analyze:   "🔬",
  model:     "🧠",
  validate:  "✅",
  visualize: "📈",
  output:    "📤",
  custom:    "🧩",
};

export function categoryEmoji(category: string | undefined): string {
  return CATEGORY_EMOJI[category ?? "custom"] ?? "🧩";
}
