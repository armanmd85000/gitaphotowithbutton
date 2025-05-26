import re
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode, MessageMediaType

# Bot Config
API_ID = 20219694
API_HASH = "29d9b3a01721ab452fcae79346769e29"
BOT_TOKEN = "7942215521:AAG5Zardlr7ULt2-yleqXeKjHKp4AQtVzd8"

class Config:
    OFFSET = 0
    PROCESSING = False
    EXTRACT_LIMIT = 100
    TARGET_CHAT = None

app = Client("link_modifier_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def modify_only_caption_links(text: str, offset: int) -> str:
    """
    सिर्फ कैप्शन में मौजूद टेलीग्राम लिंक्स को मॉडिफाई करेगा
    मीडिया सोर्स लिंक को छोड़ देगा
    """
    if not text:
        return text

    def offset_applier(match):
        url = match.group(1)
        chat = match.group(2)
        msg_id = match.group(3)
        return f"{url}{chat}/{int(msg_id) + offset}"

    # सिर्फ t.me/c/... और t.me/username/... वाले लिंक्स को टारगेट करेगा
    pattern = r'(https?://t\.me/(c/\d+|[\w-]+)/(\d+))'
    return re.sub(pattern, offset_applier, text)

async def process_single_message(client: Client, message: Message):
    try:
        # मीडिया फॉरवर्ड करने का लॉजिक
        if message.media:
            if message.media == MessageMediaType.PHOTO:
                sent_msg = await client.send_photo(
                    Config.TARGET_CHAT,
                    message.photo.file_id,
                    caption=modify_only_caption_links(message.caption, Config.OFFSET),
                    parse_mode=ParseMode.MARKDOWN
                )
            elif message.media == MessageMediaType.VIDEO:
                sent_msg = await client.send_video(
                    Config.TARGET_CHAT,
                    message.video.file_id,
                    caption=modify_only_caption_links(message.caption, Config.OFFSET),
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                sent_msg = await client.send_document(
                    Config.TARGET_CHAT,
                    message.document.file_id,
                    caption=modify_only_caption_links(message.caption, Config.OFFSET),
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            sent_msg = await client.send_message(
                Config.TARGET_CHAT,
                modify_only_caption_links(message.text, Config.OFFSET),
                parse_mode=ParseMode.MARKDOWN
            )
        
        # डीबगिंग के लिए लॉग
        debug_info = (
            f"✅ Processed\n"
            f"Original ID: {message.id}\n"
            f"Original Link: {message.link}\n"
            f"Caption Links Modified: {Config.OFFSET}\n"
            f"New Message: {sent_msg.link}"
        )
        await client.send_message("me", debug_info)
        return True
        
    except Exception as e:
        error_msg = f"❌ Error in message {message.id}\nError: {str(e)}"
        await client.send_message("me", error_msg)
        return False

@app.on_message(filters.command(["addnumber", "lessnumber"]))
async def set_offset_cmd(client: Client, message: Message):
    try:
        amount = int(message.command[1])
        if message.command[0] == "addnumber":
            Config.OFFSET += amount
            action = "जोड़ा गया"
        else:
            Config.OFFSET -= amount
            action = "घटाया गया"
        
        await message.reply(f"✅ ऑफसेट {action}: {amount}\nनया ऑफसेट: {Config.OFFSET}")
    except:
        await message.reply("⚠️ उपयोग: /addnumber 2 या /lessnumber 3")

@app.on_message(filters.command("startbatch"))
async def start_batch(client: Client, message: Message):
    if Config.PROCESSING:
        return await message.reply("⚠️ पहले से प्रोसेस चल रहा है")
    
    Config.PROCESSING = True
    args = message.text.split()
    
    if len(args) > 1:
        try:
            Config.EXTRACT_LIMIT = min(int(args[1]), 200)
        except:
            pass
    
    await message.reply(
        f"🔹 बैच प्रोसेसिंग शुरू\n"
        f"📌 लिमिट: {Config.EXTRACT_LIMIT} मैसेज\n"
        f"🔢 ऑफसेट: {Config.OFFSET}\n\n"
        f"अब निम्न फॉर्मेट में मैसेज भेजें:\n"
        f"`टारगेट_चैनल @username\n"
        f"सोर्स_पोस्ट_लिंक https://t.me/...`"
    )

@app.on_message(filters.text & ~filters.command & filters.incoming)
async def handle_batch_input(client: Client, message: Message):
    if not Config.PROCESSING:
        return
    
    try:
        # टारगेट चैनल और सोर्स लिंक पार्स करें
        parts = message.text.split('\n')
        if len(parts) < 2:
            return await message.reply("⚠️ गलत फॉर्मेट! उदाहरण:\n@target_channel\nhttps://t.me/source/123")
        
        Config.TARGET_CHAT = parts[0].strip()
        source_link = parts[1].strip()
        
        # सोर्स लिंक से चैट और मैसेज ID निकालें
        match = re.search(r't\.me/(?:c/)?(\d+|\w+)/(\d+)', source_link)
        if not match:
            return await message.reply("❌ अमान्य टेलीग्राम लिंक")
        
        chat_id = match.group(1)
        start_id = int(match.group(2))
        
        # प्रोसेसिंग शुरू
        progress_msg = await message.reply("⏳ प्रोसेसिंग शुरू...")
        success = failed = 0
        
        for i in range(Config.EXTRACT_LIMIT):
            if not Config.PROCESSING:
                break
            
            try:
                current_id = start_id + i
                msg = await client.get_messages(chat_id, current_id)
                
                if msg and not msg.empty:
                    if await process_single_message(client, msg):
                        success += 1
                    else:
                        failed += 1
                
                # हर 5 मैसेज पर अपडेट
                if (success + failed) % 5 == 0:
                    await progress_msg.edit(
                        f"⏳ प्रोग्रेस: {success + failed}/{Config.EXTRACT_LIMIT}\n"
                        f"✅ सफल: {success}\n"
                        f"❌ फेल: {failed}"
                    )
                
                await asyncio.sleep(1)  # रेट लिमिटिंग
            
            except Exception as e:
                failed += 1
                continue
        
        # कंप्लीट रिपोर्ट
        await progress_msg.edit(
            f"🎉 प्रोसेसिंग पूरी!\n"
            f"• कुल मैसेज: {success + failed}\n"
            f"• सफल: {success}\n"
            f"• फेल: {failed}\n"
            f"• लागू ऑफसेट: {Config.OFFSET}"
        )
    
    finally:
        Config.PROCESSING = False
        Config.TARGET_CHAT = None

@app.on_message(filters.command("cancel"))
async def cancel_processing(client: Client, message: Message):
    Config.PROCESSING = False
    await message.reply("❌ प्रोसेसिंग रद्द की गई")

if __name__ == "__main__":
    print("⚡ बॉट स्टार्ट हुआ!")
    app.run()
