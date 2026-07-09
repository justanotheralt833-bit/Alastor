
import os
import discord
import threading
import asyncio
import sys
from flask import Flask
from discord import app_commands
from discord.ext import commands

# Force unbuffered output for Render logs
def log(message):
    print(message, flush=True)
    sys.stdout.flush()

# --- WEB SERVER FOR RENDER ---
app = Flask("")

@app.route("/")
def home():
    return "Hazbin Bots are alive!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    log(f"[DEBUG] Web server starting on port {port}...")
    app.run(host="0.0.0.0", port=port)

# --- DISCORD BOTS ---
intents = discord.Intents.default()

class HazbinBot(commands.Bot):
    def __init__(self, token_id):
        super().__init__(command_prefix="!", intents=intents)
        self.token_id = token_id

    async def setup_hook(self):
        token_id = self.token_id

        @app_commands.command(name="hazbin", description="Sends the text you written.")
        @app_commands.describe(text="The text you want the bot to send")
        @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
        @app_commands.allowed_installs(guilds=True, users=True)
        async def hazbin(interaction: discord.Interaction, text: str):
            log(f"[COMMAND] Bot {token_id} received /hazbin: {text}")
            try:
                await interaction.response.send_message(text)
            except Exception as e:
                log(f"[ERROR] Bot {token_id} failed to reply: {e}")

        self.tree.add_command(hazbin)

        try:
            synced = await self.tree.sync()
            log(f"Bot {self.token_id}: Synced {len(synced)} command(s) globally.")
        except Exception as e:
            log(f"Bot {self.token_id}: Error syncing commands: {e}")

    async def on_ready(self):
        log(f"Bot {self.token_id}: Logged in as {self.user} (ID: {self.user.id})")
        log("------")

async def main():
    log("[DEBUG] Starting Hazbin Multi-Bot script with staggered startup...")
    
    # Start the web server immediately so Render is happy
    web_thread = threading.Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()

    bot_tasks = []
    log("[DEBUG] Searching for tokens (TOKEN_1 to TOKEN_30)...")

    for i in range(1, 31):
        token_key = f"TOKEN_{i}"
        token = os.getenv(token_key)
        if token:
            log(f"[DEBUG] Found {token_key}. Initializing bot...")
            bot = HazbinBot(token_id=i)

            # Start the bot task
            task = asyncio.create_task(bot.start(token))
            bot_tasks.append(task)
            
            # STAGGERED START: Wait 10 seconds before starting the next bot
            # This prevents Discord/Cloudflare from banning the IP for spamming logins
            log(f"[DEBUG] Bot {i} starting... waiting 10 seconds before next bot.")
            await asyncio.sleep(10)

    if not bot_tasks:
        log("[ERROR] NO TOKENS FOUND! Please add TOKEN_1, TOKEN_2, etc. in Render's Environment tab.")
        while True:
            await asyncio.sleep(3600)

    log(f"[DEBUG] All {len(bot_tasks)} bots are now attempting to connect.")
    
    # Keep the main loop running
    await asyncio.gather(*bot_tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log(f"[CRITICAL ERROR] {e}")
