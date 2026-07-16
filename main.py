import os
import discord
import threading
import asyncio
import sys
import json
from collections import deque
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, jsonify, Response, request
from discord import app_commands
from discord.ext import commands

# Force unbuffered output for Render logs
def log(message):
    print(message, flush=True)
    sys.stdout.flush()

# --- MESSAGE / COMMAND ACTIVITY STORE (for the dashboard) ---
# In-memory ring buffer. Newest entries are appended; the dashboard shows
# them newest-first. maxlen keeps memory bounded on long-running instances.
ACTIVITY = deque(maxlen=500)
ACTIVITY_LOCK = threading.Lock()

def record_activity(entry: dict):
    with ACTIVITY_LOCK:
        ACTIVITY.append(entry)

# --- WEB SERVER FOR RENDER ---
app = Flask("")

# --- DASHBOARD LOGIN ---
# Set DASHBOARD_USER and DASHBOARD_PASS in Render's Environment tab.
# If they're not set, the dashboard falls back to admin/admin (change this!).
DASHBOARD_USER = os.environ.get("DASHBOARD_USER", "admin")
DASHBOARD_PASS = os.environ.get("DASHBOARD_PASS", "admin")

def check_auth(username, password):
    return username == DASHBOARD_USER and password == DASHBOARD_PASS

def require_auth():
    return Response(
        "Login required.", 401,
        {"WWW-Authenticate": 'Basic realm="Bot Dashboard"'}
    )

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return require_auth()
        return f(*args, **kwargs)
    return wrapped

@app.route("/")
def home():
    return "Hazbin Bots are alive!"

@app.route("/api/activity")
@login_required
def api_activity():
    with ACTIVITY_LOCK:
        data = list(ACTIVITY)[::-1]  # newest first
    return jsonify(data)

@app.route("/dashboard")
@login_required
def dashboard():
    return Response(DASHBOARD_HTML, mimetype="text/html")

def run_web():
    port = int(os.environ.get("PORT", 10000))
    log(f"[DEBUG] Web server starting on port {port}...")
    app.run(host="0.0.0.0", port=port)

# --- DISCORD BOTS ---
intents = discord.Intents.default()
intents.message_content = True  # Required to read message text - must also be enabled
                                 # in the Discord Developer Portal for EACH bot app
                                 # (Bot tab -> Privileged Gateway Intents -> Message Content Intent)

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

            guild_name = interaction.guild.name if interaction.guild else "Direct Message"
            channel_name = str(interaction.channel) if interaction.channel else "unknown"

            record_activity({
                "type": "command",
                "bot_id": token_id,
                "bot_name": str(self.user),
                "bot_avatar": self.user.display_avatar.url if self.user else None,
                "author": str(interaction.user),
                "author_avatar": interaction.user.display_avatar.url,
                "guild": guild_name,
                "channel": channel_name,
                "content": f"/hazbin {text}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

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

    async def on_message(self, message: discord.Message):
        # Ignore the bot's own messages
        if message.author.id == self.user.id:
            return

        location = f"DM with {message.author}" if message.guild is None else \
            f"#{message.channel} in {message.guild.name}"

        content = message.content if message.content else "[no text content]"
        if message.attachments:
            content += f" [attachments: {', '.join(a.filename for a in message.attachments)}]"

        log(f"[MSG] Bot {self.token_id} | {location} | {message.author}: {content}")

        record_activity({
            "type": "message",
            "bot_id": self.token_id,
            "bot_name": str(self.user),
            "bot_avatar": self.user.display_avatar.url if self.user else None,
            "author": str(message.author),
            "author_avatar": message.author.display_avatar.url,
            "guild": message.guild.name if message.guild else "Direct Message",
            "channel": str(message.channel),
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Required so prefix commands (e.g. "!") still work
        await self.process_commands(message)

# --- DASHBOARD HTML (Discord-styled, auto-refreshing) ---
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Hazbin Bots - Activity Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {
    --bg: #313338;
    --bg-secondary: #2b2d31;
    --bg-tertiary: #1e1f22;
    --text-normal: #dbdee1;
    --text-muted: #949ba4;
    --text-bright: #f2f3f5;
    --brand: #5865f2;
    --command: #949cf2;
    --divider: #3f4147;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text-normal);
    font-family: "gg sans", "Whitney", "Helvetica Neue", Helvetica, Arial, sans-serif;
  }
  header {
    background: var(--bg-tertiary);
    padding: 14px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid var(--divider);
    position: sticky;
    top: 0;
    z-index: 10;
  }
  header h1 {
    font-size: 16px;
    color: var(--text-bright);
    margin: 0;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  header h1:before {
    content: "#";
    color: var(--text-muted);
    font-weight: 700;
  }
  #status {
    font-size: 12px;
    color: var(--text-muted);
  }
  #status .dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #23a55a;
    margin-right: 6px;
  }
  #feed {
    max-width: 820px;
    margin: 0 auto;
    padding: 16px 20px 60px;
  }
  .msg {
    display: flex;
    gap: 16px;
    padding: 8px 0;
    border-bottom: 1px solid transparent;
  }
  .msg:hover {
    background: rgba(4,4,5,0.07);
    border-radius: 6px;
  }
  .avatar {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    flex-shrink: 0;
    background: var(--bg-secondary);
    object-fit: cover;
  }
  .body { min-width: 0; flex: 1; }
  .line1 {
    display: flex;
    align-items: baseline;
    gap: 8px;
    flex-wrap: wrap;
  }
  .username {
    font-weight: 600;
    color: var(--text-bright);
    font-size: 15px;
  }
  .badge {
    font-size: 10px;
    text-transform: uppercase;
    background: var(--brand);
    color: white;
    padding: 1px 5px;
    border-radius: 3px;
    font-weight: 600;
  }
  .badge.command { background: var(--command); }
  .meta {
    font-size: 12px;
    color: var(--text-muted);
  }
  .content {
    font-size: 15px;
    color: var(--text-normal);
    word-wrap: break-word;
    white-space: pre-wrap;
    margin-top: 2px;
  }
  .via {
    font-size: 12px;
    color: var(--text-muted);
    margin-top: 2px;
  }
  .via img {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    vertical-align: -2px;
    margin-right: 4px;
  }
  #empty {
    color: var(--text-muted);
    text-align: center;
    margin-top: 60px;
    font-size: 14px;
  }
</style>
</head>
<body>
  <header>
    <h1>bot-activity</h1>
    <div id="status"><span class="dot"></span>live</div>
  </header>
  <div id="feed"><div id="empty">Waiting for activity...</div></div>

<script>
function escapeHtml(str) {
  const d = document.createElement("div");
  d.innerText = str == null ? "" : str;
  return d.innerHTML;
}

function formatTime(iso) {
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

async function refresh() {
  try {
    const res = await fetch("/api/activity");
    const items = await res.json();
    const feed = document.getElementById("feed");

    if (!items.length) {
      feed.innerHTML = '<div id="empty">Waiting for activity...</div>';
      return;
    }

    feed.innerHTML = items.map(item => {
      const badge = item.type === "command"
        ? '<span class="badge command">command</span>'
        : '<span class="badge">message</span>';
      const avatar = item.author_avatar || "https://cdn.discordapp.com/embed/avatars/0.png";
      const botAvatar = item.bot_avatar || "https://cdn.discordapp.com/embed/avatars/0.png";
      return `
        <div class="msg">
          <img class="avatar" src="${avatar}" alt="">
          <div class="body">
            <div class="line1">
              <span class="username">${escapeHtml(item.author)}</span>
              ${badge}
              <span class="meta">${escapeHtml(item.guild)} · #${escapeHtml(item.channel)} · ${formatTime(item.timestamp)}</span>
            </div>
            <div class="content">${escapeHtml(item.content)}</div>
            <div class="via"><img src="${botAvatar}" alt="">via ${escapeHtml(item.bot_name)} (bot ${item.bot_id})</div>
          </div>
        </div>
      `;
    }).join("");
  } catch (e) {
    console.error("Failed to refresh activity:", e);
  }
}

refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>
"""

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
