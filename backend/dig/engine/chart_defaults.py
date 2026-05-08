"""Default chart-rendering dimensions for matplotlib outputs.

Every viz-producing step (`forecast`, `pca`, `kmeans`, `correlation_matrix`,
…) used to inline its own `figsize=(...)` magic numbers, which produced a
patchwork of different image sizes across the editor's chart previews and
the run-history exports. This module centralises them so the user sees
consistent output everywhere.

The defaults target **1600×1200 px** at **144 dpi** — bumped from the
previous ~600×450 to fit modern displays without aliasing, and to give
exported charts enough resolution for slide decks / docs without
re-exporting at a higher size.

Use ``figsize_px(W, H)`` to express size in pixels at the call site —
much more readable than `(W/144, H/144)` math:

    fig, ax = plt.subplots(figsize=figsize_px(1600, 1200), dpi=DEFAULT_DPI)

For aspect-specific charts:

    - DEFAULT_FIGSIZE       — 1600×1200 (4:3) — most charts
    - WIDE_FIGSIZE          — 2000×1000 (2:1) — time series / forecast
    - SQUARE_FIGSIZE        — 1400×1400 (1:1) — correlation, scatter
    - TALL_STACK_FIGSIZE    — 1600×1600 (1:1, but room for stacked rows)
"""
from __future__ import annotations

DEFAULT_DPI: int = 144
"""Resolution for all rendered charts. Matches the existing site-wide
   pick — bumping it would explode export sizes without proportional
   gains. Override per-step only when the user explicitly opts in (the
   ``export_to_image`` step accepts user-provided dpi)."""

DEFAULT_WIDTH_PX: int = 1600
DEFAULT_HEIGHT_PX: int = 1200


def figsize_px(width_px: int, height_px: int, *, dpi: int = DEFAULT_DPI) -> tuple[float, float]:
    """Convert pixel dimensions to matplotlib's `figsize` (inches).

    Matplotlib `figsize` is always in inches — pixels = figsize × dpi.
    Wrapping the conversion makes call sites self-documenting:

        plt.subplots(figsize=figsize_px(1600, 1200), dpi=DEFAULT_DPI)

    reads as "1600 by 1200 pixels" instead of obscure float pairs.
    """
    return (width_px / dpi, height_px / dpi)


# Pre-computed for the common cases — saves the per-call division and
# avoids subtle floating-point drift if a downstream consumer compares
# figsize values.
DEFAULT_FIGSIZE: tuple[float, float] = figsize_px(DEFAULT_WIDTH_PX, DEFAULT_HEIGHT_PX)
"""4:3, the default — 1600×1200 px at 144 dpi."""

WIDE_FIGSIZE: tuple[float, float] = figsize_px(2000, 1000)
"""2:1 wide — for time-series, forecast, and any chart whose x-axis
   carries far more information density than the y-axis."""

SQUARE_FIGSIZE: tuple[float, float] = figsize_px(1400, 1400)
"""1:1 — for correlation matrices, scatter plots, embeddings (PCA,
   t-SNE, UMAP) where x and y are interchangeable signal axes."""

TALL_STACK_FIGSIZE: tuple[float, float] = figsize_px(1600, 1600)
"""1:1 with extra room — for steps that stack multiple subplots
   vertically (seasonal_decompose's observed/trend/seasonal/residual)."""
