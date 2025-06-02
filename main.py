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
    ADMIN_CACHE = {}  # Cache for admin checks

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
    try:
        if source_msg.media:
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
            else:
                await client.copy_message(
                    chat_id=target_chat_id,
                    from_chat_id=source_msg.chat.id,
                    message_id=source_msg.id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            modified_text = modify_content(source_msg.text, Config.OFFSET)
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

def parse_message_link(text: str) -> Optional[Tuple[str, int]]:
    match = re.search(
        r't\.me/(?:c/)?([^/]+)/(\d+)',
        text.split('?')[0]  # Remove URL parameters
    )
    if not match:
        return None
    return match.group(1), int(match.group(2))

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

🔹 **System:**
/reset - Reset all settings
/status - Show current configuration

📌 **Private Channel Requirements:**
1. Add bot as admin in BOTH source and target
2. In target: Enable 'Post Messages' permission
3. In source: Enable 'Read Messages' permission

🛠 **Troubleshooting:**
• If you get permission errors, use /checkperms
• For private channels, use the channel ID (-100...)
• The bot must be admin in both channels
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
        
        # Verify permissions
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
        # Check if message is a reply or contains a link
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
                # Verify access to source channel
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
                await process_message(client, msg, target_chat)
            except (MessageIdInvalid, ChannelInvalid):
                return await message.reply("❌ Invalid message or channel. Make sure the bot has access.")
            
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
        last_update = 0
        
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
                
                # Update progress every 5 messages or at the end
                now = asyncio.get_event_loop().time()
                if (processed + failed) % 5 == 0 or current_id == end_id or now - last_update > 10:
                    try:
                        await progress_msg.edit(
                            f"⏳ Processing: {current_id}/{end_id}\n"
                            f"✅ Success: {processed}\n"
                            f"❌ Failed: {failed}\n"
                            f"📶 Progress: {((current_id-start_id)/total)*100:.1f}%\n"
                            f"⏱️ Speed: {(processed + failed)/(now - last_update + 0.1):.1f} msg/s"
                        )
                        last_update = now
                    except:
                        pass
                
                await asyncio.sleep(0.5)
            
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
        
        if Config.PROCESSING:
            completion_text = (
                f"✅ Batch Complete!\n"
                f"• Total messages: {total}\n"
                f"• Successfully processed: {processed}\n"
                f"• Failed: {failed}\n"
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
    finally:
        app.stop()
