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

# Bot Configuration
API_ID = 20219694
API_HASH = "29d9b3a01721ab452fcae79346769e29"
BOT_TOKEN = "8139601508:AAE9mf6S5BrwW9ADfEh3RMnWwBKWAtLOjBc"

class Config:
    OFFSET = 0
    PROCESSING = False
    BATCH_MODE = False
    SOURCE_CHAT = None  # Now storing chat object instead of just ID
    TARGET_CHAT = None  # Added target chat storage
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

def parse_message_link(text: str) -> Optional[Tuple[Union[int, str], int]]:
    """Parse Telegram message link and return (chat_id, message_id) tuple"""
    pattern = r'(?:https?://)?(?:t\.me|telegram\.(?:me|dog))/(?:c/)?([^/\s]+)/(\d+)'
    match = re.search(pattern, text)
    if match:
        chat_id = match.group(1)
        message_id = int(match.group(2))
        return (chat_id, message_id)
    return None

def modify_content(text: str, offset: int) -> str:
    if not text:
        return text

    # Apply word replacements (case-insensitive with word boundaries)
    for original, replacement in sorted(Config.REPLACEMENTS.items(), key=lambda x: (-len(x[0]), x[0].lower())):
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
        if isinstance(chat_id, str) and chat_id.startswith('@'):
            chat = await client.get_chat(chat_id)
            chat_id = chat.id

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
        
        required_perms = ["can_post_messages", "can_delete_messages"] if chat.type == ChatType.CHANNEL else ["can_send_messages"]
        
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
        return (False, "Invalid chat ID")
    except Exception as e:
        return (False, f"Error: {str(e)}")

# [Previous functions remain the same until commands]

@app.on_message(filters.command(["setchat", "setgroup"]))
async def set_chat(client: Client, message: Message):
    try:
        if len(message.command) < 2:
            return await message.reply("Usage: /setchat [source|target] [chat_id or username]")
        
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
            Config.SOURCE_CHAT = chat
        else:
            Config.TARGET_CHAT = chat
        
        await message.reply(
            f"✅ {'Source' if chat_type == 'source' else 'Target'} chat set to:\n"
            f"Title: {chat.title}\n"
            f"ID: {chat.id}\n"
            f"Username: @{chat.username if chat.username else 'N/A'}"
        )
    except Exception as e:
        await message.reply(f"Error: {str(e)}")

@app.on_message(filters.command(["showchat", "showgroup"]))
async def show_chat(client: Client, message: Message):
    text = "🔹 Current Chat Settings:\n"
    if Config.SOURCE_CHAT:
        text += (
            f"▫️ Source: {Config.SOURCE_CHAT.title}\n"
            f"ID: {Config.SOURCE_CHAT.id}\n"
            f"Username: @{Config.SOURCE_CHAT.username if Config.SOURCE_CHAT.username else 'N/A'}\n\n"
        )
    else:
        text += "▫️ Source: Not set\n\n"
    
    if Config.TARGET_CHAT:
        text += (
            f"▫️ Target: {Config.TARGET_CHAT.title}\n"
            f"ID: {Config.TARGET_CHAT.id}\n"
            f"Username: @{Config.TARGET_CHAT.username if Config.TARGET_CHAT.username else 'N/A'}\n"
        )
    else:
        text += "▫️ Target: Not set (will use current chat)\n"
    
    await message.reply(text)

@app.on_message(filters.command("clearchat"))
async def clear_chat(client: Client, message: Message):
    try:
        if len(message.command) < 2:
            return await message.reply("Usage: /clearchat [source|target|all]")
        
        chat_type = message.command[1].lower()
        if chat_type == "source":
            Config.SOURCE_CHAT = None
            await message.reply("✅ Source chat cleared")
        elif chat_type == "target":
            Config.TARGET_CHAT = None
            await message.reply("✅ Target chat cleared")
        elif chat_type == "all":
            Config.SOURCE_CHAT = None
            Config.TARGET_CHAT = None
            await message.reply("✅ Both source and target chats cleared")
        else:
            await message.reply("Invalid type. Use 'source', 'target' or 'all'")
    except Exception as e:
        await message.reply(f"Error: {str(e)}")

# [Previous command handlers remain the same]

@app.on_message(filters.command("batch"))
async def start_batch(client: Client, message: Message):
    if Config.PROCESSING:
        return await message.reply("⚠️ Already processing! Use /stop to cancel")
    
    if not Config.SOURCE_CHAT:
        return await message.reply("❌ Source chat not set. Use /setchat source [chat_id]")
    
    Config.PROCESSING = True
    Config.BATCH_MODE = True
    Config.START_ID = None
    Config.END_ID = None
    
    await message.reply(
        f"🔹 **Batch Mode Activated**\n"
        f"▫️ Source: {Config.SOURCE_CHAT.title}\n"
        f"▫️ Target: {Config.TARGET_CHAT.title if Config.TARGET_CHAT else 'Current Chat'}\n"
        f"▫️ Offset: {Config.OFFSET}\n"
        f"▫️ Replacements: {len(Config.REPLACEMENTS)}\n\n"
        f"Reply to the FIRST message or send its link"
    )

async def process_batch(client: Client, message: Message):
    try:
        if not Config.SOURCE_CHAT:
            await message.reply("❌ Source chat not set")
            Config.PROCESSING = False
            return
            
        start_id = min(Config.START_ID, Config.END_ID)
        end_id = max(Config.START_ID, Config.END_ID)
        total = end_id - start_id + 1
        
        target_chat = Config.TARGET_CHAT.id if Config.TARGET_CHAT else message.chat.id
        
        # Verify permissions again before starting
        has_perms, perm_msg = await verify_permissions(client, Config.SOURCE_CHAT.id)
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
            f"▫️ Source: {Config.SOURCE_CHAT.title}\n"
            f"▫️ Target: {Config.TARGET_CHAT.title if Config.TARGET_CHAT else message.chat.title}\n"
            f"▫️ Range: {start_id}-{end_id}\n"
            f"▫️ Total: {total} messages\n"
            f"▫️ Offset: {Config.OFFSET}\n",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # [Rest of the process_batch function remains the same]
        
if __name__ == "__main__":
    print("⚡ Ultimate Batch Link Modifier Bot Started!")
    try:
        app.start()
        idle()
    except Exception as e:
        print(f"Fatal error: {e}")
    finally:
        app.stop()
