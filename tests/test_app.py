import asyncio
from datetime import timedelta

from jobbot.app import JobBot
from jobbot.config import Settings
from jobbot.models import Job, utcnow
from jobbot.store import Store


class FakeTG:
    def __init__(self):
        self.calls = []
        self.next_id = 100

    async def send(self, chat_id, text, buttons=None, preview=False):
        self.next_id += 1
        self.calls.append(("send", chat_id, text, buttons))
        return {"message_id": self.next_id}

    async def edit_text(self, chat_id, mid, text, buttons=None):
        self.calls.append(("edit_text", chat_id, text, buttons))

    async def edit_buttons(self, chat_id, mid, buttons):
        self.calls.append(("edit_buttons", chat_id, buttons))

    async def answer(self, cid, text="", alert=False):
        self.calls.append(("answer", text))

    async def call(self, method, **kw):
        self.calls.append((method, kw))


def make_job(i, minutes=3, **kw):
    d = dict(source="remotive", source_id=str(i), title=f"Python Developer {i}", company=f"Co{i}",
             url=f"https://x.test/{i}", location="Worldwide", posted_at=utcnow() - timedelta(minutes=minutes))
    d.update(kw)
    return Job(**d)


def make_bot(store=None, **settings):
    s = Settings()
    s.linkedin_details = False
    s.send_delay_sec = 0
    for k, v in settings.items():
        setattr(s, k, v)
    bot = JobBot(s, store or Store(), token="t", chat_id="-100", admin_ids=set())
    bot.tg = FakeTG()
    return bot


def run(coro):
    return asyncio.run(coro)


def test_scan_sends_freshest_first_and_dedupes():
    bot = make_bot(max_per_cycle=10)
    jobs = [make_job(1, 30), make_job(2, 2), make_job(3, 10),
            make_job(4, 1, source="himalayas", title="Python Developer 2", company="Co2"),  # same as #2
            make_job(5, 1, title="Senior Python Developer")]                                 # filtered

    async def fake_collect():
        return list(jobs)
    bot._collect = fake_collect
    res = run(bot.scan_once())
    sent = [c for c in bot.tg.calls if c[0] == "send"]
    assert res["sent"] == 3 == len(sent)
    assert "Python Developer 2" in sent[0][2]                  # freshest first
    # second scan: nothing new
    bot.tg.calls.clear()
    assert run(bot.scan_once())["sent"] == 0


def test_max_per_cycle_and_leftovers_next_cycle():
    bot = make_bot(max_per_cycle=2)
    jobs = [make_job(i, i) for i in range(1, 6)]

    async def fake_collect():
        return list(jobs)
    bot._collect = fake_collect
    assert run(bot.scan_once())["sent"] == 2
    assert run(bot.scan_once())["sent"] == 2
    assert run(bot.scan_once())["sent"] == 1


def test_failed_send_is_retried_later():
    bot = make_bot()
    from jobbot.telegram import TelegramError

    async def boom(*a, **k):
        raise TelegramError("chat not found")
    bot.tg.send = boom
    assert run(bot.deliver(make_job(1))) is False
    assert not bot.store.is_seen(make_job(1))


def test_commands_change_and_persist_settings():
    store = Store()
    bot = make_bot(store)
    run(bot.handle_command("-100", "/addkw Go Developer, Rust Developer"))
    run(bot.handle_command("-100", "/rmkw Java Developer"))
    run(bot.handle_command("-100", "/fresh@MyJobBot 10"))
    run(bot.handle_command("-100", "/mode remote_hybrid"))
    run(bot.handle_command("-100", "/exp entry, associate, bogus"))
    run(bot.handle_command("-100", "/years off"))
    run(bot.handle_command("-100", "/exclude php"))
    run(bot.handle_command("-100", "/include lead"))
    run(bot.handle_command("-100", "/addco greenhouse Stripe"))
    run(bot.handle_command("-100", "/pause"))
    s = bot.settings
    assert "Go Developer" in s.keywords and "Java Developer" not in s.keywords
    assert s.linkedin_max_age_min == 10 and s.work_mode == "remote_hybrid"
    assert s.experience == ["entry", "associate"] and s.max_years_experience == -1
    assert "php" in s.exclude_title_words and "lead" not in s.exclude_title_words
    assert "stripe" in s.greenhouse_companies and s.paused
    # a restarted bot on the same DB keeps the changes
    again = make_bot(store)
    assert again.settings.linkedin_max_age_min == 10 and again.settings.paused
    assert "Go Developer" in again.settings.keywords


def test_every_command_replies():
    bot = make_bot()
    for cmd in ["/start", "/help", "/settings", "/status", "/saved", "/applied", "/latest",
                "/keywords", "/muted", "/scan", "/resume", "/addco", "/nonsense"]:
        bot.tg.calls.clear()
        run(bot.handle_command("-100", cmd))
        assert bot.tg.calls and bot.tg.calls[-1][0] == "send", cmd


def cq(data, mid=5, user=42, chat=-100):
    return {"id": "cb1", "data": data, "from": {"id": user, "first_name": f"U{user}"},
            "message": {"chat": {"id": chat}, "message_id": mid}}


def test_saves_are_per_person():
    bot = make_bot()
    a, b = bot.store.record(make_job(1)), bot.store.record(make_job(2))
    run(bot.handle_callback(cq(f"save:{a}", user=1)))
    run(bot.handle_callback(cq(f"save:{a}", user=2)))
    run(bot.handle_callback(cq(f"applied:{b}", user=2)))
    st = bot.store
    assert [i for i, _ in st.user_jobs(1, "saved")] == [a]
    assert [i for i, _ in st.user_jobs(2, "applied")] == [b]
    assert st.user_jobs(1, "applied") == []                       # user 1 never applied
    assert st.job_counts(a) == {"saved": 2}
    edits = [c for c in bot.tg.calls if c[0] == "edit_buttons"]
    assert edits[1][2][1][0]["text"] == "⭐ Save · 2"               # shared count on the message
    run(bot.handle_callback(cq(f"save:{a}", user=1)))              # tap again = undo, only for user 1
    assert st.user_jobs(1, "saved") == [] and st.job_counts(a) == {"saved": 1}
    assert bot.tg.calls[-1] == ("answer", "Removed from your saved jobs")
    run(bot.handle_callback(cq(f"applied:{a}", user=2)))           # saved -> applied moves it
    assert st.user_jobs(2, "saved") == [] and len(st.user_jobs(2, "applied")) == 2


def test_not_for_me_is_personal_and_keeps_message():
    bot = make_bot()
    a = bot.store.record(make_job(1))
    run(bot.handle_callback(cq(f"save:{a}", user=1)))
    run(bot.handle_callback(cq(f"hide:{a}", user=1)))
    assert bot.store.user_status(1, a) == "hidden" and bot.store.user_jobs(1, "saved") == []
    assert not any(c[0] == "deleteMessage" for c in bot.tg.calls)
    run(bot.handle_callback(cq("save:999999")))
    assert bot.tg.calls[-1] == ("answer", "That job is gone.")


def test_mute_is_group_wide_and_admin_only_when_admins_set():
    bot = make_bot()
    a = bot.store.record(make_job(1))
    bot.admin_ids = {7}
    run(bot.handle_callback(cq(f"mute:{a}", user=5)))
    assert "Co1" not in bot.settings.muted_companies
    run(bot.handle_callback(cq(f"mute:{a}", user=7)))
    assert "Co1" in bot.settings.muted_companies


def test_saved_list_goes_to_private_chat():
    bot = make_bot()
    bot.username = "kb_jobsender_bot"
    a = bot.store.record(make_job(1))
    bot.store.set_user_status(42, a, "saved")
    user = {"id": 42, "first_name": "Asha"}
    run(bot.handle_command("-100", "/saved", user))
    to_user = [c for c in bot.tg.calls if c[0] == "send" and c[1] == 42]
    assert to_user and "Python Developer 1" in to_user[0][2] and "Total: ⭐ 1 saved" in to_user[0][2]
    assert "sent your list" in bot.tg.calls[-1][2]
    # someone else's /saved shows their own (empty) list
    bot.tg.calls.clear()
    run(bot.handle_command(9, "/saved", {"id": 9, "first_name": "B"}))
    assert "Nothing here yet" in bot.tg.calls[-1][2]


def test_saved_when_user_never_started_bot():
    from jobbot.telegram import TelegramError
    bot = make_bot()
    bot.username = "kb_jobsender_bot"
    real_send = bot.tg.send

    async def send(chat_id, text, buttons=None, preview=False):
        if chat_id == 42:
            raise TelegramError("Forbidden: bot can't initiate conversation with a user")
        return await real_send(chat_id, text, buttons)
    bot.tg.send = send
    run(bot.handle_command("-100", "/applied", {"id": 42, "first_name": "Asha"}))
    last = bot.tg.calls[-1]
    assert "press <b>Start</b>" in last[2]
    assert last[3][0][0]["url"] == "https://t.me/kb_jobsender_bot?start=applied"


def test_private_chat_only_for_group_members():
    bot = make_bot()
    bot.admin_ids = {7}
    members = {42: "member", 13: "left"}

    async def call(method, **kw):
        bot.tg.calls.append((method, kw))
        if method == "getChatMember":
            return {"status": members.get(kw["user_id"], "left")}
    bot.tg.call = call
    pm = lambda uid, text: {"update_id": 1, "message": {"text": text, "chat": {"id": uid, "type": "private"},
                                                         "from": {"id": uid, "first_name": "X"}}}
    run(bot._dispatch(pm(42, "/saved")))
    assert "Nothing here yet" in bot.tg.calls[-1][2]                 # member gets their list
    run(bot._dispatch(pm(13, "/saved")))
    assert "Join it first" in bot.tg.calls[-1][2]                    # outsider refused
    run(bot._dispatch(pm(42, "/pause")))
    assert not bot.settings.paused                                   # members can't change settings
    # group taps on job buttons work for everyone even with admins set; settings taps don't
    a = bot.store.record(make_job(1))
    run(bot._dispatch({"update_id": 2, "callback_query": cq(f"save:{a}", user=42)}))
    assert bot.store.user_status(42, a) == "saved"
    run(bot._dispatch({"update_id": 3, "callback_query": cq("set:pause", user=42)}))
    assert not bot.settings.paused and bot.tg.calls[-1] == ("answer", "Only admins can change settings.")


def test_settings_panel_toggles():
    bot = make_bot()
    s = bot.settings
    run(bot.handle_callback(cq("set:mode")))
    assert s.work_mode == "remote_hybrid"
    run(bot.handle_callback(cq("set:fresh")))
    assert s.linkedin_max_age_min == 30
    run(bot.handle_callback(cq("set:years")))
    assert s.max_years_experience == 3
    run(bot.handle_callback(cq("exp:internship")))
    assert "internship" not in s.experience
    run(bot.handle_callback(cq("set:region")))
    assert s.region_filter is False
    run(bot.handle_callback(cq("set:style")))
    assert s.style == "compact"
    run(bot.handle_callback(cq("src:remoteok")))
    assert s.sources["remoteok"] is False
    run(bot.handle_callback(cq("set:pause")))
    assert s.paused
    edits = [c for c in bot.tg.calls if c[0] == "edit_text"]
    assert edits and "PAUSED" in edits[-1][2]


def test_access_control():
    bot = make_bot()
    assert bot._allowed(-100, 5)                 # anyone in the bot's chat
    assert not bot._allowed(-999, 5)             # strangers elsewhere
    bot.admin_ids = {7}
    assert bot._allowed(-999, 7)                 # admin anywhere
    assert not bot._allowed(-100, 5)             # non-admin in group
    assert bot._allowed(-100, None)              # channel posts (no user)


def test_dispatch_ignores_plain_text_and_strangers():
    bot = make_bot()
    run(bot._dispatch({"update_id": 1, "message": {"text": "hello", "chat": {"id": -100}}}))
    run(bot._dispatch({"update_id": 2, "message": {"text": "/pause", "chat": {"id": -5}, "from": {"id": 1}}}))
    assert not bot.tg.calls and not bot.settings.paused
    run(bot._dispatch({"update_id": 3, "channel_post": {"text": "/pause", "chat": {"id": -100}}}))
    assert bot.settings.paused


def test_store_stats_and_fingerprint():
    st = Store()
    a = make_job(1)
    st.record(a)
    twin = make_job(2, title=a.title, company=a.company.upper(), source="jobicy")
    assert st.is_seen(twin)                       # same job on another board
    assert st.stats()["today"] == 1
    st.kv_set("x", {"a": 1})
    assert st.kv_get("x") == {"a": 1} and st.kv_get("missing", 5) == 5


def test_scan_interval_button_and_command():
    bot = make_bot()
    s = bot.settings
    assert s.scan_interval_sec == 300
    run(bot.handle_callback(cq("set:interval")))
    assert s.scan_interval_sec == 600
    run(bot.handle_callback(cq("set:interval")))
    assert s.scan_interval_sec == 60
    assert bot.tg.calls[-1] == ("answer", "🔁 Every 1 min. LinkedIn may block more often.")
    assert "🔁 Scan every: 1 min" in str(bot.settings_buttons())
    run(bot.handle_callback(cq("set:interval")))
    assert s.scan_interval_sec == 120
    run(bot.handle_command("-100", "/interval 1"))
    assert s.scan_interval_sec == 60 and "blocks" in bot.tg.calls[-1][2]
    run(bot.handle_command("-100", "/interval 999"))
    assert s.scan_interval_sec == 3600
    assert make_bot(bot.store).settings.scan_interval_sec == 3600     # survives restart


def test_new_interval_applies_without_waiting_old_one():
    import time
    bot = make_bot(scan_interval_sec=3600)
    scans = []

    async def fake_scan():
        scans.append(time.time())
        if len(scans) == 1:
            bot.update(scan_interval_sec=1)        # changed mid-wait from the panel
        return {}
    bot.scan_once = fake_scan

    async def go():
        task = asyncio.create_task(bot.scanner_loop())
        await asyncio.sleep(4.5)
        task.cancel()
    run(go())
    assert len(scans) >= 2                         # didn't sit out the old 1-hour wait
