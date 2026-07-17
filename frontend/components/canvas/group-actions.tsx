"use client";

/**
 * UI for creating, editing, and deleting node groups.
 *
 * Three pieces in one file because they're tightly coupled:
 *
 *   <GroupActionBar>     Floating bar shown when ≥2 step nodes are
 *                        selected. Offers "Group selected" or, when one
 *                        or more groups already exist, an "Add to
 *                        existing" picker.
 *
 *   <GroupEditPopover>   Inline editor anchored to a group's title chip.
 *                        Fields: name, SLA, warn_at, delete (with confirm).
 *
 *   <DeleteGroupConfirm> Tiny confirmation dialog. Used standalone or
 *                        from inside <GroupEditPopover>.
 */

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";

import type { PipelineDocument } from "@/lib/api/client";

// Local copy of the schema shape — kept thin so we don't have to round-trip
// through OpenAPI types for a UI-only feature.
export interface PipelineGroup {
  id: string;
  label: string;
  node_ids: string[];
  ui?: {
    color?: string | null;
    collapsed?: boolean;
    freshness?: { sla: string; warn_at?: string | null } | null;
  };
}

function genGroupId(): string {
  return `g_${Math.random().toString(36).slice(2, 10)}`;
}

// ---- selection-aware floating action bar -------------------------------

interface ActionBarProps {
  selectedNodeIds: string[];
  groups: PipelineGroup[];
  onCreateGroup: (label: string, nodeIds: string[]) => void;
  onAddToGroup: (groupId: string, nodeIds: string[]) => void;
  onClearSelection: () => void;
}

export function GroupActionBar({
  selectedNodeIds,
  groups,
  onCreateGroup,
  onAddToGroup,
  onClearSelection,
}: ActionBarProps) {
  const [creating, setCreating] = useState(false);
  const [draftLabel, setDraftLabel] = useState("");
  const [pickingExisting, setPickingExisting] = useState(false);

  const visible = selectedNodeIds.length >= 2;

  // Reset draft state when the bar disappears.
  useEffect(() => {
    if (!visible) {
      setCreating(false);
      setPickingExisting(false);
      setDraftLabel("");
    }
  }, [visible]);

  // Filter to groups that DON'T already contain all selected nodes —
  // adding 0 new nodes to a group is a no-op and we hide it from the
  // picker.
  const addableGroups = groups.filter((g) =>
    selectedNodeIds.some((id) => !g.node_ids.includes(id)),
  );

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 8 }}
          transition={{ type: "spring", stiffness: 360, damping: 28 }}
          className={[
            "absolute left-1/2 -translate-x-1/2 bottom-6 z-30",
            "rounded-full border border-border bg-card shadow-lg px-2 py-1.5",
            "flex items-center gap-1 text-xs",
          ].join(" ")}
        >
          <span className="px-2 text-muted-foreground tabular-nums">
            {selectedNodeIds.length} selected
          </span>
          {!creating && !pickingExisting && (
            <>
              <button
                type="button"
                onClick={() => setCreating(true)}
                className="px-3 py-1 rounded-full bg-emerald-600 hover:bg-emerald-700 text-white font-medium transition-colors"
              >
                📦 Group selected
              </button>
              {addableGroups.length > 0 && (
                <button
                  type="button"
                  onClick={() => setPickingExisting(true)}
                  className="px-2 py-1 rounded-full hover:bg-muted text-foreground/80 transition-colors"
                >
                  Add to ▾
                </button>
              )}
              <button
                type="button"
                onClick={onClearSelection}
                aria-label="Clear selection"
                className="px-2 py-1 rounded-full hover:bg-muted text-muted-foreground transition-colors"
              >
                ✕
              </button>
            </>
          )}
          {creating && (
            <form
              className="flex items-center gap-1 px-1"
              onSubmit={(e) => {
                e.preventDefault();
                const label = draftLabel.trim() || "New group";
                onCreateGroup(label, selectedNodeIds);
                setCreating(false);
                setDraftLabel("");
              }}
            >
              <input
                autoFocus
                type="text"
                value={draftLabel}
                onChange={(e) => setDraftLabel(e.target.value)}
                placeholder="Group name…"
                className="px-2 py-1 rounded bg-muted/40 border border-border focus:outline-none focus:ring-2 focus:ring-emerald-400/50 w-44"
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    setCreating(false);
                    setDraftLabel("");
                  }
                }}
              />
              <button
                type="submit"
                className="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-medium transition-colors"
              >
                Create
              </button>
              <button
                type="button"
                onClick={() => {
                  setCreating(false);
                  setDraftLabel("");
                }}
                className="px-2 py-1 rounded hover:bg-muted text-muted-foreground transition-colors"
              >
                Cancel
              </button>
            </form>
          )}
          {pickingExisting && (
            <div className="flex items-center gap-1 px-1">
              <select
                autoFocus
                onChange={(e) => {
                  const gid = e.target.value;
                  if (gid) {
                    onAddToGroup(gid, selectedNodeIds);
                    setPickingExisting(false);
                  }
                }}
                defaultValue=""
                className="px-2 py-1 rounded bg-muted/40 border border-border text-foreground focus:outline-none focus:ring-2 focus:ring-emerald-400/50"
              >
                <option value="" disabled>
                  Pick a group…
                </option>
                {addableGroups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.label} ({g.node_ids.length})
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => setPickingExisting(false)}
                className="px-2 py-1 rounded hover:bg-muted text-muted-foreground transition-colors"
              >
                Cancel
              </button>
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// ---- group-edit popover -----------------------------------------------

interface EditProps {
  group: PipelineGroup;
  anchor: { x: number; y: number };
  onSave: (next: PipelineGroup) => void;
  onDelete: () => void;
  onClose: () => void;
}

export function GroupEditPopover({
  group,
  anchor,
  onSave,
  onDelete,
  onClose,
}: EditProps) {
  const [label, setLabel] = useState(group.label);
  const [sla, setSla] = useState(group.ui?.freshness?.sla ?? "");
  const [warnAt, setWarnAt] = useState(group.ui?.freshness?.warn_at ?? "");
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Close on outside click + escape. setTimeout prevents the click that
  // OPENED the popover from immediately closing it.
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      const t = e.target as HTMLElement | null;
      if (t?.closest("[data-group-edit-popover]")) return;
      onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const t = setTimeout(() => {
      window.addEventListener("mousedown", onClick);
    }, 0);
    window.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(t);
      window.removeEventListener("mousedown", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const POP_W = 320;
  const left =
    typeof window !== "undefined"
      ? Math.max(8, Math.min(anchor.x, window.innerWidth - POP_W - 8))
      : anchor.x;
  const top = Math.max(8, anchor.y);

  const save = () => {
    const cleanedSla = sla.trim();
    const cleanedWarn = warnAt.trim();
    const next: PipelineGroup = {
      ...group,
      label: label.trim() || group.label,
      ui: {
        ...(group.ui ?? {}),
        freshness: cleanedSla
          ? { sla: cleanedSla, warn_at: cleanedWarn || null }
          : null,
      },
    };
    onSave(next);
    onClose();
  };

  return (
    <motion.div
      data-group-edit-popover
      initial={{ opacity: 0, y: -4, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ type: "spring", stiffness: 320, damping: 26 }}
      style={{
        position: "fixed",
        left,
        top,
        width: POP_W,
      }}
      role="dialog"
      aria-label={`Edit group ${group.label}`}
      className="z-50 rounded-lg border border-border bg-popover text-popover-foreground shadow-xl p-4 text-xs"
    >
      <div className="flex items-center gap-2 mb-3">
        <span className="text-base" aria-hidden>
          📦
        </span>
        <p className="font-semibold text-sm">Edit group</p>
        <span className="text-[10px] text-muted-foreground tabular-nums ml-auto">
          {group.node_ids.length}{" "}
          {group.node_ids.length === 1 ? "node" : "nodes"}
        </span>
      </div>

      <div className="space-y-3">
        <Field label="Name">
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            className="w-full px-2 py-1.5 rounded border border-border bg-background focus:outline-none focus:ring-2 focus:ring-emerald-400/50"
            onKeyDown={(e) => {
              if (e.key === "Enter") save();
            }}
          />
        </Field>

        <div>
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1.5 font-mono">
            Freshness SLA (optional)
          </p>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Stale after" hint="halo turns 🔴 red">
              <input
                type="text"
                value={sla}
                onChange={(e) => setSla(e.target.value)}
                placeholder="2h"
                className="w-full px-2 py-1.5 rounded border border-border bg-background focus:outline-none focus:ring-2 focus:ring-emerald-400/50"
              />
            </Field>
            <Field
              label="Warn before stale"
              hint="halo turns 🟡 amber"
            >
              <input
                type="text"
                value={warnAt}
                onChange={(e) => setWarnAt(e.target.value)}
                placeholder="30m"
                disabled={!sla.trim()}
                className="w-full px-2 py-1.5 rounded border border-border bg-background focus:outline-none focus:ring-2 focus:ring-emerald-400/50 disabled:opacity-50"
              />
            </Field>
          </div>
          {/* Worked example so the meaning is unambiguous. The visual
              gradient bar drives the point home: green block, then
              amber window, then red. */}
          <div className="mt-2.5 rounded bg-muted/30 border border-border/60 p-2 text-[10px] leading-relaxed">
            <div className="flex items-center gap-1 mb-1.5">
              <span className="font-mono text-muted-foreground">Reads as:</span>
              {sla.trim() ? (
                <span>
                  fresh up to{" "}
                  <code className="bg-background/60 px-1 rounded">{sla.trim()}</code>
                  {warnAt.trim() && (
                    <>
                      {" "}· amber in the last{" "}
                      <code className="bg-background/60 px-1 rounded">{warnAt.trim()}</code>
                      {" "}before that
                    </>
                  )}
                  · red after
                </span>
              ) : (
                <span className="text-muted-foreground">leave blank to use member-aggregated freshness only</span>
              )}
            </div>
            {sla.trim() && (
              <div className="flex h-1.5 rounded overflow-hidden">
                <div className="flex-1 bg-emerald-400/70" title="fresh" />
                {warnAt.trim() && (
                  <div className="w-1/4 bg-amber-400/70" title="amber" />
                )}
                <div className="w-px bg-rose-500/80" title="stale threshold" />
                <div className="w-2 bg-rose-500/40" title="stale" />
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between gap-2 pt-3 border-t border-border">
        <button
          type="button"
          onClick={() => setConfirmDelete(true)}
          className="text-[11px] px-2 py-1 rounded text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-colors"
        >
          🗑 Delete group
        </button>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onClose}
            className="text-[11px] px-3 py-1 rounded hover:bg-muted text-muted-foreground transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={save}
            className="text-[11px] px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-medium transition-colors"
          >
            Save
          </button>
        </div>
      </div>

      <AnimatePresence>
        {confirmDelete && (
          <DeleteGroupConfirm
            group={group}
            onCancel={() => setConfirmDelete(false)}
            onConfirm={() => {
              setConfirmDelete(false);
              onDelete();
              onClose();
            }}
          />
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground font-mono">
        {label}
      </span>
      {children}
      {hint && (
        <span className="block text-[10px] text-muted-foreground/70 mt-0.5 font-mono">
          {hint}
        </span>
      )}
    </label>
  );
}

// ---- delete confirmation dialog --------------------------------------

function DeleteGroupConfirm({
  group,
  onCancel,
  onConfirm,
}: {
  group: PipelineGroup;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="absolute inset-0 rounded-lg bg-card flex items-center justify-center p-4"
      onClick={(e) => e.stopPropagation()}
    >
      <motion.div
        initial={{ scale: 0.92, y: 4 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.96, opacity: 0 }}
        transition={{ type: "spring", stiffness: 360, damping: 28 }}
        className="text-xs"
      >
        <p className="font-semibold text-sm mb-2">
          Delete &quot;{group.label}&quot;?
        </p>
        <p className="text-muted-foreground leading-snug">
          The {group.node_ids.length}{" "}
          {group.node_ids.length === 1 ? "node" : "nodes"} stay in the
          pipeline — they just stop being grouped. Their data is unchanged.
        </p>
        <div className="mt-4 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1.5 rounded hover:bg-muted text-muted-foreground transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="px-3 py-1.5 rounded bg-rose-600 hover:bg-rose-700 text-white font-medium transition-colors"
          >
            🗑 Delete group
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ---- helpers for membership math --------------------------------------

/** Recompute group membership after a drag-end: a node is "inside" a
 *  group if its center falls within the group's current bbox. The group
 *  bbox is what buildGraph() computed last render. Returns a new
 *  groups[] with adds/removes applied. */
export function applyDragEndMembership(
  groups: PipelineGroup[],
  movedNodeId: string,
  movedNodeCenter: { x: number; y: number },
  groupBboxes: Record<string, { x: number; y: number; w: number; h: number }>,
): PipelineGroup[] {
  let touched = false;
  const next = groups.map((g) => {
    const bbox = groupBboxes[g.id];
    if (!bbox) return g;
    const inside =
      movedNodeCenter.x >= bbox.x &&
      movedNodeCenter.x <= bbox.x + bbox.w &&
      movedNodeCenter.y >= bbox.y &&
      movedNodeCenter.y <= bbox.y + bbox.h;
    const wasMember = g.node_ids.includes(movedNodeId);
    if (inside && !wasMember) {
      touched = true;
      return { ...g, node_ids: [...g.node_ids, movedNodeId] };
    }
    if (!inside && wasMember) {
      touched = true;
      return {
        ...g,
        node_ids: g.node_ids.filter((id) => id !== movedNodeId),
      };
    }
    return g;
  });
  return touched ? next : groups;
}

/** Add a node to a group's node_ids if not already present. */
export function addToGroup(
  groups: PipelineGroup[],
  groupId: string,
  nodeIds: string[],
): PipelineGroup[] {
  return groups.map((g) =>
    g.id === groupId
      ? {
          ...g,
          node_ids: Array.from(new Set([...g.node_ids, ...nodeIds])),
        }
      : g,
  );
}

/** Remove a node from a group's node_ids. */
export function removeFromGroup(
  groups: PipelineGroup[],
  groupId: string,
  nodeId: string,
): PipelineGroup[] {
  return groups.map((g) =>
    g.id === groupId
      ? { ...g, node_ids: g.node_ids.filter((id) => id !== nodeId) }
      : g,
  );
}

/** Build a fresh group from the selection. */
export function makeGroupFromSelection(
  label: string,
  nodeIds: string[],
): PipelineGroup {
  return {
    id: genGroupId(),
    label,
    node_ids: nodeIds,
    ui: { collapsed: false },
  };
}

/** Apply group changes to the pipeline document. Tolerates docs with no
 *  groups field (older pipelines that predate group support). */
export function patchGroups(
  doc: PipelineDocument,
  groups: PipelineGroup[],
): PipelineDocument {
  return { ...doc, groups } as PipelineDocument;
}
