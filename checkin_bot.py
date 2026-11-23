#!/usr/bin/env python3
"""
Automated Attendance Check-in / Check-out Bot
Runs headlessly in GitHub Actions or any Linux/Cloud server.
"""

import os
import sys
import time
import random
import argparse
import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Load environment variables from .env if present
load_dotenv()

PORTAL_URL = os.getenv("PORTAL_URL", "").strip()
PORTAL_USERNAME = os.getenv("PORTAL_USERNAME", "").strip()
PORTAL_PASSWORD = os.getenv("PORTAL_PASSWORD", "").strip()

# Selectors (Defaults will try auto-discovery if left empty)
USERNAME_SELECTOR = os.getenv("USERNAME_SELECTOR", "").strip()
PASSWORD_SELECTOR = os.getenv("PASSWORD_SELECTOR", "").strip()
LOGIN_SUBMIT_SELECTOR = os.getenv("LOGIN_SUBMIT_SELECTOR", "").strip()
CHECKIN_SELECTOR = os.getenv("CHECKIN_SELECTOR", "").strip()
CHECKOUT_SELECTOR = os.getenv("CHECKOUT_SELECTOR", "").strip()

# Telegram Alert Configuration (Optional)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Options
HEADLESS = os.getenv("HEADLESS", "True").lower() in ("true", "1", "yes")
MAX_JITTER_SECONDS = int(os.getenv("MAX_JITTER_SECONDS", "300"))  # Default up to 5 min jitter


def send_telegram_alert(message: str, image_path: str = None):
    """Send text alert and optional screenshot to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] Bot token or chat ID not set. Skipping Telegram notification.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    try:
        if image_path and os.path.exists(image_path):
            photo_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            with open(image_path, "rb") as photo_file:
                res = requests.post(
                    photo_url,
                    data={"chat_id": TELEGRAM_CHAT_ID, "caption": message, "parse_mode": "Markdown"},
                    files={"photo": photo_file},
                    timeout=20,
                )
            if res.ok:
                print("[Telegram] Photo notification sent successfully.")
                return
            else:
                print(f"[Telegram] Failed to send photo: {res.text}. Falling back to text message.")

        # Fallback to text message
        res = requests.post(url, json=payload, timeout=15)
        if res.ok:
            print("[Telegram] Notification sent successfully.")
        else:
            print(f"[Telegram] Failed to send text notification: {res.text}")
    except Exception as e:
        print(f"[Telegram Error] Could not send notification: {e}")


def apply_jitter(max_seconds: int):
    """Apply random delay within a time window so checkins appear natural."""
    if max_seconds <= 0:
        return
    delay = random.randint(10, max_seconds)
    print(f"[*] Applying human jitter delay: waiting {delay} seconds ({delay // 60}m {delay % 60}s)...")
    time.sleep(delay)


def find_and_fill(page, custom_selector: str, candidate_selectors: list, value: str, field_name: str):
    """Attempt to find input field using custom selector or candidate fallbacks."""
    if custom_selector:
        candidate_selectors = [custom_selector] + candidate_selectors

    for sel in candidate_selectors:
        try:
            elem = page.locator(sel).first
            if elem.is_visible(timeout=3000):
                print(f"[+] Found {field_name} using: {sel}")
                elem.click()
                elem.fill(value)
                return True
        except Exception:
            continue
    return False


def find_and_click(page, custom_selector: str, candidate_selectors: list, action_name: str, timeout_ms: int = 5000):
    """Attempt to click element using custom selector or candidate fallbacks."""
    if custom_selector:
        candidate_selectors = [custom_selector] + candidate_selectors

    for sel in candidate_selectors:
        try:
            elem = page.locator(sel).first
            if elem.is_visible(timeout=timeout_ms):
                print(f"[+] Found {action_name} button using: {sel}")
                elem.click()
                return True
        except Exception:
            continue
    return False


def run_attendance(action: str, no_jitter: bool = False):
    """Main execution flow for login and attendance check-in/out."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] Starting attendance task: ACTION = {action.upper()}")

    if not PORTAL_URL or not PORTAL_USERNAME or not PORTAL_PASSWORD:
        err = "ERROR: Missing required credentials (PORTAL_URL, PORTAL_USERNAME, or PORTAL_PASSWORD)."
        print(err)
        send_telegram_alert(f"⚠️ *Attendance Failed*\n{err}")
        sys.exit(1)

    if not no_jitter and MAX_JITTER_SECONDS > 0:
        apply_jitter(MAX_JITTER_SECONDS)

    screenshot_path = "attendance_result.png"

    with sync_playwright() as p:
        # Launch browser with standard desktop user-agent to avoid headless bot detection
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            timezone_id="Asia/Kolkata",
            permissions=["geolocation"],
            geolocation={"latitude": 12.9716, "longitude": 77.5946},
        )

        page = context.new_page()

        try:
            print(f"[*] Navigating to {PORTAL_URL}...")
            page.goto(PORTAL_URL, wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(3000)

            # --- STEP 1: LOGIN ---
            # First check if already logged in / on dashboard
            dashboard_indicator = page.locator('text=/Good morning|Check in|Check out|Apps|OpsHub/i')
            if dashboard_indicator.count() > 0 and dashboard_indicator.first.is_visible():
                print("[+] Already logged into dashboard!")
            else:
                print("[*] Attempting login...")
                username_candidates = [
                    'input[type="email"]',
                    'input[name*="user" i]',
                    'input[name*="login" i]',
                    'input[name*="email" i]',
                    'input[id*="user" i]',
                    'input[id*="login" i]',
                    'input[id*="email" i]',
                    'input[placeholder*="email" i]',
                    'input[placeholder*="username" i]',
                    'input[type="text"]',
                ]
                password_candidates = [
                    'input[type="password"]',
                    'input[name*="pass" i]',
                    'input[id*="pass" i]',
                ]
                submit_candidates = [
                    'button:has-text("Sign In")',
                    'button:has-text("Sign in")',
                    'button:has-text("Log In")',
                    'button:has-text("Login")',
                    'button[type="submit"]',
                    'input[type="submit"]',
                ]

                user_filled = find_and_fill(page, USERNAME_SELECTOR, username_candidates, PORTAL_USERNAME, "Username/Email")
                if not user_filled:
                    raise RuntimeError("Could not find Username/Email input field.")

                # Check if password field is visible; if not, look for Next
                if not page.locator('input[type="password"]').is_visible():
                    print("[*] Password field not yet visible, checking for 'Next' button...")
                    find_and_click(page, LOGIN_SUBMIT_SELECTOR, submit_candidates, "Next", timeout_ms=3000)
                    page.wait_for_timeout(2000)

                pass_filled = find_and_fill(page, PASSWORD_SELECTOR, password_candidates, PORTAL_PASSWORD, "Password")
                if not pass_filled:
                    raise RuntimeError("Could not find Password input field.")

                # Auto-check 'Keep me signed in' if present
                try:
                    keep_in = page.locator('input[type="checkbox"]').first
                    if keep_in.is_visible(timeout=1000) and not keep_in.is_checked():
                        keep_in.check()
                        print("[+] Checked 'Keep me signed in'")
                except Exception:
                    pass

                login_clicked = find_and_click(page, LOGIN_SUBMIT_SELECTOR, submit_candidates, "Sign In Submit")
                if not login_clicked:
                    page.keyboard.press("Enter")
                    print("[*] Pressed Enter key to submit login.")

                # Wait for dashboard to appear
                print("[*] Waiting for OpsHub dashboard...")
                try:
                    page.wait_for_selector('text=/Good morning|Check in|Check out|Apps|OpsHub/i', timeout=25000)
                    print("[+] Dashboard loaded successfully!")
                except Exception as e:
                    print(f"[*] Dashboard selector note: {e}")
                page.wait_for_timeout(4000)

            # Dismiss any announcement or welcome modal if present
            for close_sel in ['button[aria-label="Close"]', 'button:has-text("Remind me later")', 'button:has-text("Dismiss")', '.close', 'button:has-text("Later")']:
                try:
                    if page.locator(close_sel).first.is_visible(timeout=1000):
                        page.locator(close_sel).first.click()
                        page.wait_for_timeout(1000)
                except Exception:
                    pass

            # --- STEP 2: CHECKIN / CHECKOUT ACTION ---
            if action.lower() == "status":
                print("[*] Status check completed. No button clicked.")
            else:
                target_text = "Check in" if action.lower() == "checkin" else "Check out"
                opposite_text = "Check out" if action.lower() == "checkin" else "Check in"
                custom_sel = CHECKIN_SELECTOR if action.lower() == "checkin" else CHECKOUT_SELECTOR

                print(f"[*] Looking for '{target_text}' action...")

                # First check if custom selector provided
                if custom_sel:
                    clicked = find_and_click(page, custom_sel, [], target_text, timeout_ms=8000)
                    if not clicked:
                        raise RuntimeError(f"Could not click custom selector '{custom_sel}'.")
                else:
                    # Look for OpsHub center button or header button
                    # Check if already in desired state (e.g. checkin requested but only checkout exists)
                    target_btn = page.locator(f'button:has-text("{target_text}"), a:has-text("{target_text}"), [role="button"]:has-text("{target_text}")')
                    opposite_btn = page.locator(f'button:has-text("{opposite_text}"), a:has-text("{opposite_text}"), [role="button"]:has-text("{opposite_text}")')

                    t_count = target_btn.count()
                    o_count = opposite_btn.count()
                    print(f"[*] Found {t_count} '{target_text}' button(s) and {o_count} '{opposite_text}' button(s).")

                    if t_count == 0 and o_count > 0:
                        print(f"[✓] You are ALREADY in the correct state! '{opposite_text}' is currently active.")
                    elif t_count == 0:
                        # Fallback to broader text match
                        broad_target = page.locator(f'text="{target_text}"')
                        if broad_target.count() > 0:
                            print(f"[+] Found text '{target_text}'. Clicking...")
                            broad_target.first.click(timeout=5000)
                        else:
                            raise RuntimeError(f"Could not find '{target_text}' button on dashboard. Please check screenshot.")
                    else:
                        # Prioritize visible button (prefer center button if multiple)
                        clicked = False
                        for idx in reversed(range(t_count)):
                            btn = target_btn.nth(idx)
                            try:
                                if btn.is_visible(timeout=2000):
                                    btn.scroll_into_view_if_needed()
                                    btn.click(timeout=5000)
                                    print(f"[✓] Successfully clicked '{target_text}' button (element #{idx+1}).")
                                    clicked = True
                                    page.wait_for_timeout(3000)
                                    break
                            except Exception as err:
                                print(f"[!] Could not click candidate #{idx+1}: {err}")

                        if not clicked:
                            # Force click first match
                            target_btn.first.click(force=True, timeout=5000)
                            print(f"[✓] Force-clicked '{target_text}' button.")
                            page.wait_for_timeout(3000)

                # Look for modal confirm button (e.g. "Confirm", "Yes", "OK") if a popup appears
                confirm_candidates = [
                    'button:has-text("Confirm")',
                    'button:has-text("Yes")',
                    'button:has-text("OK")',
                    'button:has-text("Proceed")',
                ]
                find_and_click(page, "", confirm_candidates, "Modal Confirmation", timeout_ms=3000)
                page.wait_for_timeout(2000)

            # Capture screenshot as proof
            page.screenshot(path=screenshot_path, full_page=False)
            print(f"[✓] Screenshot saved to {screenshot_path}")

            finish_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            msg = (
                f"✅ *Attendance {action.upper()} Success*\n"
                f"📅 Time: `{finish_time}`\n"
                f"🌐 Portal: {PORTAL_URL}\n"
                f"👤 User: `{PORTAL_USERNAME}`"
            )
            send_telegram_alert(msg, screenshot_path)
            print("[✓] Task completed successfully.")

        except Exception as e:
            err_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[X] Execution failed: {e}")
            try:
                page.screenshot(path=screenshot_path, full_page=False)
            except Exception:
                pass
            msg = (
                f"❌ *Attendance {action.upper()} Failed!*\n"
                f"📅 Time: `{err_time}`\n"
                f"⚠️ Error: `{str(e)[:300]}`\n"
                f"Please verify manually!"
            )
            send_telegram_alert(msg, screenshot_path if os.path.exists(screenshot_path) else None)
            sys.exit(1)
        finally:
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automate portal attendance check-in/out.")
    parser.add_argument(
        "--action",
        choices=["checkin", "checkout", "status"],
        required=True,
        help="Action to perform: checkin, checkout, or status",
    )
    parser.add_argument(
        "--no-jitter",
        action="store_true",
        help="Skip random delay (useful for testing)",
    )
    args = parser.parse_args()

    run_attendance(action=args.action, no_jitter=args.no_jitter)
