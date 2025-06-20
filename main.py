import re
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode

# Bot Configuration
API_ID = 20219694
API_HASH = "29d9b3a01721ab452fcae79346769e29"
BOT_TOKEN = "7972190756:AAHa4pUAZBTWSZ3smee9sEWiFv-lFhT5USA"

class Config:
    OFFSET = 0
    REPLACEMENTS = {}
    TARGET_CHAT_ID = None

app = Client(
    "link_modifier_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

def modify_links(text: str) -> str:
    """Modify Telegram message links by adding/subtracting the offset"""
    if not text:
        return text
    
    # Apply word replacements
    for original, replacement in Config.REPLACEMENTS.items():
        text = text.replace(original, replacement)
    
    # Modify message IDs in links
    def replacer(match):
        prefix = match.group(1)
        chat_part = match.group(2)
        msg_id = int(match.group(3))
        return f"{prefix}{chat_part}/{msg_id + Config.OFFSET}"
    
    pattern = r'(https?://t\.me/(?:c/)?([^/]+/)(\d+))'
    return re.sub(pattern, replacer, text)

@app.on_message(filters.command(["start", "help"]))
async def start_cmd(client: Client, message: Message):
    """Simple start command"""
    await message.reply(
        "🔹 Link Modifier Bot\n\n"
        "Commands:\n"
        "/addnumber X - Add X to message IDs\n"
        "/lessnumber X - Subtract X from message IDs\n"
        "/remowords TEXT - Remove text from messages\n"
        "/setchatid ID - Set target chat ID\n\n"
        "Just send me a message with Telegram links to modify them!",
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_message(filters.command("addnumber"))
async def add_number(client: Client, message: Message):
    """Add to message IDs"""
    try:
        amount = int(message.command[1])
        Config.OFFSET += amount
        await message.reply(f"✅ Added {amount} to offset\nNew offset: {Config.OFFSET}")
    except (IndexError, ValueError):
        await message.reply("⚠️ Usage: /addnumber <integer>")

@app.on_message(filters.command("lessnumber"))
async def less_number(client: Client, message: Message):
    """Subtract from message IDs"""
    try:
        amount = int(message.command[1])
        Config.OFFSET -= amount
        await message.reply(f"✅ Subtracted {amount} from offset\nNew offset: {Config.OFFSET}")
    except (IndexError, ValueError):
        await message.reply("⚠️ Usage: /lessnumber <integer>")

@app.on_message(filters.command("remowords"))
async def remowords(client: Client, message: Message):
    """Remove words from messages"""
    if len(message.command) > 1:
        words = ' '.join(message.command[1:])
        Config.REPLACEMENTS[words] = ""
        await message.reply(f"✅ Will remove: '{words}'")
    else:
        await message.reply("⚠️ Usage: /remowords <text to remove>")

@app.on_message(filters.command("setchatid"))
async def setchatid(client: Client, message: Message):
    """Set target chat ID for private channels"""
    if len(message.command) > 1:
        try:
            Config.TARGET_CHAT_ID = int(message.command[1])
            await message.reply(f"✅ Target chat ID set to: {Config.TARGET_CHAT_ID}")
        except ValueError:
            await message.reply("⚠️ Please provide a valid chat ID (numeric)")
    else:
        await message.reply("⚠️ Usage: /setchatid <chat_id>")

@app.on_message(filters.text & ~filters.command)
async def handle_message(client: Client, message: Message):
    """Process all text messages and modify links"""
    modified_text = modify_links(message.text)
    if modified_text != message.text:
        await message.reply(modified_text)

if __name__ == "__main__":
    print("Bot started!")
    app.run()
