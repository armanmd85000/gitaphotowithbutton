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
    BATCH_MODE = False
    CHAT_ID = None
    START_ID = None
    END_ID = None

app = Client(
    "ultimate_link_modifier",
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

    pattern = r'(https?://t\.me/(c/\d+|[\w-]+)/(\d+))'
    return re.sub(pattern, replacer, text)

async def safe_send_message(client: Client, chat_id: int, text: str):
    """Handle message sending with error handling"""
    try:
        await client.send_message(
            chat_id,
            text,
            parse_mode=ParseMode.MARKDOWN
        )
        return True
    except ChatWriteForbidden:
        print(f"Cannot send messages to chat {chat_id}")
        return False
    except Exception as e:
        print(f"Error sending message: {e}")
        return False

async def process_message(client: Client, source_msg: Message, target_chat_id: int):
    try:
        if source_msg.media:
            caption = source_msg.caption or ""
            modified_caption = modify_caption_links(caption, Config.OFFSET)
            
            try:
                if source_msg.media == MessageMediaType.PHOTO:
                    await client.send_photo(
                        target_chat_id,
                        source_msg.photo.file_id,
                        caption=modified_caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                elif source_msg.media == MessageMediaType.VIDEO:
                    await client.send_video(
                        target_chat_id,
                        source_msg.video.file_id,
                        caption=modified_caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await client.send_document(
                        target_chat_id,
                        source_msg.document.file_id,
                        caption=modified_caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                return True
            except ChatWriteForbidden:
                # If can't send media, try sending just the caption as text
                if modified_caption:
                    return await safe_send_message(client, target_chat_id, modified_caption)
                return False
        else:
            modified_text = modify_caption_links(source_msg.text, Config.OFFSET)
            return await safe_send_message(client, target_chat_id, modified_text)
        
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
🤖 **Ultimate Link Modifier Bot**

🔹 /batch - Process all posts between two links
🔹 /addnumber N - Add N to message IDs in captions
🔹 /lessnumber N - Subtract N from message IDs
🔹 /setoffset N - Set absolute offset value
🔹 /cancel - Stop current processing

**How to use batch mode:**
1. Set offset if needed
2. Send /batch
3. Send starting post link (e.g. https://t.me/channel/123)
4. Send ending post link (e.g. https://t.me/channel/456)

The bot will process all posts between these two IDs.
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
        return await message.reply("⚠️ Already processing, use /cancel to stop")
    
    Config.PROCESSING = True
    Config.BATCH_MODE = True
    Config.CHAT_ID = None
    Config.START_ID = None
    Config.END_ID = None
    
    await message.reply(
        f"🔹 Batch Mode Started\n"
        f"🔢 Current Offset: {Config.OFFSET}\n\n"
        f"Please send the STARTING post link\n"
        f"(e.g. https://t.me/channel/123)"
    )

@app.on_message(filters.command("cancel"))
async def cancel_cmd(client: Client, message: Message):
    Config.PROCESSING = False
    Config.BATCH_MODE = False
    await message.reply("✅ Processing stopped")

@app.on_message(filters.text & filters.private)
async def handle_message(client: Client, message: Message):
    if not Config.PROCESSING or "t.me/" not in message.text:
        return
    
    try:
        match = re.search(r't\.me/(?:c/)?([^/]+)/(\d+)', message.text)
        if not match:
            return await message.reply("❌ Invalid link format. Send like: https://t.me/channel/123")

        chat_id = match.group(1)
        msg_id = int(match.group(2))

        if Config.BATCH_MODE:
            if Config.START_ID is None:
                Config.START_ID = msg_id
                Config.CHAT_ID = chat_id
                await message.reply(
                    f"✅ Starting point set: {msg_id}\n"
                    f"Now send the ENDING post link\n"
                    f"(e.g. https://t.me/channel/456)"
                )
            elif Config.END_ID is None:
                if chat_id != Config.CHAT_ID:
                    return await message.reply("❌ Both links must be from same channel")
                
                Config.END_ID = msg_id
                await process_batch(client, message)
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")
        Config.PROCESSING = False
        Config.BATCH_MODE = False

async def process_batch(client: Client, message: Message):
    try:
        start_id = min(Config.START_ID, Config.END_ID)
        end_id = max(Config.START_ID, Config.END_ID)
        total = end_id - start_id + 1
        
        progress_msg = await message.reply(
            f"⏳ Starting batch processing\n"
            f"From ID: {start_id} to {end_id}\n"
            f"Total posts: {total}\n"
            f"Offset: {Config.OFFSET}"
        )
        
        processed = failed = 0
        
        for current_id in range(start_id, end_id + 1):
            if not Config.PROCESSING:
                break
            
            try:
                msg = await client.get_messages(Config.CHAT_ID, current_id)
                if msg and not msg.empty:
                    success = await process_message(client, msg, message.chat.id)
                    if success:
                        processed += 1
                    else:
                        failed += 1
                
                if (processed + failed) % 5 == 0 or current_id == end_id:
                    await progress_msg.edit(
                        f"⏳ Processing: {current_id}/{end_id}\n"
                        f"✅ Success: {processed}\n"
                        f"❌ Failed: {failed}\n"
                        f"📶 Progress: {((current_id-start_id)/total)*100:.1f}%"
                    )
                
                await asyncio.sleep(1)
            
            except FloodWait as e:
                await asyncio.sleep(e.value)
                failed += 1
            except Exception as e:
                print(f"Error processing {current_id}: {e}")
                failed += 1
        
        await progress_msg.edit(
            f"✅ Batch Complete!\n"
            f"• Total Processed: {processed}\n"
            f"• Failed: {failed}\n"
            f"• Offset Applied: {Config.OFFSET}"
        )
    
    except Exception as e:
        await message.reply(f"❌ Batch Error: {str(e)}")
    finally:
        Config.PROCESSING = False
        Config.BATCH_MODE = False

if __name__ == "__main__":
    print("⚡ Ultimate Link Modifier Bot Started!")
    app.start()
    idle()
    app.stop()
