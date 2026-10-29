"""Remote Job Radar — run:  python main.py            (live, posts to Telegram)
                             python main.py --dry-run  (one scan, print to console)
                             python main.py --once     (one scan, post to Telegram, exit)"""
import argparse
import asyncio
import logging
import sys

from jobbot.app import JobBot
from jobbot.config import ROOT, load_env, load_settings
from jobbot.store import Store


def main():
    ap = argparse.ArgumentParser(description="Remote Job Radar Telegram bot")
    ap.add_argument("--dry-run", action="store_true", help="scan once and print jobs, send nothing")
    ap.add_argument("--once", action="store_true", help="scan once, post to Telegram, then exit")
    ap.add_argument("--db", default=str(ROOT / "jobbot.db"), help="SQLite file (default jobbot.db)")
    ap.add_argument("--limit", type=int, help="max jobs to send per scan (overrides config)")
    ap.add_argument("--reset-webhook", action="store_true",
                    help="remove a webhook so this script receives button taps and commands")
    ap.add_argument("-v", "--verbose", action="store_true", help="log why each job was skipped")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # emoji on Windows consoles
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    env = load_env()
    if not args.dry_run and not (env["token"] and env["chat_id"]):
        sys.exit("Set BOT_TOKEN and CHAT_ID in .env (see .env.example)")
    if args.reset_webhook:
        import httpx
        r = httpx.post(f"https://api.telegram.org/bot{env['token']}/deleteWebhook", timeout=20).json()
        sys.exit("Webhook removed." if r.get("ok") else f"Failed: {r}")
    store = Store(":memory:" if args.dry_run else args.db)
    settings = load_settings()
    if args.limit:
        settings.max_per_cycle = args.limit
    bot = JobBot(settings, store, env["token"], env["chat_id"], env["admin_ids"], dry_run=args.dry_run)
    try:
        asyncio.run(bot.run(once=args.once))
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
