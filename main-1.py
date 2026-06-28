
import os
import discord
import threading
import asyncio
from flask import Flask
from discord import app_commands
from discord.ext import commands

# --- WEB SERVER FOR RENDER ---
# This keeps the free-tier Web Service alive
app = Flask("")

@app.route("/")
def home():
    return "Hazbin Bots are alive!"

def run_web():
    # Render provides a PORT environment variable
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- DISCORD BOTS ---
intents = discord.Intents.default()

class HazbinBot(commands.Bot):
    def __init__(self, token_id):
        super().__init__(command_prefix="!", intents=intents)
        self.token_id = token_id

    async def setup_hook(self):
        # The command is registered HERE, inside setup_hook, instead of as a
        # class method. `self` is a normal Bot subclass (not a Cog), so a
        # method decorated with @app_commands.command() never gets `self`
        # bound by discord.py — every call to /hazbin would fail with
        # CommandSignatureMismatch. Defining it as a closure fixes that,
        # since it captures `self`/the bot instance naturally and each bot
        # instance gets its own independent Command object.
        @self.tree.command(name="hazbin", description="Sends the text you written.")
        @app_commands.describe(text="The text you want the bot to send")
        @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
        @app_commands.allowed_installs(guilds=True, users=True)
        async def hazbin(interaction: discord.Interaction, text: str):
            """Sends the exact text provided."""
            await interaction.response.send_message(text)

        try:
            synced = await self.tree.sync()
            print(f"Bot {self.token_id}: Synced {len(synced)} command(s) globally.")
        except Exception as e:
            print(f"Bot {self.token_id}: Error syncing commands: {e}")

    async def on_ready(self):
        print(f"Bot {self.token_id}: Logged in as {self.user} (ID: {self.user.id})")
        print("------")

async def main():
    # Start the web server in a separate thread
    web_thread = threading.Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()

    bot_tasks = []
    # This will check for TOKEN_1, TOKEN_2, ..., TOKEN_30
    for i in range(1, 31):
        token_env_var = f"TOKEN_{i}"
        token = os.getenv(token_env_var)
        if token:
            # We create a new bot instance for each token.
            # The /hazbin command is added inside setup_hook(), so nothing
            # extra needs to happen here.
            bot = HazbinBot(token_id=i)
            bot_tasks.append(bot.start(token))

    if not bot_tasks:
        print("No bot tokens found. Please set TOKEN_1, TOKEN_2, etc. in Render.")
        return

    # Run all bots at the same time
    await asyncio.gather(*bot_tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
