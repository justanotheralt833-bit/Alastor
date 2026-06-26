
import os
import discord
from discord.ext import commands

# Retrieve bot token from environment variables
TOKEN = os.getenv('DISCORD_TOKEN')

# Define bot intents
intents = discord.Intents.default()
intents.message_content = True  # Required to read message content

# Initialize the bot with a command prefix (not strictly needed for slash commands, but good practice)
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    # Register slash commands globally when the bot is ready
    await bot.tree.sync()

@bot.tree.command(name="alastor_msg", description="Echoes the text you provide.")
async def alastor_msg(interaction: discord.Interaction, text: str):
    """Echoes the text you provide."""
    await interaction.response.send_message(f"You said: {text}")

if __name__ == "__main__":
    if TOKEN is None:
        print("Error: DISCORD_TOKEN environment variable not set.")
    else:
        bot.run(TOKEN)
