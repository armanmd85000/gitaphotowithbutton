import re
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyrogram.enums import ParseMode, MessageMediaType
from pyrogram.errors import FloodWait

# Bot Configuration
API_ID = 20219694
API_HASH = "29d9b3a01721ab452fcae79346769e29"
BOT_TOKEN = "7942215521:AAG5Zardlr7ULt2-yleqXeKjHKp4AQtVzd8"

class Config:
    OFFSET = 0  # How much to add/subtract from message IDs in captions

app = Client(
    "telegram_link_modifier",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

def is_not_command(_, __, message: Message):
    """Custom filter to identify non-command messages"""
    return not message.text.startswith('/')

def modify_telegram_links(text: str, offset: int) -> str:
    """Modifies only Telegram message links in text"""
    if not text:
        return text

    def replacer(match):
        full_url = match.group(0)
        msg_id = int(match.group(2))
        return full_url.replace(f"/{msg_id}", f"/{msg_id + offset}")

    # Pattern to match Telegram links (both t.me and telegram.me)
    pattern = r'https?://(?:t\.me|telegram\.me)/(?:c/)?\d+/\d+'
    return re.sub(pattern, replacer, text)

async def process_message(client: Client, message: Message):
    try:
        if message.media:
            caption = message.caption or ""
            modified_caption = modify_telegram_links(caption, Config.OFFSET)
            
            if message.media == MessageMediaType.PHOTO:
                await message.reply_photo(
                    message.photo.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            elif message.media == MessageMediaType.VIDEO:
                await message.reply_video(
                    message.video.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await message.reply_document(
                    message.document.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            modified_text = modify_telegram_links(message.text, Config.OFFSET)
            await message.reply(
                modified_text,
                parse_mode=ParseMode.MARKDOWN
            )
        
    except FloodWait as e:
        print(f"Waiting {e.value} seconds due to flood limit")
        await asyncio.sleep(e.value)
    except Exception as e:
        print(f"Error processing message: {e}")

@app.on_message(filters.command(["start", "help"]))
async def start_cmd(client: Client, message: Message):
    help_text = """
🤖 **Telegram Link Modifier Bot**

🔹 Send me any Telegram post link
🔹 I'll modify Telegram links in captions

⚙️ **Commands:**
/addnumber N - Add N to message IDs in links
/lessnumber N - Subtract N from message IDs
/setoffset N - Set absolute offset value

Example:
1. /addnumber 5
2. Send: https://t.me/c/123456/789
3. Output: https://t.me/c/123456/794
"""
    await message.reply(help_text)

@app.on_message(filters.command(["addnumber", "lessnumber", "setoffset"]))
async def set_offset_cmd(client: Client, message: Message):
    try:
        amount = int(message.command[1])
        if message.command[0] == "addnumber":
            Config.OFFSET += amount
            action = "Added"
        elif message.command[0] == "lessnumber":
            Config.OFFSET -= amount
            action = "Subtracted"
        else:
            Config.OFFSET = amount
            action = "Set"
        
        await message.reply(f"✅ {action} offset: {amount}\nNew offset: {Config.OFFSET}")
    except:
        await message.reply("⚠️ Usage: /addnumber 2 or /lessnumber 3 or /setoffset 5")

# Fixed message handler - uses custom filter instead of ~ operator
@app.on_message(filters.text & filters.create(is_not_command))
async def handle_message(client: Client, message: Message):
    if "t.me/" not in message.text:
        return
    
    try:
        match = re.search(r't\.me/(?:c/)?(\d+)/(\d+)', message.text)
        if not match:
            return await message.reply("❌ Invalid link format. Send like: https://t.me/channel/123")

        chat_id = match.group(1)
        msg_id = int(match.group(2))

        original_msg = await client.get_messages(chat_id, msg_id)
        if not original_msg:
            return await message.reply("❌ Couldn't fetch that message")
        
        await process_message(client, original_msg)
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    print("⚡ Telegram Link Modifier Bot Started!")
    app.start()
    idle()
    app.stop()
