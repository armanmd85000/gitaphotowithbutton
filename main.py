import re
import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode, MessageMediaType
from pyrogram.errors import FloodWait, RPCError
import threading

# Bot Configuration
API_ID = 20219694
API_HASH = "29d9b3a01721ab452fcae79346769e29"
BOT_TOKEN = "7942215521:AAG5Zardlr7ULt2-yleqXeKjHKp4AQtVzd8"

class Config:
    OFFSET = 0
    PROCESSING = False
    EXTRACT_LIMIT = 100
    TARGET_CHAT = None
    ACTIVE = True
    RESTART_COUNT = 0

# Initialize with better connection settings
app = Client(
    "link_modifier_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=4,
    sleep_threshold=60,
    no_updates=True
)

def modify_only_caption_links(text: str, offset: int) -> str:
    """Modifies only Telegram message links in captions"""
    if not text:
        return text

    def replacer(match):
        url = match.group(1)
        chat = match.group(2)
        msg_id = match.group(3)
        return f"{url}{chat}/{int(msg_id) + offset}"

    pattern = r'(https?://t\.me/(c/\d+|[\w-]+)/(\d+))'
    return re.sub(pattern, replacer, text)

async def process_single_message(client: Client, message: Message):
    try:
        if message.media:
            caption = message.caption or ""
            modified_caption = modify_only_caption_links(caption, Config.OFFSET)
            
            if message.media == MessageMediaType.PHOTO:
                await client.send_photo(
                    Config.TARGET_CHAT,
                    message.photo.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            elif message.media == MessageMediaType.VIDEO:
                await client.send_video(
                    Config.TARGET_CHAT,
                    message.video.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await client.send_document(
                    Config.TARGET_CHAT,
                    message.document.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            modified_text = modify_only_caption_links(message.text, Config.OFFSET)
            await client.send_message(
                Config.TARGET_CHAT,
                modified_text,
                parse_mode=ParseMode.MARKDOWN
            )
        return True
        
    except FloodWait as e:
        print(f"Flood wait: Sleeping for {e.value} seconds")
        await asyncio.sleep(e.value)
        return False
    except Exception as e:
        print(f"Error processing message: {e}")
        return False

@app.on_message(filters.command(["addnumber", "lessnumber"]))
async def set_offset_cmd(client: Client, message: Message):
    try:
        amount = int(message.command[1])
        if message.command[0] == "addnumber":
            Config.OFFSET += amount
            action = "added"
        else:
            Config.OFFSET -= amount
            action = "subtracted"
        
        await message.reply(f"✅ Offset {action}: {amount}\nNew offset: {Config.OFFSET}")
    except:
        await message.reply("⚠️ Usage: /addnumber 2 or /lessnumber 3")

@app.on_message(filters.command("startbatch"))
async def start_batch(client: Client, message: Message):
    if Config.PROCESSING:
        return await message.reply("⚠️ Processing already in progress")
    
    Config.PROCESSING = True
    args = message.text.split()
    
    if len(args) > 1:
        try:
            Config.EXTRACT_LIMIT = min(int(args[1]), 200)
        except:
            pass
    
    await message.reply(
        f"🔹 Batch processing started\n"
        f"📌 Limit: {Config.EXTRACT_LIMIT} messages\n"
        f"🔢 Offset: {Config.OFFSET}\n\n"
        f"Now send in this format:\n"
        f"`target_channel @username\n"
        f"source_post_link https://t.me/...`"
    )

def is_not_command(_, __, message: Message):
    return not message.text.startswith('/')

@app.on_message(filters.text & filters.incoming & filters.create(is_not_command))
async def handle_batch_input(client: Client, message: Message):
    if not Config.PROCESSING:
        return
    
    try:
        parts = message.text.split('\n')
        if len(parts) < 2:
            return await message.reply("⚠️ Wrong format! Example:\n@target_channel\nhttps://t.me/source/123")
        
        Config.TARGET_CHAT = parts[0].strip()
        source_link = parts[1].strip()
        
        match = re.search(r't\.me/(?:c/)?(\d+|\w+)/(\d+)', source_link)
        if not match:
            return await message.reply("❌ Invalid Telegram link")
        
        chat_id = match.group(1)
        start_id = int(match.group(2))
        
        progress_msg = await message.reply("⏳ Processing started...")
        success = failed = 0
        
        for i in range(Config.EXTRACT_LIMIT):
            if not Config.PROCESSING:
                break
            
            try:
                current_id = start_id + i
                msg = await client.get_messages(chat_id, current_id)
                
                if msg and not msg.empty:
                    if await process_single_message(client, msg):
                        success += 1
                    else:
                        failed += 1
                
                if (success + failed) % 5 == 0:
                    await progress_msg.edit(
                        f"⏳ Progress: {success + failed}/{Config.EXTRACT_LIMIT}\n"
                        f"✅ Success: {success}\n"
                        f"❌ Failed: {failed}"
                    )
                
                await asyncio.sleep(1)
            
            except FloodWait as e:
                await asyncio.sleep(e.value)
                failed += 1
            except Exception as e:
                failed += 1
                continue
        
        await progress_msg.edit(
            f"🎉 Processing complete!\n"
            f"• Total: {success + failed}\n"
            f"• Success: {success}\n"
            f"• Failed: {failed}\n"
            f"• Applied offset: {Config.OFFSET}"
        )
    
    finally:
        Config.PROCESSING = False
        Config.TARGET_CHAT = None

@app.on_message(filters.command("cancel"))
async def cancel_processing(client: Client, message: Message):
    Config.PROCESSING = False
    await message.reply("❌ Processing cancelled")

def keep_alive():
    while Config.ACTIVE:
        time.sleep(300)
        print("Keep-alive ping")

async def run_bot():
    while Config.ACTIVE and Config.RESTART_COUNT < 5:
        try:
            print("⚡ Starting bot...")
            await app.start()
            print("✅ Bot started successfully")
            await app.idle()
        except RPCError as e:
            print(f"RPC Error: {e}")
            Config.RESTART_COUNT += 1
            await asyncio.sleep(10)
        except Exception as e:
            print(f"Unexpected error: {e}")
            Config.RESTART_COUNT += 1
            await asyncio.sleep(30)
        finally:
            if Config.ACTIVE:
                try:
                    await app.stop()
                except:
                    pass

if __name__ == "__main__":
    # Start keep-alive thread
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Run bot with restart capability
    asyncio.get_event_loop().run_until_complete(run_bot())
    
    print("Bot stopped")
