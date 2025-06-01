import re
import asyncio
from typing import Optional, Tuple, Dict, Union
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode, MessageMediaType, ChatType, ChatMemberStatus
from pyrogram.errors import (
    FloodWait, RPCError, MessageIdInvalid, ChannelInvalid,
    ChatAdminRequired, PeerIdInvalid, UserNotParticipant
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
    MAX_RETRIES = 5  # Increased retries
    MEDIA_DELAY = 1.5  # Increased delay for media
    TEXT_DELAY = 0.3  # Added delay for text messages
    SKIPPED_IDS = []  # Track skipped messages
    PROGRESS_UPDATE_INTERVAL = 10  # Seconds between progress updates

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

    # Apply word replacements (longest first)
    for original, replacement in sorted(Config.REPLACEMENTS.items(), key=lambda x: -len(x[0])):
        text = re.sub(rf'(?<!\w){re.escape(original)}(?!\w)', replacement, text, flags=re.IGNORECASE)

    # Modify Telegram links
    def replacer(match):
        full_url = match.group(0)
        msg_id = int(match.group(2))
        return full_url.replace(f"/{msg_id}", f"/{msg_id + offset}")

    pattern = r'https?://(?:t\.me|telegram\.(?:me|dog))/(?:c/)?([^/]+)/(\d+)'
    return re.sub(pattern, replacer, text)

async def verify_permissions(client: Client, chat_id: Union[int, str], is_target=False) -> Tuple[bool, str]:
    try:
        chat = await client.get_chat(chat_id)
        
        # Check if it's a channel or supergroup
        if chat.type not in [ChatType.CHANNEL, ChatType.SUPERGROUP, ChatType.GROUP]:
            return False, "This chat type is not supported"
            
        # Get bot's member status
        try:
            member = await client.get_chat_member(chat.id, "me")
        except UserNotParticipant:
            return False, "Bot is not a member of this chat"
            
        # Check admin status and permissions
        if chat.type == ChatType.CHANNEL:
            if member.status != ChatMemberStatus.ADMINISTRATOR:
                return False, "Bot needs to be admin in the channel"
            if is_target and not member.privileges.can_post_messages:
                return False, "Bot needs 'Post Messages' permission in target channel"
        else:  # Groups and supergroups
            if member.status != ChatMemberStatus.ADMINISTRATOR:
                return False, "Bot needs to be admin in the group"
            if is_target and not member.privileges.can_send_messages:
                return False, "Bot needs 'Send Messages' permission in target chat"
                
        return True, "OK"
        
    except (ChannelInvalid, PeerIdInvalid):
        return False, "Invalid chat ID or bot not in chat"
    except Exception as e:
        return False, f"Error verifying permissions: {str(e)}"

async def process_message(client: Client, source_msg: Message, target_chat_id: int) -> bool:
    retries = 0
    while retries < Config.MAX_RETRIES:
        try:
            if source_msg.media:
                caption = source_msg.caption or ""
                modified_caption = modify_content(caption, Config.OFFSET)
                
                # Enhanced media handling with all attributes
                if source_msg.media == MessageMediaType.VIDEO:
                    await client.send_video(
                        chat_id=target_chat_id,
                        video=source_msg.video.file_id,
                        duration=source_msg.video.duration,
                        width=source_msg.video.width,
                        height=source_msg.video.height,
                        thumb=source_msg.video.thumbs[0].file_id if source_msg.video.thumbs else None,
                        caption=modified_caption,
                        parse_mode=ParseMode.MARKDOWN,
                        supports_streaming=True
                    )
                elif source_msg.media == MessageMediaType.PHOTO:
                    await client.send_photo(
                        chat_id=target_chat_id,
                        photo=source_msg.photo.file_id,
                        caption=modified_caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                elif source_msg.media == MessageMediaType.DOCUMENT:
                    await client.send_document(
                        chat_id=target_chat_id,
                        document=source_msg.document.file_id,
                        thumb=source_msg.document.thumbs[0].file_id if source_msg.document.thumbs else None,
                        caption=modified_caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    # Fallback to copy_message for other media types
                    await client.copy_message(
                        chat_id=target_chat_id,
                        from_chat_id=source_msg.chat.id,
                        message_id=source_msg.id,
                        caption=modified_caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                # Extra delay for media messages
                await asyncio.sleep(Config.MEDIA_DELAY)
            else:
                modified_text = modify_content(source_msg.text, Config.OFFSET)
                await client.send_message(
                    chat_id=target_chat_id,
                    text=modified_text,
                    parse_mode=ParseMode.MARKDOWN
                )
                await asyncio.sleep(Config.TEXT_DELAY)
            
            return True
            
        except FloodWait as e:
            print(f"Flood wait: Sleeping for {e.value} seconds")
            await asyncio.sleep(e.value)
            retries += 1
        except RPCError as e:
            print(f"RPCError processing message {source_msg.id} (attempt {retries+1}): {e}")
            retries += 1
            await asyncio.sleep(3)
        except Exception as e:
            print(f"Unexpected error processing message {source_msg.id}: {e}")
            retries += 1
            await asyncio.sleep(2)
    
    print(f"Failed to process message {source_msg.id} after {Config.MAX_RETRIES} attempts")
    Config.SKIPPED_IDS.append(source_msg.id)
    return False

# [All your original command handlers remain exactly the same until process_batch]

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
            f"Target Chat: `{target_chat}`\n\n"
            f"⚠️ Please don't send other commands during processing",
            parse_mode=ParseMode.MARKDOWN
        )
        
        processed = failed = 0
        last_update = asyncio.get_event_loop().time()
        start_time = last_update
        
        for current_id in range(start_id, end_id + 1):
            if not Config.PROCESSING:
                break
            
            try:
                # Enhanced message fetching with retries
                msg = None
                for attempt in range(Config.MAX_RETRIES):
                    try:
                        msg = await client.get_messages(Config.CHAT_ID, current_id)
                        if msg and not msg.empty:
                            break
                        await asyncio.sleep(1)
                    except (MessageIdInvalid, ChannelInvalid) as e:
                        if attempt == Config.MAX_RETRIES - 1:
                            raise
                        await asyncio.sleep(3)
                    except Exception as e:
                        print(f"Error fetching message {current_id}: {e}")
                        await asyncio.sleep(2)
                
                if msg and not msg.empty:
                    success = await process_message(client, msg, target_chat)
                    if success:
                        processed += 1
                    else:
                        failed += 1
                else:
                    failed += 1
                    Config.SKIPPED_IDS.append(current_id)
                
                # Progress update logic
                now = asyncio.get_event_loop().time()
                if (now - last_update >= Config.PROGRESS_UPDATE_INTERVAL or 
                    current_id == end_id or 
                    (processed + failed) % 10 == 0):
                    
                    elapsed = now - start_time
                    speed = (processed + failed) / elapsed if elapsed > 0 else 0
                    eta = (total - (current_id - start_id)) / speed if speed > 0 else 0
                    
                    try:
                        await progress_msg.edit(
                            f"⏳ Processing: {current_id}/{end_id}\n"
                            f"✅ Success: {processed}\n"
                            f"❌ Failed: {failed}\n"
                            f"📶 Progress: {((current_id-start_id)/total)*100:.1f}%\n"
                            f"⏱️ ETA: {eta:.1f} seconds\n"
                            f"🚀 Speed: {speed:.1f} msg/sec\n\n"
                            f"Offset: {Config.OFFSET} | Replacements: {len(Config.REPLACEMENTS)}",
                            parse_mode=ParseMode.MARKDOWN
                        )
                        last_update = now
                    except Exception as e:
                        print(f"Error updating progress: {e}")
                
            except FloodWait as e:
                await progress_msg.edit(f"⏳ Flood wait: Sleeping for {e.value} seconds...")
                await asyncio.sleep(e.value)
                failed += 1
                Config.SKIPPED_IDS.append(current_id)
            except (MessageIdInvalid, ChannelInvalid):
                failed += 1
                Config.SKIPPED_IDS.append(current_id)
                await asyncio.sleep(3)
            except ChatAdminRequired:
                await progress_msg.edit("❌ Bot lost admin privileges during processing!")
                Config.PROCESSING = False
                break
            except RPCError as e:
                print(f"RPCError processing {current_id}: {e}")
                failed += 1
                Config.SKIPPED_IDS.append(current_id)
                await asyncio.sleep(5)
            except Exception as e:
                print(f"Error processing {current_id}: {e}")
                failed += 1
                Config.SKIPPED_IDS.append(current_id)
                await asyncio.sleep(2)
        
        if Config.PROCESSING:
            completion_text = (
                f"✅ Batch Complete!\n"
                f"• Total messages: {total}\n"
                f"• Successfully processed: {processed}\n"
                f"• Failed: {failed}\n"
                f"• Offset Applied: {Config.OFFSET}\n"
                f"• Word Replacements: {len(Config.REPLACEMENTS)}\n"
                f"• Target Chat: `{target_chat}`\n\n"
            )
            
            if failed > 0:
                completion_text += (
                    f"⚠️ Some messages failed (IDs: {', '.join(map(str, Config.SKIPPED_IDS[:50]))}"
                    f"{'...' if len(Config.SKIPPED_IDS) > 50 else ''})\n"
                    f"Use /retry_skipped to retry these messages"
                )
            
            await progress_msg.edit(completion_text, parse_mode=ParseMode.MARKDOWN)
    
    except asyncio.CancelledError:
        await message.reply("🛑 Batch processing stopped by user")
    except Exception as e:
        await message.reply(f"❌ Batch Error: {str(e)}")
    finally:
        Config.PROCESSING = False
        Config.BATCH_MODE = False
        Config.CURRENT_TASK = None

@app.on_message(filters.command("retry_skipped"))
async def retry_skipped(client: Client, message: Message):
    if not Config.SKIPPED_IDS:
        return await message.reply("No skipped messages to retry")
    
    if Config.PROCESSING:
        return await message.reply("Another process is already running")
    
    if not Config.TARGET_CHAT_ID:
        return await message.reply("Target chat not set")
    
    Config.PROCESSING = True
    Config.CURRENT_TASK = asyncio.create_task(retry_skipped_messages(client, message))

async def retry_skipped_messages(client: Client, message: Message):
    try:
        total = len(Config.SKIPPED_IDS)
        progress_msg = await message.reply(
            f"🔁 Retrying {total} skipped messages...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        processed = failed = 0
        skipped_ids = Config.SKIPPED_IDS.copy()
        Config.SKIPPED_IDS = []
        
        for current_id in skipped_ids:
            if not Config.PROCESSING:
                break
            
            try:
                msg = await client.get_messages(Config.CHAT_ID, current_id)
                if msg and not msg.empty:
                    success = await process_message(client, msg, Config.TARGET_CHAT_ID)
                    if success:
                        processed += 1
                    else:
                        failed += 1
                        Config.SKIPPED_IDS.append(current_id)
                else:
                    failed += 1
                    Config.SKIPPED_IDS.append(current_id)
                
                # Update progress every 5 messages
                if (processed + failed) % 5 == 0 or (processed + failed) == total:
                    await progress_msg.edit(
                        f"🔁 Retrying skipped messages\n"
                        f"✅ Success: {processed}\n"
                        f"❌ Failed: {failed}\n"
                        f"📶 Progress: {((processed + failed)/total)*100:.1f}%",
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                await asyncio.sleep(0.5)
            
            except Exception as e:
                print(f"Error retrying message {current_id}: {e}")
                failed += 1
                Config.SKIPPED_IDS.append(current_id)
                await asyncio.sleep(2)
        
        completion_text = (
            f"🔁 Retry Complete!\n"
            f"• Total retried: {total}\n"
            f"• Success: {processed}\n"
            f"• Failed: {failed}\n\n"
        )
        
        if failed > 0:
            completion_text += (
                f"⚠️ Some messages still failed (IDs: {', '.join(map(str, Config.SKIPPED_IDS[:50]))}"
                f"{'...' if len(Config.SKIPPED_IDS) > 50 else ''}"
            )
        
        await progress_msg.edit(completion_text, parse_mode=ParseMode.MARKDOWN)
    
    except Exception as e:
        await message.reply(f"❌ Retry Error: {str(e)}")
    finally:
        Config.PROCESSING = False
        Config.CURRENT_TASK = None

# [All your other original command handlers remain exactly the same]

if __name__ == "__main__":
    print("⚡ Advanced Batch Link Modifier Bot Started!")
    try:
        app.start()
        idle()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()
