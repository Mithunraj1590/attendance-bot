# 🕒 Automated Attendance Bot (Cloud / Server-Based)

Runs automated check-in and check-out for your company attendance portal 100% in the cloud via **GitHub Actions** (free).
Your local PC can be **completely shut down or offline**, and the bot will still execute at your scheduled time windows.

---

## 🚀 Key Features

- **Runs Without Your PC**: Hosted on GitHub Actions' cloud runners 24/7.
- **Natural Human Jitter**: Adds randomized delays (e.g., 0–10 mins) so punches don't look automated.
- **Telegram Notifications with Screenshot**: Receive instant confirmation or failure alerts with a screenshot directly on your phone.
- **One-Click Manual Run**: Trigger check-in or check-out anytime from GitHub web UI.
- **Credential Protection**: Passwords and URLs are encrypted in GitHub Secrets.

---

## 🛠️ Step-by-Step Setup

### Step 1: Create a Private GitHub Repository
1. Go to [GitHub New Repo](https://github.com/new).
2. Repository name: `attendance-bot` (or any name you like).
3. **IMPORTANT**: Select **Private** so your repository and code are completely private.
4. Click **Create repository**.

### Step 2: Push this Project to GitHub
Open your terminal in this project folder (`d:\PERSONAL\auto`) and run:

```bash
git init
git add .
git commit -m "Initial commit for attendance automation"
git branch -M main
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/attendance-bot.git
git push -u origin main
```

---

### Step 3: Add Your Secrets in GitHub
1. Open your repository on GitHub.
2. Go to **Settings** > **Secrets and variables** > **Actions**.
3. Under **Repository secrets**, click **New repository secret** and add:

| Secret Name | Value Example | Description |
|---|---|---|
| `PORTAL_URL` | `https://portal.mycompany.com/login` | Login URL of your portal |
| `PORTAL_USERNAME` | `john.doe@company.com` | Your username or email |
| `PORTAL_PASSWORD` | `MySecretPassword123` | Your account password |
| `TELEGRAM_BOT_TOKEN` | *(Optional)* `123456:ABC-DEF...` | Telegram bot token from `@BotFather` |
| `TELEGRAM_CHAT_ID` | *(Optional)* `987654321` | Your personal Telegram chat ID |

> **Note on Selectors**: If your company portal uses standard buttons ("Sign In", "Check In", "Check Out"), the bot **auto-detects** them! If your company uses custom button IDs or classes, you can also add optional secrets: `CHECKIN_SELECTOR` and `CHECKOUT_SELECTOR`.

---

### Step 4: Adjust Your Working Hours / Schedule
The automated schedule is defined in [`.github/workflows/attendance.yml`](.github/workflows/attendance.yml).
GitHub Actions uses **UTC** time. Convert your local hours to UTC:

> **Example for India Standard Time (IST = UTC + 5:30):**
> - **Morning Check-In at 9:00 AM IST**: `30 3 * * 1-5` (03:30 UTC, Mon–Fri)
> - **Evening Check-Out at 6:00 PM IST**: `30 12 * * 1-5` (12:30 UTC, Mon–Fri)

To change the time, edit lines 10 & 15 of `.github/workflows/attendance.yml`.

---

### Step 5: Test It Immediately (1-Click Run)
You don't have to wait for the schedule to verify it works:
1. In your GitHub repository, click on the **Actions** tab.
2. Select **Attendance Automation** from the left sidebar.
3. Click **Run workflow** dropdown on the right.
4. Choose `checkin` or `status` and click the green **Run workflow** button.
5. In 1–2 minutes, it will finish. You can inspect the step logs and download the screenshot artifact!

---

## 📱 (Optional) Setting up Telegram Alerts
To receive a photo proof on your phone whenever check-in or check-out completes:
1. Open Telegram and search for `@BotFather`.
2. Send `/newbot`, follow prompts to name it, and copy the **API Token**.
3. Search for `@userinfobot` on Telegram and click Start to get your numeric **Id** (`TELEGRAM_CHAT_ID`).
4. Send any dummy message (e.g. `hello`) to your new bot once to initialize chat.
5. Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to GitHub Secrets.

---

## 💻 Local Testing & Debugging
If you want to test locally on your PC before pushing:
1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Fill in your credentials in `.env`.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```
4. Test run:
   ```bash
   python checkin_bot.py --action checkin --no-jitter
   ```
5. Or run the visual inspector to view the browser live:
   ```bash
   python inspect_portal.py
   ```
