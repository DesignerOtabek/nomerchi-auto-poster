import asyncio
import json
import os
import re
import sys
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import (
    UserAlreadyParticipantError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    ChannelPrivateError,
    FloodWaitError,
    RPCError
)
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, IntPrompt, Confirm

console = Console()
CONFIG_FILE = "config.json"
SESSION_NAME = "auto_poster_session"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "api_id": "",
        "api_hash": "",
        "phone": "",
        "message": "",
        "interval_minutes": 10,
        "delay_between_chats": 3,
        "targets": []
    }

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def print_header():
    os.system("cls" if os.name == "nt" else "clear")
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    console.clear()
    console.print(Panel.fit(
        "[bold cyan]TELEGRAM AUTO MESSAGE & LINK JOINER[/bold cyan]\n"
        "[dim]Guruh va chatlarga avtomatik obuna bo'lish va xabar yuborish dasturi[/dim]",
        border_style="cyan"
    ))

def extract_telegram_links(text):
    # Private invite links: t.me/+hash or t.me/joinchat/hash
    invite_hashes = re.findall(r'(?:t\.me/\+|t\.me/joinchat/)([a-zA-Z0-9_-]+)', text)
    
    # Public channel/group usernames or links
    public_matches = re.findall(r'(?:https?://)?t\.me/([a-zA-Z0-9_]{5,})|@([a-zA-Z0-9_]{5,})', text)
    public_usernames = []
    for match in public_matches:
        username = match[0] or match[1]
        if username and username.lower() not in ('joinchat', 'c', 's', 'addstickers', 'addtheme'):
            if not username.startswith('+'):
                public_usernames.append(username)
                
    return list(set(invite_hashes)), list(set(public_usernames))

async def get_telegram_client(config):
    api_id = config.get("api_id")
    api_hash = config.get("api_hash")

    if not api_id or not api_hash:
        console.print("[bold yellow]⚠ Telegram API kalitlari topilmadi![/bold yellow]")
        console.print("API ID va API Hash olish uchun [link=https://my.telegram.org]https://my.telegram.org[/link] saytiga kiring.")
        
        api_id_str = Prompt.ask("[bold green]API ID ni kiriting[/bold green]")
        api_hash = Prompt.ask("[bold green]API HASH ni kiriting[/bold green]")
        
        try:
            config["api_id"] = int(api_id_str)
        except ValueError:
            console.print("[bold red]✗ API ID faqat raqamlardan iborat bo'lishi kerak![/bold red]")
            return None
        
        config["api_hash"] = api_hash.strip()
        save_config(config)

    api_id = int(config["api_id"])
    api_hash = config["api_hash"]

    client = TelegramClient(SESSION_NAME, api_id, api_hash)
    
    console.print("\n[cyan]Telegram'ga ulanmoqda...[/cyan]")
    
    def phone_callback():
        phone = Prompt.ask("[bold yellow]Telegram telefon raqamingiz (+998...)[/bold yellow]")
        config["phone"] = phone
        save_config(config)
        return phone

    def code_callback():
        return Prompt.ask("[bold yellow]Telegram'ga kelgan SMS / ilova kodini kiriting[/bold yellow]")

    def password_callback():
        return Prompt.ask("[bold yellow]2-bosqichli xavfsizlik (2FA) parolingizni kiriting[/bold yellow]", password=False)

    try:
        await client.start(
            phone=phone_callback,
            code_callback=code_callback,
            password=password_callback
        )
        me = await client.get_me()
        console.print(f"[bold green]✓ Muvaffaqiyatli ulandi:[/bold green] {me.first_name} (@{me.username or me.id})")
        return client
    except Exception as e:
        if "AuthRestartError" in str(e) or "Restart the authorization" in str(e):
            console.print("[bold yellow]⚠️ Eski sessiya tozalanmoqda, yangi SMS kod yuborilmoqda...[/bold yellow]")
            try:
                await client.disconnect()
            except Exception:
                pass
            for f in [f"{SESSION_NAME}.session", f"{SESSION_NAME}.session-journal"]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass
            try:
                client = TelegramClient(SESSION_NAME, api_id, api_hash)
                await client.start(
                    phone=phone_callback,
                    code_callback=code_callback,
                    password=password_callback
                )
                me = await client.get_me()
                console.print(f"[bold green]✓ Muvaffaqiyatli ulandi:[/bold green] {me.first_name} (@{me.username or me.id})")
                return client
            except Exception as e2:
                console.print(f"[bold red]✗ Ulanishda xatolik yuz berdi: {e2}[/bold red]")
                return None
        else:
            console.print(f"[bold red]✗ Ulanishda xatolik yuz berdi: {e}[/bold red]")
            return None

async def auto_join_links(client, config):
    console.print("\n[bold cyan]🔗 LINKLAR BO'YICHA AVTO-OBUNA BO'LISH[/bold cyan]")
    console.print("[dim]Telegram kanal/guruh linklarini yoki textni tashlang (Masalan: https://t.me/guruh_nomi yoki https://t.me/+abc1234)[/dim]")
    console.print("[dim]Kiritib bo'lgach, yangi qatorda [bold white]END[/bold white] deb yozib Enter bosing.[/dim]\n")

    lines = []
    while True:
        try:
            line = input()
            if line.strip() == "END":
                break
            lines.append(line)
        except EOFError:
            break

    raw_text = "\n".join(lines)
    invite_hashes, public_usernames = extract_telegram_links(raw_text)

    if not invite_hashes and not public_usernames:
        console.print("[bold yellow]⚠ Hech qanday Telegram linki yoki username topilmadi.[/bold yellow]")
        return

    total_found = len(invite_hashes) + len(public_usernames)
    console.print(f"[bold green]Topilgan linklar:[/bold green] {total_found} ta (Yopiq: {len(invite_hashes)}, Ochiq: {len(public_usernames)})\n")

    joined_chats = []

    # 1. Private invite links (t.me/+hash)
    for inv_hash in invite_hashes:
        try:
            console.print(f"[cyan]Ulanmoqda (Yopiq link):[/cyan] +{inv_hash}...")
            updates = await client(ImportChatInviteRequest(inv_hash))
            chat = updates.chats[0]
            console.print(f"  [bold green]✓ Muvaffaqiyatli obuna bo'lindi:[/bold green] [white]{chat.title}[/white]")
            joined_chats.append({"id": chat.id, "title": chat.title})
        except UserAlreadyParticipantError:
            console.print(f"  [yellow]ℹ Siz allaqachon ushbu guruh/kanalda bor ekansiz.[/yellow]")
            try:
                # Get chat info
                chat_info = await client.get_entity(f"https://t.me/+{inv_hash}")
                joined_chats.append({"id": chat_info.id, "title": chat_info.title})
            except Exception:
                pass
        except (InviteHashExpiredError, InviteHashInvalidError):
            console.print(f"  [red]✗ Link yaroqsiz yoki muddati o'tgan: +{inv_hash}[/red]")
        except FloodWaitError as e:
            console.print(f"  [yellow]⚠ FloodWait! {e.seconds} sekund kutilmoqda...[/yellow]")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            console.print(f"  [red]✗ Obuna bo'lishda xatolik (+{inv_hash}): {e}[/red]")
        await asyncio.sleep(2)

    # 2. Public usernames / links
    for username in public_usernames:
        try:
            console.print(f"[cyan]Ulanmoqda (Ochiq link):[/cyan] @{username}...")
            updates = await client(JoinChannelRequest(username))
            chat = updates.chats[0]
            console.print(f"  [bold green]✓ Muvaffaqiyatli obuna bo'lindi:[/bold green] [white]{chat.title}[/white]")
            joined_chats.append({"id": chat.id, "title": chat.title})
        except UserAlreadyParticipantError:
            console.print(f"  [yellow]ℹ Siz allaqachon ushbu guruh/kanalda bor ekansiz.[/yellow]")
            try:
                chat_info = await client.get_entity(username)
                joined_chats.append({"id": chat_info.id, "title": getattr(chat_info, 'title', username)})
            except Exception:
                pass
        except FloodWaitError as e:
            console.print(f"  [yellow]⚠ FloodWait! {e.seconds} sekund kutilmoqda...[/yellow]")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            console.print(f"  [red]✗ Obuna bo'lishda xatolik (@{username}): {e}[/red]")
        await asyncio.sleep(2)

    if joined_chats:
        add_to_targets = Confirm.ask("\n[bold yellow]Ushbu obuna bo'lingan guruhlarni avto-xabar yuborish ro'yxatiga qo'shasizmi?[/bold yellow]")
        if add_to_targets:
            existing_targets = config.get("targets", [])
            existing_ids = {t["id"] for t in existing_targets}
            
            added_count = 0
            for jc in joined_chats:
                if jc["id"] not in existing_ids:
                    existing_targets.append(jc)
                    existing_ids.add(jc["id"])
                    added_count += 1
            
            config["targets"] = existing_targets
            save_config(config)
            console.print(f"[bold green]✓ {added_count} ta yangi guruh xabar yuborish ro'yxatiga qo'shildi![/bold green]")

async def select_targets(client, config):
    console.print("\n[bold cyan]Guruh va chatlar yuklanmoqda...[/bold cyan]")
    dialogs = []
    
    async for dialog in client.iter_dialogs():
        if dialog.is_group or dialog.is_channel or dialog.is_user:
            dialogs.append(dialog)

    if not dialogs:
        console.print("[red]Hech qanday chat topilmadi![/red]")
        return

    table = Table(title="Mavjud Telegram Chatlar Ro'yxati", show_lines=True)
    table.add_column("№", style="cyan", justify="right", width=5)
    table.add_column("Chat Nomi", style="bold white")
    table.add_column("Turi", style="magenta")
    table.add_column("ID", style="dim")

    for idx, d in enumerate(dialogs, 1):
        chat_type = "Guruh" if d.is_group else ("Kanal" if d.is_channel else "Foydalanuvchi")
        table.add_row(str(idx), d.name or "Noma'lum", chat_type, str(d.id))

    console.print(table)
    console.print("\n[bold green]Tanlash yo'riqnomasi:[/bold green]")
    console.print("- Raqamlarni vergul bilan kiriting (Masalan: [cyan]1, 3, 5[/cyan])")
    console.print("- Barcha guruhlarni tanlash uchun [cyan]all[/cyan] deb yozing")
    console.print("- Bekor qilish uchun shunchaki [cyan]Enter[/cyan] bosing")

    selection = Prompt.ask("\n[bold yellow]Chatlarni tanlang[/bold yellow]").strip()

    if not selection:
        return

    selected_targets = []
    if selection.lower() == "all":
        for d in dialogs:
            if d.is_group or d.is_channel:
                selected_targets.append({"id": d.id, "title": d.name})
    else:
        parts = selection.split(",")
        for p in parts:
            p = p.strip()
            if p.isdigit():
                idx = int(p) - 1
                if 0 <= idx < len(dialogs):
                    d = dialogs[idx]
                    selected_targets.append({"id": d.id, "title": d.name})

    if selected_targets:
        config["targets"] = selected_targets
        save_config(config)
        console.print(f"[bold green]✓ {len(selected_targets)} ta chat tanlandi va saqlandi![/bold green]")
        for t in selected_targets:
            console.print(f"  • [cyan]{t['title']}[/cyan] (ID: {t['id']})")
    else:
        console.print("[yellow]Hech qanday chat tanlanmadi.[/yellow]")

def setup_message(config):
    console.print("\n[bold cyan]Yuboriladigan Xabar Matnini Kiriting[/bold cyan]")
    console.print("[dim]Ko'p qatorli matn kiritish uchun matnni yozib bo'lgach, yangi qatorda [bold white]END[/bold white] so'zini yozib Enter bosing.[/dim]\n")

    lines = []
    while True:
        try:
            line = input()
            if line.strip() == "END":
                break
            lines.append(line)
        except EOFError:
            break

    msg = "\n".join(lines).strip()
    if msg:
        config["message"] = msg
        save_config(config)
        console.print("[bold green]✓ Xabar matni muvaffaqiyatli saqlandi![/bold green]")
    else:
        console.print("[yellow]Xabar kiritilmadi.[/yellow]")

def setup_interval(config):
    console.print("\n[bold cyan]Yuborish Vaqt Oralig'ini Belgilash[/bold cyan]")
    current_interval = config.get("interval_minutes", 10)
    current_delay = config.get("delay_between_chats", 3)
    
    interval = IntPrompt.ask(
        f"Har necha minutda xabar yuborilsin?",
        default=current_interval
    )
    delay = IntPrompt.ask(
        f"Har bir chat orasidagi kutiladigan sekund (Flood/Spam blokining oldini olish uchun)",
        default=current_delay
    )

    config["interval_minutes"] = max(1, interval)
    config["delay_between_chats"] = max(1, delay)
    save_config(config)
    console.print("[bold green]✓ Vaqt intervallari saqlandi![/bold green]")

async def start_auto_posting(client, config):
    targets = config.get("targets", [])
    message = config.get("message", "")
    interval_minutes = config.get("interval_minutes", 10)
    delay_between = config.get("delay_between_chats", 3)

    if not targets:
        console.print("[bold red]✗ Hali hech qanday guruh/chat tanlanmagan! Avval chatlarni tanlang yoki obuna bo'ling.[/bold red]")
        return
    if not message:
        console.print("[bold red]✗ Hali xabar matni kiritilmagan! Avval 4-menyu orqali xabar yozing.[/bold red]")
        return

    console.clear()
    console.print(Panel.fit(
        f"[bold green]🚀 AVTO-POSTING ISHGA TUSHDI[/bold green]\n\n"
        f"[white]Tanlangan chatlar:[/white] [cyan]{len(targets)} ta[/cyan]\n"
        f"[white]Interval:[/white] Har [cyan]{interval_minutes}[/cyan] minutda\n"
        f"[white]Chatlar oraliq kutish:[/white] [cyan]{delay_between}[/cyan] sekund\n"
        f"[dim]Dasturni to'xtatish uchun CTRL+C bosing[/dim]",
        border_style="green"
    ))

    round_count = 0
    try:
        while True:
            round_count += 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            console.print(f"\n[bold magenta]═════════════ [{now_str}] #{round_count}-Raund Boshlandi ═════════════[/bold magenta]")
            
            success_count = 0
            fail_count = 0

            for target in targets:
                chat_id = target["id"]
                chat_title = target["title"]
                
                try:
                    await client.send_message(chat_id, message)
                    success_count += 1
                    console.print(f"  [bold green]✓ Yuborildi:[/bold green] [white]{chat_title}[/white]")
                except FloodWaitError as e:
                    console.print(f"  [bold yellow]⚠ Telegram Cheklovi (FloodWait): {e.seconds} sekund kutilmoqda...[/bold yellow]")
                    await asyncio.sleep(e.seconds)
                    try:
                        await client.send_message(chat_id, message)
                        success_count += 1
                        console.print(f"  [bold green]✓ Yuborildi (qayta):[/bold green] [white]{chat_title}[/white]")
                    except Exception as ex:
                        fail_count += 1
                        console.print(f"  [bold red]✗ Xatolik ({chat_title}): {ex}[/bold red]")
                except RPCError as e:
                    fail_count += 1
                    console.print(f"  [bold red]✗ Xatolik ({chat_title}): {e.message}[/bold red]")
                except Exception as e:
                    fail_count += 1
                    console.print(f"  [bold red]✗ Noma'lum xatolik ({chat_title}): {e}[/bold red]")

                await asyncio.sleep(delay_between)

            console.print(f"[bold green]✔ Raund tugadi. Natija: {success_count} muvaffaqiyatli, {fail_count} xato.[/bold green]")
            
            total_wait_seconds = interval_minutes * 60
            console.print(f"[cyan]Keyingi yuborishga {interval_minutes} minut qoldi... ({total_wait_seconds}s)[/cyan]")
            
            for remaining in range(total_wait_seconds, 0, -1):
                if remaining % 60 == 0 and remaining != total_wait_seconds:
                    console.print(f"[dim]⌛ Keyingi raundgacha {remaining // 60} minut qoldi...[/dim]")
                await asyncio.sleep(1)

    except asyncio.CancelledError:
        console.print("\n[yellow]Avto-posting to'xtatildi.[/yellow]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Avto-posting foydalanuvchi tomonidan to'xtatildi.[/yellow]")

def show_status(config):
    console.print("\n[bold cyan]JORIY SOZLAMALAR[/bold cyan]")
    table = Table(show_header=False, box=None)
    table.add_column("Parametr", style="bold yellow")
    table.add_column("Qiymat", style="white")

    table.add_row("API ID", str(config.get("api_id") or "Kiritilmagan"))
    table.add_row("API Hash", "••••••••" if config.get("api_hash") else "Kiritilmagan")
    table.add_row("Telefon", config.get("phone") or "Kiritilmagan")
    table.add_row("Interval", f"Har {config.get('interval_minutes', 10)} minutda")
    table.add_row("Chatlar oralig'i", f"{config.get('delay_between_chats', 3)} sekund")
    table.add_row("Tanlangan chatlar", f"{len(config.get('targets', []))} ta chat")
    
    msg_preview = config.get("message", "")
    if len(msg_preview) > 50:
        msg_preview = msg_preview[:50] + "..."
    table.add_row("Xabar matni", msg_preview or "[red]Kiritilmagan[/red]")

    console.print(table)

async def logout_account(client, config):
    console.print("\n[bold cyan]🚪 TELEGRAM AKKAUNTDAN CHIQISH[/bold cyan]")
    confirm = Confirm.ask("[bold yellow]Haqiqatdan ham joriy akkauntdan chiqmoqchimisiz?[/bold yellow]")
    if not confirm:
        console.print("[yellow]Bekor qilindi.[/yellow]")
        return client

    if client:
        try:
            if await client.is_user_authorized():
                await client.log_out()
            await client.disconnect()
        except Exception:
            pass

    for f in [f"{SESSION_NAME}.session", f"{SESSION_NAME}.session-journal"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass

    config["phone"] = ""
    save_config(config)
    console.print("[bold green]✓ Akkauntdan muvaffaqiyatli chiqildi va sessiya o'chirildi! Yangi akkaunt ulashingiz mumkin.[/bold green]")
    return None

async def main():
    config = load_config()
    client = None

    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print_header()
        show_status(config)

        console.print("\n[bold green]BOSH MENYU:[/bold green]")
        console.print(" 1. [cyan]🔑 Telegram Akkauntga Ulanish[/cyan]")
        console.print(" 2. [bold yellow]🔗 Linklar Bo'yicha Avto-Obuna Bo'lish (Yangi!)[/bold yellow]")
        console.print(" 3. [cyan]📋 Mavjud Guruh / Chatlarni Tanlash[/cyan]")
        console.print(" 4. [cyan]✍️  Xabar Matnini Kiriting / Tahrirlash[/cyan]")
        console.print(" 5. [cyan]⏱  Vaqt Intervalini Belgilash[/cyan]")
        console.print(" 6. [bold green]🚀 AVTO-POSTINGNI BOSHLASH[/bold green]")
        console.print(" 7. [bold red]🚪 Telegram Akkauntdan Chiqish (Log out / O'chirish)[/bold red]")
        console.print(" 0. [red]❌ Chiqish[/red]")

        choice = Prompt.ask("\n[bold yellow]Tanlovni kiriting[/bold yellow]", choices=["0", "1", "2", "3", "4", "5", "6", "7"])

        if choice == "0":
            if client and client.is_connected():
                await client.disconnect()
            console.print("[bold cyan]Dasturdan chiqildi. Xayr![/bold cyan]")
            sys.exit(0)

        elif choice == "1":
            client = await get_telegram_client(config)
            Prompt.ask("\n[dim]Davom etish uchun Enter bosing...[/dim]")

        elif choice == "2":
            if not client or not await client.is_user_authorized():
                client = await get_telegram_client(config)
            if client and await client.is_user_authorized():
                await auto_join_links(client, config)
            else:
                console.print("[red]Avval Telegram akkauntga ulaning![/red]")
            Prompt.ask("\n[dim]Davom etish uchun Enter bosing...[/dim]")

        elif choice == "3":
            if not client or not await client.is_user_authorized():
                client = await get_telegram_client(config)
            if client and await client.is_user_authorized():
                await select_targets(client, config)
            else:
                console.print("[red]Avval Telegram akkauntga ulaning![/red]")
            Prompt.ask("\n[dim]Davom etish uchun Enter bosing...[/dim]")

        elif choice == "4":
            setup_message(config)
            Prompt.ask("\n[dim]Davom etish uchun Enter bosing...[/dim]")

        elif choice == "5":
            setup_interval(config)
            Prompt.ask("\n[dim]Davom etish mezonlari uchun Enter bosing...[/dim]")

        elif choice == "6":
            if not client or not await client.is_user_authorized():
                client = await get_telegram_client(config)
            if client and await client.is_user_authorized():
                await start_auto_posting(client, config)
            else:
                console.print("[red]Avval Telegram akkauntga ulaning![/red]")
            Prompt.ask("\n[dim]Davom etish mezonlari uchun Enter bosing...[/dim]")

        elif choice == "7":
            client = await logout_account(client, config)
            Prompt.ask("\n[dim]Davom etish uchun Enter bosing...[/dim]")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBo'lingan. Chiqilmoqda...")
