import telebot
import requests
import os
import google.generativeai as genai
from dotenv import load_dotenv
import re

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

# Function to format text for MarkdownV2
def format_text(text):
    special_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(r'([{}])'.format(re.escape(special_chars)), r'\\\1', text)

# Function to split long messages into chunks (max 4096 chars)
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
    )

    if response.status_code == 200:
        return response.content
    elif response.status_code == 503:
        return None  # Model might be loading
    else:
        print(f'❌ Error: {response.json()}')
        return None

# Function to get response from Gemini API
def get_gemini_response(prompt):
    try:
        response = model.generate_content(prompt)
        return format_text(response.text if response and response.text else "⚠️ No response generated.")
    except Exception as error:
        print(f'❌ Error with Gemini API: {error}')
        return format_text("⚠️ Error: I couldn't process your request at the moment.")

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

    if not image_prompt:
        bot.reply_to(message, format_text('⚠️ Please provide a description for the image.\nExample: `/imagine sunset over mountains`'), parse_mode='MarkdownV2')
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

    if not question:
        bot.reply_to(message, format_text('⚠️ Please provide a question.\nExample: `/ask What is artificial intelligence?`'), parse_mode='MarkdownV2')
        return

    processing_message = bot.reply_to(message, '🤖 Processing your question...')
    bot.send_chat_action(chat_id, 'typing')
    response = get_gemini_response(question)

    chunks = split_text_into_chunks(response, 3000)
    for chunk in chunks:
        bot.send_message(chat_id, chunk, parse_mode='MarkdownV2', disable_web_page_preview=True)

    bot.delete_message(chat_id, processing_message.message_id)

# Handle all other messages
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    user_message = message.text.lower().strip()

    # Handle questions about bot creator
    owner_keywords = ['who is your owner', 'who created you', 'who made you', 'your creator', 'your owner']
    if any(keyword in user_message for keyword in owner_keywords):
        bot.reply_to(message, format_text("👨‍💻 I was created by *BAIPILLA SWAMY ESHWAR ROHANTH*."), parse_mode='MarkdownV2')
        return

    # Remind users to use commands
    bot.reply_to(
        message,
        format_text(
            "⚠️ Please use commands to interact with me:\n"
            "🔹 `/ask [your question]` - For text responses\n"
            "🔹 `/imagine [description]` - For image generation"
        ),
        parse_mode='MarkdownV2'
    )

# Run the bot
if __name__ == '__main__':
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
