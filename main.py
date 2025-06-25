import re
import asyncio
from typing import Optional, Tuple, Dict, Union, List
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode, MessageMediaType, ChatType, ChatMemberStatus
from pyrogram.errors import (
    FloodWait, RPCError, MessageIdInvalid, ChannelInvalid,
    ChatAdminRequired, PeerIdInvalid, UserNotParticipant, BadRequest
)

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
    REPLACEMENTS = {}
    ADMIN_CACHE = {}
    MESSAGE_FILTERS = {
        'text': True,
        'photo': True,
        'video': True,
        'document': True,
        'audio': True,
        'animation': True,
        'voice': True,
        'video_note': True,
        'sticker': True,
        'poll': True,
        'contact': True
    }
    MAX_RETRIES = 3
    DELAY_BETWEEN_MESSAGES = 0.3

app = Client(
    "ultimate_batch_link_modifier",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

def is_not_command(_, __, message: Message) -> bool:
    return not message.text.startswith('/')

def modify_content(text: str, offset: int) -> str:
    if not text:
        return text

    # Apply word replacements (case-insensitive with word boundaries)
    for original, replacement in sorted(Config.REPLACEMENTS.items(), key=lambda x: (-len(x[0]), x[0].lower()):
        text = re.sub(rf'\b{re.escape(original)}\b', replacement, text, flags=re.IGNORECASE)

    # Modify Telegram links
    def replacer(match):
        prefix = match.group(1) or ""
        domain = match.group(2)
        chat_part = match.group(3) or ""
        chat_id = match.group(4)
        post_id = match.group(5)
        return f"{prefix}{domain}/{chat_part}{chat_id}/{int(post_id) + offset}"

    pattern = r'(https?://)?(t\.me|telegram\.(?:me|dog))/(c/)?([^/\s]+)/(\d+)'
    return re.sub(pattern, replacer, text)

async def verify_permissions(client: Client, chat_id: Union[int, str]) -> Tuple[bool, str]:
    try:
        if chat_id in Config.ADMIN_CACHE:
            return Config.ADMIN_CACHE[chat_id]

        chat = await client.get_chat(chat_id)
        
        if chat.type not in [ChatType.CHANNEL, ChatType.SUPERGROUP]:
            result = (False, "Only channels and supergroups are supported")
            Config.ADMIN_CACHE[chat_id] = result
            return result
            
        try:
            member = await client.get_chat_member(chat.id, "me")
        except UserNotParticipant:
            result = (False, "Bot is not a member of this chat")
            Config.ADMIN_CACHE[chat_id] = result
            return result
            
        if member.status != ChatMemberStatus.ADMINISTRATOR:
            result = (False, "Bot needs to be admin")
            Config.ADMIN_CACHE[chat_id] = result
            return result
        
        required_perms = ["can_post_messages"] if chat.type == ChatType.CHANNEL else ["can_send_messages"]
        
        if member.privileges:
            missing_perms = [
                perm for perm in required_perms 
                if not getattr(member.privileges, perm, False)
            ]
            if missing_perms:
                result = (False, f"Missing permissions: {', '.join(missing_perms)}")
                Config.ADMIN_CACHE[chat_id] = result
                return result
        
        result = (True, "OK")
        Config.ADMIN_CACHE[chat_id] = result
        return result
        
    except (ChannelInvalid, PeerIdInvalid):
        return False, "Invalid chat ID"
    except Exception as e:
        return False, f"Error: {str(e)}"

async def process_message(client: Client, source_msg: Message, target_chat_id: int) -> bool:
    for attempt in range(Config.MAX_RETRIES):
        try:
            if source_msg.service or source_msg.empty:
                return False
                
            media_type = source_msg.media
            if media_type and Config.MESSAGE_FILTERS.get(media_type.value, False):
                caption = source_msg.caption or ""
                modified_caption = modify_content(caption, Config.OFFSET)
                
                media_mapping = {
                    MessageMediaType.PHOTO: client.send_photo,
                    MessageMediaType.VIDEO: client.send_video,
                    MessageMediaType.DOCUMENT: client.send_document,
                    MessageMediaType.AUDIO: client.send_audio,
                    MessageMediaType.ANIMATION: client.send_animation,
                    MessageMediaType.VOICE: client.send_voice,
                    MessageMediaType.VIDEO_NOTE: client.send_video_note,
                    MessageMediaType.STICKER: client.send_sticker
                }
                
                if media_type in media_mapping:
                    await media_mapping[media_type](
                        chat_id=target_chat_id,
                        **{media_type.value: getattr(source_msg, media_type.value).file_id},
                        caption=modified_caption if media_type != MessageMediaType.STICKER else None,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return True
                else:
                    await client.copy_message(
                        chat_id=target_chat_id,
                        from_chat_id=source_msg.chat.id,
                        message_id=source_msg.id,
                        caption=modify_content(source_msg.caption or "", Config.OFFSET),
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return True
            elif source_msg.text and Config.MESSAGE_FILTERS['text']:
                await client.send_message(
                    chat_id=target_chat_id,
                    text=modify_content(source_msg.text, Config.OFFSET),
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=source_msg.reply_markup
                )
                return True
                
            return False
            
        except FloodWait as e:
            if attempt == Config.MAX_RETRIES - 1:
                raise
            await asyncio.sleep(e.value)
        except Exception as e:
            print(f"Attempt {attempt + 1} failed for message {source_msg.id}: {e}")
            if attempt == Config.MAX_RETRIES - 1:
                return False
            await asyncio.sleep(1)
    
    return False

@app.on_message(filters.command(["start", "help"]))
async def start_cmd(client: Client, message: Message):
    help_text = """
🚀 **Ultimate Batch Link Modifier Bot** 🚀

🔹 **Core Features:**
- Batch process messages with ID offset
- Smart word replacement system
- Comprehensive media support
- Automatic retry mechanism

🔹 **Basic Commands:**
/batch - Start batch processing
/addnumber N - Add offset N
/lessnumber N - Subtract offset N
/setoffset N - Set absolute offset
/stop - Cancel current operation

🔹 **Word Replacement:**
/replacewords - View replacements
/addreplace ORIG REPL - Add replacement
/removereplace WORD - Remove replacement

🔹 **Message Filters:**
/filtertypes - Show filters
/enablefilter TYPE - Enable filter
/disablefilter TYPE - Disable filter

🔹 **System:**
/status - Show current config
/reset - Reset all settings

📌 **Note:** 
- Bot must be admin in both chats
- Works best in supergroups/channels
- Automatically detects target chat
"""
    await message.reply(help_text, parse_mode=ParseMode.MARKDOWN)

# [Previous command handlers for offset, replacements, filters etc...]

@app.on_message(filters.command("batch"))
async def start_batch(client: Client, message: Message):
    if Config.PROCESSING:
        return await message.reply("⚠️ Already processing! Use /stop to cancel")
    
    Config.PROCESSING = True
    Config.BATCH_MODE = True
    Config.CHAT_ID = None
    Config.START_ID = None
    Config.END_ID = None
    
    await message.reply(
        f"🔹 **Batch Mode Activated**\n"
        f"▫️ Offset: {Config.OFFSET}\n"
        f"▫️ Replacements: {len(Config.REPLACEMENTS)}\n\n"
        f"Reply to the FIRST message or send its link"
    )

@app.on_message(filters.command(["stop", "cancel"]))
async def stop_cmd(client: Client, message: Message):
    if Config.PROCESSING:
        Config.PROCESSING = False
        if Config.CURRENT_TASK:
            Config.CURRENT_TASK.cancel()
        await message.reply("✅ Processing stopped")
    else:
        await message.reply("⚠️ No active process")

@app.on_message(filters.text & filters.create(is_not_command))
async def handle_message(client: Client, message: Message):
    if not Config.PROCESSING:
        return
    
    try:
        if message.reply_to_message:
            source_msg = message.reply_to_message
            chat_id = source_msg.chat.username or f"-100{abs(source_msg.chat.id)}"
            msg_id = source_msg.id
        else:
            link_info = parse_message_link(message.text)
            if not link_info:
                return await message.reply("❌ Invalid message link")
            chat_id, msg_id = link_info

        if Config.BATCH_MODE:
            if Config.START_ID is None:
                has_perms, perm_msg = await verify_permissions(client, chat_id)
                if not has_perms:
                    Config.PROCESSING = False
                    return await message.reply(f"❌ Permission error: {perm_msg}")
                
                Config.START_ID = msg_id
                Config.CHAT_ID = chat_id
                await message.reply(
                    f"✅ First message set: {msg_id}\n"
                    f"Now reply to the LAST message or send its link"
                )
            elif Config.END_ID is None:
                if chat_id != Config.CHAT_ID:
                    return await message.reply("❌ Both messages must be from same chat")
                
                Config.END_ID = msg_id
                Config.CURRENT_TASK = asyncio.create_task(process_batch(client, message))
        else:
            try:
                msg = await client.get_messages(chat_id, msg_id)
                if msg and not msg.empty:
                    target_chat = message.chat.id
                    success = await process_message(client, msg, target_chat)
                    if not success:
                        await message.reply("⚠️ Failed to process this message")
            except Exception as e:
                await message.reply(f"❌ Error: {str(e)}")
            
    except Exception as e:
        await message.reply(f"❌ Critical error: {str(e)}")
        Config.PROCESSING = False
        Config.BATCH_MODE = False

async def process_batch(client: Client, message: Message):
    try:
        start_id = min(Config.START_ID, Config.END_ID)
        end_id = max(Config.START_ID, Config.END_ID)
        total = end_id - start_id + 1
        
        target_chat = message.chat.id
        
        # Verify permissions again before starting
        has_perms, perm_msg = await verify_permissions(client, Config.CHAT_ID)
        if not has_perms:
            await message.reply(f"❌ Source chat permission error: {perm_msg}")
            Config.PROCESSING = False
            return
            
        has_perms, perm_msg = await verify_permissions(client, target_chat)
        if not has_perms:
            await message.reply(f"❌ Target chat permission error: {perm_msg}")
            Config.PROCESSING = False
            return

        progress_msg = await message.reply(
            f"⚡ **Batch Processing Started**\n"
            f"▫️ Source: {Config.CHAT_ID}\n"
            f"▫️ Range: {start_id}-{end_id}\n"
            f"▫️ Total: {total} messages\n"
            f"▫️ Offset: {Config.OFFSET}\n"
            f"▫️ Target: Current chat",
            parse_mode=ParseMode.MARKDOWN
        )
        
        processed = failed = 0
        last_update = time.time()
        
        for current_id in range(start_id, end_id + 1):
            if not Config.PROCESSING:
                break
            
            try:
                msg = await client.get_messages(Config.CHAT_ID, current_id)
                if msg and not msg.empty:
                    success = await process_message(client, msg, target_chat)
                    if success:
                        processed += 1
                    else:
                        failed += 1
                else:
                    failed += 1
                
                if time.time() - last_update >= 5 or current_id == end_id:
                    progress = ((current_id - start_id) / total) * 100
                    try:
                        await progress_msg.edit(
                            f"⚡ **Processing Batch**\n"
                            f"▫️ Progress: {progress:.1f}%\n"
                            f"▫️ Current: {current_id}\n"
                            f"✅ Success: {processed}\n"
                            f"❌ Failed: {failed}"
                        )
                        last_update = time.time()
                    except:
                        pass
                
                await asyncio.sleep(Config.DELAY_BETWEEN_MESSAGES)
            except FloodWait as e:
                await progress_msg.edit(f"⏳ Flood wait: {e.value}s...")
                await asyncio.sleep(e.value)
            except Exception as e:
                print(f"Error processing {current_id}: {e}")
                failed += 1
                await asyncio.sleep(1)
        
        if Config.PROCESSING:
            await progress_msg.edit(
                f"✅ **Batch Complete!**\n"
                f"▫️ Total: {total}\n"
                f"✅ Success: {processed}\n"
                f"❌ Failed: {failed}\n"
                f"▫️ Success Rate: {(processed/total)*100:.1f}%"
            )
    
    except Exception as e:
        await message.reply(f"❌ Batch failed: {str(e)}")
    finally:
        Config.PROCESSING = False
        Config.BATCH_MODE = False
        Config.CURRENT_TASK = None

if __name__ == "__main__":
    print("⚡ Ultimate Batch Link Modifier Bot Started!")
    try:
        app.start()
        idle()
    except Exception as e:
        print(f"Fatal error: {e}")
    finally:
        app.stop()
