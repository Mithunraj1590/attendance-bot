#!/usr/bin/env python3
"""
Portal Inspector & Interactive Testing Tool
Runs locally with a visible browser window so you can test login
and find the exact button selectors for your company portal.
"""

import os
import sys
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

PORTAL_URL = os.getenv("PORTAL_URL", "").strip()
PORTAL_USERNAME = os.getenv("PORTAL_USERNAME", "").strip()
PORTAL_PASSWORD = os.getenv("PORTAL_PASSWORD", "").strip()


def inspect():
    url = PORTAL_URL or input("Enter your portal URL: ").strip()
    if not url:
        print("Error: Portal URL is required.")
        sys.exit(1)

    print("\n==========================================")
    print("Launching visible browser window...")
    print("You can interact with the page, inspect elements,")
    print("or test your login credentials.")
    print("Close the browser window when finished.")
    print("==========================================\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(viewport={"width": 1366, "height": 768})
        page = context.new_page()

        page.goto(url)

        if PORTAL_USERNAME and PORTAL_PASSWORD:
            print("[*] Found credentials in .env. Attempting autofill...")
            try:
                # Try filling username
                for sel in ['input[type="email"]', 'input[name*="user" i]', 'input[type="text"]']:
                    if page.locator(sel).first.is_visible(timeout=2000):
                        page.locator(sel).first.fill(PORTAL_USERNAME)
                        print(f"[+] Filled username in {sel}")
                        break

                # Try filling password
                for sel in ['input[type="password"]', 'input[name*="pass" i]']:
                    if page.locator(sel).first.is_visible(timeout=2000):
                        page.locator(sel).first.fill(PORTAL_PASSWORD)
                        print(f"[+] Filled password in {sel}")
                        break
            except Exception as e:
                print(f"[!] Autofill note: {e}")

        print("\nBrowser is open. Waiting for you to close it...")
        try:
            page.wait_for_close(timeout=0)
        except Exception:
            pass


if __name__ == "__main__":
    inspect()
