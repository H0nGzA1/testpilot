"""Capture a logged-in browser session (storage_state) WITHOUT exposing your password.

    python scripts/capture_login.py https://<target-url>  [auth.json]

Opens a real (headed) Chromium. You log in by hand, then press Enter in this
terminal. The resulting cookies + localStorage are written to auth.json, whose
contents go into a project's login_state so runs start already logged in.
"""

from __future__ import annotations

import asyncio
import sys

from playwright.async_api import async_playwright


async def main(url: str, out: str) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(url)
        print(f"\n>>> A browser opened at {url}")
        print(">>> Log in by hand, land on a logged-in page, then press Enter here...")
        await asyncio.get_running_loop().run_in_executor(None, input)
        await ctx.storage_state(path=out)
        print(f">>> Saved login state to {out}")
        await browser.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python scripts/capture_login.py <url> [auth.json]")
        raise SystemExit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "auth.json"))
