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
            print("[*] Attempting login...")
            username_candidates = [
                'input[type="email"]',
                'input[name*="user" i]',
                'input[name*="email" i]',
                'input[id*="user" i]',
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
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Sign In")',
                'button:has-text("Log In")',
                'button:has-text("Login")',
                'button:has-text("Submit")',
                'button:has-text("Next")',
            ]

            user_filled = find_and_fill(page, USERNAME_SELECTOR, username_candidates, PORTAL_USERNAME, "Username/Email")
            if not user_filled:
                raise RuntimeError("Could not find Username/Email input field.")

            # Some modern portals have a 2-step login (First enter email, click Next, then password)
            if not page.locator('input[type="password"]').is_visible():
                print("[*] Password field not yet visible, checking for 'Next' button...")
                find_and_click(page, LOGIN_SUBMIT_SELECTOR, submit_candidates, "Next", timeout_ms=3000)
                page.wait_for_timeout(2000)

            pass_filled = find_and_fill(page, PASSWORD_SELECTOR, password_candidates, PORTAL_PASSWORD, "Password")
            if not pass_filled:
                raise RuntimeError("Could not find Password input field.")

            login_clicked = find_and_click(page, LOGIN_SUBMIT_SELECTOR, submit_candidates, "Login Submit")
            if not login_clicked:
                # Press Enter as fallback
                page.keyboard.press("Enter")
                print("[*] Pressed Enter key to submit login.")

            # Wait for dashboard / post-login page load
            print("[*] Waiting for dashboard navigation...")
            page.wait_for_load_state("networkidle", timeout=30000)
            page.wait_for_timeout(5000)

            # Dismiss any announcement or welcome modal if present
            for close_sel in ['button[aria-label="Close"]', 'button:has-text("Remind me later")', 'button:has-text("Dismiss")', '.close', 'button:has-text("Later")']:
                try:
                    if page.locator(close_sel).first.is_visible(timeout=1000):
                        page.locator(close_sel).first.click()
                        page.wait_for_timeout(1000)
                except Exception:
                    pass

            # --- STEP 2: CHECKIN / CHECKOUT ACTION ---
            if action.lower() == "checkin":
                action_name = "Check-in"
                candidates = [
                    'button:has-text("Web Check In")',
                    'button:has-text("Web Check-in")',
                    'button:has-text("Web Clock In")',
                    'button:has-text("Web Clock-in")',
                    'button:has-text("Check In")',
                    'button:has-text("Check-in")',
                    'button:has-text("Checkin")',
                    'button:has-text("Clock In")',
                    'button:has-text("Clock-in")',
                    'button:has-text("Punch In")',
                    'button:has-text("Punch-in")',
                    'button:has-text("Mark Attendance")',
                    'a:has-text("Web Check In")',
                    'a:has-text("Check In")',
                    'a:has-text("Clock In")',
                    'div[role="button"]:has-text("Check In")',
                    'div[role="button"]:has-text("Clock In")',
                    'span:has-text("Web Check In")',
                    'span:has-text("Web Check-In")',
                    'span:has-text("Check In")',
                    '[aria-label*="Check In" i]',
                    '[aria-label*="Clock In" i]',
                    '[title*="Check In" i]',
                    '[title*="Clock In" i]',
                ]
                selector = CHECKIN_SELECTOR
            elif action.lower() == "checkout":
                action_name = "Check-out"
                candidates = [
                    'button:has-text("Web Check Out")',
                    'button:has-text("Web Check-out")',
                    'button:has-text("Web Clock Out")',
                    'button:has-text("Web Clock-out")',
                    'button:has-text("Check Out")',
                    'button:has-text("Check-out")',
                    'button:has-text("Checkout")',
                    'button:has-text("Clock Out")',
                    'button:has-text("Clock-out")',
                    'button:has-text("Punch Out")',
                    'button:has-text("Punch-out")',
                    'a:has-text("Web Check Out")',
                    'a:has-text("Check Out")',
                    'a:has-text("Clock Out")',
                    'div[role="button"]:has-text("Check Out")',
                    'div[role="button"]:has-text("Clock Out")',
                    'span:has-text("Web Check Out")',
                    'span:has-text("Web Check-Out")',
                    'span:has-text("Check Out")',
                    '[aria-label*="Check Out" i]',
                    '[aria-label*="Clock Out" i]',
                    '[title*="Check Out" i]',
                    '[title*="Clock Out" i]',
                ]
                selector = CHECKOUT_SELECTOR
            elif action.lower() == "status":
                action_name = "Status Check"
                candidates = []
                selector = None
            else:
                raise ValueError(f"Unknown action: {action}. Use 'checkin' or 'checkout'.")

            if selector or candidates:
                print(f"[*] Looking for {action_name} button...")
                action_clicked = find_and_click(page, selector, candidates, action_name, timeout_ms=8000)

                if action_clicked:
                    print(f"[✓] {action_name} button clicked successfully.")
                    page.wait_for_timeout(3000)

                    # Look for modal confirm button (e.g. "Confirm", "Yes", "OK") if a popup appears
                    confirm_candidates = [
                        'button:has-text("Confirm")',
                        'button:has-text("Yes")',
                        'button:has-text("OK")',
                        'button:has-text("Submit")',
                        'button:has-text("Proceed")',
                    ]
                    find_and_click(page, "", confirm_candidates, "Modal Confirmation", timeout_ms=3000)
                    page.wait_for_timeout(3000)
                else:
                    print(f"[!] Warning: Could not find or click {action_name} button with default selectors.")
                    raise RuntimeError(f"Could not find or click the {action_name} button. The portal may use a custom button selector or require navigating to an Attendance section. Please check the screenshot artifact.")

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
