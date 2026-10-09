"""Drive the eval-builder label sheet in headless Chrome: check it renders offline,
label every case from a decisions file with the keyboard, export, and save the download.

usage: drive_sheet.py <label_sheet.html> <decisions.json> <out_dir> [--labeler NAME]
decisions.json: {"case-001": {"label": "pass", "note": "..."}, ...}
"""

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("sheet")
ap.add_argument("decisions")
ap.add_argument("out")
ap.add_argument("--labeler", default="")
args = ap.parse_args()
sheet = Path(args.sheet).resolve()
decisions = json.loads(Path(args.decisions).read_text())
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
log = []

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(accept_downloads=True, viewport={"width": 1100, "height": 900})
    page = ctx.new_page()
    requests, errors = [], []
    page.on("request", lambda r: requests.append(r.url))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(sheet.as_uri())
    total = page.evaluate(
        "JSON.parse(document.getElementById('sheet-data').textContent).cases.length"
    )
    log.append(f"title: {page.title()}")
    log.append(f"cases in sheet: {total}")
    log.append(f"progress at start: {page.text_content('#count')}")
    page.screenshot(path=str(out / "sheet-first-case.png"), full_page=False)
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(out / "sheet-phone.png"), full_page=False)
    page.set_viewport_size({"width": 1100, "height": 900})
    if args.labeler:
        page.fill("#labeler", args.labeler)
        page.keyboard.press("Escape")
    seen = []
    for i in range(total):
        cid = page.text_content("#card .meta span:last-child").strip()
        seen.append(cid)
        d = decisions[cid]
        if d.get("note"):
            page.keyboard.press("n")
            page.keyboard.type(d["note"])
            page.keyboard.press("Escape")
        page.keyboard.press(d["label"][0].lower())
        if i == total // 2:
            # reload half way: progress must survive (local storage)
            page.wait_for_timeout(300)
            before = page.text_content("#count")
            page.reload()
            after = page.text_content("#count")
            log.append(f"reload after {i + 1} labels: '{before}' -> '{after}'")
            page.keyboard.press("u")
        page.wait_for_timeout(250)
    page.wait_for_selector("#export:not([hidden])")
    log.append(f"export summary: {page.text_content('#export-summary')}")
    warn = page.locator("#export-warn")
    log.append(f"export warning shown: {warn.is_visible()}")
    page.screenshot(path=str(out / "sheet-export.png"), full_page=True)
    blob = page.input_value("#blob")
    with page.expect_download() as dl:
        page.click("#download")
    d = dl.value
    target = out / d.suggested_filename
    d.save_as(str(target))
    log.append(f"download: {d.suggested_filename}, {target.stat().st_size} bytes")
    log.append(f"download equals the copy box: {target.read_text() == blob}")
    log.append(f"import command shown: {page.text_content('#import-cmd')}")
    non_local = [u for u in requests if not u.startswith(("file:", "blob:", "data:"))]
    log.append(f"requests: {len(requests)} total, {len(non_local)} not file/blob/data: {non_local}")
    log.append(f"console errors: {errors}")
    log.append(f"cases visited: {len(seen)}, distinct {len(set(seen))}")
    browser.close()

print("\n".join(log))
(out / "drive_log.txt").write_text("\n".join(log) + "\n")
sys.exit(0 if not errors else 1)
