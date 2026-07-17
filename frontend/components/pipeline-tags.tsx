"use client";

/**
 * Pipeline tag editor.
 *
 * Compact chip-strip in the pipeline editor toolbar. Shows current
 * tags + lets the user add / remove. Persists via the
 * `/search/pipelines/{id}/tags` endpoint.
 *
 * Layout policy: stays on a single row. Earlier versions used
 * `flex-wrap` and the chips would stack vertically when the header
 * got squeezed (e.g. a pipeline with 4 tags + "Save / Save As / undo
 * / redo / Add dataset / Run" buttons), which broke the header's
 * vertical alignment and pushed everything below the fold. Now we
 * cap visible chips at ``MAX_VISIBLE`` and roll the rest into a
 * "+N" pill that expands on click.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { toast } from "sonner";
import { searchApi } from "@/lib/api/client";

interface Props {
  pipelineId: string;
  initialTags: string[];
  onChange?: (tags: string[]) => void;
  /**
   * Current pipeline etag — sent as If-Match on the tag PUT so the
   * backend rejects the call if another writer (autosave, another tab)
   * modified the pipeline. The parent passes the live etag from its
   * useState; without this, a tag-edit can race with autosave and
   * silently lose either side's changes (round-3 QA finding).
   */
  etag?: number | null;
}

// Hard cap on inline chips before the overflow pill takes over. Three is
// the right number for a typical demo / project / domain trio; four
// already crowds the header on a 13" laptop with the params panel open.
const MAX_VISIBLE = 3;

export function PipelineTags({ pipelineId, initialTags, onChange, etag }: Props) {
  const [tags, setTags] = useState<string[]>(initialTags);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState("");
  const [allTags, setAllTags] = useState<string[]>([]);
  const [expanded, setExpanded] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  // Wraps both the +N pill and the popover. Used by the click-outside
  // handler so a click on the PILL itself doesn't fire the close path
  // — without this, capture-phase mousedown closes the popover, then
  // the pill's onClick re-opens it (popover never actually closes).
  const wrapperRef = useRef<HTMLDivElement>(null);

  // Tags split into "visible" (inline) and "hidden" (behind overflow pill).
  // When the user clicks the +N pill, ``expanded`` flips and the popover
  // shows every tag at once. Two-trip render keeps the closed-state header
  // single-row regardless of tag count.
  const { visible, hidden } = useMemo(() => {
    if (tags.length <= MAX_VISIBLE) {
      return { visible: tags, hidden: [] as string[] };
    }
    return {
      visible: tags.slice(0, MAX_VISIBLE),
      hidden: tags.slice(MAX_VISIBLE),
    };
  }, [tags]);

  // Click-outside dismiss for the overflow popover. The check uses
  // ``wrapperRef`` (which contains BOTH the pill and the popover) so that
  // a click on the pill itself doesn't trigger the close path. Earlier
  // versions checked only ``popoverRef``, which closed on every pill
  // click; the pill's own ``onClick`` then re-opened it on the same
  // event, leaving the popover stuck open.
  useEffect(() => {
    if (!expanded) return;
    const onDoc = (e: MouseEvent) => {
      if (!wrapperRef.current) return;
      if (wrapperRef.current.contains(e.target as Node)) return;
      setExpanded(false);
    };
    window.addEventListener("mousedown", onDoc, true);
    return () => window.removeEventListener("mousedown", onDoc, true);
  }, [expanded]);

  // Sync incoming changes (e.g. after a doc reload).
  useEffect(() => setTags(initialTags), [initialTags]);

  // Pre-load all known tags for autocomplete suggestions when adding.
  useEffect(() => {
    if (!adding) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await searchApi.listTags();
        if (!cancelled) setAllTags(res.tags);
      } catch {
        /* autocomplete is a nice-to-have; failure is non-fatal */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [adding]);

  // Auto-focus the input when entering add-mode.
  useEffect(() => {
    if (adding) inputRef.current?.focus();
  }, [adding]);

  const persist = async (next: string[]) => {
    try {
      const res = await searchApi.setPipelineTags(pipelineId, next, etag);
      setTags(res.tags);
      onChange?.(res.tags);
    } catch (e) {
      toast.error(`Tag save failed: ${(e as Error).message}`);
    }
  };

  const addTag = (raw: string) => {
    // Round-3 QA finding: pasting "demo, housing, geo" used to fail the
    // single-tag regex and silently reject. Now we split on commas /
    // semicolons / whitespace, normalise each piece, drop dupes, and
    // persist them as a single batch (one PUT instead of N).
    const pieces = raw
      .split(/[,;\s]+/)
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);
    if (pieces.length === 0) return;

    const accepted: string[] = [];
    const rejected: string[] = [];
    const existing = new Set(tags);
    for (const p of pieces) {
      if (!/^[a-z0-9_-]+$/.test(p)) {
        rejected.push(p);
        continue;
      }
      if (existing.has(p) || accepted.includes(p)) continue;
      accepted.push(p);
    }
    if (rejected.length) {
      toast.error(
        `Tags must be alphanumeric, dashes, or underscores — rejected: ${rejected.slice(0, 5).join(", ")}${rejected.length > 5 ? `, +${rejected.length - 5} more` : ""}`,
      );
    }
    if (accepted.length) {
      persist([...tags, ...accepted]);
    }
    setDraft("");
  };

  const removeTag = (t: string) => {
    persist(tags.filter((x) => x !== t));
  };

  // Filter known tags by what the user has typed (case-insensitive
  // prefix); skip ones already applied.
  const suggestions = allTags
    .filter((t) => t.startsWith(draft.toLowerCase()) && !tags.includes(t))
    .slice(0, 5);

  // Single chip render — used for both inline + popover. Pulled into a
  // local fn so the popover renders identical-looking chips, including
  // the inline remove ✕.
  const renderChip = (t: string) => (
    <motion.span
      key={t}
      initial={{ opacity: 0, scale: 0.92 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.92 }}
      transition={{ duration: 0.15 }}
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-200 border border-emerald-300/60 dark:border-emerald-800 whitespace-nowrap shrink-0 max-w-[140px]"
      title={t}
    >
      <span aria-hidden>🏷</span>
      <span className="truncate">{t}</span>
      <button
        type="button"
        onClick={() => removeTag(t)}
        title={`Remove tag "${t}"`}
        // Round-3 UX/a11y finding: the previous ✕ button measured ≈ 8×17px,
        // failing WCAG 2.5.5 Target Size (AA = 24×24, AAA = 44×44). The
        // emoji glyph itself stays ✕ but we expand the tap area via
        // padding + min-width/height to 24×24 minimum. Negative margin
        // keeps the chip's visual height unchanged so the header still
        // fits a single row.
        className="ml-0.5 -my-1 inline-flex items-center justify-center min-w-[24px] min-h-[24px] rounded text-emerald-600 dark:text-emerald-400 hover:text-emerald-900 hover:bg-emerald-100/40 dark:hover:text-emerald-100 dark:hover:bg-emerald-900/30 shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60"
        aria-label={`Remove tag ${t}`}
      >
        ✕
      </button>
    </motion.span>
  );

  return (
    // ``flex-nowrap`` keeps every chip on the header's single row even
    // when the available width is tight. ``shrink-0`` is critical: an
    // earlier version used ``min-w-0`` to allow the wrapper to shrink
    // below its content width, but flexbox combined that with
    // ``flex-shrink: 1`` (default) and collapsed the wrapper to **zero
    // width** when the header was crowded. The chips still rendered
    // (since the inner items are ``shrink-0``) but they leaked
    // out of a zero-wide parent and the next flex sibling (💾 Save)
    // took the wrapper's start coordinate as its own — so the Save
    // button ended up *underneath* the tag chips visually. ``shrink-0``
    // makes the wrapper claim its natural content width and forces the
    // other flex items to absorb any shrinkage instead. Cap with the
    // overflow pill (MAX_VISIBLE) so the natural width stays bounded.
    <div ref={wrapperRef} className="flex items-center gap-1.5 flex-nowrap shrink-0 relative">
      <AnimatePresence initial={false}>
        {visible.map((t) => renderChip(t))}
      </AnimatePresence>
      {hidden.length > 0 && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          title={`Show ${hidden.length} more tag${hidden.length === 1 ? "" : "s"}: ${hidden.join(", ")}`}
          className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] bg-muted/60 hover:bg-muted text-muted-foreground border border-border whitespace-nowrap shrink-0"
        >
          +{hidden.length}
        </button>
      )}
      {expanded && hidden.length > 0 && (
        <div
          ref={popoverRef}
          className="absolute top-full left-0 mt-1 z-30 bg-popover border border-border rounded-md shadow-lg p-2 flex flex-wrap gap-1 max-w-[320px]"
        >
          <AnimatePresence initial={false}>
            {hidden.map((t) => renderChip(t))}
          </AnimatePresence>
        </div>
      )}
      {adding ? (
        <div className="relative">
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => {
              // 120ms grace to allow suggestion clicks to fire BEFORE
              // we close the input.
              setTimeout(() => {
                addTag(draft);
                setAdding(false);
              }, 120);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                addTag(draft);
                setAdding(false);
              } else if (e.key === "Escape") {
                setDraft("");
                setAdding(false);
              }
            }}
            placeholder="tag…"
            className="text-[11px] px-2 py-0.5 rounded-full bg-card border border-border outline-none focus:border-emerald-400 w-[100px]"
          />
          {suggestions.length > 0 && draft.length > 0 && (
            <div className="absolute top-full left-0 mt-1 z-30 bg-popover border border-border rounded shadow-lg min-w-[120px] py-1">
              {suggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    addTag(s);
                    setAdding(false);
                  }}
                  className="block w-full text-left text-[11px] px-2 py-1 hover:bg-muted"
                >
                  #{s}
                </button>
              ))}
            </div>
          )}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setAdding(true)}
          title="Add a tag — used for workspace search and the catalog filter"
          className="text-[11px] px-2 py-0.5 rounded-full text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        >
          + tag
        </button>
      )}
    </div>
  );
}
