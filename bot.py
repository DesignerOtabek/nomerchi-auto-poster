# -*- coding: utf-8 -*-
"""
TELEGRAM ULTRA-PRO AUTO-POSTER & LINK JOINER CONTROL CENTER v2.0
- Interactive Group Selector (Guruhlarni bittalab ✅/❌ bosib tanlash)
- Multi-Message Ad Rotator (5 xil e'lon matnlarini almashtirib yuborish)
- Multi-Account Session Rotation (Akkauntlarni navbatma-navbat almashtirish)
- Fast Speed Preset Buttons (30s, 50s, 2m, 5m tugmalari)
- Cybertech Uzbek UI Dashboard
"""

import asyncio, os, sys, re, json, time, random, logging
if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass

from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import (
    UserAlreadyParticipantError, InviteHashExpiredError, InviteHashInvalidError,
    FloodWaitError, RPCError, SessionPasswordNeededError, PhonePasswordFloodError, PasswordHashInvalidError
)
from dotenv import load_dotenv

logging.getLogger('telethon').setLevel(logging.CRITICAL)
load_dotenv()

import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def start_health_server():
    try:
        port = int(os.environ.get("PORT", 8080))
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        server.serve_forever()
    except Exception:
        pass

def self_ping_loop():
    """Ping own URL every 13 min to keep Render free tier awake."""
    import urllib.request
    time.sleep(60)  # Wait 1 min before first ping
    url = "https://nomerchi-auto-poster.onrender.com/"
    while True:
        try:
            urllib.request.urlopen(url, timeout=15)
            print("[PING] Self-ping OK - staying alive!", flush=True)
        except Exception as e:
            print(f"[PING] {e}", flush=True)
        time.sleep(13 * 60)  # 13 minutes

threading.Thread(target=start_health_server, daemon=True).start()
threading.Thread(target=self_ping_loop, daemon=True).start()


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# Use /tmp/sessions on Linux (Render) — always writable
SESSIONS_DIR = "/tmp/sessions" if os.name == "posix" else os.path.join(BASE_DIR, "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

# ── Session Persistence (Render free tier) ─────────
import shutil, base64

def _copy_repo_sessions():
    """Copy bundled session files from repo to /tmp/sessions at startup."""
    repo_sessions = os.path.join(BASE_DIR, "sessions")
    for src_dir in [repo_sessions, BASE_DIR]:
        if not os.path.isdir(src_dir) and src_dir == BASE_DIR:
            continue
        try:
            items = os.listdir(src_dir) if os.path.isdir(src_dir) else []
        except Exception:
            items = []
        for fname in items:
            if fname.endswith(".session") and fname not in ("controller_bot.session", "auto_poster_session.session"):
                src = os.path.join(src_dir, fname)
                dst = os.path.join(SESSIONS_DIR, fname)
                try:
                    if not os.path.exists(dst):
                        shutil.copy2(src, dst)
                        print(f"[SESSION] Copied from repo: {fname}", flush=True)
                except Exception as e:
                    print(f"[SESSION] Copy error: {e}", flush=True)

def _restore_sessions_from_env():
    """Restore sessions from Render env vars SESSION_1..SESSION_10."""
    for i in range(1, 11):
        b64 = os.environ.get(f"SESSION_{i}", "")
        name = os.environ.get(f"SESSION_NAME_{i}", "")
        if b64 and name:
            try:
                data = base64.b64decode(b64)
                path = os.path.join(SESSIONS_DIR, name)
                with open(path, "wb") as f:
                    f.write(data)
                print(f"[SESSION] Restored from env: {name}", flush=True)
            except Exception as e:
                print(f"[SESSION] Restore error {name}: {e}", flush=True)

def save_session_to_env(phone):
    """Save session file to Render env var for persistence across restarts."""
    session_path = os.path.join(SESSIONS_DIR, f"{phone}.session")
    render_key = os.environ.get("RENDER_API_KEY", "")
    service_id = os.environ.get("RENDER_SERVICE_ID", "")
    if not render_key or not service_id or not os.path.exists(session_path):
        return
    try:
        import urllib.request as _ur
        with open(session_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        fname = f"{phone}.session"

        # Get current env vars
        req = _ur.Request(
            f"https://api.render.com/v1/services/{service_id}/env-vars",
            headers={"Authorization": f"Bearer {render_key}"}
        )
        resp = json.loads(_ur.urlopen(req, timeout=10).read())
        current = {v.get("envVar", {}).get("key", ""): v.get("envVar", {}).get("value", "") for v in resp}

        # Find slot for this phone
        slot = None
        for i in range(1, 11):
            if current.get(f"SESSION_NAME_{i}", "") == fname:
                slot = i
                break
        if slot is None:
            for i in range(1, 11):
                if not current.get(f"SESSION_NAME_{i}", ""):
                    slot = i
                    break
        if slot is None:
            print("[SESSION] No free slot (max 10 accounts)", flush=True)
            return

        current[f"SESSION_{slot}"] = b64
        current[f"SESSION_NAME_{slot}"] = fname
        payload = json.dumps([{"key": k, "value": v} for k, v in current.items() if k]).encode()
        req2 = _ur.Request(
            f"https://api.render.com/v1/services/{service_id}/env-vars",
            data=payload,
            headers={"Authorization": f"Bearer {render_key}", "Content-Type": "application/json"},
            method="PUT"
        )
        _ur.urlopen(req2, timeout=15)
        print(f"[SESSION] Saved to Render env SESSION_{slot}: {fname}", flush=True)
    except Exception as e:
        print(f"[SESSION] Env save error: {e}", flush=True)

_copy_repo_sessions()
_restore_sessions_from_env()

# ── Configuration Manager ──────────────────────
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
            
    # Try to restore from Render Env
    env_config = os.environ.get("BOT_CONFIG")
    if env_config:
        try:
            cfg = json.loads(base64.b64decode(env_config).decode("utf-8"))
            # Save it locally for next reads
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            print("[CONFIG] Restored from Render environment!", flush=True)
            return cfg
        except Exception as e:
            print(f"[CONFIG] Failed to decode env config: {e}", flush=True)

    return {
        "api_id": 36765468,
        "api_hash": "fef302fe2a86e2718a15a05f970edce3",
        "bot_token": "8715724185:AAFMlUMkhtQ7fGN7WyRSpJJmgs0b-HzaZNc",
        "admin_id": 0,
        "messages": [
            "Assalomu alaykum! Bu avtomatik e'lon xabari #1"
        ],
        "message": "Assalomu alaykum! Bu avtomatik e'lon xabari.",
        "interval_seconds": 10,
        "delay_between_chats": 1,
        "all_dialogs": [],
        "targets": [],
        "multi_acc_rotation": True
    }

def _save_config_to_env(config):
    render_key = os.environ.get("RENDER_API_KEY", "")
    service_id = os.environ.get("RENDER_SERVICE_ID", "")
    if not render_key or not service_id:
        return
    try:
        import urllib.request as _ur
        b64 = base64.b64encode(json.dumps(config).encode("utf-8")).decode()
        
        req = _ur.Request(
            f"https://api.render.com/v1/services/{service_id}/env-vars",
            headers={"Authorization": f"Bearer {render_key}"}
        )
        resp = json.loads(_ur.urlopen(req, timeout=10).read())
        current = {v.get("envVar", {}).get("key", ""): v.get("envVar", {}).get("value", "") for v in resp}
        
        if current.get("BOT_CONFIG") == b64:
            return # No change needed
            
        current["BOT_CONFIG"] = b64
        payload = json.dumps([{"key": k, "value": v} for k, v in current.items() if k]).encode()
        
        req2 = _ur.Request(
            f"https://api.render.com/v1/services/{service_id}/env-vars",
            data=payload,
            headers={"Authorization": f"Bearer {render_key}", "Content-Type": "application/json"},
            method="PUT"
        )
        _ur.urlopen(req2, timeout=15)
        print("[CONFIG] Saved to Render environment!", flush=True)
    except Exception as e:
        print(f"[CONFIG] Env save error: {e}", flush=True)

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    # Background save to Render Env so it doesn't block Telegram events
    threading.Thread(target=_save_config_to_env, args=(config,), daemon=True).start()

config = load_config()

# Global States
is_posting_active = config.get("auto_posting", True)
posting_task = None
user_states = {} # user_id -> state string
current_msg_index = 0

# Helper to check session
def get_active_user_sessions():
    sessions = []
    for s in os.listdir(SESSIONS_DIR):
        if s.endswith(".session") and s not in ("controller_bot.session", "auto_poster_session.session"):
            sessions.append(os.path.join(SESSIONS_DIR, s))
    return sessions

def extract_telegram_links(text):
    invite_hashes = re.findall(r'(?:t\.me/\+|t\.me/joinchat/)([a-zA-Z0-9_-]+)', text)
    public_matches = re.findall(r'(?:https?://)?t\.me/([a-zA-Z0-9_]{5,})|@([a-zA-Z0-9_]{5,})', text)
    public_usernames = []
    for match in public_matches:
        username = match[0] or match[1]
        if username and username.lower() not in ('joinchat', 'c', 's', 'addstickers', 'addtheme'):
            if not username.startswith('+'):
                public_usernames.append(username)
    return list(set(invite_hashes)), list(set(public_usernames))

# ── Main Menu Keyboards ──────────────────────────
def get_main_keyboard():
    status_emoji = "🟢 FAOL (Ishlamoqda)" if is_posting_active else "🔴 TO'XTATILGAN"
    return [
        [Button.inline(f"🚀 Avto-Posting Status: {status_emoji}", data="toggle_posting")],
        [Button.inline("✍️ Xabar Matnlari (Multi-Ad)", data="menu_messages"), Button.inline("⏱ Interval & Tezlik", data="menu_speed")],
        [Button.inline("🔗 Linklar (Avto-Obuna)", data="auto_join"), Button.inline("📋 Chatlar Boshqaruvi", data="manage_chats")],
        [Button.inline("📱 Akkauntlar (Multi-Session)", data="manage_accs"), Button.inline("📊 Live Dashboard & Stats", data="show_stats")]
    ]

# Helper to build interactive group toggle keyboard
def build_chat_toggle_keyboard(cfg, page=0):
    all_d = cfg.get("all_dialogs", [])
    targets = cfg.get("targets", [])
    target_ids = set(t["id"] for t in targets)

    if not all_d and targets:
        all_d = targets

    if not all_d:
        return [
            [Button.inline("🔄 Akkauntdan Guruhlarni Yuklash", data="select_chats")],
            [Button.inline("⬅️ Orqaga", data="manage_chats")]
        ]

    buttons = []
    start_idx = page * 10
    end_idx = start_idx + 10
    page_items = all_d[start_idx:end_idx]

    for item in page_items:
        is_sel = item["id"] in target_ids
        icon = "✅" if is_sel else "❌"
        title = item["title"][:25]
        buttons.append([Button.inline(f"{icon} {title}", data=f"tgt_tgl_{item['id']}")])

    nav_row = []
    if page > 0:
        nav_row.append(Button.inline("⬅️ Oldingi", data=f"tgt_page_{page-1}"))
    if end_idx < len(all_d):
        nav_row.append(Button.inline("Keyingi ➡️", data=f"tgt_page_{page+1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        Button.inline("✅ Hammasini Tanlash", data="tgt_sel_all"),
        Button.inline("❌ Hammasini O'chirish", data="tgt_desel_all")
    ])
    buttons.append([Button.inline("⬅️ Orqaga", data="manage_chats")])
    return buttons

# Global dialog cache for speed
global_acc_dialogs_cache = {}

# ── Main Poster Loop Task (PARALLEL - barcha akkauntlar bir vaqtda) ──
async def auto_poster_loop(bot_client, chat_id):
    global is_posting_active, current_msg_index, global_acc_dialogs_cache
    round_num = 0

    while is_posting_active:
        round_num += 1
        cfg = load_config()
        targets = cfg.get("targets", [])
        if not targets and cfg.get("all_dialogs"):
            targets = cfg.get("all_dialogs", [])

        msgs = cfg.get("messages", [])
        if not msgs and cfg.get("message"):
            msgs = [cfg.get("message")]
        msgs = [m for m in msgs if m]

        interval_sec = cfg.get("interval_seconds", 10)
        delay_sec = cfg.get("delay_between_chats", 1)

        if not targets:
            await bot_client.send_message(chat_id, "⚠️ **Diqqat:** Guruhlar ro'yxati bo'sh! Guruh qo'shishingizni kutyapman...")
            await asyncio.sleep(30)
            continue
        if not msgs:
            await bot_client.send_message(chat_id, "⚠️ **Diqqat:** Xabar matni kiritilmagan! Kutyapman...")
            await asyncio.sleep(30)
            continue

        sessions = get_active_user_sessions()
        if not sessions:
            await bot_client.send_message(chat_id, "⚠️ **Diqqat:** Akkaunt ulangan emas! Kutyapman...")
            await asyncio.sleep(30)
            continue

        active_message = msgs[current_msg_index % len(msgs)]
        current_msg_index += 1

        n_sess = len(sessions)
        
        now_time = datetime.now().strftime("%H:%M:%S")
        await bot_client.send_message(
            chat_id,
            f"🔄 **[{now_time}] #{round_num}-Raund Boshlandi**\n"
            f"⏳ Akkauntlar guruhlari tekshirilmoqda..."
        )

        # 1. Fetch which dialogs each account has
        async def get_acc_dialogs(session_path):
            if session_path in global_acc_dialogs_cache:
                return session_path, global_acc_dialogs_cache[session_path]
            try:
                cl = TelegramClient(session_path, cfg["api_id"], cfg["api_hash"])
                await cl.connect()
                if not await cl.is_user_authorized():
                    await cl.disconnect()
                    return session_path, set()
                d_ids = set()
                async for d in cl.iter_dialogs():
                    if d.is_group or d.is_channel:
                        d_ids.add(d.id)
                await cl.disconnect()
                global_acc_dialogs_cache[session_path] = d_ids
                return session_path, d_ids
            except Exception as e:
                err_msg = str(e)
                sess_name = os.path.basename(session_path).replace(".session", "")
                await bot_client.send_message(chat_id, f"⚠️ **{sess_name}** akkauntida guruhlarni yuklashda xatolik: `{err_msg}`\nIltimos, botni to'xtatib 1 daqiqa kuting yoki shu akkauntga guruhlarni qayta yuklang.")
                return session_path, set()

        try:
            dialog_results = await asyncio.gather(*[get_acc_dialogs(s) for s in sessions], return_exceptions=True)
            acc_dialogs = {r[0]: r[1] for r in dialog_results if isinstance(r, tuple)}
        except Exception as e:
            print("Dialog fetch error:", e)
            acc_dialogs = {s: set() for s in sessions}

        # 2. Assign targets to ALL accounts that are actually members
        acc_assigned_targets = {s: [] for s in sessions}
        unreachable = 0
        for tgt in targets:
            possible_accs = [s for s in sessions if tgt["id"] in acc_dialogs[s]]
            if possible_accs:
                # Bitta guruhga a'zo bo'lgan BARCHA akkauntlarga shu guruhni beramiz (ikkalasi ham tashlaydi)
                for acc in possible_accs:
                    acc_assigned_targets[acc].append(tgt)
            else:
                unreachable += 1

        unreach_msg = f"\n⚠️ **{unreachable} ta guruhga** hech qaysi akkaunt a'zo emas!" if unreachable else ""
        await bot_client.send_message(
            chat_id,
            f"👥 **{n_sess} ta akkaunt** parallel ishlaydi\n"
            f"📊 Jami **{len(targets)} ta** guruhdan **{len(targets) - unreachable} tasiga** yuboriladi{unreach_msg}"
        )

        async def session_task(session_path, my_targets):
            sess_name = os.path.basename(session_path).replace(".session", "")
            succ = fail = 0
            if not my_targets:
                return sess_name, 0, 0
                
            try:
                cl = TelegramClient(session_path, cfg["api_id"], cfg["api_hash"])
                connected = False
                for _ in range(3):
                    try:
                        await cl.connect()
                        connected = True
                        break
                    except Exception:
                        await asyncio.sleep(1)
                if not connected:
                    return sess_name, 0, 0

                if not await cl.is_user_authorized():
                    await cl.disconnect()
                    return sess_name, 0, 0

                me = await cl.get_me()
                display = me.first_name or sess_name

                for tgt in my_targets:
                    if not is_posting_active:
                        break
                    try:
                        await cl.send_message(tgt["id"], active_message)
                        succ += 1
                    except FloodWaitError as e:
                        wait = min(e.seconds, 60)
                        await asyncio.sleep(wait)
                        try:
                            await cl.send_message(tgt["id"], active_message)
                            succ += 1
                        except Exception:
                            fail += 1
                    except Exception:
                        fail += 1
                    await asyncio.sleep(delay_sec)

                await cl.disconnect()
                return display, succ, fail
            except Exception as ex:
                return sess_name, succ, fail

        # Run ALL accounts simultaneously with their assigned targets
        results = await asyncio.gather(
            *[session_task(s, acc_assigned_targets[s]) for s in sessions],
            return_exceptions=True
        )

        valid = [r for r in results if isinstance(r, tuple)]
        total_succ = sum(r[1] for r in valid)
        total_fail = sum(r[2] for r in valid)
        now_end = datetime.now().strftime("%H:%M:%S")

        acc_lines = "\n".join(
            f"  👤 {r[0]}: ✅{r[1]} ta | ❌{r[2]} ta"
            for r in valid
        )
        await bot_client.send_message(
            chat_id,
            f"✅ **#{round_num}-Raund Yakunlandi ({now_end})**\n\n"
            f"📊 **Jami:** ✅ {total_succ} yuborildi | ❌ {total_fail} xato\n\n"
            f"**Akkauntlar natijalari:**\n{acc_lines}\n\n"
            f"⏳ Keyingi raund: **{interval_sec}s**"
        )

        for _ in range(interval_sec):
            if not is_posting_active:
                break
            await asyncio.sleep(1)



async def main():
    cfg = load_config()
    bot_token = cfg.get("bot_token", "").strip()

    if not bot_token:
        bot_token = "8715724185:AAFMlUMkhtQ7fGN7WyRSpJJmgs0b-HzaZNc"
        cfg["bot_token"] = bot_token
        save_config(cfg)

    api_id = cfg["api_id"]
    api_hash = cfg["api_hash"]

    bot = TelegramClient(os.path.join(BASE_DIR, "controller_bot"), api_id, api_hash)
    await bot.start(bot_token=bot_token)
    bot_me = await bot.get_me()

    print("\n" + "="*60)
    print(f"🚀 CONTROLLER BOT ULTRA-PRO v2.0 MUVAFFAQIYATLI ISHGA TUSHDI!")
    print(f"🤖 Bot Nomi: {bot_me.first_name} (@{bot_me.username})")
    print("="*60 + "\n")

    global posting_task
    if is_posting_active and cfg.get("admin_id"):
        print("🔄 Avto-posting avtomatik ravishda tiklandi...")
        posting_task = asyncio.create_task(auto_poster_loop(bot, cfg["admin_id"]))

    # ── Command /start Handler ───────────────────
    @bot.on(events.NewMessage(pattern=r"^/start"))
    async def start_handler(event):
        sender = await event.get_sender()
        cfg = load_config()
        if not cfg.get("admin_id"):
            cfg["admin_id"] = event.sender_id
            save_config(cfg)

        msg_text = (
            f"👋 **Assalomu alaykum, {sender.first_name}!**\n\n"
            f"⚡ **Telegram Ultra-Pro v2.0 Control Center Botiga xush kelibsiz!**\n\n"
            f"Ushbu bot orqali siz barcha guruhlarga avtomatik e'lonlar yuborishingiz, "
            f"bir nechta e'lon matnlarini navbatma-navbat almashtirishingiz va bir nechta akkauntlarni boshqarishingiz mumkin!"
        )
        await event.respond(msg_text, buttons=get_main_keyboard())

    # ── Callback Query Handler ───────────────────
    @bot.on(events.CallbackQuery)
    async def callback_handler(event):
        global is_posting_active, posting_task
        data = event.data.decode('utf-8')
        user_id = event.sender_id
        cfg = load_config()

        if data == "toggle_posting":
            if is_posting_active:
                is_posting_active = False
                if posting_task:
                    posting_task.cancel()
                await event.answer("🛑 Avto-posting to'xtatildi!", alert=True)
            else:
                is_posting_active = True
                posting_task = asyncio.create_task(auto_poster_loop(bot, event.chat_id))
                await event.answer("🚀 Avto-posting ishga tushirildi!", alert=True)

            cfg["auto_posting"] = is_posting_active
            save_config(cfg)
            await event.edit(buttons=get_main_keyboard())

        elif data == "show_stats":
            targets = cfg.get("targets", [])
            msgs = cfg.get("messages", [])
            status = "🟢 FAOL" if is_posting_active else "🔴 TO'XTATILGAN"
            sessions = get_active_user_sessions()

            stats_text = (
                f"📊 **LIVE DASHBOARD & STATISTIKA**\n\n"
                f"⚡ Status: **{status}**\n"
                f"📱 Ulangan Akkauntlar: **{len(sessions)} ta**\n"
                f"📋 Tanlangan Chatlar: **{len(targets)} ta**\n"
                f"📝 E'lon Matnlari Soni: **{len(msgs)} ta**\n"
                f"⏱ Interval: **Har {cfg.get('interval_seconds', 50)} sekundda**\n"
                f"⏳ Chatlar oralig'i: **{cfg.get('delay_between_chats', 3)} sekund**"
            )
            await event.respond(stats_text, buttons=[[Button.inline("⬅️ Orqaga", data="main_menu")]])

        elif data == "menu_messages":
            msgs = cfg.get("messages", [])
            txt = f"📝 **XABAR MATNLARI BOSHGARUVI ({len(msgs)} ta matn):**\n\n"
            for i, m in enumerate(msgs, 1):
                txt += f"**[{i}]** `{m[:80]}...`\n\n"
            
            buttons = [
                [Button.inline("➕ Yangi Matn Qo'shish", data="add_msg_text")],
                [Button.inline("🗑️ Barcha Matnlarni Tozalash", data="clear_all_msgs")],
                [Button.inline("⬅️ Orqaga", data="main_menu")]
            ]
            await event.respond(txt, buttons=buttons)

        elif data == "add_msg_text":
            user_states[user_id] = "awaiting_msg"
            await event.respond("✍️ **Yangi e'lon matnini ushbu chatga yuboring:**")

        elif data == "clear_all_msgs":
            cfg["messages"] = []
            save_config(cfg)
            await event.answer("🗑️ Barcha matnlar tozalandi!", alert=True)
            await event.respond("✅ Barcha xabar matnlari tozalandi. Yangi matn qo'shishingiz mumkin.", buttons=get_main_keyboard())

        elif data == "menu_speed":
            buttons = [
                [Button.inline("🔥 10 Sekund (TURBO FAST)", data="set_sec_10"), Button.inline("⚡ 30 Sekund (Tezkor)", data="set_sec_30")],
                [Button.inline("🚀 50 Sekund (Standart)", data="set_sec_50"), Button.inline("⏱ 2 Minut (Xavfsiz)", data="set_sec_120")],
                [Button.inline("✏️ Qo'lda Sekund Kiritish", data="custom_sec")],
                [Button.inline("⬅️ Orqaga", data="main_menu")]
            ]
            cur_sec = cfg.get("interval_seconds", 10)
            await event.respond(f"⏱ **TEZLIK VA INTERVAL SOZLAMALARI:**\n\nJoriy interval: **Har {cur_sec} sekundda 1 marta**", buttons=buttons)

        elif data.startswith("set_sec_"):
            sec_val = int(data.split("_")[2])
            cfg["interval_seconds"] = sec_val
            save_config(cfg)
            await event.answer(f"✅ Interval {sec_val}s ga o'rnatildi!", alert=True)
            await event.respond(f"✅ **Interval har {sec_val} sekundga muvaffaqiyatli o'rnatildi!**", buttons=get_main_keyboard())

        elif data == "custom_sec":
            user_states[user_id] = "awaiting_interval"
            await event.respond("⏱ **Xabar yuborish intervalini (SEKUNDLARDA) kiriting:**\n\n*(Masalan: 40, 60, 90 deb sekund yuboring)*")

        elif data == "manage_chats":
            targets = cfg.get("targets", [])
            txt = f"📋 **TANLANGAN CHATLAR BOSHGARUVI ({len(targets)} ta tanlangan):**\n\n"
            for i, t in enumerate(targets[:10], 1):
                txt += f"{i}. **{t['title']}**\n"
            if len(targets) > 10:
                txt += f"\n... va yana {len(targets)-10} ta guruh."
            
            buttons = [
                [Button.inline("☑️ Guruhlarni Bittalab Tanlash (✅/❌)", data="chat_selector_0")],
                [Button.inline("🔄 Akkauntdan Qayta Yuklash", data="select_chats")],
                [Button.inline("🗑️ Barcha Chatlarni Tozalash", data="clear_chats")],
                [Button.inline("⬅️ Orqaga", data="main_menu")]
            ]
            await event.respond(txt, buttons=buttons)

        elif data.startswith("chat_selector_"):
            page = int(data.split("_")[2])
            kb = build_chat_toggle_keyboard(cfg, page=page)
            targets = cfg.get("targets", [])
            txt = f"☑️ **GURUHLARNI TANLASH VA O'CHIRISH (Jami: {len(targets)} ta faol):**\n\n"
            txt += "Guruh nomini bossangiz u **✅ (yuboriladi)** yoki **❌ (yuborilmaydi)** rejimiga o'tadi."
            await event.edit(txt, buttons=kb)

        elif data.startswith("tgt_tgl_"):
            tgt_id = int(data.split("_")[2])
            all_d = cfg.get("all_dialogs", [])
            targets = cfg.get("targets", [])
            target_ids = set(t["id"] for t in targets)

            if tgt_id in target_ids:
                targets = [t for t in targets if t["id"] != tgt_id]
                await event.answer("❌ Guruh yuborish ro'yxatidan chiqarildi!", alert=False)
            else:
                found_item = next((d for d in all_d if d["id"] == tgt_id), None)
                if found_item:
                    targets.append(found_item)
                    await event.answer("✅ Guruh yuborish ro'yxatiga qo'shildi!", alert=False)

            cfg["targets"] = targets
            save_config(cfg)
            kb = build_chat_toggle_keyboard(cfg, page=0)
            await event.edit(buttons=kb)

        elif data == "tgt_sel_all":
            all_d = cfg.get("all_dialogs", [])
            if all_d:
                cfg["targets"] = list(all_d)
                save_config(cfg)
                await event.answer("✅ Barcha guruhlar tanlandi!", alert=True)
            kb = build_chat_toggle_keyboard(cfg, page=0)
            await event.edit(buttons=kb)

        elif data == "tgt_desel_all":
            cfg["targets"] = []
            save_config(cfg)
            await event.answer("❌ Barcha guruhlar tozalandi!", alert=True)
            kb = build_chat_toggle_keyboard(cfg, page=0)
            await event.edit(buttons=kb)

        elif data.startswith("tgt_page_"):
            page = int(data.split("_")[2])
            kb = build_chat_toggle_keyboard(cfg, page=page)
            await event.edit(buttons=kb)

        elif data == "clear_chats":
            cfg["targets"] = []
            save_config(cfg)
            await event.answer("🗑️ Barcha guruhlar tozalandi!", alert=True)
            await event.respond("✅ Barcha guruhlar ro'yxatdan tozalandi.", buttons=get_main_keyboard())

        elif data == "auto_join":
            user_states[user_id] = "awaiting_links"
            await event.respond(
                "🔗 **TELEGRAM GURUH LINKLARINI YUBORING:**\n\n"
                "Kanal va guruh linklarini matn ko'rinishida bitta xabarda yuboring.\n"
                "Masalan:\n`https://t.me/guruh1\nhttps://t.me/+abc1234hash\n@guruh2`"
            )

        elif data == "manage_accs":
            sessions = get_active_user_sessions()
            txt = f"📱 **ULANGAN AKKAUNTLAR RO'YXATI ({len(sessions)} ta):**\n\n"
            buttons = []
            for s in sessions:
                name = os.path.basename(s).replace(".session", "")
                txt += f"• `{name}` ✅\n"
                buttons.append([Button.inline(f"🗑️ O'chirish: {name}", data=f"del_acc_{name}")])
            txt += "\n➕ Yangi akkaunt ulash uchun pastdagi tugmani bosing:"
            buttons.append([Button.inline("➕ Yangi Akkaunt Ulash (SMS)", data="add_new_acc")])
            buttons.append([Button.inline("⬅️ Orqaga", data="main_menu")])
            await event.respond(txt, buttons=buttons)

        elif data.startswith("del_acc_"):
            acc_name = data.replace("del_acc_", "")
            
            # Remove from /tmp/sessions
            path = os.path.join(SESSIONS_DIR, f"{acc_name}.session")
            if os.path.exists(path):
                try: os.remove(path)
                except: pass
                
            # Remove from Render env
            render_key = os.environ.get("RENDER_API_KEY", "")
            service_id = os.environ.get("RENDER_SERVICE_ID", "")
            if render_key and service_id:
                try:
                    import urllib.request as _ur
                    req = _ur.Request(
                        f"https://api.render.com/v1/services/{service_id}/env-vars",
                        headers={"Authorization": f"Bearer {render_key}"}
                    )
                    resp = json.loads(_ur.urlopen(req, timeout=10).read())
                    current = {v.get("envVar", {}).get("key", ""): v.get("envVar", {}).get("value", "") for v in resp}
                    
                    slot = None
                    for i in range(1, 11):
                        if current.get(f"SESSION_NAME_{i}", "") == f"{acc_name}.session":
                            slot = i
                            break
                    if slot:
                        current[f"SESSION_{slot}"] = ""
                        current[f"SESSION_NAME_{slot}"] = ""
                        payload = json.dumps([{"key": k, "value": v} for k, v in current.items() if k]).encode()
                        req2 = _ur.Request(
                            f"https://api.render.com/v1/services/{service_id}/env-vars",
                            data=payload,
                            headers={"Authorization": f"Bearer {render_key}", "Content-Type": "application/json"},
                            method="PUT"
                        )
                        _ur.urlopen(req2, timeout=15)
                except Exception as e:
                    print(f"Del env error: {e}")
                    
            await event.answer(f"{acc_name} o'chirildi!", alert=True)
            # Reload manage_accs menu
            sessions = get_active_user_sessions()
            txt = f"📱 **ULANGAN AKKAUNTLAR RO'YXATI ({len(sessions)} ta):**\n\n"
            buttons = []
            for s in sessions:
                name = os.path.basename(s).replace(".session", "")
                txt += f"• `{name}` ✅\n"
                buttons.append([Button.inline(f"🗑️ O'chirish: {name}", data=f"del_acc_{name}")])
            txt += "\n➕ Yangi akkaunt ulash uchun pastdagi tugmani bosing:"
            buttons.append([Button.inline("➕ Yangi Akkaunt Ulash (SMS)", data="add_new_acc")])
            buttons.append([Button.inline("⬅️ Orqaga", data="main_menu")])
            await event.edit(txt, buttons=buttons)

        elif data == "add_new_acc":
            user_states[user_id] = "awaiting_phone"
            await event.respond("📲 **Yangi Telegram akkaunt telefon raqamini kiriting:**\n\n*(Masalan: +998901234567)*")

        elif data == "select_chats":
            sessions = get_active_user_sessions()
            if not sessions:
                await event.answer("⚠️ Avval akkaunt ulang!", alert=True)
                return
            await event.respond("⏳ Akkauntdan barcha guruhlar va yangi obunalar yuklanmoqda...")
            
            success_fetch = False
            for s in sessions:
                user_client = TelegramClient(s, cfg["api_id"], cfg["api_hash"])
                try:
                    await user_client.connect()
                    if not await user_client.is_user_authorized():
                        await user_client.disconnect()
                        if os.path.exists(s):
                            try: os.remove(s)
                            except Exception: pass
                        continue

                    fetched_dialogs = []
                    async for d in user_client.iter_dialogs():
                        if d.is_group or d.is_channel:
                            fetched_dialogs.append({"id": d.id, "title": d.name or "Noma'lum Guruh"})
                    await user_client.disconnect()

                    old_targets = cfg.get("targets", [])
                    old_ids = set(t["id"] for t in old_targets)
                    
                    newly_added_count = 0
                    for fd in fetched_dialogs:
                        if fd["id"] not in old_ids:
                            old_targets.append(fd)
                            old_ids.add(fd["id"])
                            newly_added_count += 1

                    cfg["all_dialogs"] = fetched_dialogs
                    cfg["targets"] = old_targets if old_targets else fetched_dialogs
                    save_config(cfg)
                    success_fetch = True

                    msg_info = (
                        f"🎉 **AKKAUNT GURUHLARI MUVAFFAQIYATLI YANGILANDI!**\n\n"
                        f"👤 Akkaunt: `{os.path.basename(s)}`\n"
                        f"📊 Akkauntdagi jami guruhlar: **{len(fetched_dialogs)} ta**\n"
                        f"✨ Yangi aniqlanib qo'shilgan guruhlar: **+{newly_added_count} ta**\n"
                        f"🎯 Jami postingga tayyor faol guruhlar: **{len(cfg['targets'])} ta**"
                    )
                    await event.respond(msg_info, buttons=get_main_keyboard())
                    break
                except Exception as ex:
                    try: await user_client.disconnect()
                    except Exception: pass
                    if "Key is not registered" in str(ex) or "AuthKeyUnregisteredError" in str(ex):
                        if os.path.exists(s):
                            try: os.remove(s)
                            except Exception: pass

            if not success_fetch:
                await event.respond("⚠️ Ulangan akkauntlar sessiyasi eskirgan yoki o'chgan. Iltimos, **📱 Akkauntlar** bo'limidan yangi akkaunt ulang!", buttons=get_main_keyboard())

        elif data == "main_menu":
            await event.respond("🎛 **Asosiy Boshqaruv Menyusi:**", buttons=get_main_keyboard())

    # ── Text Messages Handler (State Machine) ─────
    @bot.on(events.NewMessage)
    async def message_handler(event):
        if event.text.startswith("/"):
            return
        user_id = event.sender_id
        state = user_states.get(user_id)
        cfg = load_config()

        if state == "awaiting_msg":
            msgs = cfg.get("messages", [])
            msgs.append(event.text)
            cfg["messages"] = msgs
            cfg["message"] = event.text
            save_config(cfg)
            user_states[user_id] = None
            await event.respond(f"✅ **Yangi e'lon matni #{len(msgs)} muvaffaqiyatli saqlandi!**", buttons=get_main_keyboard())

        elif state == "awaiting_interval":
            if event.text.isdigit():
                val = int(event.text)
                cfg["interval_seconds"] = max(1, val)
                save_config(cfg)
                user_states[user_id] = None
                await event.respond(f"✅ **Interval har {val} sekundga o'rnatildi!**", buttons=get_main_keyboard())
            else:
                await event.respond("⚠️ Faqat raqam kiriting (Masalan: 50, 30, 60):")

        elif state == "awaiting_links":
            raw_text = event.text
            invites, publics = extract_telegram_links(raw_text)
            if not invites and not publics:
                await event.respond("⚠️ Hech qanday guruh linki topilmadi! Qayta kiriting.")
                return

            user_states[user_id] = None
            total = len(invites) + len(publics)
            status_msg = await event.respond(f"⏳ **Topilgan {total} ta guruhga avto-obuna boshlanmoqda...**")

            sessions = get_active_user_sessions()
            if not sessions:
                await event.respond("⚠️ Avval Telegram akkaunt ulang!")
                return

            user_client = TelegramClient(sessions[0], cfg["api_id"], cfg["api_hash"])
            await user_client.connect()

            joined_chats = []

            for inv in invites:
                try:
                    res = await user_client(ImportChatInviteRequest(inv))
                    ch = res.chats[0]
                    joined_chats.append({"id": ch.id, "title": ch.title})
                except UserAlreadyParticipantError:
                    try:
                        ci = await user_client.get_entity(f"https://t.me/+{inv}")
                        joined_chats.append({"id": ci.id, "title": ci.title})
                    except Exception: pass
                except Exception: pass
                await asyncio.sleep(2)

            for pub in publics:
                try:
                    res = await user_client(JoinChannelRequest(pub))
                    ch = res.chats[0]
                    joined_chats.append({"id": ch.id, "title": ch.title})
                except UserAlreadyParticipantError:
                    try:
                        ci = await user_client.get_entity(pub)
                        joined_chats.append({"id": ci.id, "title": getattr(ci, 'title', pub)})
                    except Exception: pass
                except Exception: pass
                await asyncio.sleep(2)

            await user_client.disconnect()

            if joined_chats:
                cur_targets = cfg.get("targets", [])
                ex_ids = {t["id"] for t in cur_targets}
                added_cnt = 0
                for jc in joined_chats:
                    if jc["id"] not in ex_ids:
                        cur_targets.append(jc)
                        ex_ids.add(jc["id"])
                        added_cnt += 1
                cfg["targets"] = cur_targets
                save_config(cfg)
                await event.respond(f"🎉 **{added_cnt} ta yangi guruhga obuna bo'lindi va posting ro'yxatiga qo'shildi!**", buttons=get_main_keyboard())
            else:
                await event.respond("⚠️ Guruhlarga ulanib bo'lmadi yoki allaqachon a'zosiz.", buttons=get_main_keyboard())

        elif state == "awaiting_phone":
            phone = event.text.strip().replace(" ", "").replace("-", "")
            cfg["pending_phone"] = phone
            user_states[user_id] = "awaiting_code"

            temp_client = TelegramClient(os.path.join(SESSIONS_DIR, f"{phone}.session"), cfg["api_id"], cfg["api_hash"])
            await temp_client.connect()
            try:
                sent = await temp_client.send_code_request(phone)
                cfg["phone_code_hash"] = sent.phone_code_hash
                save_config(cfg)
                await temp_client.disconnect()
                await event.respond(
                    f"📩 **SMS / Telegram kod yuborildi!**\n\n"
                    f"Telegram ilovangizga kelgan 5-xonali kodni shu yerga yozib yuboring:"
                )
            except Exception as ex:
                await temp_client.disconnect()
                user_states[user_id] = None
                await event.respond(f"❌ SMS kod yuborishda xatolik: {ex}", buttons=get_main_keyboard())

        elif state == "awaiting_code":
            code = event.text.strip()
            phone = cfg.get("pending_phone")
            code_hash = cfg.get("phone_code_hash")

            temp_client = TelegramClient(os.path.join(SESSIONS_DIR, f"{phone}.session"), cfg["api_id"], cfg["api_hash"])
            await temp_client.connect()

            try:
                await temp_client.sign_in(phone, code, phone_code_hash=code_hash)
                me = await temp_client.get_me()
                await temp_client.disconnect()
                user_states[user_id] = None
                save_session_to_env(phone)
                sessions_count = len(get_active_user_sessions())
                await event.respond(f"🎉 **Muvaffaqiyatli ulandi:** {me.first_name} (@{me.username or me.id})!\n\n📱 Jami ulangan akkauntlar: {sessions_count} ta", buttons=get_main_keyboard())
            except SessionPasswordNeededError:
                cfg["pending_code"] = code
                save_config(cfg)
                user_states[user_id] = "awaiting_2fa"
                await temp_client.disconnect()
                await event.respond("🔒 **2-bosqichli xavfsizlik (2FA) parolingizni kiriting:**")
            except Exception as ex:
                await temp_client.disconnect()
                user_states[user_id] = None
                await event.respond(f"❌ Kirishda xatolik: {ex}", buttons=get_main_keyboard())

        elif state == "awaiting_2fa":
            pwd = event.text.strip()
            phone = cfg.get("pending_phone")

            temp_client = TelegramClient(os.path.join(SESSIONS_DIR, f"{phone}.session"), cfg["api_id"], cfg["api_hash"])
            await temp_client.connect()

            try:
                await temp_client.sign_in(password=pwd)
                me = await temp_client.get_me()
                await temp_client.disconnect()
                user_states[user_id] = None
                save_session_to_env(phone)
                sessions_count = len(get_active_user_sessions())
                await event.respond(f"🎉 **2FA Parol qabul qilindi! Muvaffaqiyatli ulandi:** {me.first_name} (@{me.username or me.id})!\n\n📱 Jami ulangan akkauntlar: {sessions_count} ta", buttons=get_main_keyboard())
            except Exception as ex:
                await temp_client.disconnect()
                await event.respond(f"❌ 2FA Parolda xatolik: {ex}. Qayta kiriting:")

    await bot.run_until_disconnected()

if __name__ == "__main__":
    while True:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print("\nBot to'xtatildi.")
            break
        except Exception as net_err:
            print(f"\n[!] Internet ulanishda tanaffus: {net_err}. 5 soniyadan keyin qayta ulanmoqda...")
            time.sleep(5)
