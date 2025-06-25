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
        'audio': True,
        'animation': True,
        'voice': True,
        'video_note': True,
        'sticker': False
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
        chat_id = match.group(4)
        post_id = match.group(5)
        return f"{prefix}{domain}/{chat_part}{chat_id}/{int(post_id) + offset}"

    # Updated pattern to handle all Telegram link formats
    pattern = r'(https?://)?(t\.me|telegram\.(?:me|dog))/(c/)?([^/\s]+)/(\d+)'
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
            if chat.type == ChatType.CHANNEL:
                required_perms.append("can_post_messages")
            else:
                required_perms.append("can_send_messages")
        
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
                try:
                    await media_mapping[media_type](
                        chat_id=target_chat_id,
                        **{media_type.value: getattr(source_msg, media_type.value).file_id},
                        caption=modified_caption if media_type != MessageMediaType.STICKER else None,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return True
                except Exception as e:
                    print(f"Error sending media {media_type}: {e}")
                    return False
            else:
                try:
                    modified_caption = modify_content(source_msg.caption or "", Config.OFFSET)
                    await client.copy_message(
                        chat_id=target_chat_id,
                        from_chat_id=source_msg.chat.id,
                        message_id=source_msg.id,
                        caption=modified_caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return True
                except Exception as e:
                    print(f"Error copying message: {e}")
                    return False
        elif source_msg.text and Config.MESSAGE_FILTERS['text']:
            try:
                modified_text = modify_content(source_msg.text, Config.OFFSET)
                await client.send_message(
                    chat_id=target_chat_id,
                    text=modified_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=source_msg.reply_markup
                )
                return True
            except Exception as e:
                print(f"Error sending text message: {e}")
                return False
                
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

# ... [rest of the command handlers remain the same, but make sure to update the verify_permissions calls]

async def process_batch(client: Client, message: Message):
    try:
        start_id = min(Config.START_ID, Config.END_ID)
        end_id = max(Config.START_ID, Config.END_ID)
        total = end_id - start_id + 1
        
        target_chat = Config.TARGET_CHAT_ID
        
        # Verify permissions again before starting
        has_perms, perm_msg = await verify_permissions(client, Config.CHAT_ID)
        if not has_perms:
            await message.reply(f"❌ Permission issue in source chat: {perm_msg}")
            Config.PROCESSING = False
            return
            
        has_perms, perm_msg = await verify_permissions(client, target_chat, is_target=True)
        if not has_perms:
            await message.reply(f"❌ Permission issue in target chat: {perm_msg}")
            Config.PROCESSING = False
            return

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
                    speed = (processed + failed) / (now - last_progress + 0.1) if (now - last_progress) > 0 else 0
                    
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
                
                await asyncio.sleep(0.5)  # Increased delay to reduce flood
            except FloodWait as e:
                await progress_msg.edit(f"⏳ Flood wait: Sleeping for {e.value} seconds...")
                await asyncio.sleep(e.value)
                failed += 1
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
