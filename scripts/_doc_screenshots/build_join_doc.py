"""Build the docs/JOINS.md screenshots end-to-end.

Two pipelines are created (idempotent by name prefix):

  📚 Join doc · TC1 · two datasets
      customers + orders → 🔗 Join.

  📚 Join doc · TC2 · mid-chain branch
      ds_customers → filter_active
      ds_orders    → filter_2024
      both → 🔗 Join → filter_high_total

Then Playwright drives the editor and captures + VALIDATES screenshots.
Each capture asserts expected DOM strings before saving the PNG so a
silently broken state can't make it into the docs.

Run with the backend up on http://127.0.0.1:8190 and the frontend on
http://localhost:3100:

    backend/.venv/bin/python scripts/_doc_screenshots/build_join_doc.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from urllib import request as urlreq
from urllib.error import HTTPError

from playwright.async_api import Page, async_playwright


_API = "http://127.0.0.1:8190"
_FE = "http://localhost:3100"
_OUT = Path("docs/images/joins")
_VIEWPORT = {"width": 1600, "height": 1000}

# Dataset ULIDs (already uploaded by the existing sampling_join_demos.py).
_CUST_ULID = "01KR1T87553SNQAYTZ3CX8ZHWF"
_ORDERS_ULID = "01KR1T87AFT7YK4XRJVCD63AHT"


# ── Backend helpers ────────────────────────────────────────────────


def _request(method: str, path: str, body: dict | None = None) -> dict:
    url = _API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urlreq.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urlreq.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except HTTPError as e:
        body_str = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"{method} {path} → {e.code}: {body_str}") from e


def _list(path: str) -> list:
    val = _request("GET", path, None)
    return val if isinstance(val, list) else []


def _find_pipeline(prefix: str) -> str | None:
    for p in _list("/pipelines"):
        if (p.get("name") or "").startswith(prefix):
            return p["id"]
    return None


def _save_or_update(prefix: str, name: str, doc: dict) -> str:
    existing = _find_pipeline(prefix)
    if existing:
        cur = _request("GET", f"/pipelines/{existing}")
        doc["id"] = existing
        doc["name"] = name
        body = {"document": doc, "expectedEtag": cur["etag"], "triggeredBy": "import"}
        try:
            _request("PUT", f"/pipelines/{existing}", body)
            return existing
        except SystemExit:
            pass
    res = _request("POST", "/pipelines", {"name": name, "document": doc})
    return res["id"]


def _ds_alias(ulid: str) -> str:
    return f"ds_{ulid.lower()}"


def _ds_entry(ulid: str, label: str) -> dict:
    rows = _list("/datasets")
    row = next((r for r in rows if r.get("id") == ulid), None)
    if not row:
        raise SystemExit(f"dataset {ulid} not found — run sampling_join_demos.py first")
    return {
        "id": _ds_alias(ulid),
        "connector": "parquet",
        "uri": row.get("storageUri") or row.get("storage_uri"),
        "label": label,
        "options": {},
    }


# ── Pipeline definitions ───────────────────────────────────────────


def build_tc1() -> str:
    """TC1: a clean two-dataset join, no downstream — terminal join."""
    doc = {
        "schemaVersion": 1,
        "datasets": [
            _ds_entry(_CUST_ULID, "customers"),
            _ds_entry(_ORDERS_ULID, "orders"),
        ],
        "nodes": [
            {
                "id": "n_join",
                "step": "join",
                "stepVersion": "1.2.0",
                "inputs": {
                    "left": {"ref": _ds_alias(_CUST_ULID)},
                    "right": {"ref": _ds_alias(_ORDERS_ULID)},
                },
                "outputs": ["out"],
                "params": {
                    "kind": "inner",
                    "keys": [{"left": "customer_id", "right": "customer_id", "op": "="}],
                    "columnCollisions": "keep_both",
                    "suffixes": ["_cust", "_order"],
                },
                "ui": {"x": 480, "y": 220, "label": "🔗 customers ⋈ orders"},
            },
        ],
        "outputs": [],
        # Random sampling so the match-quality bar reflects the full
        # join behaviour (head-sample on orders is dominated by customer 1
        # and would produce a misleading 3% match%).
        "metadata": {
            "sampling": {"method": "random", "size": 5000, "seed": 42},
        },
    }
    return _save_or_update(
        "📚 Join doc · TC1",
        "📚 Join doc · TC1 · two datasets",
        doc,
    )


def build_tc2() -> str:
    """TC2: two filter steps feed the join + a downstream filter so the
    join is mid-chain — swap-sides will branch instead of mutating in place.
    """
    doc = {
        "schemaVersion": 1,
        "datasets": [
            _ds_entry(_CUST_ULID, "customers"),
            _ds_entry(_ORDERS_ULID, "orders"),
        ],
        "nodes": [
            {
                "id": "n_filter_active",
                "step": "filter_rows",
                "stepVersion": "1.0.0",
                "inputs": {"in": {"ref": _ds_alias(_CUST_ULID)}},
                "outputs": ["out"],
                "params": {"predicate": "\"churn_status\" = 'active'"},
                "ui": {"x": 240, "y": 120, "label": "🔍 active customers"},
            },
            {
                "id": "n_filter_2024",
                "step": "filter_rows",
                "stepVersion": "1.0.0",
                "inputs": {"in": {"ref": _ds_alias(_ORDERS_ULID)}},
                "outputs": ["out"],
                "params": {"predicate": "\"order_year\" = 2024"},
                "ui": {"x": 240, "y": 320, "label": "🔍 2024 orders"},
            },
            {
                "id": "n_join",
                "step": "join",
                "stepVersion": "1.2.0",
                "inputs": {
                    "left": {"ref": "n_filter_active", "port": "out"},
                    "right": {"ref": "n_filter_2024", "port": "out"},
                },
                "outputs": ["out"],
                "params": {
                    "kind": "inner",
                    "keys": [{"left": "customer_id", "right": "customer_id", "op": "="}],
                    "columnCollisions": "keep_both",
                    "suffixes": ["_cust", "_order"],
                },
                "ui": {"x": 540, "y": 220, "label": "🔗 active ⋈ 2024-orders"},
            },
            {
                "id": "n_filter_high_total",
                "step": "filter_rows",
                "stepVersion": "1.0.0",
                "inputs": {"in": {"ref": "n_join", "port": "out"}},
                "outputs": ["out"],
                "params": {"predicate": "\"total\" > 100"},
                "ui": {"x": 840, "y": 220, "label": "🔍 total > 100"},
            },
        ],
        "outputs": [],
        "metadata": {
            "sampling": {"method": "random", "size": 5000, "seed": 42},
        },
    }
    return _save_or_update(
        "📚 Join doc · TC2",
        "📚 Join doc · TC2 · mid-chain branch",
        doc,
    )


# ── Validate-and-screenshot helper ─────────────────────────────────


async def shoot(
    page: Page,
    out_path: Path,
    must_contain: list[str],
    *,
    must_not_contain: list[str] | None = None,
    must_count_at_least: dict[str, int] | None = None,
    clip: dict | None = None,
    element: object | None = None,
    description: str = "",
) -> None:
    """Validate body text contains every string in `must_contain`, none of
    those in `must_not_contain`, and that each key in `must_count_at_least`
    appears at least N times. Fails the whole run on any miss — silent
    regressions don't reach docs.
    """
    body_text = await page.locator("body").inner_text()
    for needle in must_contain:
        if needle not in body_text:
            raise AssertionError(
                f"❌ '{needle}' missing from page when capturing {out_path.name}\n"
                f"   ({description})"
            )
    for forbidden in must_not_contain or []:
        if forbidden in body_text:
            raise AssertionError(
                f"❌ '{forbidden}' present (should not be) when capturing {out_path.name}\n"
                f"   ({description})"
            )
    for needle, n in (must_count_at_least or {}).items():
        actual = body_text.count(needle)
        if actual < n:
            raise AssertionError(
                f"❌ '{needle}' appeared {actual}× (need ≥{n}) when capturing {out_path.name}\n"
                f"   ({description})"
            )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if element is not None:
        await element.screenshot(path=str(out_path))
    elif clip:
        await page.screenshot(path=str(out_path), clip=clip)
    else:
        await page.screenshot(path=str(out_path))
    print(f"  ✓ {out_path.name} — {description}")


async def open_pipeline(page: Page, pid: str) -> None:
    await page.goto(f"{_FE}/pipelines/{pid}")
    await page.wait_for_load_state("networkidle")
    # Dismiss the "Pipeline tune-up" modal if it appears.
    for label in ("Skip for now", "Got it ✓", "Got it"):
        try:
            await page.click(f'button:has-text("{label}")', timeout=1200)
            await asyncio.sleep(0.3)
        except Exception:
            pass
    # Wait for the strip to actually populate — it lives behind a
    # client-side query so networkidle alone is insufficient.
    for _ in range(40):
        text = await page.locator("body").inner_text()
        if "STEPS" in text and "Join" in text:
            break
        await asyncio.sleep(0.5)
    # Once more, attempt to dismiss any "click any X to act on a column"
    # hint that mounts after the grid renders.
    try:
        await page.click('button:has-text("Got it ✓")', timeout=800)
    except Exception:
        pass
    await asyncio.sleep(1.5)


async def click_node_by_label(page: Page, label_substring: str) -> None:
    """Click the strip chip whose text contains `label_substring`. The
    strip uses the step's manifest label (e.g. "🔗 Join") + a derived
    hint string ("INNER on ?"), not the user-set ui.label, so callers
    pass either form. We retry briefly while the strip mounts.
    """
    # Strip chips are <div role="button"> (not <button>), so the
    # role-based selector covers both. We pick the FIRST match —
    # the topmost div is the chip wrapper, descendants will also
    # match has-text but are smaller.
    sel = f"[role='button']:has-text('{label_substring}')"
    try:
        await page.locator(sel).first.click(timeout=8000)
    except Exception:
        # Diagnostics: surface what's actually on the page.
        chips = await page.evaluate(
            "() => Array.from(document.querySelectorAll('button'))"
            ".map(b => b.textContent.replace(/\\s+/g,' ').trim())"
        )
        all_chips = [c for c in chips if c]
        body_text = await page.locator("body").inner_text()
        await page.screenshot(path=str(_OUT / f"_debug_{label_substring.replace(' ', '_')}.png"))
        raise AssertionError(
            f"❌ couldn't find chip with '{label_substring}'\n"
            f"   total buttons: {len(chips)}\n"
            f"   non-empty button texts: {len(all_chips)}\n"
            f"   ALL chips: {all_chips}\n"
            f"   body length: {len(body_text)}\n"
            f"   has STEPS: {'STEPS' in body_text}\n"
            f"   has Join: {'Join' in body_text}"
        )
    await asyncio.sleep(1.5)


async def panel_clip(page: Page) -> dict:
    """Return a clip rect that covers the right-hand params panel."""
    box = await page.locator("text=PARAMS").first.bounding_box()
    if not box:
        return {"x": 1080, "y": 0, "width": 520, "height": 1000}
    # The panel runs from a bit above PARAMS down to bottom of viewport.
    return {
        "x": max(0, box["x"] - 12),
        "y": max(0, box["y"] - 8),
        "width": 540,
        "height": _VIEWPORT["height"] - max(0, box["y"] - 8) - 50,
    }


# ── Capture flows ──────────────────────────────────────────────────


async def capture_tc1(page: Page, pid: str) -> None:
    print("\n=== Test Case 1: two-dataset join ===")
    await open_pipeline(page, pid)
    # The page auto-focuses the last node — the join in TC1's case.
    # Click the chip anyway for determinism (idempotent).
    await click_node_by_label(page, "🔗 Join")

    await shoot(
        page,
        _OUT / "tc1-01-overview.png",
        must_contain=["🔌 INPUTS", "JOIN TYPE", "KEYS", "RESULT COLUMNS", "customers", "orders"],
        description="Test case 1: full editor with the join panel populated",
    )

    # Section-level screenshots: locate each panel widget by its
    # heading text and screenshot just that container. This produces
    # distinct, focused images instead of three copies of the same clip.
    inputs_box = page.locator(
        "div.rounded-md", has=page.locator("text=🔌 Inputs"),
    ).first
    await shoot(
        page,
        _OUT / "tc1-02-inputs-panel.png",
        must_contain=["🔌 INPUTS", "↔ swap sides", "customers", "orders", "5,000"],
        element=inputs_box,
        description="🔌 Inputs section — both datasets wired with sample row counts",
    )

    # The cardinality strip sits between Inputs and Join type — its
    # outer wrapper has the "match" + "result" text. We grab the
    # whole "join params surface" container (everything between the
    # InputsPanel and ResultColumnsPanel) by clipping with bounding
    # boxes.
    inputs_b = await inputs_box.bounding_box()
    res_box = page.locator(
        "div.rounded-md", has=page.locator("text=📋 Result columns"),
    ).first
    res_b = await res_box.bounding_box()
    if inputs_b and res_b:
        clip_mid = {
            "x": inputs_b["x"],
            "y": inputs_b["y"] + inputs_b["height"] + 4,
            "width": inputs_b["width"],
            "height": res_b["y"] - (inputs_b["y"] + inputs_b["height"]) - 4,
        }
    else:
        clip_mid = None
    await shoot(
        page,
        _OUT / "tc1-03-cardinality-keys.png",
        must_contain=["≈", "match", "result", "JOIN TYPE", "KEYS"],
        clip=clip_mid,
        description="Cardinality strip + join type icons + keys + match-quality",
    )

    await shoot(
        page,
        _OUT / "tc1-04-result-columns.png",
        must_contain=[
            "📋 RESULT COLUMNS", "of", "included",
            "customer_id", "name", "total",
        ],
        element=res_box,
        description="Result columns section with L/R provenance + checkboxes",
    )


async def capture_tc2(page: Page, pid: str) -> None:
    print("\n=== Test Case 2: mid-chain branch ===")
    await open_pipeline(page, pid)
    # Click the JOIN chip (not the auto-focused downstream filter).
    await click_node_by_label(page, "🔗 Join")

    inputs_box = page.locator(
        "div.rounded-md", has=page.locator("text=🔌 Inputs"),
    ).first

    await shoot(
        page,
        _OUT / "tc2-01-pre-branch.png",
        must_contain=[
            "🔌 INPUTS", "active customers", "2024 orders",
            "🔗 Join", "🔍 Filter rows",
        ],
        description="Pre-branch state: join consumes two filter steps, downstream filter visible",
    )

    await shoot(
        page,
        _OUT / "tc2-02-pre-branch-panel.png",
        must_contain=["🔌 INPUTS", "active customers", "2024 orders"],
        must_not_contain=["branch 2"],
        element=inputs_box,
        description="Inputs panel showing both step-node sources before swap",
    )

    # Trigger swap-sides — should branch since n_filter_high_total is
    # downstream. We then poll for the sonner toast text to actually
    # appear (not just the click to register), so the screenshot is
    # taken while the toast is still visible.
    await page.click("button:has-text('↔ swap sides')")
    for _ in range(40):
        body = await page.locator("body").inner_text()
        if "Branched mid-pipeline join" in body:
            break
        await asyncio.sleep(0.1)

    # Capture ONLY the branch toast, not whatever other toast is
    # currently visible (e.g. session-conflict). We grab the sonner
    # `li` whose text contains our specific message so the
    # element-level screenshot can't pick up the wrong row.
    toast_loc = page.locator(
        "[data-sonner-toaster] li", has_text="Branched mid-pipeline join",
    ).first
    try:
        await toast_loc.wait_for(state="visible", timeout=3000)
        # Verify the captured element's OWN text is right before snap.
        toast_text = await toast_loc.inner_text()
        assert "Branched mid-pipeline join" in toast_text, (
            f"toast locator captured '{toast_text}' instead of branch toast"
        )
        await shoot(
            page,
            _OUT / "tc2-03-branch-toast.png",
            must_contain=["Branched mid-pipeline join", "downstream chain preserved"],
            element=toast_loc,
            description="Sonner toast announcing the branch (zoomed)",
        )
    except Exception as e:
        # Toast already faded — fall back to a full-page shot which
        # at least captures the persisted state change.
        print(f"  ⚠ branch toast capture fell back to full page: {e}")
        await shoot(
            page,
            _OUT / "tc2-03-branch-toast.png",
            must_contain=["Branched mid-pipeline join"],
            description="Branch toast (full page fallback)",
        )

    # Wait long enough for the toast to clear, then capture the strip.
    await asyncio.sleep(6)

    # The strip uses `overflow-x-auto` — at default 1600px viewport with
    # 7 chips, the rightmost join (the new branch) is scrolled off-screen.
    # Widen the viewport temporarily AND scroll the strip's inner
    # container to its end so both joins are visible in the screenshot.
    await page.set_viewport_size({"width": 2400, "height": 1000})
    await asyncio.sleep(0.4)
    # Scroll the strip's overflow-x-auto inner container fully to the
    # right so the latest (branch) join is visible.
    await page.evaluate("""
      () => {
        const root = document.querySelector('div.border-t.bg-background\\\\/60');
        if (!root) return;
        const scroller = root.querySelector('div.overflow-x-auto') || root.firstElementChild;
        if (scroller) scroller.scrollLeft = scroller.scrollWidth;
      }
    """)
    await asyncio.sleep(0.3)
    strip_locator = page.locator("div.border-t.bg-background\\/60").first
    try:
        await shoot(
            page,
            _OUT / "tc2-04-branch-strip.png",
            must_contain=["🔗 Join", "🔍 Filter rows"],
            must_count_at_least={"🔗 Join": 2},
            element=strip_locator,
            description="Strip: original join + new branch + downstream chain preserved",
        )
    except Exception:
        # Strip selector miss — fall back to full page shot which
        # the validator will still verify by body text.
        await shoot(
            page,
            _OUT / "tc2-04-branch-strip.png",
            must_contain=["🔗 Join", "🔍 Filter rows"],
            must_count_at_least={"🔗 Join": 2},
            description="Strip (full page fallback)",
        )
    # Restore viewport for any further captures (none currently, but
    # keeps the function self-contained for callers).
    await page.set_viewport_size(_VIEWPORT)


# ── Driver ─────────────────────────────────────────────────────────


async def main() -> None:
    print("Setting up pipelines via API…")
    tc1_id = build_tc1()
    tc2_id = build_tc2()
    print(f"  tc1 = {tc1_id}")
    print(f"  tc2 = {tc2_id}")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport=_VIEWPORT, device_scale_factor=2)
        page = await ctx.new_page()
        try:
            await capture_tc1(page, tc1_id)
            await capture_tc2(page, tc2_id)
        finally:
            await browser.close()
    print("\n✅ Captured + validated all screenshots in", _OUT)
    print(f"   TC1 pipeline: {_FE}/pipelines/{tc1_id}")
    print(f"   TC2 pipeline: {_FE}/pipelines/{tc2_id}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
