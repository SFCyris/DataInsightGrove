"use client";

/**
 * JoinPanel — top-level join params surface.
 *
 * Wires the six widgets together:
 *
 *   ┌─ InputsPanel                          (which datasets/steps feed l/r)
 *   ├─ CardinalityStrip                     (row-count consequences)
 *   ├─ JoinTypeIcons                        (`kind`)
 *   ├─ JoinKeysBuilder                      (`keys`)
 *   ├─ ColumnCollisionsPanel                (renders only on collisions)
 *   └─ ResultColumnsPanel                   (provenance + include/rename)
 *
 * Param-form's default rendering is replaced for the join step
 * entirely — see param-form.tsx's per-manifest-id branch. This is
 * the only step in DIG that gets a bespoke panel layout, justified
 * by the design doc's "joins are the highest-stakes UX surface" call.
 */
import { useMemo } from "react";
import { JoinTypeIcons, type JoinKind } from "./join-type-icons";
import { JoinKeysBuilder, type JoinKey } from "./join-keys-builder";
import { CardinalityStrip } from "./cardinality-strip";
import { ColumnCollisionsPanel } from "./column-collisions-panel";
import { ResultColumnsPanel, type OutputColumnsValue } from "./result-columns-panel";
import { InputsPanel, type EligibleSource } from "./inputs-panel";
import { useJoinSamples } from "./use-samples";
import { cardinalityEstimate } from "./match-quality";

type CollisionRule = "keep_both" | "keep_left" | "keep_right" | "coalesce";

export interface JoinPanelProps {
  pipelineId: string;
  /** Pipeline etag — bumps on save; we key sample queries on it. */
  etag: number;
  /** The focused join node's full param map (so this widget owns the
   *  canonical mapping between internal value shape and the param doc). */
  params: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  /** Upstream node id wired to the `left` port (or null if unwired). */
  leftRef: string | null | undefined;
  /** Upstream node id wired to the `right` port. */
  rightRef: string | null | undefined;
  /** Datasets + non-descendant nodes the user can pick as inputs. */
  eligibleSources: EligibleSource[];
  /** Rewire one port. Owner of the callback decides terminal-mutate
   *  vs. mid-chain-branch and surfaces a toast in the branch case. */
  onSetInputRef?: (port: string, newRef: string) => void;
  /** Flip left ↔ right (also swaps keys, suffixes, kind, output renames). */
  onSwapSides?: () => void;
}

export function JoinPanel({
  pipelineId, etag, params, onChange, leftRef, rightRef,
  eligibleSources, onSetInputRef, onSwapSides,
}: JoinPanelProps) {
  const samples = useJoinSamples({ pipelineId, leftRef, rightRef, etag });

  const kind = (params.kind ?? params.how ?? "inner") as JoinKind;
  const keys = (params.keys ?? params.on ?? []) as JoinKey[];
  const rule = ((params.columnCollisions as CollisionRule | undefined) ?? "keep_both") as CollisionRule;
  const suffixes = (params.suffixes as [string, string] | undefined)
    ?? ["_left", "_right"];
  const overrides = (params.columnOverrides as Record<string, CollisionRule> | undefined)
    ?? undefined;
  const outputColumns = (params.outputColumns as OutputColumnsValue | undefined)
    ?? { excluded: [], renames: {} };

  const estimate = useMemo(
    () => cardinalityEstimate(samples.leftRows, samples.rightRows, keys, kind),
    [samples.leftRows, samples.rightRows, keys, kind],
  );

  // Equality-key left columns are collapsed by the SQL builder, so
  // they're not collisions — pass to the panel as exclusions.
  const equalityLeftKeys = useMemo(
    () => new Set(keys.filter((k) => (k.op ?? "=") === "=").map((k) => k.left)),
    [keys],
  );

  const setKind = (next: JoinKind) =>
    onChange({ ...params, kind: next, how: undefined });
  const setKeys = (next: JoinKey[]) =>
    onChange({ ...params, keys: next, on: undefined });
  const setCollisions = (next: { rule: CollisionRule; suffixes: [string, string]; overrides?: Record<string, CollisionRule> }) =>
    onChange({
      ...params,
      columnCollisions: next.rule,
      suffixes: next.suffixes,
      columnOverrides: next.overrides,
    });
  const setOutputColumns = (next: OutputColumnsValue) =>
    onChange({ ...params, outputColumns: next });

  return (
    <div className="space-y-3">
      <InputsPanel
        leftRef={leftRef}
        rightRef={rightRef}
        eligibleSources={eligibleSources}
        samples={samples}
        onSetInputRef={onSetInputRef}
        onSwapSides={onSwapSides}
      />

      <CardinalityStrip
        estimate={estimate}
        leftTotal={samples.leftTotal}
        rightTotal={samples.rightTotal}
        loading={samples.loading}
      />

      <div>
        <p className="text-[11px] uppercase tracking-widest text-muted-foreground mb-1.5">
          Join type
        </p>
        <JoinTypeIcons value={kind} onChange={setKind} />
      </div>

      <div>
        <p className="text-[11px] uppercase tracking-widest text-muted-foreground mb-1.5">
          Keys
        </p>
        <JoinKeysBuilder
          value={keys}
          onChange={setKeys}
          leftCols={samples.leftCols}
          rightCols={samples.rightCols}
          leftRows={samples.leftRows}
          rightRows={samples.rightRows}
          loading={samples.loading}
        />
      </div>

      <ColumnCollisionsPanel
        value={{ rule, suffixes, overrides }}
        onChange={setCollisions}
        leftCols={samples.leftCols}
        rightCols={samples.rightCols}
        excludeLeftCols={equalityLeftKeys}
      />

      <ResultColumnsPanel
        value={outputColumns}
        onChange={setOutputColumns}
        leftCols={samples.leftCols}
        rightCols={samples.rightCols}
        leftRows={samples.leftRows}
        rightRows={samples.rightRows}
        keys={keys}
        rule={rule}
        suffixes={suffixes}
        kind={kind}
      />

      {samples.error && (
        <p className="text-[11px] text-rose-600 dark:text-rose-400 bg-rose-50/50 dark:bg-rose-950/20 px-2 py-1.5 rounded-md">
          ⚠ Couldn&apos;t sample upstream rows: {samples.error}. Pick keys
          manually; the cardinality strip and match-quality bars will
          stay blank until samples are available.
        </p>
      )}
    </div>
  );
}

export type { JoinKind, JoinKey };
