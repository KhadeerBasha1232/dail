import asyncio
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from datetime import datetime
import os
import random

# Telegram API credentials (get from https://my.telegram.org)
api_id = 20404457  # 🔁 Replace with your API ID
api_hash = 'f95437b50eec8ad9719b8a9470258d60'  # 🔁 Replace with your API Hash
session_name = 'my_session'  # Will create/use 'my_session.session'

# List of group usernames or chat IDs
groups = ['@allcodingsolution_ltd', '@projects_helping']  # 🔁 Replace with your groups
messages = [
    (
        "🌟 *DON’T MISS OUT! YOUR DREAM WEBSITE IS HERE!* 🚀\n\n"
        "💻 *Stunning Websites & Web Apps – FAST & AFFORDABLE!* 💰\n"
        "Turn your vision into a 🔥 *digital masterpiece* without draining your wallet!\n\n"
        "🎯 *Perfect For:*\n"
        "✅ Sleek Portfolios\n"
        "✅ College Projects\n"
        "✅ Business Websites\n"
        "✅ Dynamic Dashboards\n"
        "✅ E-commerce Stores\n"
        "✅ Custom Web Tools\n\n"
        "🔥 *Why Choose Us?*\n"
        "✨ *Premium Designs* delivered at ⚡ lightning speed\n"
        "✨ Built with *React, Django, MERN, Flask* – your choice!\n"
        "✨ *Mobile-ready*, *SEO-optimized*, and super fast 📱\n"
        "✨ *Budget-friendly* with 24/7 support 🚀\n\n"
        "⏳ *LIMITED SLOTS LEFT THIS MONTH!*\n"
        "👉 **[Join Now!](https://t.me/projects_helping)**\n"
        "💬 DM for a *FREE Quote* – Let’s talk today! 💡\n\n"
        "🌐 *Build your dream site the SMART way!*"
    ),
    (
        "🔥 *YOUR VISION, OUR CODE – AFFORDABLE WEBSITES!* 🚀\n\n"
        "💻 *Need a Website or App FAST?* We’ve got you! 💰\n"
        "Bring your ideas to life with 🔥 *stunning designs* at budget prices!\n\n"
        "🎯 *Ideal For:*\n"
        "✅ Portfolios\n"
        "✅ College Projects\n"
        "✅ Business Sites\n"
        "✅ Dashboards\n"
        "✅ Online Stores\n"
        "✅ Custom Tools\n\n"
        "🔥 *Why Us?*\n"
        "✨ *Top-tier Designs* with ⚡ fast delivery\n"
        "✨ *React, Django, MERN, Flask* – we do it all!\n"
        "✨ *Mobile-friendly* & *SEO-ready* 📱\n"
        "✨ *Affordable* with stellar support 🚀\n\n"
        "⏳ *HURRY – SLOTS ARE LIMITED!*\n"
        "👉 **[Join Now!](https://t.me/projects_helping)**\n"
        "💬 DM for a *FREE Quote* today! 💡\n\n"
        "🌐 *Your dream site starts here!*"
    ),
    (
        "💥 *ELEVATE YOUR ONLINE PRESENCE TODAY!* 🌟\n\n"
        "🌐 *Want a Website or App That Wows?* Affordable & Fast! 💸\n"
        "We craft 🔥 *stunning digital solutions* tailored to your needs!\n\n"
        "🎯 *Great For:*\n"
        "✅ Professional Portfolios\n"
        "✅ College Projects\n"
        "✅ Business Websites\n"
        "✅ Admin Dashboards\n"
        "✅ E-commerce Platforms\n"
        "✅ Custom Web Apps\n\n"
        "🚀 *Why Work With Us?*\n"
        "✨ *Sleek Designs* delivered ⚡ super fast\n"
        "✨ Powered by *React, Django, MERN, Flask*\n"
        "✨ *Mobile-optimized* & *SEO-friendly* 📱\n"
        "✨ *Wallet-friendly* with top-notch support 💪\n\n"
        "⏰ *SLOTS FILLING FAST!*\n"
        "👉 **[Join Our Group!](https://t.me/projects_helping)**\n"
        "💬 DM for a *FREE Quote* now! 💡\n\n"
        "🔥 *Let’s make your vision shine online!*"
    ),
    (
        "🚀 *BUILD YOUR DREAM WEBSITE TODAY!* 🌟\n\n"
        "💻 *Need a Fast, Affordable Website or App?* Look no further! 💰\n"
        "We turn your ideas into 🔥 *eye-catching digital solutions*! \n\n"
        "🎯 *Best For:*\n"
        "✅ Portfolios that pop\n"
        "✅ College Projects\n"
        "✅ Business Websites\n"
        "✅ Dashboards & Tools\n"
        "✅ Online Stores\n"
        "✅ Custom Apps\n\n"
        "🔥 *What Sets Us Apart?*\n"
        "✨ *Premium Designs* at ⚡ warp speed\n"
        "✨ *React, Django, MERN, Flask* – we’ve got the tech!\n"
        "✨ *Mobile-ready* & *SEO-optimized* 📱\n"
        "✨ *Affordable* with 24/7 support 🚀\n\n"
        "⏳ *GRAB YOUR SLOT BEFORE IT’S GONE!*\n"
        "👉 **[Join Now!](https://t.me/projects_helping)**\n"
        "💬 DM for a *FREE Quote* – Let’s start! 💡\n\n"
        "🌐 *Your dream site is just a click away!*"
    ),
    (
        "🌟 *UNLOCK YOUR PERFECT WEBSITE NOW!* 🚀\n\n"
        "💻 *Want a Website or App That Stands Out?* Fast & Budget-Friendly! 💸\n"
        "We bring your ideas to life with 🔥 *stunning designs*! \n\n"
        "🎯 *Perfect For:*\n"
        "✅ Standout Portfolios\n"
        "✅ College Projects\n"
        "✅ Business Websites\n"
        "✅ Dynamic Dashboards\n"
        "✅ E-commerce Stores\n"
        "✅ Custom Tools\n\n"
        "🔥 *Why We’re the Best Choice:*\n"
        "✨ *High-Quality Designs* delivered ⚡ lightning fast\n"
        "✨ Built with *React, Django, MERN, Flask* – your pick!\n"
        "✨ *Mobile-friendly* & *SEO-ready* 📱\n"
        "✨ *Affordable* with unbeatable support 🚀\n\n"
        "⏰ *LIMITED SPOTS AVAILABLE!*\n"
        "👉 **[Join Our Group!](https://t.me/projects_helping)**\n"
        "💬 DM for a *FREE Quote* today! 💡\n\n"
        "🌐 *Let’s create your online masterpiece!*"
    )
]

# Delay configs
delay_between_groups = 300     # 5 minutes between messages to each group
delay_between_cycles = 7200   # 2 hours between cycles

client = TelegramClient(session_name, api_id, api_hash)

async def send_scheduled_messages():
    while True:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Sending messages...")
        for group in groups:
            try:
                message = random.choice(messages)  # Randomly select a message variation
                await client.send_message(
                    group,
                    message,
                    parse_mode='Markdown'
                )
                print(f"✅ Sent message to {group}")
            except FloodWaitError as e:
                print(f"❌ Flood wait for {group}: Waiting {e.seconds} seconds")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                print(f"❌ Error sending to {group}: {e}")
            await asyncio.sleep(delay_between_groups + random.uniform(5, 15))  # Random delay 305–315s
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Cycle complete. Sleeping for 2 hours...\n")
        await asyncio.sleep(delay_between_cycles)

async def main():
    await client.start()
    await send_scheduled_messages()

if __name__ == '__main__':
    asyncio.run(main())