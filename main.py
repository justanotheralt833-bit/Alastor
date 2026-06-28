class HazbinBot(commands.Bot):
    def __init__(self, token_id):
        super().__init__(
            command_prefix="!",
            intents=intents
        )
        self.token_id = token_id

    async def setup_hook(self):
        # Register the slash command
        self.tree.add_command(self.hazbin)

        try:
            synced = await self.tree.sync()
            log(f"Bot {self.token_id}: Synced {len(synced)} command(s) globally.")
        except Exception as e:
            log(f"Bot {self.token_id}: Error syncing commands: {e}")

    @app_commands.command(
        name="hazbin",
        description="Sends the text you wrote."
    )
    @app_commands.describe(text="The text to send")
    async def hazbin(self, interaction: discord.Interaction, text: str):
        log(f"[COMMAND] Bot {self.token_id} executing /hazbin: {text}")

        await interaction.response.send_message(text)

        log(f"[SUCCESS] Bot {self.token_id} replied.")

    async def on_ready(self):
        log(f"Bot {self.token_id}: Logged in as {self.user} (ID: {self.user.id})")
        log("------")
