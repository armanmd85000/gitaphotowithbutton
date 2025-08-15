import re
import asyncio
import time
from typing import Optional, Tuple, Dict, Union, List
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode, MessageMediaType, ChatType, ChatMemberStatus
from pyrogram.errors import (
    FloodWait, RPCError, MessageIdInvalid, ChannelInvalid,
    ChatAdminRequired, PeerIdInvalid, UserNotParticipant, BadRequest
)

# ====================== CONFIGURATION ======================
from config import Config

class GitaConfig:
    OFFSET = 0
    PROCESSING = False
    BATCH_MODE = False
    PHOTO_FORWARD_MODE = False
    SOURCE_CHAT = None
    TARGET_CHAT = None
    START_ID = None
    END_ID = None
    CURRENT_TASK = None
    REPLACEMENTS = {}
    ADMIN_CACHE = {}
    # Button configuration
    CUSTOM_BUTTONS = {
        'enabled': True,
        'buttons': [
            [
                InlineKeyboardButton("🔗 Source Link", url="https://t.me/your_channel"),
                InlineKeyboardButton("📢 Channel", url="https://t.me/your_main_channel")
            ],
            [
                InlineKeyboardButton("💡 More Info", callback_data="info"),
                InlineKeyboardButton("⭐ Rate Us", callback_data="rate")
            ]
        ]
    }
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
    MAX_MESSAGES_PER_BATCH = 100000

# Initialize bot with your existing config
bot = Client(
    Config.BOT_SESSION,
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)

# ====================== UTILITY FUNCTIONS ======================
def is_not_command(_, __, message: Message) -> bool:
    return not message.text.startswith('/')

def create_custom_buttons() -> InlineKeyboardMarkup:
    """Create custom inline keyboard buttons"""
    if GitaConfig.CUSTOM_BUTTONS['enabled']:
        return InlineKeyboardMarkup(GitaConfig.CUSTOM_BUTTONS['buttons'])
    return None

def parse_message_link(text: str) -> Optional[Tuple[Union[int, str], int]]:
    """Parse Telegram message link and return (chat_id, message_id) tuple"""
    pattern = r'(?:https?://)?(?:t\.me|telegram\.(?:me|dog))/(?:c/)?([^/\s]+)/(\d+)'
    match = re.search(pattern, text)
    if match:
        chat_id = match.group(1)
        message_id = int(match.group(2))
        return (chat_id, message_id)
    return None

def generate_message_link(chat: object, message_id: int) -> str:
    """Generate message link for a chat and message ID"""
    if hasattr(chat, 'username') and chat.username:
        return f"https://t.me/{chat.username}/{message_id}"
    else:
        chat_id_str = str(chat.id).replace('-100', '')
        return f"https://t.me/c/{chat_id_str}/{message_id}"

def modify_content(text: str, offset: int) -> str:
    if not text:
        return text

    # Apply word replacements
    for original, replacement in sorted(GitaConfig.REPLACEMENTS.items(), key=lambda x: (-len(x[0]), x[0].lower())):
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
        if isinstance(chat_id, str):
            chat = await client.get_chat(chat_id)
            chat_id = chat.id

        if chat_id in GitaConfig.ADMIN_CACHE:
            return GitaConfig.ADMIN_CACHE[chat_id]

        chat = await client.get_chat(chat_id)
        
        if chat.type not in [ChatType.CHANNEL, ChatType.SUPERGROUP]:
            result = (False, "Only channels and supergroups are supported")
            GitaConfig.ADMIN_CACHE[chat_id] = result
            return result
            
        try:
            member = await client.get_chat_member(chat.id, "me")
        except UserNotParticipant:
            result = (False, "Bot is not a member of this chat")
            GitaConfig.ADMIN_CACHE[chat_id] = result
            return result
            
        if member.status != ChatMemberStatus.ADMINISTRATOR:
            result = (False, "Bot needs to be admin")
            GitaConfig.ADMIN_CACHE[chat_id] = result
            return result
        
        result = (True, "OK")
        GitaConfig.ADMIN_CACHE[chat_id] = result
        return result
        
    except (ChannelInvalid, PeerIdInvalid):
        return (False, "Invalid chat ID")
    except Exception as e:
        return (False, f"Error: {str(e)}")

async def process_message(client: Client, source_msg: Message, target_chat_id: int) -> bool:
    for attempt in range(GitaConfig.MAX_RETRIES):
        try:
            if source_msg.service or source_msg.empty:
                return False
                
            # Create custom buttons
            reply_markup = create_custom_buttons()
                
            media_type = source_msg.media
            if media_type and GitaConfig.MESSAGE_FILTERS.get(media_type.value, False):
                caption = source_msg.caption or ""
                modified_caption = modify_content(caption, GitaConfig.OFFSET)
                
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
                    kwargs = {
                        'chat_id': target_chat_id,
                        'caption': modified_caption if media_type != MessageMediaType.STICKER else None,
                        'parse_mode': ParseMode.MARKDOWN,
                        'reply_markup': reply_markup
                    }
                    kwargs[media_type.value] = getattr(source_msg, media_type.value).file_id
                    
                    await media_mapping[media_type](**kwargs)
                    return True
                else:
                    await client.copy_message(
                        chat_id=target_chat_id,
                        from_chat_id=source_msg.chat.id,
                        message_id=source_msg.id,
                        caption=modified_caption,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=reply_markup
                    )
                    return True
            elif source_msg.text and GitaConfig.MESSAGE_FILTERS['text']:
                await client.send_message(
                    chat_id=target_chat_id,
                    text=modify_content(source_msg.text, GitaConfig.OFFSET),
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
                return True
                
            return False
            
        except FloodWait as e:
            if attempt == GitaConfig.MAX_RETRIES - 1:
                raise
            await asyncio.sleep(e.value)
        except Exception as e:
            print(f"Attempt {attempt + 1} failed for message {source_msg.id}: {e}")
            if attempt == GitaConfig.MAX_RETRIES - 1:
                return False
            await asyncio.sleep(1)
    
    return False

async def process_photo_with_link(client: Client, source_msg: Message, target_chat_id: int) -> bool:
    """Process photo message and send with link included in caption"""
    for attempt in range(GitaConfig.MAX_RETRIES):
        try:
            if source_msg.service or source_msg.empty or not source_msg.photo:
                return False
            
            # Get the original caption and modify it
            caption = source_msg.caption or ""
            modified_caption = modify_content(caption, GitaConfig.OFFSET)
            
            # Generate the message link
            message_link = generate_message_link(source_msg.chat, source_msg.id)
            
            # Combine caption with link
            if modified_caption:
                final_caption = f"{modified_caption}\n\n🔗 **Link:** {message_link}"
            else:
                final_caption = f"🔗 **Link:** {message_link}"
            
            # Create custom buttons
            reply_markup = create_custom_buttons()
            
            # Send the photo with combined caption and buttons
            await client.send_photo(
                chat_id=target_chat_id,
                photo=source_msg.photo.file_id,
                caption=final_caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            
            return True
            
        except FloodWait as e:
            if attempt == GitaConfig.MAX_RETRIES - 1:
                raise
            await asyncio.sleep(e.value)
        except Exception as e:
            print(f"Attempt {attempt + 1} failed for photo message {source_msg.id}: {e}")
            if attempt == GitaConfig.MAX_RETRIES - 1:
                return False
            await asyncio.sleep(1)
    
    return False

# ====================== COMMAND HANDLERS ======================
@bot.on_message(filters.command(["gita_start", "gita_help"]))
async def start_cmd(client: Client, message: Message):
    help_text = """
🚀 **Ultimate Batch Link Modifier Bot** 📝

🔹 **Core Features:**
- Batch process messages with ID offset
- Smart word replacement system
- Comprehensive media support
- **NEW: Photo forwarding with links**
- **Custom buttons with every message**
- Automatic retry mechanism

🔹 **Basic Commands:**
/gita_setchat source [chat] - Set source chat
/gita_setchat target [chat] - Set target chat
/gita_batch - Start batch processing
/gita_photoforward - Start photo forwarding mode
/gita_addnumber N - Add offset N
/gita_lessnumber N - Subtract offset N
/gita_setoffset N - Set absolute offset
/gita_stop - Cancel current operation

🔹 **Button Commands:**
/gita_setbuttons - Configure custom buttons
/gita_showbuttons - Show current buttons
/gita_togglebuttons - Enable/disable buttons

🔹 **Advanced Commands:**
/gita_replacewords - View replacements
/gita_addreplace ORIG REPL - Add replacement
/gita_removereplace WORD - Remove replacement
/gita_filtertypes - Show filters
/gita_enablefilter TYPE - Enable filter
/gita_disablefilter TYPE - Disable filter

🔹 **System Commands:**
/gita_status - Show current config
/gita_reset - Reset all settings

🔹 **Batch Limit:** Up to 100,000 messages per batch
"""
    await message.reply(help_text, parse_mode=ParseMode.MARKDOWN)

# Button management commands
@bot.on_message(filters.command("gita_setbuttons"))
async def set_buttons(client: Client, message: Message):
    await message.reply(
        "🔧 **Button Configuration**\n\n"
        "Send button configuration in this format:\n"
        "`Button Text 1|URL1||Button Text 2|URL2`\n"
        "`Button Text 3|callback_data3||Button Text 4|callback_data4`\n\n"
        "**Examples:**\n"
        "`Channel|https://t.me/yourchannel||Bot|https://t.me/yourbot`\n"
        "`Info|info_callback||Help|help_callback`\n\n"
        "Use `||` to separate buttons in same row\n"
        "Send each row on a new line for multiple rows\n"
        "/gita_cancel to cancel",
        parse_mode=ParseMode.MARKDOWN
    )
    GitaConfig.PROCESSING = True

@bot.on_message(filters.command("gita_showbuttons"))
async def show_buttons(client: Client, message: Message):
    if GitaConfig.CUSTOM_BUTTONS['enabled']:
        button_text = "🔘 **Current Buttons:**\n\n"
        for row_idx, row in enumerate(GitaConfig.CUSTOM_BUTTONS['buttons'], 1):
            button_text += f"**Row {row_idx}:**\n"
            for button in row:
                if button.url:
                    button_text += f"▫️ {button.text} → {button.url}\n"
                else:
                    button_text += f"▫️ {button.text} → callback: {button.callback_data}\n"
            button_text += "\n"
        button_text += f"**Status:** {'✅ Enabled' if GitaConfig.CUSTOM_BUTTONS['enabled'] else '❌ Disabled'}"
    else:
        button_text = "❌ **No buttons configured**"
    
    await message.reply(button_text, parse_mode=ParseMode.MARKDOWN)

@bot.on_message(filters.command("gita_togglebuttons"))
async def toggle_buttons(client: Client, message: Message):
    GitaConfig.CUSTOM_BUTTONS['enabled'] = not GitaConfig.CUSTOM_BUTTONS['enabled']
    status = "✅ Enabled" if GitaConfig.CUSTOM_BUTTONS['enabled'] else "❌ Disabled"
    await message.reply(f"🔘 **Buttons {status}**")

# Handle button configuration input
@bot.on_message(filters.text & ~filters.command(["gita_cancel"]) & filters.create(is_not_command))
async def handle_button_config(client: Client, message: Message):
    if GitaConfig.PROCESSING and not GitaConfig.BATCH_MODE and not GitaConfig.PHOTO_FORWARD_MODE:
        try:
            # Parse button configuration
            lines = message.text.strip().split('\n')
            new_buttons = []
            
            for line in lines:
                if not line.strip():
                    continue
                    
                row_buttons = []
                button_pairs = line.split('||')
                
                for pair in button_pairs:
                    parts = pair.strip().split('|', 1)
                    if len(parts) == 2:
                        text, data = parts
                        text = text.strip()
                        data = data.strip()
                        
                        if data.startswith('http'):
                            # URL button
                            row_buttons.append(InlineKeyboardButton(text, url=data))
                        else:
                            # Callback button
                            row_buttons.append(InlineKeyboardButton(text, callback_data=data))
                
                if row_buttons:
                    new_buttons.append(row_buttons)
            
            if new_buttons:
                GitaConfig.CUSTOM_BUTTONS['buttons'] = new_buttons
                GitaConfig.CUSTOM_BUTTONS['enabled'] = True
                GitaConfig.PROCESSING = False
                
                # Show preview
                preview_markup = InlineKeyboardMarkup(new_buttons)
                await message.reply(
                    "✅ **Buttons Updated Successfully!**\n\n"
                    "Preview of your buttons:",
                    reply_markup=preview_markup
                )
            else:
                await message.reply("❌ **Invalid button format!** Please try again.")
        except Exception as e:
            await message.reply(f"❌ **Error parsing buttons:** {str(e)}")
        return

# NEW COMMAND: Photo Forward Mode
@bot.on_message(filters.command("gita_photoforward"))
async def start_photo_forward(client: Client, message: Message):
    if GitaConfig.PROCESSING:
        return await message.reply("⚠️ Already processing! Use /gita_stop to cancel")
    
    if not GitaConfig.SOURCE_CHAT:
        return await message.reply("❌ Source chat not set. Use /gita_setchat source [chat_id]")
    
    GitaConfig.PROCESSING = True
    GitaConfig.PHOTO_FORWARD_MODE = True
    GitaConfig.START_ID = None
    GitaConfig.END_ID = None
    
    await message.reply(
        f"📸 **Photo Forward Mode Activated**\n"
        f"▫️ Source: {GitaConfig.SOURCE_CHAT.title}\n"
        f"▫️ Target: {GitaConfig.TARGET_CHAT.title if GitaConfig.TARGET_CHAT else 'Current Chat'}\n"
        f"▫️ Buttons: {'✅ Enabled' if GitaConfig.CUSTOM_BUTTONS['enabled'] else '❌ Disabled'}\n"
        f"▫️ Max Batch Size: {GitaConfig.MAX_MESSAGES_PER_BATCH:,} messages\n\n"
        f"📝 **Instructions:**\n"
        f"1. Reply to the FIRST message or send its link\n"
        f"2. Bot will filter and forward only photos\n"
        f"3. Link will be included in photo caption\n"
        f"4. Custom buttons will be added to each photo\n\n"
        f"🔗 **Example output:**\n"
        f"[Photo with original caption]\n\n"
        f"🔗 Link: https://t.me/c/123456/789\n"
        f"[Custom Buttons Below]",
        parse_mode=ParseMode.MARKDOWN
    )

@bot.on_message(filters.command(["gita_addnumber", "gita_addnum"]))
async def add_offset(client: Client, message: Message):
    try:
        offset = int(message.command[1])
        GitaConfig.OFFSET += offset
        await message.reply(f"✅ Offset increased by {offset}. New offset: {GitaConfig.OFFSET}")
    except (IndexError, ValueError):
        await message.reply("❌ Please provide a valid number to add")

@bot.on_message(filters.command(["gita_lessnumber", "gita_lessnum"]))
async def subtract_offset(client: Client, message: Message):
    try:
        offset = int(message.command[1])
        GitaConfig.OFFSET -= offset
        await message.reply(f"✅ Offset decreased by {offset}. New offset: {GitaConfig.OFFSET}")
    except (IndexError, ValueError):
        await message.reply("❌ Please provide a valid number to subtract")

@bot.on_message(filters.command("gita_setoffset"))
async def set_offset(client: Client, message: Message):
    try:
        offset = int(message.command[1])
        GitaConfig.OFFSET = offset
        await message.reply(f"✅ Offset set to {GitaConfig.OFFSET}")
    except (IndexError, ValueError):
        await message.reply("❌ Please provide a valid offset number")

@bot.on_message(filters.command("gita_replacewords"))
async def show_replacements(client: Client, message: Message):
    if not GitaConfig.REPLACEMENTS:
        await message.reply("ℹ️ No word replacements set")
        return
    
    replacements_text = "🔹 Current Word Replacements:\n"
    for original, replacement in GitaConfig.REPLACEMENTS.items():
        replacements_text += f"▫️ `{original}` → `{replacement}`\n"
    
    await message.reply(replacements_text, parse_mode=ParseMode.MARKDOWN)

@bot.on_message(filters.command("gita_addreplace"))
async def add_replacement(client: Client, message: Message):
    try:
        original = message.command[1]
        replacement = message.command[2]
        GitaConfig.REPLACEMENTS[original] = replacement
        await message.reply(f"✅ Added replacement: `{original}` → `{replacement}`", parse_mode=ParseMode.MARKDOWN)
    except IndexError:
        await message.reply("❌ Usage: /gita_addreplace ORIGINAL REPLACEMENT")

@bot.on_message(filters.command("gita_removereplace"))
async def remove_replacement(client: Client, message: Message):
    try:
        word = message.command[1]
        if word in GitaConfig.REPLACEMENTS:
            del GitaConfig.REPLACEMENTS[word]
            await message.reply(f"✅ Removed replacement for `{word}`", parse_mode=ParseMode.MARKDOWN)
        else:
            await message.reply(f"❌ No replacement found for `{word}`", parse_mode=ParseMode.MARKDOWN)
    except IndexError:
        await message.reply("❌ Please specify a word to remove")

@bot.on_message(filters.command("gita_filtertypes"))
async def show_filters(client: Client, message: Message):
    filters_text = "🔹 Current Message Filters:\n"
    for filter_type, enabled in GitaConfig.MESSAGE_FILTERS.items():
        status = "✅ Enabled" if enabled else "❌ Disabled"
        filters_text += f"▫️ {filter_type}: {status}\n"
    
    await message.reply(filters_text)

@bot.on_message(filters.command("gita_enablefilter"))
async def enable_filter(client: Client, message: Message):
    try:
        filter_type = message.command[1].lower()
        if filter_type in GitaConfig.MESSAGE_FILTERS:
            GitaConfig.MESSAGE_FILTERS[filter_type] = True
            await message.reply(f"✅ Enabled {filter_type} messages")
        else:
            await message.reply(f"❌ Invalid filter type. Available types: {', '.join(GitaConfig.MESSAGE_FILTERS.keys())}")
    except IndexError:
        await message.reply("❌ Please specify a filter type to enable")

@bot.on_message(filters.command("gita_disablefilter"))
async def disable_filter(client: Client, message: Message):
    try:
        filter_type = message.command[1].lower()
        if filter_type in GitaConfig.MESSAGE_FILTERS:
            GitaConfig.MESSAGE_FILTERS[filter_type] = False
            await message.reply(f"✅ Disabled {filter_type} messages")
        else:
            await message.reply(f"❌ Invalid filter type. Available types: {', '.join(GitaConfig.MESSAGE_FILTERS.keys())}")
    except IndexError:
        await message.reply("❌ Please specify a filter type to disable")

@bot.on_message(filters.command("gita_status"))
async def show_status(client: Client, message: Message):
    status_text = f"""
🔹 **Current Configuration**
▫️ Offset: {GitaConfig.OFFSET}
▫️ Replacements: {len(GitaConfig.REPLACEMENTS)}
▫️ Processing: {'✅ Yes' if GitaConfig.PROCESSING else '❌ No'}
▫️ Batch Mode: {'✅ Yes' if GitaConfig.BATCH_MODE else '❌ No'}
▫️ Photo Forward Mode: {'✅ Yes' if GitaConfig.PHOTO_FORWARD_MODE else '❌ No'}
▫️ Custom Buttons: {'✅ Enabled' if GitaConfig.CUSTOM_BUTTONS['enabled'] else '❌ Disabled'}
▫️ Button Rows: {len(GitaConfig.CUSTOM_BUTTONS['buttons'])}
▫️ Max Batch Size: {GitaConfig.MAX_MESSAGES_PER_BATCH:,} messages
▫️ Message Filters: {sum(GitaConfig.MESSAGE_FILTERS.values())}/{len(GitaConfig.MESSAGE_FILTERS)} enabled
"""
    if GitaConfig.SOURCE_CHAT:
        status_text += f"▫️ Source Chat: {GitaConfig.SOURCE_CHAT.title} (ID: {GitaConfig.SOURCE_CHAT.id})\n"
    else:
        status_text += "▫️ Source Chat: Not set\n"
    
    if GitaConfig.TARGET_CHAT:
        status_text += f"▫️ Target Chat: {GitaConfig.TARGET_CHAT.title} (ID: {GitaConfig.TARGET_CHAT.id})"
    else:
        status_text += "▫️ Target Chat: Not set (will use current chat)"
    
    await message.reply(status_text, parse_mode=ParseMode.MARKDOWN)

@bot.on_message(filters.command("gita_reset"))
async def reset_config(client: Client, message: Message):
    GitaConfig.OFFSET = 0
    GitaConfig.REPLACEMENTS = {}
    GitaConfig.PROCESSING = False
    GitaConfig.BATCH_MODE = False
    GitaConfig.PHOTO_FORWARD_MODE = False
    GitaConfig.SOURCE_CHAT = None
    GitaConfig.TARGET_CHAT = None
    GitaConfig.START_ID = None
    GitaConfig.END_ID = None
    GitaConfig.MESSAGE_FILTERS = {k: True for k in GitaConfig.MESSAGE_FILTERS}
    
    if GitaConfig.CURRENT_TASK:
        GitaConfig.CURRENT_TASK.cancel()
        GitaConfig.CURRENT_TASK = None
    
    await message.reply("✅ All settings have been reset to defaults")

@bot.on_message(filters.command(["gita_setchat", "gita_setgroup"]))
async def set_chat(client: Client, message: Message):
    try:
        if len(message.command) < 2:
            return await message.reply("Usage: /gita_setchat [source|target] [chat_id or username]")
        
        chat_type = message.command[1].lower()
        if chat_type not in ["source", "target"]:
            return await message.reply("Invalid type. Use 'source' or 'target'")
        
        if message.reply_to_message:
            chat = message.reply_to_message.chat
        elif len(message.command) > 2:
            chat_id = message.command[2]
            try:
                chat = await client.get_chat(chat_id)
            except Exception as e:
                return await message.reply(f"Invalid chat: {str(e)}")
        else:
            chat = message.chat
        
        has_perms, perm_msg = await verify_permissions(client, chat.id)
        if not has_perms:
            return await message.reply(f"Permission error: {perm_msg}")
        
        if chat_type == "source":
            GitaConfig.SOURCE_CHAT = chat
        else:
            GitaConfig.TARGET_CHAT = chat
        
        await message.reply(
            f"✅ {'Source' if chat_type == 'source' else 'Target'} chat set to:\n"
            f"Title: {chat.title}\n"
            f"ID: {chat.id}\n"
            f"Username: @{chat.username if chat.username else 'N/A'}"
        )
    except Exception as e:
        await message.reply(f"Error: {str(e)}")

@bot.on_message(filters.command("gita_batch"))
async def start_batch(client: Client, message: Message):
    if GitaConfig.PROCESSING:
        return await message.reply("⚠️ Already processing! Use /gita_stop to cancel")
    
    if not GitaConfig.SOURCE_CHAT:
        return await message.reply("❌ Source chat not set. Use /gita_setchat source [chat_id]")
    
    GitaConfig.PROCESSING = True
    GitaConfig.BATCH_MODE = True
    GitaConfig.PHOTO_FORWARD_MODE = False
    GitaConfig.START_ID = None
    GitaConfig.END_ID = None
    
    await message.reply(
        f"🔹 **Batch Mode Activated**\n"
        f"▫️ Source: {GitaConfig.SOURCE_CHAT.title}\n"
        f"▫️ Target: {GitaConfig.TARGET_CHAT.title if GitaConfig.TARGET_CHAT else 'Current Chat'}\n"
        f"▫️ Offset: {GitaConfig.OFFSET}\n"
        f"▫️ Replacements: {len(GitaConfig.REPLACEMENTS)}\n"
        f"▫️ Buttons: {'✅ Enabled' if GitaConfig.CUSTOM_BUTTONS['enabled'] else '❌ Disabled'}\n"
        f"▫️ Max Batch Size: {GitaConfig.MAX_MESSAGES_PER_BATCH:,} messages\n\n"
        f"Reply to the FIRST message or send its link"
    )

@bot.on_message(filters.command(["gita_stop", "gita_cancel"]))
async def stop_cmd(client: Client, message: Message):
    if GitaConfig.PROCESSING:
        GitaConfig.PROCESSING = False
        GitaConfig.BATCH_MODE = False
        GitaConfig.PHOTO_FORWARD_MODE = False
        if GitaConfig.CURRENT_TASK:
            GitaConfig.CURRENT_TASK.cancel()
            GitaConfig.CURRENT_TASK = None
        await message.reply("✅ Processing stopped")
    else:
        await message.reply("⚠️ No active process")

# Handle callback queries for custom buttons
@bot.on_callback_query()
async def handle_callbacks(client: Client, callback_query):
    data = callback_query.data
    
    if data == "info":
        await callback_query.answer("ℹ️ This is an info button!")
    elif data == "rate":
        await callback_query.answer("⭐ Thanks for rating us!")
    else:
        await callback_query.answer(f"Button pressed: {data}")

# Main message handler for batch processing
@bot.on_message(filters.text & filters.create(is_not_command))
async def handle_message(client: Client, message: Message):
    if not GitaConfig.PROCESSING:
        return
    
    # Skip if this is button configuration mode
    if GitaConfig.PROCESSING and not GitaConfig.BATCH_MODE and not GitaConfig.PHOTO_FORWARD_MODE:
        return  # This will be handled by button config handler
    
    try:
        # Get source message details
        if message.reply_to_message:
            source_msg = message.reply_to_message
            chat_id = source_msg.chat.id
            msg_id = source_msg.id
        else:
            link_info = parse_message_link(message.text)
            if not link_info:
                return await message.reply("❌ Invalid message link")
            
            chat_identifier, msg_id = link_info
            
            try:
                chat = await client.get_chat(chat_identifier)
                chat_id = chat.id
            except Exception as e:
                return await message.reply(f"❌ Could not resolve chat: {str(e)}")

        if GitaConfig.BATCH_MODE or GitaConfig.PHOTO_FORWARD_MODE:
            if GitaConfig.START_ID is None:
                has_perms, perm_msg = await verify_permissions(client, chat_id)
                if not has_perms:
                    GitaConfig.PROCESSING = False
                    return await message.reply(f"❌ Permission error: {perm_msg}")
                
                if GitaConfig.SOURCE_CHAT and chat_id != GitaConfig.SOURCE_CHAT.id:
                    return await message.reply("❌ First message must be from the source chat")
                
                GitaConfig.START_ID = msg_id
                mode_text = "Photo Forward" if GitaConfig.PHOTO_FORWARD_MODE else "Batch"
                await message.reply(
                    f"✅ First message set: {msg_id}\n"
                    f"Now reply to the LAST message or send its link\n"
                    f"Mode: {mode_text}"
                )
            elif GitaConfig.END_ID is None:
                if not GitaConfig.SOURCE_CHAT:
                    GitaConfig.PROCESSING = False
                    return await message.reply("❌ Source chat not set")
                
                if chat_id != GitaConfig.SOURCE_CHAT.id:
                    return await message.reply("❌ Last message must be from the same chat as source chat")
                
                GitaConfig.END_ID = msg_id
                if GitaConfig.PHOTO_FORWARD_MODE:
                    GitaConfig.CURRENT_TASK = asyncio.create_task(process_photo_batch(client, message))
                else:
                    GitaConfig.CURRENT_TASK = asyncio.create_task(process_batch(client, message))
        else:
            try:
                msg = await client.get_messages(chat_id, msg_id)
                if msg and not msg.empty:
                    target_chat = GitaConfig.TARGET_CHAT.id if GitaConfig.TARGET_CHAT else message.chat.id
                    success = await process_message(client, msg, target_chat)
                    if not success:
                        await message.reply("⚠️ Failed to process this message")
            except Exception as e:
                await message.reply(f"❌ Error: {str(e)}")
            
    except Exception as e:
        await message.reply(f"❌ Critical error: {str(e)}")
        GitaConfig.PROCESSING = False
        GitaConfig.BATCH_MODE = False
        GitaConfig.PHOTO_FORWARD_MODE = False

async def process_photo_batch(client: Client, message: Message):
    """Process batch of messages, filtering and forwarding only photos with links"""
    try:
        if not GitaConfig.SOURCE_CHAT:
            await message.reply("❌ Source chat not set")
            GitaConfig.PROCESSING = False
            return
            
        start_id = min(GitaConfig.START_ID, GitaConfig.END_ID)
        end_id = max(GitaConfig.START_ID, GitaConfig.END_ID)
        total = end_id - start_id + 1
        
        if total > GitaConfig.MAX_MESSAGES_PER_BATCH:
            await message.reply(f"❌ Batch too large ({total:,} messages). Max allowed: {GitaConfig.MAX_MESSAGES_PER_BATCH:,}")
            GitaConfig.PROCESSING = False
            return
            
        target_chat = GitaConfig.TARGET_CHAT.id if GitaConfig.TARGET_CHAT else message.chat.id
        
        # Verify permissions
        has_perms, perm_msg = await verify_permissions(client, GitaConfig.SOURCE_CHAT.id)
        if not has_perms:
            await message.reply(f"❌ Source chat permission error: {perm_msg}")
            GitaConfig.PROCESSING = False
            return
            
        has_perms, perm_msg = await verify_permissions(client, target_chat)
        if not has_perms:
            await message.reply(f"❌ Target chat permission error: {perm_msg}")
            GitaConfig.PROCESSING = False
            return

        progress_msg = await message.reply(
            f"📸 **Photo Forward Processing Started**\n"
            f"▫️ Source: {GitaConfig.SOURCE_CHAT.title}\n"
            f"▫️ Target: {GitaConfig.TARGET_CHAT.title if GitaConfig.TARGET_CHAT else message.chat.title}\n"
            f"▫️ Range: {start_id:,}-{end_id:,}\n"
            f"▫️ Total Messages: {total:,}\n"
            f"▫️ Buttons: {'✅ Enabled' if GitaConfig.CUSTOM_BUTTONS['enabled'] else '❌ Disabled'}\n"
            f"▫️ Filter: Photos only with links in caption\n",
            parse_mode=ParseMode.MARKDOWN
        )
        
        processed = photos_found = failed = 0
        last_update = time.time()
        
        for current_id in range(start_id, end_id + 1):
            if not GitaConfig.PROCESSING:
                break
            
            try:
                msg = await client.get_messages(GitaConfig.SOURCE_CHAT.id, current_id)
                if msg and not msg.empty:
                    processed += 1
                    if msg.photo:
                        photos_found += 1
                        success = await process_photo_with_link(client, msg, target_chat)
                        if not success:
                            failed += 1
                
                if time.time() - last_update >= 5 or current_id == end_id:
                    progress = ((current_id - start_id) / total) * 100
                    try:
                        await progress_msg.edit(
                            f"📸 **Processing Photo Batch**\n"
                            f"▫️ Progress: {progress:.1f}%\n"
                            f"▫️ Current: {current_id:,}\n"
                            f"📝 Checked: {processed:,}\n"
                            f"📸 Photos Found: {photos_found:,}\n"
                            f"❌ Failed: {failed:,}"
                        )
                        last_update = time.time()
                    except:
                        pass
                
                await asyncio.sleep(GitaConfig.DELAY_BETWEEN_MESSAGES)
            except FloodWait as e:
                await progress_msg.edit(f"⏳ Flood wait: {e.value}s...")
                await asyncio.sleep(e.value)
            except Exception as e:
                print(f"Error processing {current_id}: {e}")
                failed += 1
                await asyncio.sleep(1)
        
        if GitaConfig.PROCESSING:
            success_photos = photos_found - failed
            await progress_msg.edit(
                f"✅ **Photo Forward Complete!**\n"
                f"📝 Total Messages Checked: {processed:,}\n"
                f"📸 Photos Found: {photos_found:,}\n"
                f"✅ Successfully Forwarded: {success_photos:,}\n"
                f"❌ Failed: {failed:,}\n"
                f"📊 Success Rate: {(success_photos/photos_found)*100:.1f}%" if photos_found > 0 else "📊 No photos found"
            )
    
    except Exception as e:
        await message.reply(f"❌ Photo batch failed: {str(e)}")
    finally:
        GitaConfig.PROCESSING = False
        GitaConfig.PHOTO_FORWARD_MODE = False
        GitaConfig.CURRENT_TASK = None

async def process_batch(client: Client, message: Message):
    try:
        if not GitaConfig.SOURCE_CHAT:
            await message.reply("❌ Source chat not set")
            GitaConfig.PROCESSING = False
            return
            
        start_id = min(GitaConfig.START_ID, GitaConfig.END_ID)
        end_id = max(GitaConfig.START_ID, GitaConfig.END_ID)
        total = end_id - start_id + 1
        
        if total > GitaConfig.MAX_MESSAGES_PER_BATCH:
            await message.reply(f"❌ Batch too large ({total:,} messages). Max allowed: {GitaConfig.MAX_MESSAGES_PER_BATCH:,}")
            GitaConfig.PROCESSING = False
            return
            
        target_chat = GitaConfig.TARGET_CHAT.id if GitaConfig.TARGET_CHAT else message.chat.id
        
        # Verify permissions
        has_perms, perm_msg = await verify_permissions(client, GitaConfig.SOURCE_CHAT.id)
        if not has_perms:
            await message.reply(f"❌ Source chat permission error: {perm_msg}")
            GitaConfig.PROCESSING = False
            return
            
        has_perms, perm_msg = await verify_permissions(client, target_chat)
        if not has_perms:
            await message.reply(f"❌ Target chat permission error: {perm_msg}")
            GitaConfig.PROCESSING = False
            return

        progress_msg = await message.reply(
            f"⚡ **Batch Processing Started**\n"
            f"▫️ Source: {GitaConfig.SOURCE_CHAT.title}\n"
            f"▫️ Target: {GitaConfig.TARGET_CHAT.title if GitaConfig.TARGET_CHAT else message.chat.title}\n"
            f"▫️ Range: {start_id:,}-{end_id:,}\n"
            f"▫️ Total: {total:,} messages\n"
            f"▫️ Buttons: {'✅ Enabled' if GitaConfig.CUSTOM_BUTTONS['enabled'] else '❌ Disabled'}\n"
            f"▫️ Offset: {GitaConfig.OFFSET}\n",
            parse_mode=ParseMode.MARKDOWN
        )
        
        processed = failed = 0
        last_update = time.time()
        
        for current_id in range(start_id, end_id + 1):
            if not GitaConfig.PROCESSING:
                break
            
            try:
                msg = await client.get_messages(GitaConfig.SOURCE_CHAT.id, current_id)
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
                            f"▫️ Current: {current_id:,}\n"
                            f"✅ Success: {processed:,}\n"
                            f"❌ Failed: {failed:,}"
                        )
                        last_update = time.time()
                    except:
                        pass
                
                await asyncio.sleep(GitaConfig.DELAY_BETWEEN_MESSAGES)
            except FloodWait as e:
                await progress_msg.edit(f"⏳ Flood wait: {e.value}s...")
                await asyncio.sleep(e.value)
            except Exception as e:
                print(f"Error processing {current_id}: {e}")
                failed += 1
                await asyncio.sleep(1)
        
        if GitaConfig.PROCESSING:
            await progress_msg.edit(
                f"✅ **Batch Complete!**\n"
                f"▫️ Total: {total:,}\n"
                f"✅ Success: {processed:,}\n"
                f"❌ Failed: {failed:,}\n"
                f"▫️ Success Rate: {(processed/total)*100:.1f}%"
            )
    
    except Exception as e:
        await message.reply(f"❌ Batch failed: {str(e)}")
    finally:
        GitaConfig.PROCESSING = False
        GitaConfig.BATCH_MODE = False
        GitaConfig.CURRENT_TASK = None

if __name__ == "__main__":
    print("⚡ Ultimate Batch Link Modifier Bot with Custom Buttons Started!")
    print(f"📊 Max Batch Size: {GitaConfig.MAX_MESSAGES_PER_BATCH:,} messages")
    print(f"🔘 Custom Buttons: {'✅ Enabled' if GitaConfig.CUSTOM_BUTTONS['enabled'] else '❌ Disabled'}")
    try:
        bot.start()
        print("✅ Bot started successfully!")
        idle()
    except KeyboardInterrupt:
        print("\n⚠️ Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
    finally:
        try:
            bot.stop()
            print("✅ Bot stopped gracefully")
        except:
            print("⚠️ Bot was already stopped")
