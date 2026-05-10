"""Internal screenshot capture helper for the v0.8 polish docs.

Drives a headless Chromium against the running preview server, navigates
to specific routes, applies small DOM tweaks (dismiss popups, switch
modes), and writes half-resolution PNGs into docs/images/phase-a-pro/.

Run with the dev server (port 3000) and DIG backend (port 8090) up:

    python3 scripts/capture_doc_screenshots.py [name1 name2 ...]

Pass capture names to limit; no args runs all defined below. Each image
is captured at the viewport's natural pixel density and downsampled to
~50% via Pillow so the doc doesn't carry heavy retina assets.

The auth token comes from ~/.config/dig/auth.token if present (matches
the preview server's NEXT_PUBLIC_DIG_AUTH_TOKEN env wiring).
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "images" / "phase-a-pro"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TOKEN_PATH = Path("~/.config/dig/auth.token").expanduser()
TOKEN = TOKEN_PATH.read_text().strip() if TOKEN_PATH.exists() else ""
PIPELINE_ID = "01KR4K2K8SRTDAEN18RQETX3FH"   # Phase A testbed


def half_resize(png_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(png_bytes))
    new = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
    out = io.BytesIO()
    new.save(out, format="PNG", optimize=True)
    return out.getvalue()


def write(name: str, png_bytes: bytes) -> Path:
    path = OUT_DIR / f"{name}.png"
    path.write_bytes(half_resize(png_bytes))
    print(f"  ✓ {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")
    return path


def goto_pipeline(page: Page) -> None:
    """Navigate to the testbed pipeline + dismiss the tune-up popup."""
    page.goto(f"http://localhost:3000/pipelines/{PIPELINE_ID}", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=15000)
    # Dismiss the autosave/tune-up popup if present.
    try:
        skip = page.get_by_role("button", name="Skip for now")
        if skip.is_visible(timeout=1500):
            skip.click()
    except Exception:
        pass
    # Switch to Graph mode (canvas) if not already. The toolbar shows
    # both "🛤 Strip" and "🕸 Graph"; we want Graph. Some renders don't
    # auto-mount the canvas until clicked.
    try:
        page.evaluate("""() => {
            const btn = [...document.querySelectorAll('button')].find(b => b.textContent?.includes('Graph'));
            btn?.click();
        }""")
    except Exception:
        pass
    # Wait for canvas to render with at least one node.
    try:
        page.locator(".react-flow__node").first.wait_for(timeout=10000)
    except Exception:
        pass
    page.wait_for_timeout(1500)


# ---- captures -------------------------------------------------------------

def cap_minimap(page: Page) -> None:
    goto_pipeline(page)
    # Diagnostics: where are we, what buttons exist?
    state = page.evaluate("""() => {
        const btns = [...document.querySelectorAll('button')].map(b => b.textContent?.trim().slice(0, 30)).filter(Boolean);
        return {
            url: location.pathname,
            rfNodes: document.querySelectorAll('.react-flow__node').length,
            mm: !!document.querySelector('.react-flow__minimap'),
            mode: btns.find(b => b?.includes('Graph') || b?.includes('Strip')),
            btnSample: btns.slice(0, 30),
        };
    }""")
    print(f"   debug: {state}")
    # If mode toggle still on Strip view, click Graph.
    if not state.get("mm"):
        try:
            page.locator("button", has_text="🕸 Graph").click(timeout=2000)
            page.wait_for_timeout(1500)
        except Exception:
            try:
                page.locator("button", has_text="Graph").first.click(timeout=2000)
                page.wait_for_timeout(1500)
            except Exception:
                pass
    # Mini-map sits in the bottom-right of the canvas region.
    mm = page.locator(".react-flow__minimap").first
    mm.scroll_into_view_if_needed(timeout=10000)
    page.wait_for_timeout(500)
    box = mm.bounding_box()
    if not box:
        return
    pad = 24
    clip = {
        "x": max(0, box["x"] - pad),
        "y": max(0, box["y"] - pad),
        "width": box["width"] + pad * 2,
        "height": box["height"] + pad * 2,
    }
    write("01-canvas-minimap", page.screenshot(clip=clip))


def cap_sankey_zoom(page: Page) -> None:
    goto_pipeline(page)
    # Open the Sankey overlay.
    page.evaluate("""() => {
        const btn = [...document.querySelectorAll('button')].find(b => b.textContent?.includes('Volume view'));
        btn?.click();
    }""")
    page.wait_for_timeout(1200)
    # Expand the canvas region a bit so the Sankey gets vertical room.
    page.evaluate("""() => {
        const wrap = [...document.querySelectorAll('svg[width="1400"]')][0]?.parentElement;
        if (wrap) { wrap.style.height = 'auto'; wrap.style.minHeight = '700px'; }
        document.querySelector('svg[width="1400"]')?.scrollIntoView({ block: 'start' });
    }""")
    page.wait_for_timeout(1000)
    # Zoom in twice to demonstrate.
    page.evaluate("""() => {
        const plus = [...document.querySelectorAll('button')].find(b => b.title?.includes('Zoom in'));
        plus?.click(); plus?.click();
    }""")
    page.wait_for_timeout(700)
    sankey = page.locator('svg[width="1400"]').first
    box = sankey.bounding_box()
    if not box:
        return
    pad = 16
    clip = {
        "x": max(0, box["x"] - pad),
        "y": max(0, box["y"] - pad - 80),  # include toolbar above
        "width": min(box["width"] + pad * 2, page.viewport_size["width"] - max(0, box["x"] - pad)),
        "height": box["height"] + pad * 2 + 80,
    }
    write("02-sankey-zoom-pan", page.screenshot(clip=clip))


def open_dna_for_column(page: Page, header_text: str = "production_cost") -> None:
    """Right-click a column header in the default-focus grid + open Column DNA.

    The default focus shows columns from the early-pipeline output,
    which DuckDB-WASM evaluates instantly without needing the full
    backend run. Use `production_cost` for a small lineage, or focus
    a downstream node first to inspect a richer column."""
    goto_pipeline(page)
    page.wait_for_timeout(1500)
    # Right-click the target column header via real Playwright event.
    page.locator(f"th:has-text('{header_text}')").first.click(button="right", timeout=8000)
    page.wait_for_timeout(700)
    # Choose "Column DNA (full graph)".
    page.locator("button:has-text('Column DNA (full graph)')").first.click(timeout=4000)
    page.wait_for_timeout(2500)


def cap_dna_zoom(page: Page) -> None:
    open_dna_for_column(page, "production_cost")
    page.locator("text=Column DNA").first.wait_for(timeout=10000)
    page.wait_for_timeout(800)
    # Show at default 100% so the full lineage is visible alongside the
    # zoom controls (button cluster top-right of the canvas area).
    modal = page.locator(".fixed.inset-0.z-50").first
    box = modal.bounding_box()
    if not box:
        return
    write("03-dna-zoom-pan", page.screenshot(clip=box))


def cap_dna_downstream(page: Page) -> None:
    """Open DNA on a SOURCE column then flip to downstream walk."""
    open_dna_for_column(page, "production_cost")
    page.locator("text=Column DNA").first.wait_for(timeout=10000)
    page.wait_for_timeout(800)
    # Click the leftmost "unit_cost" source node so the trace from that
    # specific column lights up. Then switch direction to downstream.
    page.evaluate("""() => {
        const nodes = [...document.querySelectorAll('[data-dna-node]')];
        const src = nodes.find(n => n.textContent?.includes('unit_cost') && n.textContent?.includes('production'));
        src?.click();
    }""")
    page.wait_for_timeout(300)
    page.evaluate("""() => {
        const btn = [...document.querySelectorAll('button')].find(b => b.textContent?.trim() === 'downstream →');
        btn?.click();
    }""")
    page.wait_for_timeout(700)
    modal = page.locator(".fixed.inset-0.z-50").first
    box = modal.bounding_box()
    if not box:
        return
    write("04-dna-downstream-walk", page.screenshot(clip=box))


def cap_impact_badge(page: Page) -> None:
    """Crop the live-grid header row showing the new → N impact chip."""
    goto_pipeline(page)
    page.wait_for_timeout(2000)
    # Click a step that has downstream consumers — `cast unit_cost` or
    # similar mid-pipeline node — so the badge actually has count > 0.
    page.evaluate("""() => {
        const node = [...document.querySelectorAll('.react-flow__node')].find(n => n.textContent?.includes('cast unit_cost'));
        node?.click();
    }""")
    page.wait_for_timeout(2000)
    # Capture the table headers row.
    thead = page.locator("thead").first
    box = thead.bounding_box()
    if not box:
        return
    pad = 8
    clip = {
        "x": max(0, box["x"] - pad),
        "y": max(0, box["y"] - pad),
        "width": min(box["width"] + pad * 2, page.viewport_size["width"]),
        "height": box["height"] + pad * 2,
    }
    write("05-impact-badge", page.screenshot(clip=clip))


def cap_catalog(page: Page) -> None:
    page.goto("http://localhost:3000/catalog", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=15000)
    page.wait_for_timeout(2500)
    write("06-catalog-column-edges", page.screenshot(full_page=False))


def cap_check_step(page: Page) -> None:
    """Open the step library and search for 'check' to surface the new step."""
    goto_pipeline(page)
    page.wait_for_timeout(1500)
    # The "Add step" / step library opens via cmdk (cmd+k) or toolbar.
    # We'll trigger it by a global keyboard shortcut.
    page.keyboard.press("Meta+K")
    page.wait_for_timeout(800)
    # Type "check" to filter the step list
    page.keyboard.type("data quality")
    page.wait_for_timeout(700)
    write("07-check-step", page.screenshot(full_page=False))


def cap_profile_drawer(page: Page) -> None:
    """Profile drawer with the new percentile + std-dev + top-N
    chips rendered against the production dataset."""
    goto_pipeline(page)
    page.wait_for_timeout(2000)
    # Click a dataset node so the live grid shows source columns.
    page.evaluate("""() => {
        const node = [...document.querySelectorAll('.react-flow__node')].find(n =>
            n.textContent?.includes('production') &&
            !n.textContent?.includes('cost') &&
            !n.textContent?.includes('derive'));
        node?.click();
    }""")
    page.wait_for_timeout(2500)
    # Click the units_produced column header → opens the drawer.
    page.evaluate("""() => {
        const btn = [...document.querySelectorAll('th button')].find(b =>
            b.textContent?.trim() === 'units_produced');
        btn?.click();
    }""")
    page.wait_for_timeout(800)
    drawer = page.locator("aside").first
    box = drawer.bounding_box()
    if not box:
        return
    write("08-profile-drawer", page.screenshot(clip={
        "x": max(0, box["x"] - 8),
        "y": 0,
        "width": min(box["width"] + 16, page.viewport_size["width"]),
        "height": min(box["height"] + 8, page.viewport_size["height"]),
    }))


def cap_workspace_cmdk(page: Page) -> None:
    """Cmdk palette with a search query that triggers column hits."""
    goto_pipeline(page)
    page.wait_for_timeout(1500)
    # Cmd+K to open the palette
    page.keyboard.press("Meta+K")
    page.wait_for_timeout(500)
    page.keyboard.type("plant")
    page.wait_for_timeout(800)
    write("09-workspace-cmdk", page.screenshot(full_page=False))


def cap_catalog_tags(page: Page) -> None:
    page.goto("http://localhost:3000/catalog", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=15000)
    page.wait_for_timeout(2500)
    write("10-catalog-tags", page.screenshot(full_page=False))


def cap_runs_list(page: Page) -> None:
    page.goto("http://localhost:3000/runs", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=15000)
    page.wait_for_timeout(2000)
    write("11-runs-list", page.screenshot(full_page=False))


def cap_run_detail(page: Page) -> None:
    page.goto("http://localhost:3000/runs", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=15000)
    page.wait_for_timeout(1500)
    # Click the first run row.
    page.evaluate("""() => {
        const link = document.querySelector('tbody tr a[href^="/runs/"]');
        if (link) link.click();
    }""")
    page.wait_for_timeout(3000)
    write("12-run-detail", page.screenshot(full_page=False))


CAPTURES = {
    "minimap": cap_minimap,
    "sankey-zoom": cap_sankey_zoom,
    "dna-zoom": cap_dna_zoom,
    "dna-downstream": cap_dna_downstream,
    "impact-badge": cap_impact_badge,
    "catalog": cap_catalog,
    "check-step": cap_check_step,
    "profile-drawer": cap_profile_drawer,
    "workspace-cmdk": cap_workspace_cmdk,
    "catalog-tags": cap_catalog_tags,
    "runs-list": cap_runs_list,
    "run-detail": cap_run_detail,
}


def main(argv: list[str]) -> int:
    targets = argv or list(CAPTURES.keys())
    bad = [t for t in targets if t not in CAPTURES]
    if bad:
        print(f"unknown captures: {bad}\nknown: {list(CAPTURES.keys())}", file=sys.stderr)
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 1080},
            device_scale_factor=2,
            extra_http_headers={"Authorization": f"Bearer {TOKEN}"} if TOKEN else None,
            storage_state={
                "cookies": [],
                "origins": [
                    {
                        "origin": "http://localhost:3000",
                        "localStorage": [
                            {"name": "dig_auth_token", "value": TOKEN},
                        ],
                    }
                ],
            } if TOKEN else None,
        )
        page = ctx.new_page()
        # Inject the token before any script runs so the API client picks it up.
        if TOKEN:
            page.add_init_script(f"window.__DIG_TOKEN__ = '{TOKEN}';")

        for name in targets:
            print(f"capturing {name}...")
            try:
                CAPTURES[name](page)
            except Exception as e:
                print(f"  ✗ {name}: {e}", file=sys.stderr)

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
