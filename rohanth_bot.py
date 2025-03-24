import telebot
import requests
import os
import google.generativeai as genai
from dotenv import load_dotenv
import re
import time

# Load environment variables
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
HF_API_KEY = os.getenv('HF_API_KEY')

if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY or not HF_API_KEY:
    raise ValueError('🚨 Telegram Bot Token, Gemini API Key, and Hugging Face API Key are required.')

# Initialize Gemini and Telegram Bot
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(model_name='gemini-1.5-flash')
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
print('🤖 Telegram bot is running...')

# Store last message timestamps to prevent spam
user_last_message = {}

# Function to format text for MarkdownV2
def format_text(text):
    return re.sub(r'([_*[\]()~`>#+\-=|{}.!])', r'\\\1', text)  # Escape special characters

# Function to split long messages into chunks
def split_text_into_chunks(text, max_length=4096):
    words = text.split(' ')
    chunks = []
    current_chunk = ''

    for word in words:
        if len(current_chunk) + len(word) + 1 <= max_length:
            current_chunk += (' ' if current_chunk else '') + word
        else:
            chunks.append(current_chunk.strip())
            current_chunk = word

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks

# Function to generate an image using Hugging Face API
def generate_image(prompt):
    print(f'🎨 Generating image: {prompt}')
    try:
        response = requests.post(
            "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0",
            headers={"Authorization": f"Bearer {HF_API_KEY}", "Content-Type": "application/json"},
            json={
                "inputs": prompt,
                "parameters": {
                    "num_inference_steps": 30,
                    "guidance_scale": 7.5,
                    "negative_prompt": "blurry, bad quality, distorted, deformed"
                }
            },
            timeout=60
        )

        if response.status_code == 200:
            return response.content
        else:
            print(f'❌ Error: {response.json()}')
            return None
    except requests.RequestException as e:
        print(f'❌ Request error: {e}')
        return None

# Function to get response from Gemini API
def get_gemini_response(prompt):
    try:
        response = model.generate_content(prompt)
        return format_text(response.text if response and response.text else "⚠️ No response generated.")
    except Exception as error:
        print(f'❌ Error with Gemini API: {error}')
        return format_text("⚠️ Error: I couldn't process your request at the moment.")

# Cooldown function to prevent spam
def is_spamming(user_id, cooldown=5):
    current_time = time.time()
    if user_id in user_last_message and current_time - user_last_message[user_id] < cooldown:
        return True
    user_last_message[user_id] = current_time
    return False

# Handle /start command
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = format_text(
        "👋 Hello! I'm your AI assistant.\n\n"
        "🤖 *Commands Available:*\n"
        "🔹 `/ask [your question]` - Ask me anything\n"
        "🔹 `/imagine [description]` - Generate an image\n\n"
        "*Examples:*\n"
        "👉 `/ask What is artificial intelligence?`\n"
        "👉 `/imagine sunset over a mountain lake`"
    )
    bot.reply_to(message, welcome_text, parse_mode='MarkdownV2')

# Handle /imagine command
@bot.message_handler(commands=['imagine'])
def handle_imagine(message):
    chat_id = message.chat.id
    image_prompt = message.text[9:].strip()

    if not image_prompt or '@' in image_prompt:
        bot.reply_to(message, format_text('⚠️ Please provide a valid description.\nExample: `/imagine sunset over mountains`'), parse_mode='MarkdownV2')
        return

    if is_spamming(chat_id):
        bot.reply_to(message, format_text("⚠️ Please wait a few seconds before requesting again."), parse_mode='MarkdownV2')
        return

    generating_message = bot.reply_to(message, '🎨 Generating your image...')
    bot.send_chat_action(chat_id, 'upload_photo')

    try:
        image_buffer = generate_image(image_prompt)
        if image_buffer:
            bot.send_photo(chat_id, image_buffer, caption=format_text(f'🖼️ Generated image for: "{image_prompt}"'), reply_to_message_id=message.message_id)
        else:
            bot.reply_to(message, format_text('⚠️ The image generation service is temporarily unavailable. Try again later.'), parse_mode='MarkdownV2')
    except Exception as e:
        bot.reply_to(message, format_text(f'⚠️ Failed to generate image: {str(e)}'), parse_mode='MarkdownV2')

    bot.delete_message(chat_id, generating_message.message_id)

# Handle /ask command
@bot.message_handler(commands=['ask'])
def handle_ask(message):
    chat_id = message.chat.id
    question = message.text[5:].strip()
    
    # Remove bot username (@botname) if present
    question = re.sub(r'@\w+', '', question).strip().lower()

    # Check if the user is asking about the owner
    owner_keywords = ['who is your owner', 'who created you', 'who made you', 'your creator', 'your owner']
    if any(keyword in question for keyword in owner_keywords):
        bot.reply_to(message, format_text("👨‍💻 I was created by *BAIPILLA SWAMY ESHWAR ROHANTH*."), parse_mode='MarkdownV2')
        return

    if not question:
        bot.reply_to(message, format_text('⚠️ Please provide a valid question.'), parse_mode='MarkdownV2')
        return

    if is_spamming(chat_id):
        bot.reply_to(message, format_text("⚠️ Please wait a few seconds before asking again."), parse_mode='MarkdownV2')
        return

    try:
        processing_message = bot.reply_to(message, '🤖 Thinking...')
        bot.send_chat_action(chat_id, 'typing')

        response = get_gemini_response(question)
        if not response:
            bot.reply_to(message, format_text("⚠️ No response generated. Please try again."), parse_mode='MarkdownV2')
            return

        for chunk in split_text_into_chunks(response, 2800):
            bot.send_message(chat_id, chunk, parse_mode='MarkdownV2')

    except telebot.apihelper.ApiException as e:
        print(f'⚠️ Telegram API Error: {e}')
        bot.reply_to(message, format_text("⚠️ An error occurred while sending the message."), parse_mode='MarkdownV2')

    except Exception as e:
        bot.reply_to(message, format_text(f'⚠️ Error: {str(e)}'), parse_mode='MarkdownV2')

    finally:
        try:
            bot.delete_message(chat_id, processing_message.message_id)
        except Exception:
            pass

# Run the bot
if __name__ == '__main__':
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
