import os
import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode, MessageMediaType

# Bot Configuration
API_ID = 20219694 
API_HASH = "29d9b3a01721ab452fcae79346769e29"
BOT_TOKEN = "8050401845:AAHJh55GaGGt79-D0lJT2apXu3DxkVrgmjQ"

class Config:
    OFFSET = 0
    PROCESSING = False
    CURRENT_BATCH = []
    EXTRACT_LIMIT = 100
    CURRENT_CHAT_ID = None
    CURRENT_START_MSG_ID = 0

# Initialize Pyrogram Client
app = Client(
    "caption_link_modifier",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

def modify_links(text: str, offset: int) -> str:
    """Modify only Telegram message IDs in text while preserving other links"""
    if not text:
        return text
        
    def replacer(match):
        url = match.group(0)
        # Skip if it's a message link (we'll handle these separately)
        if re.search(r't\.me/(?:c/)?[\w-]+/\d+$', url):
            return url
        parts = url.split('/')
        if parts[-1].isdigit():
            parts[-1] = str(int(parts[-1]) + offset)
        return '/'.join(parts)
        
    # First modify non-message links
    pattern = r'https?://(?:t\.me|telegram\.me)/(?:c/)?[\w-]+/\d+'
    text = re.sub(pattern, replacer, text)
    
    # Then modify message links
    def msg_link_replacer(match):
        prefix = match.group(1)
        chat = match.group(2)
        msg_id = match.group(3)
        if msg_id.isdigit():
            return f"{prefix}{chat}/{int(msg_id) + offset}"
        return match.group(0)
    
    msg_pattern = r'(https?://(?:t\.me|telegram\.me)/(?:c/)?([\w-]+)/(\d+))'
    return re.sub(msg_pattern, msg_link_replacer, text)

async def process_message(client: Client, message: Message, target_chat: str):
    """Process and forward message with modified caption links"""
    try:
        caption = message.caption or ""
        modified_caption = modify_links(caption, Config.OFFSET)
        
        if message.media:
            if message.media == MessageMediaType.PHOTO:
                await client.send_photo(
                    target_chat,
                    message.photo.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            elif message.media == MessageMediaType.VIDEO:
                await client.send_video(
                    target_chat,
                    message.video.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            elif message.media == MessageMediaType.DOCUMENT:
                await client.send_document(
                    target_chat,
                    message.document.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            elif message.media == MessageMediaType.ANIMATION:
                await client.send_animation(
                    target_chat,
                    message.animation.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
        elif message.text:
            modified_text = modify_links(message.text, Config.OFFSET)
            await client.send_message(
                target_chat,
                modified_text,
                parse_mode=ParseMode.MARKDOWN
            )
        return True
    except Exception as e:
        print(f"Error processing message: {e}")
        return False

@app.on_message(filters.command("start"))
async def start(client: Client, message: Message):
    await message.reply(
        "🤖 **Advanced Telegram Post Processor**\n\n"
        "🔹 /batch [limit] - Start processing messages (default 100)\n"
        "🔹 /addnumber N - Add N to message IDs in links\n"
        "🔹 /lessnumber N - Subtract N from message IDs in links\n"
        "🔹 /setoffset N - Set absolute offset value\n"
        "🔹 /cancel - Cancel current operation\n\n"
        "📌 Send a Telegram post link after starting batch mode",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Help", callback_data="help")]
        ])
    )

@app.on_message(filters.command(["addnumber", "lessnumber", "setoffset"]))
async def set_offset(client: Client, message: Message):
    try:
        amount = int(message.command[1])
        if message.command[0] == "addnumber":
            Config.OFFSET += amount
            action = "added to"
        elif message.command[0] == "lessnumber":
            Config.OFFSET -= amount
            action = "subtracted from"
        else:
            Config.OFFSET = amount
            action = "set to"
            
        await message.reply(f"✅ Offset {action} {amount}\nNew offset: {Config.OFFSET}")
    except (IndexError, ValueError):
        await message.reply("⚠️ Usage: /addnumber 2 or /lessnumber 3 or /setoffset 5")

@app.on_message(filters.command("batch"))
async def batch(client: Client, message: Message):
    if Config.PROCESSING:
        await message.reply("⚠️ Another operation in progress")
        return
        
    Config.PROCESSING = True
    if len(message.command) > 1:
        try:
            Config.EXTRACT_LIMIT = min(int(message.command[1]), 200)
        except ValueError:
            await message.reply("⚠️ Invalid limit number")
            Config.PROCESSING = False
            return
            
    await message.reply(
        f"🔹 Batch Mode Started\n"
        f"📌 Limit: {Config.EXTRACT_LIMIT} messages\n"
        f"🔗 Current Offset: {Config.OFFSET}\n\n"
        f"📤 Send me:\n"
        f"1. The target chat username where to forward\n"
        f"2. A Telegram post link from source channel\n\n"
        f"Example:\n"
        f"`@destination_channel\n"
        f"https://t.me/source_channel/123`",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Cancel", callback_data="cancel")]
        ]),
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_message(filters.command("cancel"))
async def cancel(client: Client, message: Message):
    Config.PROCESSING = False
    Config.CURRENT_CHAT_ID = None
    await message.reply("✅ Operation cancelled")

@app.on_message(filters.text & filters.incoming)
async def handle_message(client: Client, message: Message):
    if not Config.PROCESSING:
        return
        
    try:
        # First message should be the target chat
        if Config.CURRENT_CHAT_ID is None:
            target_chat = message.text.strip()
            if not target_chat.startswith('@') and not target_chat.startswith('-100'):
                await message.reply("⚠️ First send the target chat username (e.g. @channel_username)")
                return
                
            Config.CURRENT_CHAT_ID = target_chat
            await message.reply(f"✅ Target chat set to {target_chat}\nNow send the source post link")
            return
            
        # Second message should be the source link
        link = re.search(r't\.me/(?:c/)?([^/]+)/(\d+)', message.text)
        if not link:
            await message.reply("⚠️ Invalid Telegram link format. Send like: https://t.me/channel/123")
            return
            
        chat_id = link.group(1)
        start_msg_id = int(link.group(2))
        
        progress = await message.reply("⏳ Starting processing...")
        processed = 0
        failed = 0
        
        for i in range(Config.EXTRACT_LIMIT):
            if not Config.PROCESSING:
                break
                
            try:
                msg = await client.get_messages(chat_id, start_msg_id + i)
                if not msg or msg.empty:
                    continue
                    
                if await process_message(client, msg, Config.CURRENT_CHAT_ID):
                    processed += 1
                else:
                    failed += 1
                    
                if (processed + failed) % 5 == 0:
                    await progress.edit(
                        f"⏳ Progress: {processed + failed}/{Config.EXTRACT_LIMIT}\n"
                        f"✅ Success: {processed}\n"
                        f"❌ Failed: {failed}"
                    )
                    
                await asyncio.sleep(1)  # Rate limiting
            except Exception as e:
                print(f"Error getting message {i}: {e}")
                failed += 1
                continue
                
        await progress.edit(
            f"✅ Batch Complete!\n"
            f"📊 Total: {processed + failed}\n"
            f"✅ Success: {processed}\n"
            f"❌ Failed: {failed}\n"
            f"🔗 Offset Applied: {Config.OFFSET}"
        )
        
        # Reset state
        Config.PROCESSING = False
        Config.CURRENT_CHAT_ID = None
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")
        Config.PROCESSING = False
        Config.CURRENT_CHAT_ID = None

@app.on_callback_query(filters.regex("cancel"))
async def cancel_callback(client, callback):
    Config.PROCESSING = False
    Config.CURRENT_CHAT_ID = None
    await callback.message.edit("❌ Operation cancelled")

if __name__ == "__main__":
    print("⚡ Advanced Bot Started!")
    app.run()
