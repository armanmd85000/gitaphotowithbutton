import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode, ChatType, ChatMemberStatus
from pyrogram.errors import FloodWait, RPCError

# Bot Configuration
API_ID = 20219694
API_HASH = "29d9b3a01721ab452fcae79346769e29"
BOT_TOKEN = "7972190756:AAHa4pUAZBTWSZ3smee9sEWiFv-lFhT5USA"

class Config:
    OFFSET = 0
    REPLACEMENTS = {}
    TARGET_CHAT_ID = None
    ADMIN_CACHE = {}

app = Client(
    "advanced_link_modifier",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

def modify_content(text: str) -> str:
    """Modify Telegram links in text with current offset"""
    if not text:
        return text

    # Apply word replacements
    for original, replacement in Config.REPLACEMENTS.items():
        text = re.sub(rf'\b{re.escape(original)}\b', replacement, text, flags=re.IGNORECASE)

    # Modify Telegram links
    def replacer(match):
        prefix = match.group(1) or ""
        domain = match.group(2)
        chat_part = match.group(3) or ""
        chat_ref = match.group(4)
        msg_id = int(match.group(5))
        return f"{prefix}://{domain}/{chat_part}{chat_ref}/{msg_id + Config.OFFSET}"

    pattern = r'(https?://)?(t\.me|telegram\.(?:me|dog))/(c/)?([^/]+)/(\d+)'
    return re.sub(pattern, replacer, text)

async def verify_admin(client: Client, chat_id: int) -> bool:
    """Check if bot is admin in chat"""
    if chat_id in Config.ADMIN_CACHE:
        return Config.ADMIN_CACHE[chat_id]
    
    try:
        chat = await client.get_chat(chat_id)
        if chat.type not in [ChatType.CHANNEL, ChatType.SUPERGROUP]:
            Config.ADMIN_CACHE[chat_id] = False
            return False
            
        member = await client.get_chat_member(chat.id, "me")
        is_admin = member.status == ChatMemberStatus.ADMINISTRATOR
        Config.ADMIN_CACHE[chat_id] = is_admin
        return is_admin
    except Exception:
        return False

@app.on_message(filters.command("start"))
async def start_cmd(client: Client, message: Message):
    help_text = """
🤖 **Advanced Link Modifier Bot** 🚀

🔹 **Core Commands:**
/addnumber N - Add N to message IDs
/lessnumber N - Subtract N from message IDs
/remowords - Remove all word replacements
/setchatid @channel - Set target channel

🔹 **Current Settings:**
Offset: `{offset}`
Target Chat: `{target_chat}`
Word Replacements: `{replacements}`

📌 **Note:** Bot needs admin in both source and target chats
""".format(
    offset=Config.OFFSET,
    target_chat=Config.TARGET_CHAT_ID or "Not set",
    replacements=len(Config.REPLACEMENTS))
    
    await message.reply(help_text, parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command(["addnumber", "lessnumber"]))
async def offset_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply("⚠️ Usage: /addnumber 2 or /lessnumber 3")
    
    try:
        amount = int(message.command[1])
        if message.command[0] == "addnumber":
            Config.OFFSET += amount
            action = "Added"
        else:
            Config.OFFSET -= amount
            action = "Subtracted"
        
        await message.reply(f"✅ {action} offset: {amount}\nNew offset: `{Config.OFFSET}`", 
                          parse_mode=ParseMode.MARKDOWN)
    except ValueError:
        await message.reply("⚠️ Please provide a valid number")

@app.on_message(filters.command("remowords"))
async def remowords_cmd(client: Client, message: Message):
    count = len(Config.REPLACEMENTS)
    Config.REPLACEMENTS = {}
    await message.reply(f"✅ Removed all {count} word replacements")

@app.on_message(filters.command("setchatid"))
async def setchatid_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply("⚠️ Usage: /setchatid @channel or -100123456789")
    
    chat_id = message.command[1]
    try:
        chat = await client.get_chat(chat_id)
        
        is_admin = await verify_admin(client, chat.id)
        if not is_admin:
            return await message.reply("❌ Bot must be admin in target chat")
        
        Config.TARGET_CHAT_ID = chat.id
        Config.ADMIN_CACHE.clear()
        
        await message.reply(
            f"✅ Target chat set to:\n"
            f"Title: `{chat.title}`\n"
            f"Type: `{chat.type}`\n"
            f"ID: `{chat.id}`",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.text & ~filters.command)
async def handle_text_messages(client: Client, message: Message):
    if not Config.TARGET_CHAT_ID:
        return
    
    try:
        if not await verify_admin(client, message.chat.id):
            return
        
        modified_text = modify_content(message.text)
        
        if modified_text != message.text:
            await client.send_message(
                chat_id=Config.TARGET_CHAT_ID,
                text=modified_text,
                parse_mode=ParseMode.MARKDOWN
            )
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except RPCError as e:
        print(f"Error processing message: {e}")

if __name__ == "__main__":
    print("⚡ Advanced Link Modifier Bot Started!")
    app.run()
