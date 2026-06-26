
import os
import discord
from discord import app_commands
from discord.ext import commands

# Retrieve bot token from environment variables
TOKEN = os.getenv('DISCORD_TOKEN')

# Define bot intents
intents = discord.Intents.default()
# intents.message_content = True # Not strictly required for slash commands

class AlastorBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # This is where you'd register your commands
        # For user-installable apps, we use global commands
        await self.tree.sync()
        print(f"Synced slash commands for {self.user}")

bot = AlastorBot()

# Define the command with context support
# contexts=[0, 1, 2] means:
# 0: Guild (Servers)
# 1: Bot DM
# 2: Private Channels (DMs/Group DMs)
@bot.tree.command(
    name="alastor_msg", 
    description="Sends the text you written.",
    contexts={discord.InteractionContextType.guild, discord.InteractionContextType.bot_dm, discord.InteractionContextType.private_channel},
    integration_types={discord.IntegrationType.user_install, discord.IntegrationType.guild_install}
)
@app_commands.describe(text="The text you want the bot to send")
async def alastor_msg(interaction: discord.Interaction, text: str):
    """Echoes the text you provide in any chat."""
    # Using simple send_message. For user apps, this works in the context where used.
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
