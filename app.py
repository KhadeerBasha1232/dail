from flask import Flask, send_file
from datetime import datetime
from PIL import Image
import os
import requests

# === CONFIGURATION ===
TELEGRAM_BOT_TOKEN = '8167126085:AAEMm0bXMM1WzPwh0gVgAK8hxtH94qTmFQo'
CHAT_ID = '8167126085'  # Replace with your actual chat/user ID

app = Flask(__name__)

@app.route('/')
def home():
    return 'This bot is made by and currently it is hosted and live for everyone'

@app.route("/resume-open")
def track_open():
    # Log the event
    timestamp = datetime.now()
    print(f"Resume opened at {timestamp}")

    # Send Telegram message
    message = f"📄 Resume was just opened!\n⏰ Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
    telegram_api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(telegram_api_url, data={
            'chat_id': CHAT_ID,
            'text': message
        })
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

    # Return transparent image
    img_path = "transparent.png"
    if not os.path.exists(img_path):
        Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(img_path)

    return send_file(img_path, mimetype="image/png")

if __name__ == '__main__':
    app.run(debug=True)
