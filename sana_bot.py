from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.constants import ParseMode
from dotenv import load_dotenv

import httpx
import os
import html
import base64
from io import BytesIO
import traceback
import logging

# -------------------- Logging Setup --------------------
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Show in CMD
        logging.FileHandler("bot.log", encoding='utf-8')  # Save to file
    ]
)

# -------------------- Environment --------------------
load_dotenv()

GROQ_API_KEY = "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"
STABILITY_API_KEY = "sk-PPJXRdVWdkjAsHR7bXabfxhWj3RjaLLqk3bT0qVqN7XksUp6"
GROQ_MODEL = "llama3-8b-8192"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
STABILITY_API_URL = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image"
TELEGRAM_BOT_TOKEN = "8182317181:AAE9Mt0e74T7vbka6shIQawjlxAeKUVnxGQ"

HEADERS = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json"
}

# -------------------- Format Messages --------------------
def format_html_reply(text: str) -> str:
    parts = text.split("```")
    formatted = ""
    for i, part in enumerate(parts):
        if i % 2 == 0:
            cleaned = part.replace("**", "")
            escaped = html.escape(cleaned)
            bolded = f"<b>{escaped}</b>"
            formatted += bolded
        else:
            formatted += f"<pre>{html.escape(part)}</pre>"
    return formatted

# -------------------- Handlers --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"/start by {update.effective_user.id}")
    await update.message.reply_text(
        "<b>Hey!</b> I'm your Groq-powered AI 🤖\n"
        "Ask me <i>anything</i> — from code to coffee! ☕\n\n"
        "Use <code>/explain_code &lt;your code&gt;</code> to get a breakdown 🧑‍🏫",
        parse_mode=ParseMode.HTML
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    logging.info(f"[Chat] {update.effective_user.username}: {user_message}")

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": (
                "You are a helpful AI assistant. You MUST always use emojis in every reply, including technical responses. "
                "Respond using <b>bold text</b> for emphasis, <pre> blocks for code, and make your tone friendly and fun."
            )},
            {"role": "user", "content": user_message}
        ]
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(GROQ_API_URL, headers=HEADERS, json=payload)
            data = response.json()

        if "choices" in data:
            raw_reply = data["choices"][0]["message"]["content"]
            formatted_reply = format_html_reply(raw_reply)
            await update.message.reply_text(formatted_reply, parse_mode=ParseMode.HTML)
        else:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            logging.warning(f"Groq error: {error_msg}")
            await update.message.reply_text(f"⚠️ Error: {error_msg}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error("Error in handle_message", exc_info=True)

async def explain_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    code_to_explain = user_message.replace("/explain_code", "").strip()

    logging.info(f"/explain_code by {update.effective_user.id}")

    if not code_to_explain:
        await update.message.reply_text(
            "🧠 <b>Please provide some code to explain!</b>",
            parse_mode=ParseMode.HTML
        )
        return

    prompt = f"Explain the following code:\n\n{code_to_explain}"

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": (
                "You're a senior developer who explains code clearly and simply. "
                "Use markdown (triple backticks) and emojis for clarity."
            )},
            {"role": "user", "content": prompt}
        ]
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(GROQ_API_URL, headers=HEADERS, json=payload)
            data = response.json()

        if "choices" in data:
            explanation = data["choices"][0]["message"]["content"]
            formatted_reply = format_html_reply(explanation)
            await update.message.reply_text(
                f"🔍 <b>Code Explanation:</b>\n\n{formatted_reply}",
                parse_mode=ParseMode.HTML
            )
        else:
            error_message = data.get("error", {}).get("message", "Unknown error")
            logging.warning(f"Explain error: {error_message}")
            await update.message.reply_text(
                f"Something went wrong 🛠<br>Error: {error_message}",
                parse_mode=ParseMode.HTML
            )
    except Exception:
        logging.error("Error in explain_code", exc_info=True)

async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text.replace("/generate_image", "").strip()

    logging.info(f"/generate_image by {update.effective_user.id}: {prompt}")

    if not prompt:
        await update.message.reply_text("🎨 Please provide a prompt to generate an image!")
        return

    await update.message.reply_text("🎨 Generating your image... Please wait.")

    headers = {
        "Authorization": f"Bearer {STABILITY_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    payload = {
        "text_prompts": [{"text": prompt}],
        "cfg_scale": 7,
        "clip_guidance_preset": "FAST_BLUE",
        "height": 1024,
        "width": 1024,
        "samples": 1,
        "steps": 30
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(STABILITY_API_URL, headers=headers, json=payload)

        if response.status_code == 200:
            result = response.json()
            image_base64 = result["artifacts"][0]["base64"]
            image_data = base64.b64decode(image_base64)

            image_file = BytesIO(image_data)
            image_file.name = "generated.png"

            await update.message.reply_photo(photo=image_file, caption=f"🖼️ Prompt: {prompt}")
        else:
            logging.error(f"Image gen failed: {response.status_code} {response.text}")
            await update.message.reply_text(
                f"❌ Failed to generate image.\nStatus: {response.status_code}\n{response.text}"
            )

    except Exception:
        error_details = traceback.format_exc()
        logging.error("Image generation exception", exc_info=True)
        await update.message.reply_text(
            f"❌ <b>Error during image generation:</b>\n<pre>{html.escape(error_details)}</pre>",
            parse_mode=ParseMode.HTML
        )

# -------------------- App Init --------------------
def main():
    logging.info("Bot starting up...")

    if not TELEGRAM_BOT_TOKEN:
        logging.critical("TELEGRAM_BOT_TOKEN is missing. Check your .env file.")
        return

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("explain_code", explain_code))
    app.add_handler(CommandHandler("generate_image", generate_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Bot is now running. Waiting for messages...")

    app.run_polling()

if __name__ == "__main__":
    main()
