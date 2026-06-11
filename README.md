# Driest-region weather bot

Checks daily rain probability for cities across **Lithuania, Latvia and Poland**
over a target window (default **2026-06-13 → 2026-06-21**), ranks them driest →
wettest, and posts the winner to **Telegram**.

- **Weather data:** [Open-Meteo](https://open-meteo.com) forecast API — free, no API key, ~16-day horizon.
- **Delivery:** Telegram Bot API.
- **Hosting:** GitHub Actions cron (free, no server to maintain).

## What a message looks like

```
Driest route 2026-06-13 -> 2026-06-21

Where to head each day for the lowest rain chance:

Sat 13 Jun  ->  Krakow, PL  10%, 0.0 mm
    backup: Wroclaw, PL (15%)
Sun 14 Jun  ->  Vilnius, LT  5%, 0.0 mm
    backup: Kaunas, LT (12%)
Mon 15 Jun  ->  Riga, LV  8%, 0.0 mm
    backup: Liepaja, LV (14%)
...

If you'd rather stay put: Krakow, PL is the driest single base overall (9% avg).
```

Each day points you toward the city (across LT/LV/PL) with the lowest rain
chance, plus a backup direction. The closing line gives the single best base if
you'd rather not move every day.

---

## 1. Create the Telegram bot (one-time, ~2 min)

1. In Telegram, open a chat with **@BotFather**.
2. Send `/newbot`, pick a name and username. BotFather replies with a **token**
   like `123456:ABC...` — that is your `TELEGRAM_BOT_TOKEN`.
3. Get your **chat id**:
   - Send any message to your new bot first (bots can't message you until you do).
   - Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser.
   - Find `"chat":{"id":...}` — that number is your `TELEGRAM_CHAT_ID`.
   - For a group, add the bot to the group, post a message, then read `getUpdates`
     the same way (group ids are usually negative).

## 2. Test it locally (optional but recommended)

```bash
pip install -r requirements.txt

# See the message without sending anything:
python weather_bot.py --dry-run

# Actually send to Telegram:
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export TELEGRAM_CHAT_ID="123456789"
python weather_bot.py
```

> If the target window is more than 16 days away, Open-Meteo has no forecast yet,
> so the script prints a notice and exits without sending. This is expected.

## 3. Deploy on GitHub Actions (free, always-on)

1. Create a new GitHub repo and push these files:
   ```bash
   git init
   git add .
   git commit -m "weather bot"
   git branch -M main
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
2. In the repo: **Settings → Secrets and variables → Actions → New repository secret**.
   Add two secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. The workflow in `.github/workflows/weather.yml` runs **daily at 06:00 UTC**.
   To test immediately: **Actions tab → weather-bot → Run workflow**.

That's it — it's live.

## Customising

- **Cities:** edit the `REGIONS` list in `weather_bot.py`.
- **Dates:** change `START_DATE` / `END_DATE` in the workflow (or your shell).
- **Frequency:** edit the `cron:` line in the workflow.
  `0 6 * * *` = daily 06:00 UTC. `0 6,18 * * *` = twice daily.
- **Ranking rule:** `rank()` sorts by average rain probability, tie-broken by
  total precipitation. Swap in `max_rain_prob` if you'd rather minimise the
  single worst day.

## Notes

- GitHub's scheduled runs can be delayed several minutes at peak times, and
  Actions disables schedules on repos with no activity for 60 days — push a
  commit occasionally if you keep it long-term.
- Rain probability is a forecast, not a guarantee, and accuracy drops the
  further out the date is.
