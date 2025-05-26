import os
import re
import asyncio
from typing import List, Optional
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo
)
from pyrogram.enums import ParseMode, MessageMediaType
from config import API_ID, API_HASH, BOT_TOKEN, TARGET_CHANNEL
# MongoDB connection
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = "mongodb+srv://lecocita:pQx2GGUZtQSPhjMx@cluster0.oz5kyow.mongodb.net/telegrambot?retryWrites=true&w=majority&appName=Cluster0"

# Connect MongoDB and select default database
mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo.get_default_database() or mongo["telegrambot"]

# Initialize Pyrogram Client
app = Client(
    "advanced_telegram_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Global Variables
class Config:
    OFFSET = 0
    EXTRACT_LIMIT = 100
    CURRENT_BATCH = []
    PROCESSING = False

# Helper Functions
def modify_links(text: str, offset: int) -> str:
    """Modify Telegram message IDs in links by given offset"""
    def replacer(match):
        parts = match.group(0).split('/')
        parts[-1] = str(int(parts[-1]) + offset)
        return '/'.join(parts)
    
    pattern = r'https?://t\.me/(?:c/)?[\w/-]+/\d+'
    return re.sub(pattern, replacer, text)

async def download_media(client: Client, message: Message) -> Optional[str]:
    """Download media from Telegram message"""
    if not message.media:
        return None
        
    file_name = f"downloads/{message.id}"
    
    if message.media == MessageMediaType.PHOTO:
        file_name += ".jpg"
    elif message.media == MessageMediaType.VIDEO:
        file_name += ".mp4"
    elif message.media == MessageMediaType.DOCUMENT:
        file_name = message.document.file_name or f"document_{message.id}.bin"
    
    download_path = await client.download_media(message, file_name=file_name)
    return download_path

async def process_message(client: Client, source_msg: Message, offset: int) -> Message:
    """Process and forward a single message with modified links"""
    # Modify caption/text
    caption = source_msg.caption or source_msg.text or ""
    modified_caption = modify_links(caption, offset)
    
    # Download media if exists
    file_path = await download_media(client, source_msg)
    
    # Forward to target channel
    if file_path:
        if source_msg.media == MessageMediaType.PHOTO:
            sent_msg = await client.send_photo(
                TARGET_CHANNEL,
                photo=file_path,
                caption=modified_caption,
                parse_mode=ParseMode.MARKDOWN
            )
        elif source_msg.media == MessageMediaType.VIDEO:
            sent_msg = await client.send_video(
                TARGET_CHANNEL,
                video=file_path,
                caption=modified_caption,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            sent_msg = await client.send_document(
                TARGET_CHANNEL,
                document=file_path,
                caption=modified_caption,
                parse_mode=ParseMode.MARKDOWN
            )
        os.remove(file_path)
    else:
        sent_msg = await client.send_message(
            TARGET_CHANNEL,
            text=modified_caption,
            parse_mode=ParseMode.MARKDOWN
        )
    
    return sent_msg

# Command Handlers
@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    await message.reply(
        "🤖 **Advanced Telegram File Processor**\n\n"
        "🔹 /batch [limit] - Start batch processing\n"
        "🔹 /setoffset [+/-N] - Set link offset\n"
        "🔹 /cancel - Cancel current operation",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Help", callback_data="help")]
        ])
    )

@app.on_message(filters.command("setoffset"))
async def set_offset_command(client: Client, message: Message):
    try:
        offset = message.text.split()[1]
        Config.OFFSET = int(offset)
        await message.reply(f"✅ Link offset set to: {Config.OFFSET}")
    except (IndexError, ValueError):
        await message.reply("⚠️ Usage: /setoffset +2 or /setoffset -3")

@app.on_message(filters.command("batch"))
async def batch_command(client: Client, message: Message):
    try:
        Config.PROCESSING = True
        Config.CURRENT_BATCH = []
        
        if len(message.command) > 1:
            Config.EXTRACT_LIMIT = int(message.command[1])
            
        await message.reply(
            f"🔹 **Batch Mode Activated**\n"
            f"📌 Extraction Limit: {Config.EXTRACT_LIMIT} messages\n"
            f"🔗 Now send me the first Telegram post link!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Cancel", callback_data="cancel_batch")]
            )
        )
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")
        Config.PROCESSING = False

@app.on_message(filters.command("cancel"))
async def cancel_command(client: Client, message: Message):
    Config.PROCESSING = False
    await message.reply("✅ Current operation cancelled")

# Message Handler
@app.on_message(filters.text & filters.incoming)
async def message_handler(client: Client, message: Message):
    if not Config.PROCESSING or "t.me/" not in message.text:
        return

    try:
        # Extract chat_id and message_id from link
        if "t.me/c/" in message.text:
            parts = message.text.split("/")
            chat_id = int("-100" + parts[4])
            start_msg_id = int(parts[5])
        else:
            parts = message.text.split("/")
            chat_id = parts[3]
            start_msg_id = int(parts[4])

        # Process messages in batch
        progress_msg = await message.reply("⏳ Starting batch processing...")
        processed_count = 0

        for i in range(Config.EXTRACT_LIMIT):
            if not Config.PROCESSING:
                break

            try:
                msg_id = start_msg_id + i
                source_msg = await client.get_messages(chat_id, msg_id)
                
                if not source_msg or source_msg.empty:
                    continue

                await process_message(client, source_msg, Config.OFFSET)
                processed_count += 1

                if processed_count % 10 == 0:
                    await progress_msg.edit(
                        f"⏳ Processing...\n"
                        f"✅ {processed_count}/{Config.EXTRACT_LIMIT} messages processed"
                    )

            except Exception as e:
                print(f"Error processing message {msg_id}: {str(e)}")
                continue

        await progress_msg.edit(
            f"✅ Batch Processing Complete!\n"
            f"• Total Processed: {processed_count} messages\n"
            f"• Link Offset: {Config.OFFSET}"
        )
        Config.PROCESSING = False

    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")
        Config.PROCESSING = False

# Callback Query Handler
@app.on_callback_query(filters.regex("cancel_batch"))
async def cancel_batch_callback(client, callback_query):
    Config.PROCESSING = False
    await callback_query.message.edit("❌ Batch processing cancelled")

if __name__ == "__main__":
    # Create downloads directory if not exists
    os.makedirs("downloads", exist_ok=True)
    
    print("⚡ Advanced Telegram Bot Started!")
    app.run()
