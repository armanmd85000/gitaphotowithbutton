import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode, ChatType, ChatMemberStatus

# Bot Configuration
API_ID = 20219694
API_HASH = "29d9b3a01721ab452fcae79346769e29"
BOT_TOKEN = "7972190756:AAHa4pUAZBTWSZ3smee9sEWiFv-lFhT5USA"

class Config:
    OFFSET = 0
    REPLACEMENTS = {}
    TARGET_CHAT_ID = None

app = Client("link_modifier_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def modify_links(text: str, offset: int) -> str:
    if not text:
        return text

    # Apply word replacements
    for original, replacement in Config.REPLACEMENTS.items():
        text = re.sub(rf'\b{re.escape(original)}\b', replacement, text, flags=re.IGNORECASE)

    # Modify Telegram message IDs in links
    def replacer(match):
        prefix = match.group(1) or ""
        domain = match.group(2)
        chat_part = match.group(3) or ""
        msg_id = int(match.group(4))
        return f"{prefix}://{domain}/{chat_part}{msg_id + offset}"

    pattern = r'(https?://)?(t\.me|telegram\.(?:me|dog))/(c/)?([^/]+)/(\d+)'
    return re.sub(pattern, replacer, text)

@app.on_message(filters.command(["start", "help"]))
async def start_cmd(client: Client, message: Message):
    help_text = """
🤖 **Link Modifier Bot** 🚀

🔹 **Basic Commands:**
/addnumber N - Add N to message IDs
/lessnumber N - Subtract N from message IDs
/setchatid @channel - Set target channel

🔹 **Word Replacement:**
/removereplace WORD - Remove word replacement

📌 **Requirements:**
1. Add bot as admin in target channel
2. Bot needs message posting permissions
"""
    await message.reply(help_text, parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command(["addnumber", "lessnumber"]))
async def set_offset_cmd(client: Client, message: Message):
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
        
        await message.reply(f"✅ {action} offset: {amount}\nNew offset: {Config.OFFSET}")
    except ValueError:
        await message.reply("⚠️ Please provide a valid number")

@app.on_message(filters.command("removereplace"))
async def remove_replacement(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply("⚠️ Usage: /removereplace WORD")
    
    word = message.command[1].lower()
    if word in Config.REPLACEMENTS:
        del Config.REPLACEMENTS[word]
        await message.reply(f"✅ Removed replacement for `{word}`", parse_mode=ParseMode.MARKDOWN)
    else:
        await message.reply(f"⚠️ No replacement found for `{word}`")

@app.on_message(filters.command("setchatid"))
async def set_target_chat(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply("⚠️ Usage: /setchatid @channel or -100123456789")
    
    chat_id = message.command[1]
    try:
        chat = await client.get_chat(chat_id)
        
        # Verify bot permissions
        try:
            member = await client.get_chat_member(chat.id, "me")
            if member.status != ChatMemberStatus.ADMINISTRATOR:
                return await message.reply("❌ Bot needs to be admin in the channel")
            if not member.privileges.can_post_messages:
                return await message.reply("❌ Bot needs message posting permissions")
        except Exception as e:
            return await message.reply(f"❌ Permission error: {str(e)}")
        
        Config.TARGET_CHAT_ID = chat.id
        await message.reply(
            f"✅ Target chat set to:\n"
            f"Title: {chat.title}\n"
            f"ID: `{chat.id}`",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        await message.reply(f"❌ Error setting chat ID: {str(e)}")

@app.on_message(filters.text & ~filters.command)
async def handle_message(client: Client, message: Message):
    if not Config.TARGET_CHAT_ID:
        return
    
    try:
        modified_text = modify_links(message.text, Config.OFFSET)
        await client.send_message(
            chat_id=Config.TARGET_CHAT_ID,
            text=modified_text,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        await message.reply(f"❌ Error processing message: {str(e)}")

if __name__ == "__main__":
    print("⚡ Link Modifier Bot Started!")
    app.run()
