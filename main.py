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

app = Client(
    "personal_link_modifier",
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

    # This pattern matches t.me/.../123 links in captions
    pattern = r'(https?://t\.me/(c/\d+|[\w-]+)/(\d+))'
    return re.sub(pattern, replacer, text)

async def process_message(client: Client, message: Message):
    try:
        if message.media:
            caption = message.caption or ""
            modified_caption = modify_caption_links(caption, Config.OFFSET)
            
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
            modified_text = modify_caption_links(message.text, Config.OFFSET)
            await message.reply(
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
🤖 **Personal Link Modifier Bot**

🔹 Send me a post link or forward posts to me
🔹 I'll modify Telegram links in captions

⚙️ **Commands:**
/addnumber N - Add N to message IDs in captions
/lessnumber N - Subtract N from message IDs
/setoffset N - Set absolute offset value
/batch - Process from given post to first post
/cancel - Stop current processing

Example link:
https://t.me/public_channel/123
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
    await message.reply(
        f"🔹 Batch Mode Started\n"
        f"🔢 Current Offset: {Config.OFFSET}\n\n"
        f"Send me a post link to start from\n"
        f"(I'll process from that post to the first post)\n\n"
        f"Example:\n"
        f"https://t.me/source_channel/123"
    )

@app.on_message(filters.command("cancel"))
async def cancel_cmd(client: Client, message: Message):
    Config.PROCESSING = False
    await message.reply("✅ Processing stopped")

# Handle single posts and forwarded messages
@app.on_message(filters.text & ~filters.command & filters.private)
async def handle_single_post(client: Client, message: Message):
    if "t.me/" in message.text:
        # Process a single post link
        await process_post_link(client, message)
    elif message.forward_from_chat:
        # Process forwarded message
        await process_forwarded_message(client, message)

async def process_post_link(client: Client, message: Message):
    try:
        match = re.search(r't\.me/(?:c/)?([^/]+)/(\d+)', message.text)
        if not match:
            return await message.reply("❌ Invalid link format. Send like: https://t.me/channel/123")

        chat_id = match.group(1)
        msg_id = int(match.group(2))

        if Config.PROCESSING:
            # Batch processing mode
            progress_msg = await message.reply("⏳ Starting batch processing...")
            processed = failed = 0
            
            current_id = msg_id
            while Config.PROCESSING and current_id >= 1:
                try:
                    msg = await client.get_messages(chat_id, current_id)
                    if msg and not msg.empty:
                        if await process_message(client, msg):
                            processed += 1
                        else:
                            failed += 1
                    
                    if (processed + failed) % 5 == 0:
                        await progress_msg.edit(
                            f"⏳ Progress: {processed} processed, {failed} failed\n"
                            f"🔢 Current ID: {current_id}"
                        )
                    
                    current_id -= 1
                    await asyncio.sleep(1)
                
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
                f"• Offset Applied: {Config.OFFSET}"
            )
            Config.PROCESSING = False
        else:
            # Single post processing
            msg = await client.get_messages(chat_id, msg_id)
            if not msg:
                return await message.reply("❌ Couldn't fetch that message")
            
            await process_message(client, msg)
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")
        Config.PROCESSING = False

async def process_forwarded_message(client: Client, message: Message):
    try:
        await process_message(client, message)
    except Exception as e:
        await message.reply(f"❌ Error processing forwarded message: {str(e)}")

if __name__ == "__main__":
    print("⚡ Personal Link Modifier Bot Started!")
    app.start()
    idle()
    app.stop()
