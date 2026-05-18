"""spatial_join — predicate-based join over geometry columns.

shapely.STRtree builds an R-tree spatial index on the right side
(O(N log N) build) and answers candidate queries in O(log N) per
left row. The candidate matches are then verified with the exact
predicate. For 100k × 100k joins this is ~5 minutes, vs ~hours
for a naive cross product.

Geometry on the frame is WKB bytes (parse_geometry shape) — both
sides re-hydrate via shapely.from_wkb before the join.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


_PREDICATES = {
    "within": "within",
    "contains": "contains",
    "intersects": "intersects",
    "touches": "touches",
    "covers": "covers",
    "covered_by": "covered_by",
}


class SpatialJoinStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from shapely import from_wkb
        from shapely.strtree import STRtree

        left_df = inputs["left"]
        right_df = inputs["right"]
        left_geom = params["leftGeometry"]
        right_geom = params["rightGeometry"]
        predicate = (params.get("predicate") or "within").lower()
        join_type = (params.get("joinType") or "inner").lower()
        suffix = params.get("rightSuffix") or "_r"

        if predicate not in _PREDICATES:
            raise ValueError(f"spatial_join: unknown predicate {predicate!r}")
        if left_geom not in left_df.columns:
            raise ValueError(
                f"spatial_join: leftGeometry column {left_geom!r} not found",
            )
        if right_geom not in right_df.columns:
            raise ValueError(
                f"spatial_join: rightGeometry column {right_geom!r} not found",
            )

        # Hydrate geometries (skip None entries — they cannot match).
        left_geoms = [
            from_wkb(b) if b is not None else None
            for b in left_df[left_geom].to_list()
        ]
        right_geoms = [
            from_wkb(b) if b is not None else None
            for b in right_df[right_geom].to_list()
        ]
        right_valid_idx = [i for i, g in enumerate(right_geoms) if g is not None]
        right_valid = [right_geoms[i] for i in right_valid_idx]

        if not right_valid:
            # Empty right side: depending on join type, empty inner or
            # all-left with NULL right.
            if join_type == "inner":
                empty = left_df.head(0)
                return PolarsResult(output=empty)

        tree = STRtree(right_valid)
        # tree.query returns *candidate* indices; we still need to
        # verify the exact predicate. shapely supports passing the
        # predicate directly which combines both steps.
        pairs: list[tuple[int, int]] = []
        for li, lg in enumerate(left_geoms):
            if lg is None:
                continue
            cands = tree.query(lg, predicate=predicate)
            for ci in cands.tolist():
                pairs.append((li, right_valid_idx[ci]))

        # Build the joined frame. Disambiguate column names that exist
        # on both sides by suffixing the right-side column.
        right_renames: dict[str, str] = {}
        left_cols = set(left_df.columns)
        for c in right_df.columns:
            if c in left_cols:
                right_renames[c] = f"{c}{suffix}"
        right_renamed = right_df.rename(right_renames)

        if not pairs:
            if join_type == "left_outer":
                # Cross-product zero rows from right → just left + NULL
                # padding columns.
                out_df = left_df
                for c in right_renamed.columns:
                    out_df = out_df.with_columns(pl.lit(None).alias(c))
                return PolarsResult(output=out_df)
            empty_cols = list(left_df.columns) + list(right_renamed.columns)
            return PolarsResult(output=pl.DataFrame({c: [] for c in empty_cols}))

        # Materialise the join.
        l_idx = [p[0] for p in pairs]
        r_idx = [p[1] for p in pairs]
        # Use Polars' index-based slicing (pl.DataFrame doesn't have
        # iloc, but row indexing via take works).
        left_taken = left_df[l_idx]
        right_taken = right_renamed[r_idx]
        joined = pl.concat([left_taken, right_taken], how="horizontal")

        if join_type == "left_outer":
            # Add unmatched left rows with NULL right.
            matched = set(l_idx)
            unmatched = [i for i in range(left_df.height) if i not in matched]
            if unmatched:
                left_only = left_df[unmatched]
                pad = {c: [None] * left_only.height for c in right_renamed.columns}
                left_only_padded = pl.concat([left_only, pl.DataFrame(pad)], how="horizontal")
                joined = pl.concat([joined, left_only_padded], how="vertical_relaxed")

        return PolarsResult(output=joined)


step = SpatialJoinStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
