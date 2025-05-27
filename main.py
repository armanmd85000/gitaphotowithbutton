import re
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyrogram.enums import ParseMode, MessageMediaType
from pyrogram.errors import FloodWait, RPCError

# Bot Configuration
API_ID = 20219694
API_HASH = "29d9b3a01721ab452fcae79346769e29"
BOT_TOKEN = "7972190756:AAHa4pUAZBTWSZ3smee9sEWiFv-lFhT5USA"

class Config:
    OFFSET = 0
    PROCESSING = False
    BATCH_MODE = False
    CHAT_ID = None
    START_ID = None
    END_ID = None
    CURRENT_TASK = None

app = Client(
    "batch_link_modifier",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

def is_not_command(_, __, message: Message):
    return not message.text.startswith('/')

def modify_telegram_links(text: str, offset: int) -> str:
    if not text:
        return text

    def replacer(match):
        full_url = match.group(0)
        msg_id = int(match.group(2))
        return full_url.replace(f"/{msg_id}", f"/{msg_id + offset}")

    pattern = r'https?://(?:t\.me|telegram\.me)/(?:c/)?([^/]+)/(\d+)'
    return re.sub(pattern, replacer, text)

async def process_message(client: Client, source_msg: Message, target_chat_id: int):
    try:
        if source_msg.media:
            caption = source_msg.caption or ""
            modified_caption = modify_telegram_links(caption, Config.OFFSET)
            
            if source_msg.media == MessageMediaType.PHOTO:
                await client.send_photo(
                    chat_id=target_chat_id,
                    photo=source_msg.photo.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            elif source_msg.media == MessageMediaType.VIDEO:
                await client.send_video(
                    chat_id=target_chat_id,
                    video=source_msg.video.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            elif source_msg.media == MessageMediaType.DOCUMENT:
                await client.send_document(
                    chat_id=target_chat_id,
                    document=source_msg.document.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await client.copy_message(
                    chat_id=target_chat_id,
                    from_chat_id=source_msg.chat.id,
                    message_id=source_msg.id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            modified_text = modify_telegram_links(source_msg.text, Config.OFFSET)
            await client.send_message(
                chat_id=target_chat_id,
                text=modified_text,
                parse_mode=ParseMode.MARKDOWN
            )
        return True
        
    except FloodWait as e:
        print(f"Flood wait: Sleeping for {e.value} seconds")
        await asyncio.sleep(e.value)
        return False
    except RPCError as e:
        print(f"RPCError processing message {source_msg.id}: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error processing message {source_msg.id}: {e}")
        return False

@app.on_message(filters.command(["start", "help"]))
async def start_cmd(client: Client, message: Message):
    help_text = """
🤖 **Batch Link Modifier Bot**

🔹 /batch - Process all posts between two links
🔹 /addnumber N - Add N to message IDs in captions
🔹 /lessnumber N - Subtract N from message IDs
🔹 /setoffset N - Set absolute offset value
🔹 /stop - Stop current processing

**How to use batch mode:**
1. First set your offset if needed
2. Send /batch command
3. Reply to the FIRST message you want to process
4. Reply to the LAST message you want to process
5. The bot will process all messages in between

Alternatively, you can send message links instead of replying.
"""
    await message.reply(help_text)

@app.on_message(filters.command(["addnumber", "lessnumber", "setoffset"]))
async def set_offset_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply("⚠️ Usage: /addnumber 2 or /lessnumber 3 or /setoffset 5")
    
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
    except ValueError:
        await message.reply("⚠️ Please provide a valid number")

@app.on_message(filters.command("batch"))
async def start_batch(client: Client, message: Message):
    if Config.PROCESSING:
        return await message.reply("⚠️ Already processing, use /stop to cancel")
    
    Config.PROCESSING = True
    Config.BATCH_MODE = True
    Config.CHAT_ID = None
    Config.START_ID = None
    Config.END_ID = None
    
    await message.reply(
        f"🔹 Batch Mode Started\n"
        f"🔢 Current Offset: {Config.OFFSET}\n\n"
        f"Please REPLY to the FIRST message you want to process\n"
        f"or send its link (e.g. https://t.me/channel/123)"
    )

@app.on_message(filters.command(["stop", "cancel"]))
async def stop_cmd(client: Client, message: Message):
    if Config.PROCESSING:
        Config.PROCESSING = False
        if Config.CURRENT_TASK:
            Config.CURRENT_TASK.cancel()
        await message.reply("✅ Processing stopped")
    else:
        await message.reply("⚠️ No active process to stop")

@app.on_message(filters.text & filters.create(is_not_command))
async def handle_message(client: Client, message: Message):
    if not Config.PROCESSING:
        return
    
    try:
        # Check if message is a reply or contains a link
        if message.reply_to_message:
            source_msg = message.reply_to_message
            chat_id = source_msg.chat.username or f"-100{source_msg.chat.id}"
            msg_id = source_msg.id
        elif "t.me/" in message.text:
            match = re.search(r't\.me/(?:c/)?([^/]+)/(\d+)', message.text)
            if not match:
                return await message.reply("❌ Invalid link format. Send like: https://t.me/channel/123")
            chat_id = match.group(1)
            msg_id = int(match.group(2))
        else:
            return await message.reply("❌ Please reply to a message or send a message link")

        if Config.BATCH_MODE:
            if Config.START_ID is None:
                Config.START_ID = msg_id
                Config.CHAT_ID = chat_id
                await message.reply(
                    f"✅ Starting point set: Message {msg_id}\n"
                    f"Now REPLY to the LAST message you want to process\n"
                    f"or send its link (e.g. https://t.me/channel/456)"
                )
            elif Config.END_ID is None:
                if chat_id != Config.CHAT_ID:
                    return await message.reply("❌ Both messages must be from same chat")
                
                Config.END_ID = msg_id
                Config.CURRENT_TASK = asyncio.create_task(process_batch(client, message))
        else:
            msg = await client.get_messages(chat_id, msg_id)
            if not msg or msg.empty:
                return await message.reply("❌ Couldn't fetch that message")
            
            await process_message(client, msg, message.chat.id)
            
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
            f"Chat: {Config.CHAT_ID}\n"
            f"From ID: {start_id} to {end_id}\n"
            f"Total messages: {total}\n"
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
                
                # Update progress every 5 messages or at the end
                if (processed + failed) % 5 == 0 or current_id == end_id:
                    try:
                        await progress_msg.edit(
                            f"⏳ Processing: {current_id}/{end_id}\n"
                            f"✅ Success: {processed}\n"
                            f"❌ Failed: {failed}\n"
                            f"📶 Progress: {((current_id-start_id)/total)*100:.1f}%"
                        )
                    except:
                        pass
                
                await asyncio.sleep(1)
            
            except FloodWait as e:
                await asyncio.sleep(e.value)
                failed += 1
            except RPCError as e:
                print(f"RPCError processing {current_id}: {e}")
                failed += 1
                await asyncio.sleep(5)
            except Exception as e:
                print(f"Error processing {current_id}: {e}")
                failed += 1
        
        if Config.PROCESSING:  # Only send completion if not stopped
            await progress_msg.edit(
                f"✅ Batch Complete!\n"
                f"• Total messages: {total}\n"
                f"• Successfully processed: {processed}\n"
                f"• Failed: {failed}\n"
                f"• Offset Applied: {Config.OFFSET}"
            )
    
    except asyncio.CancelledError:
        await message.reply("🛑 Batch processing stopped by user")
    except Exception as e:
        await message.reply(f"❌ Batch Error: {str(e)}")
    finally:
        Config.PROCESSING = False
        Config.BATCH_MODE = False
        Config.CURRENT_TASK = None

if __name__ == "__main__":
    print("⚡ Batch Link Modifier Bot Started!")
    try:
        app.start()
        idle()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()
