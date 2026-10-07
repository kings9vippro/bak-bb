# UI/utility additions for ALB Forge.
# Safe scope: Telegram UI, bounded file-to-message workflow, health/ping.
from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

FILE_MAX_LINES = 30
FILE_MIN_INTERVAL = 3.0
FILE_MAX_BYTES = 256 * 1024
FILE_DIR = Path(os.environ.get("DATA_DIR", "/tmp/alb_data")) / "uploads"
FILE_DIR.mkdir(parents=True, exist_ok=True)
FILE_SESSIONS: dict[int, dict] = {}
FILE_JOBS: dict[int, asyncio.Task] = {}


def parse_numbered_text(raw: str) -> list[str]:
    """Keep only `1. text` style lines and strip the numeric prefix."""
    out: list[str] = []
    for line in raw.splitlines():
        m = re.match(r"^\s*\d+\.\s*(.+?)\s*$", line)
        if m and m.group(1).strip():
            out.append(m.group(1).strip())
        if len(out) >= FILE_MAX_LINES:
            break
    return out


def file_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✨ Xem trước", callback_data="file_preview"),
         InlineKeyboardButton("🚀 Gửi có giới hạn", callback_data="file_send")],
        [InlineKeyboardButton("🗑 Xóa tệp", callback_data="file_clear")],
    ])


def render_preview(items: list[str], title: str = "✨ FILE MESSAGE") -> str:
    preview = "\n".join(f"{i}. {x}" for i, x in enumerate(items, 1))
    return (
        f"✨ *{title}*\n\n"
        f"📦 Số dòng hợp lệ: `{len(items)}`\n"
        f"⏱ Khoảng cách tối thiểu: `{FILE_MIN_INTERVAL:.0f}s`\n"
        "🧹 Phần `1.` `2.` ... chỉ dùng để nhận biết và sẽ không được gửi.\n\n"
        f"```text\n{preview[:2800]}\n```"
    )


async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE, admin_ids: set[int]):
    if not update.message or not update.effective_user:
        return
    if update.effective_user.id not in admin_ids:
        return
    doc = update.message.document
    if not doc:
        return
    if doc.file_size and doc.file_size > FILE_MAX_BYTES:
        await update.message.reply_text("⛔ Tệp quá lớn. Giới hạn 256 KB.")
        return
    name = (doc.file_name or "messages.txt").lower()
    if not name.endswith((".txt", ".log", ".csv")):
        await update.message.reply_text("⛔ Chỉ nhận .txt/.log/.csv cho chế độ này.")
        return
    tg_file = await doc.get_file()
    path = FILE_DIR / f"{update.effective_user.id}_{int(time.time())}.txt"
    await tg_file.download_to_drive(custom_path=str(path))
    raw = path.read_text(encoding="utf-8", errors="replace")
    items = parse_numbered_text(raw)
    if not items:
        await update.message.reply_text("⚠️ Không tìm thấy dòng dạng `1. nội dung` trong tệp.", parse_mode=ParseMode.MARKDOWN)
        return
    FILE_SESSIONS[update.effective_user.id] = {"path": str(path), "items": items, "created": time.time()}
    await update.message.reply_text(render_preview(items), parse_mode=ParseMode.MARKDOWN, reply_markup=file_keyboard())


async def file_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE, admin_ids: set[int]):
    q = update.callback_query
    if not q or q.from_user.id not in admin_ids:
        return
    uid = q.from_user.id
    session = FILE_SESSIONS.get(uid)
    if q.data == "file_clear":
        FILE_SESSIONS.pop(uid, None)
        await q.edit_message_text("🗑 Đã xóa phiên tệp.")
        return
    if not session:
        await q.edit_message_text("⚠️ Phiên tệp đã hết hoặc chưa tải tệp.")
        return
    items = session["items"]
    if q.data == "file_preview":
        await q.edit_message_text(render_preview(items), parse_mode=ParseMode.MARKDOWN, reply_markup=file_keyboard())
        return
    if q.data == "file_send":
        if uid in FILE_JOBS and not FILE_JOBS[uid].done():
            await q.edit_message_text("⏳ Đang có một phiên gửi tệp chạy.")
            return
        chat_id = q.message.chat_id
        async def worker():
            sent = 0
            try:
                for text in items:
                    await ctx.bot.send_message(chat_id=chat_id, text=text)
                    sent += 1
                    if sent < len(items):
                        await asyncio.sleep(FILE_MIN_INTERVAL)
                await ctx.bot.send_message(chat_id=chat_id, text=f"✨ Hoàn tất: {sent}/{len(items)} dòng.")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await ctx.bot.send_message(chat_id=chat_id, text=f"⚠️ Phiên gửi dừng ở {sent}/{len(items)}: {exc}")
            finally:
                FILE_JOBS.pop(uid, None)
        FILE_JOBS[uid] = ctx.application.create_task(worker(), update=q.message)
        await q.edit_message_text(
            f"🚀 Đã bắt đầu gửi `{len(items)}` dòng.\n"
            f"⏱ Mỗi dòng cách nhau ít nhất `{FILE_MIN_INTERVAL:.0f}s`.\n"
            "🛑 Dùng /filestop để dừng.",
            parse_mode=ParseMode.MARKDOWN,
        )


async def file_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE, admin_ids: set[int]):
    uid = update.effective_user.id
    if uid not in admin_ids:
        return
    task = FILE_JOBS.get(uid)
    if task and not task.done():
        task.cancel()
        await update.message.reply_text("🛑 Đã yêu cầu dừng phiên gửi tệp.")
    else:
        await update.message.reply_text("📭 Không có phiên gửi tệp đang chạy.")
