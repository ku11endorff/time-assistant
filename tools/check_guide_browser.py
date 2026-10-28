#!/usr/bin/env python3
"""Drive docs/guide.html in a real browser and check it works end to end.

    pip install playwright            # and a Chromium, e.g. `playwright install chromium`
    python3 tools/check_guide_browser.py [--chrome /path/to/chrome] [--shots DIR]

Not part of the normal test run (CI has no browser; tests/test_guide.py covers the page
statically and runs its config builder in node). Run it after changing the guide. It checks:
no console errors and no network requests, routes and step ticking, saved progress across a
reload, commands following the target name, the config builder (the generated config is fed
to `sync.py check-config`), copy and download buttons, the other tabs, the troubleshooting
filter, clearing saved data, labels on every control, no horizontal scroll on a phone, and
dark mode. Exits 1 on the first failure.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE = "file://" + os.path.join(ROOT, "docs", "guide.html")
passed = []


def check(cond, msg):
    if not cond:
        print(f"FAIL  {msg}")
        sys.exit(1)
    passed.append(msg)
    print(f"ok    {msg}")


def find_chrome():
    for pat in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome", os.path.expanduser(
            "~/.cache/ms-playwright/chromium-*/chrome-linux/chrome")):
        found = sorted(glob.glob(pat))
        if found:
            return found[-1]
    return None


def fill_valid(page):
    page.fill("#f-username", "you@example.com")
    page.fill("#f-projects", "1000001")
    page.fill("#f-expprojects", "2000001, 2000002")
    page.fill("#f-userid", "100")
    page.fill("#f-projectid", "5001")
    rows = page.locator("#actrows .actrow")
    rows.nth(0).locator("input").nth(0).fill("1001")
    rows.nth(0).locator("input").nth(1).fill("201")
    rows.nth(0).locator("input").nth(2).fill("301")
    page.fill("#f-wage", "401")
    page.fill("#f-cat", "301")
    page.select_option("#f-paid", "self")
    page.check("#f-allow")
    page.fill("#f-dom", "501")
    page.fill("#f-for", "502")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome", default=find_chrome())
    ap.add_argument("--shots", default=None, help="save screenshots here")
    args = ap.parse_args()
    shots = args.shots
    if shots:
        os.makedirs(shots, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chrome, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1100, "height": 900}, accept_downloads=True,
                                  permissions=["clipboard-read", "clipboard-write"])
        page = ctx.new_page()
        errors, requests = [], []
        page.on("console", lambda m: errors.append(m.text) if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda r: requests.append(r.url))
        page.goto(GUIDE)

        # --- load, privacy ---
        check(page.title() == "time-assistant setup guide", "page title")
        check("never asks for a password" in page.inner_text(".privacy"), "privacy notice is shown")
        check(page.locator("input[type=password]").count() == 0, "no password field anywhere")
        check(not page.is_visible("#stepsCard"), "no route chosen yet: steps are hidden")

        # --- routes and steps ---
        check(page.locator("#routes .route").count() == 3, "three routes offered")
        page.click("#routes .route[data-route=computer]")
        check(page.is_visible("#stepsCard"), "choosing a route shows its steps")
        n = page.locator("#steps > li").count()
        check(n == 12, f"route A has its steps ({n})")
        check(page.inner_text("#progressText") == f"0 of {n} steps done", "progress starts at 0")
        page.check("#chk-r\\:computer\\:prereq")
        page.check("#chk-r\\:computer\\:clone")
        check(page.inner_text("#progressText") == f"2 of {n} steps done", "ticking steps updates progress")
        check(page.locator("#steps > li.done").count() == 2, "ticked steps are marked done")
        page.reload()
        check(page.is_checked("#chk-r\\:computer\\:prereq") and page.inner_text("#progressText") == f"2 of {n} steps done",
              "progress survives a reload")

        # --- commands follow the target name ---
        pwd_block = page.locator("#steps li", has_text="Store the TimeKeeper password").locator("pre").first
        check("time-assistant:client" in pwd_block.inner_text(), "keychain command uses the default target name")
        page.click("#tab-builder")
        page.fill("#f-target", "partner")
        page.click("#tab-guide")
        pwd_block = page.locator("#steps li", has_text="Store the TimeKeeper password").locator("pre").first
        check("time-assistant:partner" in pwd_block.inner_text(), "keychain command follows the target name")
        check("password" in pwd_block.inner_text() and "-w" in pwd_block.inner_text(), "command prompts instead of taking a password")

        # --- other routes ---
        page.click("#routes .route[data-route=phone]")
        check("api2.timekeeper.se" in page.inner_text("#steps"), "cloud route mentions the network allow-list")
        page.click("#routes .route[data-route=claude]")
        check("Project instructions" in page.inner_text("#steps"), "Claude project route has the instruction text")

        # --- config builder ---
        page.click("#tab-builder")
        check(page.is_visible("#result-status ul.problems"), "an empty builder lists what is missing")
        check(not page.is_visible("#result-wrap"), "no config is offered while there are problems")
        fill_valid(page)
        page.fill("#f-target", "client")
        check(page.is_visible("#result-wrap"), "a complete form offers a config")
        check(page.locator("#result-status ul.problems").count() == 0, "no problems left")
        cfg_text = page.inner_text("#out-config")
        cfg = json.loads(cfg_text)
        check(cfg["targets"][0]["source_project_ids"] == [1000001, 2000001, 2000002], "expense project ids are merged")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write(cfg_text + "\n")
            r = subprocess.run([sys.executable, os.path.join(ROOT, "sync.py"), "--config", path, "check-config"],
                               capture_output=True, text=True, cwd=ROOT)
            check(r.returncode == 0 and "valid" in r.stdout, f"sync.py check-config accepts the generated config ({r.stdout.strip().splitlines()[-1] if r.stdout else r.stderr.strip()})")
            check("NOTE" not in r.stdout, "no leftover notes (category and allowances are set)")
        page.click("#result-wrap summary")
        env = page.inner_text("#out-env")
        check(env.startswith("TIME_ASSISTANT_AUTH=proxy\nTIME_ASSISTANT_CONFIG_JSON='"), "cloud environment lines are shown")
        check("password" not in env.lower(), "environment lines hold no secret")

        page.click("#copy-config")
        check(page.evaluate("navigator.clipboard.readText()") == cfg_text + "\n" or page.evaluate("navigator.clipboard.readText()").strip() == cfg_text.strip(),
              "copy button puts the config on the clipboard")
        with page.expect_download() as dl:
            page.click("#dl-config")
        download = dl.value
        check(download.suggested_filename == "config.json", "download is named config.json")
        with open(download.path(), encoding="utf-8") as f:
            check(json.loads(f.read()) == cfg, "downloaded file equals the shown config")

        # mistakes
        page.fill("#f-projectid", "0")
        check("project id" in page.inner_text("#result-status").lower(), "a wrong id is explained")
        check(not page.is_visible("#result-wrap"), "and no config is offered")
        page.fill("#f-projectid", "5001")
        page.fill("#f-username", "")
        check(page.is_visible("#result-status .note"), "a missing login name is a warning, not a blocker")
        check(page.is_visible("#result-wrap"), "config still offered without a login name")
        page.fill("#f-username", "you@example.com")
        page.click("#addact")
        check(page.locator("#actrows .actrow").count() == 2, "activity rows can be added")
        page.locator("#actrows .actrow").nth(1).locator("button").click()
        check(page.locator("#actrows .actrow").count() == 1, "and removed")
        page.uncheck("#f-expenses")
        check("expense_map" not in page.inner_text("#out-config"), "unticking expenses drops expense_map")
        page.check("#f-expenses")

        # --- ids, week, help ---
        page.click("#tab-ids")
        check("re_invoice_project.id" in page.inner_text("#panel-ids"), "ids tab explains the expense project id")
        page.click("#tab-week")
        check(page.locator("#weekSteps > li").count() == 4, "weekly routine has its steps")
        page.click("#wk-phone")
        check("Start a Claude Code session" in page.inner_text("#weekSteps"), "weekly routine switches to phone")
        page.click("#tab-help")
        total = page.locator("#helplist details").count()
        page.fill("#helpq", "401")
        check(0 < page.locator("#helplist details").count() < total, "troubleshooting filter narrows the list")
        check("HTTP 401" in page.inner_text("#helplist"), "and finds the 401 entry")
        page.fill("#helpq", "zzzzzz")
        check("Nothing matches" in page.inner_text("#helplist"), "no match gives a hint")

        # --- reset ---
        page.click("#reset")
        page.click("#tab-guide")
        check(not page.is_visible("#stepsCard"), "clearing saved progress resets the route")
        page.click("#tab-builder")
        check(page.input_value("#f-userid") == "", "and the form")
        stored = page.evaluate("window.localStorage.getItem('time-assistant-guide-v1')")
        check(stored is None, "nothing is left in browser storage after clearing")

        # --- accessibility basics ---
        page.click("#tab-guide")
        page.click("#routes .route[data-route=computer]")
        unlabeled = page.evaluate("""() => [...document.querySelectorAll('input,select,textarea')].filter(e => {
            if (e.type === 'hidden') return false;
            const id = e.id; const byFor = id && document.querySelector('label[for="'+id+'"]');
            return !(byFor || e.closest('label') || e.getAttribute('aria-label'));
        }).map(e => e.id || e.outerHTML.slice(0, 60))""")
        check(unlabeled == [], f"every control has a label ({unlabeled})")
        check(page.evaluate("[...document.querySelectorAll('button')].every(b => (b.textContent||'').trim() || b.getAttribute('aria-label'))"),
              "every button has a name")
        check(page.evaluate("document.querySelectorAll('[role=tab]').length") == 5 and
              page.evaluate("document.querySelectorAll('[aria-selected=true]').length") == 1, "tabs expose their selected state")
        if shots:
            page.screenshot(path=os.path.join(shots, "desktop-guide.png"), full_page=False)
            page.click("#tab-builder")
            page.screenshot(path=os.path.join(shots, "desktop-builder.png"), full_page=True)

        # --- phone width and dark mode ---
        for name, scheme in (("phone-light", "light"), ("phone-dark", "dark")):
            mctx = browser.new_context(viewport={"width": 375, "height": 800}, color_scheme=scheme, is_mobile=True, device_scale_factor=2)
            m = mctx.new_page()
            m.goto(GUIDE)
            m.click("#routes .route[data-route=computer]")
            for tab in ("builder", "guide", "ids", "week", "help"):
                m.click(f"#tab-{tab}")
                w = m.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
                check(w[0] <= w[1], f"{name}: no horizontal scroll on the {tab} tab ({w[0]} <= {w[1]})")
            bg = m.evaluate("getComputedStyle(document.body).backgroundColor")
            check((scheme == "dark") == (sum(int(x) for x in bg[4:-1].split(",")[:3]) < 200), f"{name}: page follows the colour scheme ({bg})")
            if shots:
                m.click("#tab-guide")
                m.screenshot(path=os.path.join(shots, f"{name}.png"), full_page=False)
            mctx.close()

        # --- global ---
        check(errors == [], f"no console errors or warnings {errors}")
        outside = [u for u in requests if not u.startswith("file://") and not u.startswith("data:") and not u.startswith("blob:")]
        check(outside == [], f"no network requests {outside}")
        browser.close()
    print(f"\n{len(passed)} checks passed")


if __name__ == "__main__":
    main()
