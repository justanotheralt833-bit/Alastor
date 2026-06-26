
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
        # Syncing global commands
        await self.tree.sync()
        print(f"Synced slash commands for {self.user}")

bot = AlastorBot()

# We use the decorator-style for best compatibility
@bot.tree.command(name="alastor", description="Sends the text you written.")
@app_commands.describe(text="The text you want the bot to send")
# Use the integer values for contexts and integration types for maximum compatibility
# Contexts: 0=Guild, 1=BotDM, 2=PrivateChannel
# Integration Types: 0=Guild, 1=User
@app_commands.allowed_contexts(guild=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guild=True, user=True)
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
