import re
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyrogram.enums import ParseMode, MessageMediaType
from pyrogram.errors import FloodWait, ChatWriteForbidden

# Bot Configuration
API_ID = 20219694
API_HASH = "29d9b3a01721ab452fcae79346769e29"
BOT_TOKEN = "7942215521:AAG5Zardlr7ULt2-yleqXeKjHKp4AQtVzd8"

class Config:
    OFFSET = 0  # How much to add/subtract from message IDs in captions
    PROCESSING = False

app = Client(
    "fixed_link_modifier",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

def modify_caption_links(text: str, offset: int) -> str:
    """Only modifies Telegram message links in captions without duplicating parts"""
    if not text:
        return text

    def replacer(match):
        # Get the full matched URL
        full_url = match.group(0)
        # Extract just the message ID part
        msg_id = match.group(3)
        # Calculate new ID
        new_id = int(msg_id) + offset
        # Replace only the message ID part in the URL
        return full_url.replace(f"/{msg_id}", f"/{new_id}")

    # Improved pattern to match Telegram links
    pattern = r'https?://(?:t\.me|telegram\.me)/(?:c/)?(\d+|\w+)/(\d+)(?![^\s])'
    return re.sub(pattern, replacer, text)

async def process_message(client: Client, source_msg: Message):
    try:
        if source_msg.media:
            caption = source_msg.caption or ""
            modified_caption = modify_caption_links(caption, Config.OFFSET)
            
            if source_msg.media == MessageMediaType.PHOTO:
                await client.send_photo(
                    source_msg.chat.id,
                    source_msg.photo.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            elif source_msg.media == MessageMediaType.VIDEO:
                await client.send_video(
                    source_msg.chat.id,
                    source_msg.video.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await client.send_document(
                    source_msg.chat.id,
                    source_msg.document.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            modified_text = modify_caption_links(source_msg.text, Config.OFFSET)
            await client.send_message(
                source_msg.chat.id,
                modified_text,
                parse_mode=ParseMode.MARKDOWN
            )
        return True
        
    except FloodWait as e:
        print(f"Waiting {e.value} seconds due to flood limit")
        await asyncio.sleep(e.value)
        return False
    except Exception as e:
        print(f"Error processing message: {e}")
        return False

@app.on_message(filters.command(["start", "help"]))
async def start_cmd(client: Client, message: Message):
    help_text = """
🤖 **Fixed Link Modifier Bot**

🔹 Send me any Telegram post link
🔹 I'll modify Telegram links in captions

⚙️ **Commands:**
/addnumber N - Add N to message IDs in captions
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

@app.on_message(filters.text & ~filters.command)
async def handle_message(client: Client, message: Message):
    if "t.me/" not in message.text:
        return
    
    try:
        match = re.search(r't\.me/(?:c/)?([^/]+)/(\d+)', message.text)
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
    print("⚡ Fixed Link Modifier Bot Started!")
    app.start()
    idle()
    app.stop()
