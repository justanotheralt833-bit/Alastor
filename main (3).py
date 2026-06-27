
import os
import discord
import threading
from flask import Flask
from discord import app_commands
from discord.ext import commands

# --- WEB SERVER FOR RENDER ---
# This keeps the free-tier Web Service alive
app = Flask('')

@app.route('/')
def home():
    return "Alastor is alive!"

def run_web():
    # Render provides a PORT environment variable
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- DISCORD BOT ---
TOKEN = os.getenv('DISCORD_TOKEN')
intents = discord.Intents.default()

class AlastorBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s) globally.")
        except Exception as e:
            print(f"Error syncing commands: {e}")

bot = AlastorBot()

@bot.tree.command(name="alastor", description="Sends the text you written.")
@app_commands.describe(text="The text you want the bot to send")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def alastor(interaction: discord.Interaction, text: str):
    """Sends the exact text provided."""
    await interaction.response.send_message(text)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')

if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_TOKEN environment variable not set.")
    else:
        # Start the web server in a separate thread
        threading.Thread(target=run_web).start()
        # Start the Discord bot
        bot.run(TOKEN)
