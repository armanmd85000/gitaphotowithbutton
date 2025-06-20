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
    TARGET_CHAT_ID = None
    REPLACEMENTS = {}
    ADMIN_CACHE = {}
    MESSAGE_FILTERS = {
        'text': True,
        'photo': True,
        'video': True,
        'document': True,
        'audio': True
    }

app = Client(
    "advanced_batch_link_modifier",
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
        msg_id = int(match.group(4))
        return f"{prefix}://{domain}/{chat_part}{msg_id + offset}"

    pattern = r'(https?://)?(t\.me|telegram\.(?:me|dog))/(c/)?([^/]+)/(\d+)'
    return re.sub(pattern, replacer, text)

async def verify_permissions(client: Client, chat_id: Union[int, str], is_target=False) -> Tuple[bool, str]:
    try:
        if chat_id in Config.ADMIN_CACHE:
            return Config.ADMIN_CACHE[chat_id]

        chat = await client.get_chat(chat_id)
        
        if chat.type not in [ChatType.CHANNEL, ChatType.SUPERGROUP, ChatType.GROUP]:
            result = (False, "This chat type is not supported")
            Config.ADMIN_CACHE[chat_id] = result
            return result
            
        try:
            member = await client.get_chat_member(chat.id, "me")
        except UserNotParticipant:
            result = (False, "Bot is not a member of this chat")
            Config.ADMIN_CACHE[chat_id] = result
            return result
            
        required_perms = []
        if is_target:
            required_perms.append("can_post_messages" if chat.type == ChatType.CHANNEL else "can_send_messages")
        
        if chat.type == ChatType.CHANNEL:
            if member.status != ChatMemberStatus.ADMINISTRATOR:
                result = (False, "Bot needs to be admin in the channel")
                Config.ADMIN_CACHE[chat_id] = result
                return result
        else:
            if member.status != ChatMemberStatus.ADMINISTRATOR:
                result = (False, "Bot needs to be admin in the group")
                Config.ADMIN_CACHE[chat_id] = result
                return result
        
        if required_perms and member.privileges:
            missing_perms = [
                perm for perm in required_perms 
                if not getattr(member.privileges, perm, False)
            ]
            if missing_perms:
                result = (False, f"Bot missing permissions: {', '.join(missing_perms)}")
                Config.ADMIN_CACHE[chat_id] = result
                return result
        
        result = (True, "OK")
        Config.ADMIN_CACHE[chat_id] = result
        return result
        
    except (ChannelInvalid, PeerIdInvalid):
        return False, "Invalid chat ID or bot not in chat"
    except Exception as e:
        return False, f"Error verifying permissions: {str(e)}"

async def process_message(client: Client, source_msg: Message, target_chat_id: int) -> bool:
    try:
        if source_msg.service or source_msg.empty:
            return False
            
        if source_msg.media and Config.MESSAGE_FILTERS.get(source_msg.media.value, True):
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
            
            if source_msg.media in media_mapping:
                await media_mapping[source_msg.media](
                    chat_id=target_chat_id,
                    **{source_msg.media.value: getattr(source_msg, source_msg.media.value).file_id},
                    caption=modified_caption if source_msg.media != MessageMediaType.STICKER else None,
                    parse_mode=ParseMode.MARKDOWN
                )
                return True
            else:
                modified_caption = modify_content(source_msg.caption or "", Config.OFFSET)
                await client.copy_message(
                    chat_id=target_chat_id,
                    from_chat_id=source_msg.chat.id,
                    message_id=source_msg.id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
                return True
        elif source_msg.text and Config.MESSAGE_FILTERS['text']:
            modified_text = modify_content(source_msg.text, Config.OFFSET)
            await client.send_message(
                chat_id=target_chat_id,
                text=modified_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=source_msg.reply_markup
            )
            return True
            
        return False
        
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

def parse_message_link(text: str) -> Optional[Tuple[str, int]]:
    patterns = [
        r't\.me/(?:c/)?([^/]+)/(\d+)',
        r't\.me/joinchat/([^/]+)',
        r't\.me/\+([^/]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text.split('?')[0])
        if match:
            return match.group(1), int(match.group(2)) if len(match.groups()) > 1 else None
    return None

@app.on_message(filters.command(["start", "help"]))
async def start_cmd(client: Client, message: Message):
    help_text = """
🤖 **Advanced Batch Link Modifier Bot** 🚀

🔹 **Basic Commands:**
/batch - Process messages between two points
/addnumber N - Add N to message IDs
/lessnumber N - Subtract N from message IDs
/setoffset N - Set absolute offset value
/stop - Cancel current operation

🔹 **Word Replacement:**
/replacewords - View current replacements
/addreplace ORIG REPL - Add new replacement
/removereplace WORD - Remove replacement

🔹 **Channel Setup:**
/setchatid @channel - Set target channel
/chatinfo - Check current chat info
/checkperms - Verify bot permissions

📌 **Requirements:**
1. Add bot as admin in BOTH source and target
2. In target: Enable 'Post Messages' permission
3. In source: Enable 'Read Messages' permission
"""
    await message.reply(help_text, parse_mode=ParseMode.MARKDOWN)

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

@app.on_message(filters.command("replacewords"))
async def show_replacements(client: Client, message: Message):
    if not Config.REPLACEMENTS:
        return await message.reply("No word replacements set yet.")
    
    replacements_text = "\n".join(
        f"• `{original}` → `{replacement}`"
        for original, replacement in sorted(Config.REPLACEMENTS.items())
    )
    await message.reply(
        f"🔤 Current Word Replacements ({len(Config.REPLACEMENTS)}):\n\n{replacements_text}",
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_message(filters.command("addreplace"))
async def add_replacement(client: Client, message: Message):
    if len(message.command) < 3:
        return await message.reply("⚠️ Usage: /addreplace ORIGINAL REPLACEMENT")
    
    original = message.command[1].lower()
    replacement = ' '.join(message.command[2:])
    
    Config.REPLACEMENTS[original] = replacement
    await message.reply(
        f"✅ Added replacement:\n"
        f"`{original}` → `{replacement}`\n\n"
        f"Total replacements now: {len(Config.REPLACEMENTS)}",
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_message(filters.command("removereplace"))
async def remove_replacement(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply("⚠️ Usage: /removereplace WORD")
    
    word = message.command[1].lower()
    if word in Config.REPLACEMENTS:
        del Config.REPLACEMENTS[word]
        await message.reply(
            f"✅ Removed replacement for `{word}`\n\n"
            f"Total replacements now: {len(Config.REPLACEMENTS)}",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await message.reply(f"⚠️ No replacement found for `{word}`")

@app.on_message(filters.command("setchatid"))
async def set_target_chat(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply("⚠️ Usage: /setchatid @channel or -100123456789")
    
    chat_id = message.command[1]
    try:
        chat = await client.get_chat(chat_id)
        
        has_perms, perm_msg = await verify_permissions(client, chat.id, is_target=True)
        if not has_perms:
            return await message.reply(f"❌ Permission issue: {perm_msg}")
        
        Config.TARGET_CHAT_ID = chat.id
        await message.reply(
            f"✅ Target chat set to:\n"
            f"Title: {chat.title}\n"
            f"Type: {chat.type}\n"
            f"Username: @{chat.username if chat.username else 'N/A'}\n"
            f"ID: `{chat.id}`\n\n"
            f"Permissions verified ✅",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        await message.reply(f"❌ Error setting chat ID: {str(e)}")

@app.on_message(filters.command("chatinfo"))
async def chat_info(client: Client, message: Message):
    try:
        chat = await client.get_chat(message.chat.id)
        member = await client.get_chat_member(chat.id, "me")
        
        info_text = (
            f"ℹ️ **Chat Information**\n"
            f"Title: {chat.title}\n"
            f"Type: {chat.type}\n"
            f"ID: `{chat.id}`\n"
            f"Username: @{chat.username if chat.username else 'N/A'}\n\n"
            f"🤖 **Bot Status**\n"
            f"Role: {member.status}\n"
        )
        
        if member.status == ChatMemberStatus.ADMINISTRATOR:
            perms = []
            for perm, value in member.privileges.__dict__.items():
                if value and perm != "_":
                    perms.append(f"• {perm}")
            
            info_text += "Admin Permissions:\n" + "\n".join(perms)
        
        await message.reply(info_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await message.reply(f"❌ Error getting chat info: {str(e)}")

@app.on_message(filters.command("checkperms"))
async def check_perms(client: Client, message: Message):
    try:
        chat = await client.get_chat(message.chat.id)
        has_perms, perm_msg = await verify_permissions(client, chat.id)
        
        if has_perms:
            await message.reply(f"✅ Bot has sufficient permissions in this chat!\n\n{perm_msg}")
        else:
            await message.reply(f"❌ Permission issues found:\n{perm_msg}")
    except Exception as e:
        await message.reply(f"❌ Error checking permissions: {str(e)}")

@app.on_message(filters.command("status"))
async def show_status(client: Client, message: Message):
    status_text = (
        f"⚙️ **Bot Status**\n"
        f"Processing: {'✅' if Config.PROCESSING else '❌'}\n"
        f"Batch Mode: {'✅' if Config.BATCH_MODE else '❌'}\n"
        f"Current Offset: {Config.OFFSET}\n"
        f"Word Replacements: {len(Config.REPLACEMENTS)}\n"
    )
    
    if Config.TARGET_CHAT_ID:
        try:
            chat = await client.get_chat(Config.TARGET_CHAT_ID)
            status_text += f"Target Chat: {chat.title} (ID: `{chat.id}`)"
        except:
            status_text += f"Target Chat: ID `{Config.TARGET_CHAT_ID}` (could not fetch details)"
    
    await message.reply(status_text, parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command("reset"))
async def reset_settings(client: Client, message: Message):
    Config.OFFSET = 0
    Config.PROCESSING = False
    Config.BATCH_MODE = False
    Config.CHAT_ID = None
    Config.START_ID = None
    Config.END_ID = None
    Config.TARGET_CHAT_ID = None
    Config.REPLACEMENTS = {}
    
    if Config.CURRENT_TASK:
        Config.CURRENT_TASK.cancel()
        Config.CURRENT_TASK = None
    
    await message.reply("✅ All settings have been completely reset")

@app.on_message(filters.command("batch"))
async def start_batch(client: Client, message: Message):
    if Config.PROCESSING:
        return await message.reply("⚠️ Already processing, use /stop to cancel")
    
    if Config.TARGET_CHAT_ID is None:
        return await message.reply("⚠️ Please set target chat first with /setchatid")
    
    Config.PROCESSING = True
    Config.BATCH_MODE = True
    Config.CHAT_ID = None
    Config.START_ID = None
    Config.END_ID = None
    
    await message.reply(
        f"🔹 Batch Mode Started\n"
        f"🔢 Current Offset: {Config.OFFSET}\n"
        f"🔤 Word Replacements: {len(Config.REPLACEMENTS)}\n"
        f"💬 Target Chat: `{Config.TARGET_CHAT_ID}`\n\n"
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
        if message.reply_to_message:
            source_msg = message.reply_to_message
            chat_id = source_msg.chat.username or f"-100{source_msg.chat.id}"
            msg_id = source_msg.id
        else:
            link_info = parse_message_link(message.text)
            if not link_info:
                return await message.reply("❌ Invalid link format. Send like: https://t.me/channel/123")
            chat_id, msg_id = link_info

        if Config.BATCH_MODE:
            if Config.START_ID is None:
                has_perms, perm_msg = await verify_permissions(client, chat_id)
                if not has_perms:
                    Config.PROCESSING = False
                    return await message.reply(f"❌ Permission issue in source: {perm_msg}")
                
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
            try:
                msg = await client.get_messages(chat_id, msg_id)
                if not msg or msg.empty:
                    return await message.reply("❌ Couldn't fetch that message")
                
                target_chat = Config.TARGET_CHAT_ID or message.chat.id
                success = await process_message(client, msg, target_chat)
                if not success:
                    await message.reply("⚠️ Failed to process this message")
            except (MessageIdInvalid, ChannelInvalid):
                return await message.reply("❌ Invalid message or channel. Make sure the bot has access.")
            except Exception as e:
                return await message.reply(f"❌ Error processing message: {str(e)}")
            
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")
        Config.PROCESSING = False
        Config.BATCH_MODE = False

async def process_batch(client: Client, message: Message):
    try:
        start_id = min(Config.START_ID, Config.END_ID)
        end_id = max(Config.START_ID, Config.END_ID)
        total = end_id - start_id + 1
        
        target_chat = Config.TARGET_CHAT_ID
        
        progress_msg = await message.reply(
            f"⏳ Starting batch processing\n"
            f"Chat: {Config.CHAT_ID}\n"
            f"From ID: {start_id} to {end_id}\n"
            f"Total messages: {total}\n"
            f"Offset: {Config.OFFSET}\n"
            f"Replacements: {len(Config.REPLACEMENTS)}\n"
            f"Target Chat: `{target_chat}`",
            parse_mode=ParseMode.MARKDOWN
        )
        
        processed = failed = 0
        last_update = asyncio.get_event_loop().time()
        last_progress = 0
        
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
                
                now = asyncio.get_event_loop().time()
                if (processed + failed) % 5 == 0 or now - last_update >= 10 or current_id == end_id:
                    progress = ((current_id - start_id) / total) * 100
                    speed = (processed + failed) / (now - last_progress + 0.1)
                    
                    try:
                        await progress_msg.edit(
                            f"⏳ Processing: {current_id}/{end_id}\n"
                            f"✅ Success: {processed}\n"
                            f"❌ Failed: {failed}\n"
                            f"📶 Progress: {progress:.1f}%\n"
                            f"⏱️ Speed: {speed:.1f} msg/s"
                        )
                        last_update = now
                        if (processed + failed) % 50 == 0:
                            last_progress = now
                    except Exception as e:
                        print(f"Error updating progress: {e}")
                
                await asyncio.sleep(0.3)
            
            except FloodWait as e:
                await progress_msg.edit(f"⏳ Flood wait: Sleeping for {e.value} seconds...")
                await asyncio.sleep(e.value)
                failed += 1
            except (MessageIdInvalid, ChannelInvalid):
                failed += 1
                await asyncio.sleep(1)
            except ChatAdminRequired:
                await progress_msg.edit("❌ Bot lost admin privileges during processing!")
                Config.PROCESSING = False
                break
            except RPCError as e:
                print(f"RPCError processing {current_id}: {e}")
                failed += 1
                await asyncio.sleep(5)
            except Exception as e:
                print(f"Error processing {current_id}: {e}")
                failed += 1
                await asyncio.sleep(1)
        
        if Config.PROCESSING:
            completion_text = (
                f"✅ Batch Complete!\n"
                f"• Total messages: {total}\n"
                f"• Successfully processed: {processed}\n"
                f"• Failed: {failed}\n"
                f"• Success rate: {(processed/total)*100:.1f}%\n"
                f"• Offset Applied: {Config.OFFSET}\n"
                f"• Word Replacements: {len(Config.REPLACEMENTS)}\n"
                f"• Target Chat: `{target_chat}`"
            )
            
            if failed > 0:
                completion_text += "\n\n⚠️ Some messages failed. Check bot logs for details."
            
            await progress_msg.edit(completion_text, parse_mode=ParseMode.MARKDOWN)
    
    except asyncio.CancelledError:
        await message.reply("🛑 Batch processing stopped by user")
    except Exception as e:
        await message.reply(f"❌ Batch Error: {str(e)}")
    finally:
        Config.PROCESSING = False
        Config.BATCH_MODE = False
        Config.CURRENT_TASK = None

if __name__ == "__main__":
    print("⚡ Advanced Batch Link Modifier Bot Started!")
    try:
        app.start()
        idle()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Fatal error: {e}")
    finally:
        app.stop()
