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
    PROCESSING = False
    CURRENT_CHAT_ID = None

app = Client(
    "batch_link_modifier",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

def modify_caption_links(text: str, offset: int) -> str:
    """Only modifies Telegram message links in captions"""
    if not text:
        return text

    def replacer(match):
        url = match.group(1)
        chat = match.group(2)
        msg_id = match.group(3)
        return f"{url}{chat}/{int(msg_id) + offset}"

    # This pattern matches t.me/.../123 links but not media source links
    pattern = r'(https?://t\.me/(c/\d+|[\w-]+)/(\d+))'
    return re.sub(pattern, replacer, text)

async def process_message(client: Client, message: Message, target_chat: str):
    try:
        if message.media:
            caption = message.caption or ""
            modified_caption = modify_caption_links(caption, Config.OFFSET)
            
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
            else:
                await client.send_document(
                    target_chat,
                    message.document.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            modified_text = modify_caption_links(message.text, Config.OFFSET)
            await client.send_message(
                target_chat,
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
🤖 **Batch Link Modifier Bot**

🔹 /batch - Process all posts from a given link to latest
🔹 /addnumber N - Add N to message IDs in captions
🔹 /lessnumber N - Subtract N from message IDs
🔹 /setoffset N - Set absolute offset value
🔹 /cancel - Stop current processing

**How to use:**
1. First set offset if needed
2. Send /batch
3. Send target chat (@username)
4. Send source post link (https://t.me/channel/123)
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

@app.on_message(filters.command("batch"))
async def start_batch(client: Client, message: Message):
    if Config.PROCESSING:
        return await message.reply("⚠️ Processing already in progress")
    
    Config.PROCESSING = True
    Config.CURRENT_CHAT_ID = message.chat.id
    await message.reply(
        f"🔹 Batch Mode Started\n"
        f"🔢 Current Offset: {Config.OFFSET}\n\n"
        f"Please send:\n"
        f"1. Target chat username (where to forward)\n"
        f"2. Source post link (starting point)\n\n"
        f"Example:\n"
        f"```\n"
        f"@my_backup_channel\n"
        f"https://t.me/source_channel/123\n"
        f"```",
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_message(filters.command("cancel"))
async def cancel_cmd(client: Client, message: Message):
    Config.PROCESSING = False
    await message.reply("✅ Processing stopped")

# Handle batch input
@app.on_message(filters.text & filters.private)
async def handle_batch_input(client: Client, message: Message):
    if not Config.PROCESSING or message.chat.id != Config.CURRENT_CHAT_ID:
        return
    
    try:
        parts = message.text.split('\n')
        if len(parts) < 2:
            return await message.reply("⚠️ Invalid format! Send:\n@target_channel\nhttps://t.me/source/123")
        
        target_chat = parts[0].strip()
        source_link = parts[1].strip()
        
        match = re.search(r't\.me/(?:c/)?([^/]+)/(\d+)', source_link)
        if not match:
            return await message.reply("❌ Invalid Telegram link format")
        
        chat_id = match.group(1)
        start_msg_id = int(match.group(2))
        
        progress_msg = await message.reply("⏳ Starting processing from this post to latest...")
        processed = failed = 0
        
        # Process from given message to latest (message_id = 1)
        current_id = start_msg_id
        while Config.PROCESSING and current_id >= 1:
            try:
                msg = await client.get_messages(chat_id, current_id)
                if msg and not msg.empty:
                    if await process_message(client, msg, target_chat):
                        processed += 1
                    else:
                        failed += 1
                
                if (processed + failed) % 5 == 0:
                    await progress_msg.edit(
                        f"⏳ Progress: {processed} processed, {failed} failed\n"
                        f"🔢 Current ID: {current_id}\n"
                        f"⚙️ Offset Applied: {Config.OFFSET}"
                    )
                
                current_id -= 1
                await asyncio.sleep(1)  # Rate limiting
            
            except FloodWait as e:
                await asyncio.sleep(e.value)
                failed += 1
            except Exception as e:
                print(f"Error getting message {current_id}: {e}")
                failed += 1
                continue
        
        await progress_msg.edit(
            f"✅ Batch Complete!\n"
            f"• Total Processed: {processed}\n"
            f"• Failed: {failed}\n"
            f"• Final Offset Applied: {Config.OFFSET}"
        )
    
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")
    finally:
        Config.PROCESSING = False
        Config.CURRENT_CHAT_ID = None

if __name__ == "__main__":
    print("⚡ Batch Processing Bot Started!")
    app.start()
    idle()
    app.stop()
