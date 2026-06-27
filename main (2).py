
import os
import discord
from discord import app_commands
from discord.ext import commands

# Retrieve bot token from environment variables
TOKEN = os.getenv('DISCORD_TOKEN')

# Define bot intents
intents = discord.Intents.default()

class AlastorBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # This clears and re-syncs all global commands
        # This is the most reliable way to make sure Discord sees the /alastor command
        synced = await self.tree.sync()
        print(f"Synced {len(synced)} command(s) globally.")

bot = AlastorBot()

# We define the command directly in the tree to ensure context and integration settings apply
@bot.tree.command(
    name="alastor", 
    description="Sends the text you written.",
)
@app_commands.describe(text="The text you want the bot to send")
# Fixed keyword arguments for discord.py v2.4+
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def alastor(interaction: discord.Interaction, text: str):
    """Sends the exact text provided."""
    # This will send ONLY the text provided by the user
    await interaction.response.send_message(text)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')

if __name__ == "__main__":
    if TOKEN is None:
        print("Error: DISCORD_TOKEN environment variable not set.")
    else:
        bot.run(TOKEN)
