import re
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyrogram.enums import ParseMode, MessageMediaType
from pyrogram.errors import FloodWait

# Bot Configuration
API_ID = 20219694
API_HASH = "29d9b3a01721ab452fcae79346769e29"
BOT_TOKEN = "7942215521:AAG5Zardlr7ULt2-yleqXeKjHKp4AQtVzd8"

class Config:
    OFFSET = 0  # How much to add/subtract from message IDs in captions
    PROCESSING = False

app = Client(
    "caption_link_modifier",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

def modify_caption_links(text: str, offset: int) -> str:
    """Only modifies Telegram message links in captions"""
    if not text:
        return text

    def replacer(match):
        url = match.group(1)
        chat = match.group(2)
        msg_id = match.group(3)
        return f"{url}{chat}/{int(msg_id) + offset}"

    # This pattern matches t.me/.../123 links but not media source links
    pattern = r'(https?://t\.me/(c/\d+|[\w-]+)/(\d+))'
    return re.sub(pattern, replacer, text)

async def process_public_post(client: Client, message: Message):
    try:
        # Extract the public post link from message
        if not message.text or "t.me/" not in message.text:
            return await message.reply("Please send a valid Telegram post link")

        match = re.search(r't\.me/(?:c/)?([^/]+)/(\d+)', message.text)
        if not match:
            return await message.reply("Invalid link format. Send like: https://t.me/channel/123")

        chat_id = match.group(1)
        msg_id = int(match.group(2))

        # Get the original message
        original_msg = await client.get_messages(chat_id, msg_id)
        if not original_msg:
            return await message.reply("Couldn't fetch that message")

        # Process the message
        if original_msg.media:
            caption = original_msg.caption or ""
            modified_caption = modify_caption_links(caption, Config.OFFSET)
            
            if original_msg.media == MessageMediaType.PHOTO:
                await client.send_photo(
                    message.chat.id,
                    original_msg.photo.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            elif original_msg.media == MessageMediaType.VIDEO:
                await client.send_video(
                    message.chat.id,
                    original_msg.video.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await client.send_document(
                    message.chat.id,
                    original_msg.document.file_id,
                    caption=modified_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            modified_text = modify_caption_links(original_msg.text, Config.OFFSET)
            await client.send_message(
                message.chat.id,
                modified_text,
                parse_mode=ParseMode.MARKDOWN
            )

        await message.reply("✅ Post processed successfully!")

    except FloodWait as e:
        await asyncio.sleep(e.value)
        await message.reply(f"⚠️ Please wait {e.value} seconds and try again")
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command(["start", "help"]))
async def start_cmd(client: Client, message: Message):
    help_text = """
🤖 **Simple Telegram Link Modifier Bot**

🔹 Just send me a public channel post link
🔹 I'll forward it with modified caption links

⚙️ **Commands:**
/addnumber N - Add N to message IDs in captions
/lessnumber N - Subtract N from message IDs in captions
/setoffset N - Set absolute offset value

Example link:
https://t.me/public_channel/123
"""
    await message.reply(help_text)

@app.on_message(filters.command(["addnumber", "lessnumber", "setoffset"]))
async def set_offset_cmd(client: Client, message: Message):
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
    except:
        await message.reply("⚠️ Usage: /addnumber 2 or /lessnumber 3 or /setoffset 5")

@app.on_message(filters.text & ~filters.command)
async def handle_message(client: Client, message: Message):
    if Config.PROCESSING:
        return
    
    Config.PROCESSING = True
    try:
        await process_public_post(client, message)
    finally:
        Config.PROCESSING = False

if __name__ == "__main__":
    print("⚡ Bot Started!")
    app.start()
    idle()
    app.stop()
