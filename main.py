import os
import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode, MessageMediaType

# Bot Configuration
API_ID = 20219694 
API_HASH = "29d9b3a01721ab452fcae79346769e29"
BOT_TOKEN = "7942215521:AAG5Zardlr7ULt2-yleqXeKjHKp4AQtVzd8" 
TARGET_CHANNEL = "-1002421745690"  # Replace with your target channel

class Config:
    OFFSET = 0
    PROCESSING = False
    CURRENT_BATCH = []
    EXTRACT_LIMIT = 100

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
        if re.search(r't\.me/(?:c/)?[\w-]+/\d+$', url):
            return url
        parts = url.split('/')
        if parts[-1].isdigit():
            parts[-1] = str(int(parts[-1]) + offset)
        return '/'.join(parts)
        
    pattern = r'https?://(?:t\.me|telegram\.me)/(?:c/)?[\w-]+/\d+'
    return re.sub(pattern, replacer, text)

async def process_message(client: Client, message: Message):
    """Process and forward message with modified caption links"""
    try:
        caption = message.caption or message.text or ""
        modified_caption = modify_links(caption, Config.OFFSET)
        
        if message.media:
            if message.media == MessageMediaType.PHOTO:
                await client.send_photo(
                    TARGET_CHANNEL,
                    message.photo.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            elif message.media == MessageMediaType.VIDEO:
                await client.send_video(
                    TARGET_CHANNEL,
                    message.video.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await client.send_document(
                    TARGET_CHANNEL,
                    message.document.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            await client.send_message(
                TARGET_CHANNEL,
                modified_caption,
                parse_mode=ParseMode.MARKDOWN
            )
        return True
    except Exception as e:
        print(f"Error processing message: {e}")
        return False

@app.on_message(filters.command("start"))
async def start(client: Client, message: Message):
    await message.reply(
        "🤖 **Caption Link Modifier Bot**\n\n"
        "🔹 /batch - Start processing messages\n"
        "🔹 /addnumber N - Add to caption links\n"
        "🔹 /lessnumber N - Subtract from caption links\n"
        "🔹 /cancel - Cancel current operation",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Help", callback_data="help")]
        ])
    )

@app.on_message(filters.command(["addnumber", "lessnumber"]))
async def set_offset(client: Client, message: Message):
    try:
        amount = int(message.command[1])
        if message.command[0] == "addnumber":
            Config.OFFSET += amount
            action = "added"
        else:
            Config.OFFSET -= amount
            action = "subtracted"
        await message.reply(f"✅ {action} {amount} to offset\nNew offset: {Config.OFFSET}")
    except (IndexError, ValueError):
        await message.reply("⚠️ Usage: /addnumber 2 or /lessnumber 3")

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
        f"🔗 Offset: {Config.OFFSET}\n"
        f"📤 Send me a Telegram post link",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Cancel", callback_data="cancel")]
        ])
    )

@app.on_message(filters.command("cancel"))
async def cancel(client: Client, message: Message):
    Config.PROCESSING = False
    await message.reply("✅ Operation cancelled")

@app.on_message(filters.text & filters.incoming)
async def handle_message(client: Client, message: Message):
    if not Config.PROCESSING or "t.me/" not in message.text:
        return
        
    try:
        link = re.search(r't\.me/(?:c/)?([^/]+)/(\d+)', message.text)
        if not link:
            await message.reply("⚠️ Invalid Telegram link")
            return
            
        chat_id = f"-100{link.group(1)}" if "c/" in message.text else link.group(1)
        start_msg_id = int(link.group(2))
        
        progress = await message.reply("⏳ Starting processing...")
        processed = 0
        
        for i in range(Config.EXTRACT_LIMIT):
            if not Config.PROCESSING:
                break
                
            try:
                msg = await client.get_messages(chat_id, start_msg_id + i)
                if not msg or msg.empty:
                    continue
                    
                if await process_message(client, msg):
                    processed += 1
                    
                if processed % 5 == 0:
                    await progress.edit(f"⏳ Processed: {processed}/{Config.EXTRACT_LIMIT}")
                    
            except Exception as e:
                print(f"Error getting message: {e}")
                continue
                
        await progress.edit(f"✅ Done! Processed {processed} messages")
        Config.PROCESSING = False
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")
        Config.PROCESSING = False

@app.on_callback_query(filters.regex("cancel"))
async def cancel_callback(client, callback):
    Config.PROCESSING = False
    await callback.message.edit("❌ Operation cancelled")

if __name__ == "__main__":
    print("⚡ Bot Started!")
    app.run()
