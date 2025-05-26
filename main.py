import os
import re
import asyncio
from typing import List, Optional, Dict, Union
from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    CallbackQuery
)
from pyrogram.enums import ParseMode, MessageMediaType
from config import API_ID, API_HASH, BOT_TOKEN, TARGET_CHANNEL

# Enhanced MongoDB connection with error handling
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError

MONGO_URI = "mongodb+srv://lecocita:pQx2GGUZtQSPhjMx@cluster0.oz5kyow.mongodb.net/telegrambot?retryWrites=true&w=majority&appName=Cluster0"

class Database:
    def __init__(self):
        self.client = None
        self.db = None
        
    async def connect(self):
        try:
            self.client = AsyncIOMotorClient(MONGO_URI)
            self.db = self.client.get_default_database()
            await self.db.command("ping")
            print("✅ Connected to MongoDB successfully")
        except PyMongoError as e:
            print(f"❌ MongoDB connection error: {e}")
            raise

    async def close(self):
        if self.client:
            self.client.close()

db = Database()

# Initialize Pyrogram Client with enhanced settings
app = Client(
    "caption_link_modifier_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=100,
    sleep_threshold=60,
    parse_mode=ParseMode.MARKDOWN
)

# Global Configuration with proper encapsulation
class Config:
    def __init__(self):
        self.OFFSET = 0
        self.EXTRACT_LIMIT = 100
        self.CURRENT_BATCH = []
        self.PROCESSING = False
        self.ACTIVE_TASKS = set()
        self.MAX_CONCURRENT_TASKS = 5
        self.ALLOWED_USERS = []  # Add user IDs here for restricted access
        
    def reset(self):
        self.OFFSET = 0
        self.EXTRACT_LIMIT = 100
        self.CURRENT_BATCH = []
        self.PROCESSING = False
        
config = Config()

# Utility Functions with enhanced error handling
class MediaHandler:
    @staticmethod
    async def download_media(client: Client, message: Message) -> Optional[str]:
        """Download media from Telegram message with proper cleanup"""
        if not message.media:
            return None
            
        try:
            os.makedirs("downloads", exist_ok=True)
            file_name = f"downloads/{message.id}"
            
            if message.media == MessageMediaType.PHOTO:
                file_name += ".jpg"
            elif message.media == MessageMediaType.VIDEO:
                file_name += ".mp4"
            elif message.media == MessageMediaType.DOCUMENT:
                file_name = message.document.file_name or f"document_{message.id}.bin"
            
            download_path = await client.download_media(message, file_name=file_name)
            return download_path
        except Exception as e:
            print(f"❌ Media download error: {e}")
            return None
            
    @staticmethod
    def cleanup_media(file_path: str):
        """Clean up downloaded media files"""
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"❌ Media cleanup error: {e}")

class LinkModifier:
    @staticmethod
    def modify_links(text: str, offset: int) -> str:
        """
        Only modify Telegram message IDs in caption links while preserving:
        - Main media links (t.me/channel/123)
        - Other non-Telegram links
        """
        if not text:
            return text
            
        def replacer(match):
            url = match.group(0)
            # Skip if it's the main media link (we don't want to modify this)
            if re.search(r't\.me/(?:c/)?[\w-]+/\d+$', url):
                return url
                
            # Only modify message IDs in URLs that look like Telegram post links
            parts = url.split('/')
            if parts[-1].isdigit():
                parts[-1] = str(int(parts[-1]) + offset)
                return '/'.join(parts)
            return url
            
        # Pattern to match Telegram links but not the main media link
        pattern = r'https?://(?:t\.me|telegram\.me)/(?:c/)?[\w-]+/\d+'
        return re.sub(pattern, replacer, text)

# Core Processing Functions with proper task management
class MessageProcessor:
    @staticmethod
    async def process_single_message(client: Client, source_msg: Message) -> Optional[Message]:
        """Process and forward a single message with modified caption links"""
        try:
            # Get the original caption/text
            caption = source_msg.caption or source_msg.text or ""
            
            # Apply offset ONLY to links in caption (not main media link)
            modified_caption = LinkModifier.modify_links(caption, config.OFFSET)
            
            # Download media if exists
            file_path = await MediaHandler.download_media(client, source_msg)
            
            # Forward to target channel with proper media handling
            try:
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
                else:
                    sent_msg = await client.send_message(
                        TARGET_CHANNEL,
                        text=modified_caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
                return sent_msg
            finally:
                if file_path:
                    MediaHandler.cleanup_media(file_path)
                    
        except Exception as e:
            print(f"❌ Message processing error: {e}")
            return None
            
    @staticmethod
    async def process_batch(client: Client, chat_id: Union[int, str], start_msg_id: int, progress_msg: Message):
        """Process a batch of messages with proper rate limiting"""
        processed_count = 0
        failed_count = 0
        
        try:
            for i in range(config.EXTRACT_LIMIT):
                if not config.PROCESSING:
                    break
                    
                try:
                    msg_id = start_msg_id + i
                    source_msg = await client.get_messages(chat_id, msg_id)
                    
                    if not source_msg or source_msg.empty:
                        continue
                        
                    # Process message with proper concurrency control
                    task = asyncio.create_task(
                        MessageProcessor.process_single_message(client, source_msg)
                    )
                    config.ACTIVE_TASKS.add(task)
                    task.add_done_callback(lambda t: config.ACTIVE_TASKS.remove(t))
                    
                    # Wait if we have too many concurrent tasks
                    if len(config.ACTIVE_TASKS) >= config.MAX_CONCURRENT_TASKS:
                        await asyncio.wait(config.ACTIVE_TASKS, return_when=asyncio.FIRST_COMPLETED)
                        
                    processed_count += 1
                    
                    # Update progress every 5 messages
                    if processed_count % 5 == 0:
                        await progress_msg.edit(
                            f"⏳ Processing...\n"
                            f"✅ {processed_count}/{config.EXTRACT_LIMIT} processed\n"
                            f"❌ {failed_count} failed\n"
                            f"🔗 Offset: {config.OFFSET}"
                        )
                        
                except Exception as e:
                    failed_count += 1
                    print(f"❌ Error processing message {msg_id}: {e}")
                    continue
                    
            return processed_count, failed_count
        except Exception as e:
            print(f"❌ Batch processing error: {e}")
            return processed_count, failed_count

# Command Handlers with proper access control
@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Enhanced start command with detailed help"""
    help_text = """
🌟 **Advanced Caption Link Modifier Bot** 🌟

🔹 `/batch [limit]` - Start processing messages
🔹 `/addnumber N` - Add N to caption links
🔹 `/lessnumber N` - Subtract N from caption links
🔹 `/currentoffset` - Show current offset
🔹 `/cancel` - Cancel current operation

📌 **Key Features:**
- Only modifies links in captions
- Preserves original media links
- Batch processing support
- Real-time progress tracking
"""
    await message.reply(
        help_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Quick Start", callback_data="quickstart")],
            [InlineKeyboardButton("Cancel Operation", callback_data="cancel")]
        ])
    )

@app.on_message(filters.command(["addnumber", "lessnumber"]))
async def set_offset_command(client: Client, message: Message):
    """Set offset with add/subtract functionality"""
    try:
        if len(message.command) < 2:
            await message.reply("⚠️ Usage: /addnumber 2 or /lessnumber 3")
            return
            
        amount = int(message.command[1])
        if message.command[0] == "addnumber":
            config.OFFSET += amount
            action = "added"
        else:
            config.OFFSET -= amount
            action = "subtracted"
            
        await message.reply(
            f"✅ Successfully {action} {amount} to offset\n"
            f"🔢 New offset: {config.OFFSET}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Reset to 0", callback_data="resetoffset")]
            ])
        )
    except ValueError:
        await message.reply("⚠️ Please provide a valid number")

@app.on_message(filters.command("currentoffset"))
async def show_offset_command(client: Client, message: Message):
    """Show current offset value"""
    await message.reply(f"🔢 Current link offset: {config.OFFSET}")

@app.on_message(filters.command("batch"))
async def batch_command(client: Client, message: Message):
    """Start batch processing with proper validation"""
    if config.PROCESSING:
        await message.reply("⚠️ Another operation is already in progress")
        return
        
    try:
        config.PROCESSING = True
        config.CURRENT_BATCH = []
        
        if len(message.command) > 1:
            try:
                config.EXTRACT_LIMIT = min(int(message.command[1]), 200)  # Max 200 messages
            except ValueError:
                await message.reply("⚠️ Please provide a valid number for limit")
                config.PROCESSING = False
                return
                
        await message.reply(
            f"🔹 **Batch Mode Activated**\n"
            f"📌 Extraction Limit: {config.EXTRACT_LIMIT} messages\n"
            f"🔗 Current Offset: {config.OFFSET}\n"
            f"📤 Now send me the Telegram post link!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Cancel", callback_data="cancel_batch")]
            ])
        )
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")
        config.PROCESSING = False

@app.on_message(filters.command("cancel"))
async def cancel_command(client: Client, message: Message):
    """Cancel current operation with proper cleanup"""
    config.PROCESSING = False
    config.ACTIVE_TASKS.clear()
    await message.reply("✅ Current operation cancelled")

# Main Message Handler with enhanced validation
@app.on_message(filters.text & filters.incoming)
async def message_handler(client: Client, message: Message):
    """Handle incoming messages with Telegram links"""
    if not config.PROCESSING or "t.me/" not in message.text:
        return
        
    try:
        # Validate and extract chat_id and message_id
        link_parser = re.search(
            r't\.me/(?:c/)?([^/]+)/(\d+)',
            message.text
        )
        
        if not link_parser:
            await message.reply("⚠️ Invalid Telegram link format")
            return
            
        chat_identifier = link_parser.group(1)
        start_msg_id = int(link_parser.group(2))
        
        # Determine if it's a channel (c/) or username
        if "c/" in message.text:
            chat_id = int("-100" + chat_identifier)
        else:
            chat_id = chat_identifier
            
        # Start processing with progress tracking
        progress_msg = await message.reply("⏳ Starting batch processing...")
        
        processed_count, failed_count = await MessageProcessor.process_batch(
            client,
            chat_id,
            start_msg_id,
            progress_msg
        )
        
        # Final status report
        result_text = (
            f"✅ **Batch Processing Complete!**\n"
            f"• Successfully processed: {processed_count}\n"
            f"• Failed: {failed_count}\n"
            f"• Link Offset: {config.OFFSET}\n"
            f"• Last Message ID: {start_msg_id + processed_count - 1}"
        )
        
        await progress_msg.edit(
            result_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("New Batch", callback_data="new_batch")]
            ])
        )
        
        config.PROCESSING = False
    except Exception as e:
        await message.reply(f"❌ Processing error: {str(e)}")
        config.PROCESSING = False

# Callback Query Handler with all actions
@app.on_callback_query()
async def callback_handler(client: Client, callback_query: CallbackQuery):
    """Handle all inline button callbacks"""
    try:
        if callback_query.data == "cancel_batch":
            config.PROCESSING = False
            await callback_query.message.edit("❌ Batch processing cancelled")
            
        elif callback_query.data == "resetoffset":
            config.OFFSET = 0
            await callback_query.message.edit(
                "✅ Offset reset to 0",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Back", callback_data="back_to_settings")]
                )
            )
            
        elif callback_query.data == "new_batch":
            config.PROCESSING = True
            await callback_query.message.edit(
                "🔹 **New Batch Started**\n"
                "📤 Send me the Telegram post link!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Cancel", callback_data="cancel_batch")]
                )
            )
            
        elif callback_query.data == "quickstart":
            await callback_query.message.edit(
                "🚀 **Quick Start Guide**\n\n"
                "1. Use /addnumber or /lessnumber to set offset\n"
                "2. Send /batch to start processing\n"
                "3. Paste a Telegram post link\n"
                "4. The bot will process messages while modifying only caption links",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Back", callback_data="back_to_main")]
                )
            )
            
        elif callback_query.data == "back_to_main":
            await callback_query.message.edit(
                "🌟 **Advanced Caption Link Modifier Bot** 🌟",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Quick Start", callback_data="quickstart")],
                    [InlineKeyboardButton("Cancel Operation", callback_data="cancel")]
                ])
            )
            
        await callback_query.answer()
    except Exception as e:
        print(f"❌ Callback error: {e}")
        await callback_query.answer("⚠️ An error occurred")

# Startup and Shutdown Handlers
@app.on_startup()
async def startup():
    """Initialize resources when bot starts"""
    try:
        await db.connect()
        os.makedirs("downloads", exist_ok=True)
        print("✅ Bot initialized successfully")
    except Exception as e:
        print(f"❌ Startup error: {e}")
        raise

@app.on_shutdown()
async def shutdown():
    """Cleanup resources when bot stops"""
    try:
        await db.close()
        # Cleanup downloads directory
        for filename in os.listdir("downloads"):
            file_path = os.path.join("downloads", filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"❌ Error deleting {file_path}: {e}")
        print("✅ Bot shutdown cleanly")
    except Exception as e:
        print(f"❌ Shutdown error: {e}")

if __name__ == "__main__":
    print("⚡ Advanced Caption Link Modifier Bot Started!")
    app.run()
