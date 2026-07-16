import os
import discord
import threading
import asyncio
import sys
import json
import uuid
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
    entry["id"] = uuid.uuid4().hex
    with ACTIVITY_LOCK:
        ACTIVITY.append(entry)
    return entry["id"]

# --- WHITELIST (off by default) ---
# When enabled, only whitelisted guild IDs / user IDs (for DMs) can use the
# bots. Everything else is silently ignored (and logged as "blocked" for
# visibility in the dashboard). Managed live from the dashboard - nothing
# to configure in Render env vars.
WHITELIST_LOCK = threading.Lock()
WHITELIST_STATE = {
    "enabled": False,
    "guilds": set(),   # server IDs (as strings)
    "users": set(),     # user IDs (as strings), used for DMs
}

def is_whitelisted(guild_id, user_id):
    with WHITELIST_LOCK:
        if not WHITELIST_STATE["enabled"]:
            return True
        if guild_id is not None:
            return str(guild_id) in WHITELIST_STATE["guilds"]
        return str(user_id) in WHITELIST_STATE["users"]

def whitelist_snapshot():
    with WHITELIST_LOCK:
        return {
            "enabled": WHITELIST_STATE["enabled"],
            "guilds": sorted(WHITELIST_STATE["guilds"]),
            "users": sorted(WHITELIST_STATE["users"]),
        }

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

@app.route("/api/activity/<entry_id>", methods=["DELETE"])
@login_required
def api_activity_delete(entry_id):
    with ACTIVITY_LOCK:
        before = len(ACTIVITY)
        kept = [e for e in ACTIVITY if e.get("id") != entry_id]
        ACTIVITY.clear()
        ACTIVITY.extend(kept)
        removed = before != len(ACTIVITY)
    return jsonify({"removed": removed})

@app.route("/api/activity/clear", methods=["POST"])
@login_required
def api_activity_clear():
    with ACTIVITY_LOCK:
        ACTIVITY.clear()
    return jsonify({"ok": True})

@app.route("/api/whitelist")
@login_required
def api_whitelist_get():
    return jsonify(whitelist_snapshot())

@app.route("/api/whitelist/toggle", methods=["POST"])
@login_required
def api_whitelist_toggle():
    with WHITELIST_LOCK:
        WHITELIST_STATE["enabled"] = not WHITELIST_STATE["enabled"]
        state = WHITELIST_STATE["enabled"]
    log(f"[ADMIN] Whitelist {'ENABLED' if state else 'DISABLED'} from dashboard.")
    return jsonify(whitelist_snapshot())

@app.route("/api/whitelist/add", methods=["POST"])
@login_required
def api_whitelist_add():
    data = request.get_json(force=True, silent=True) or {}
    kind = data.get("kind")  # "guild" or "user"
    value = str(data.get("value", "")).strip()
    if kind not in ("guild", "user") or not value.isdigit():
        return jsonify({"error": "kind must be 'guild' or 'user', value must be a numeric ID"}), 400
    with WHITELIST_LOCK:
        WHITELIST_STATE["guilds" if kind == "guild" else "users"].add(value)
    log(f"[ADMIN] Whitelisted {kind} ID {value} from dashboard.")
    return jsonify(whitelist_snapshot())

@app.route("/api/whitelist/remove", methods=["POST"])
@login_required
def api_whitelist_remove():
    data = request.get_json(force=True, silent=True) or {}
    kind = data.get("kind")
    value = str(data.get("value", "")).strip()
    if kind not in ("guild", "user"):
        return jsonify({"error": "kind must be 'guild' or 'user'"}), 400
    with WHITELIST_LOCK:
        WHITELIST_STATE["guilds" if kind == "guild" else "users"].discard(value)
    log(f"[ADMIN] Removed {kind} ID {value} from whitelist via dashboard.")
    return jsonify(whitelist_snapshot())

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
            guild_name = interaction.guild.name if interaction.guild else "Direct Message"
            channel_name = str(interaction.channel) if interaction.channel else "unknown"
            guild_id = interaction.guild.id if interaction.guild else None

            if not is_whitelisted(guild_id, interaction.user.id):
                log(f"[BLOCKED] Bot {token_id}: /hazbin from non-whitelisted {interaction.user} in {guild_name}")
                record_activity({
                    "type": "blocked",
                    "bot_id": token_id,
                    "bot_name": str(self.user),
                    "bot_avatar": self.user.display_avatar.url if self.user else None,
                    "author": str(interaction.user),
                    "author_avatar": interaction.user.display_avatar.url,
                    "guild": guild_name,
                    "channel": channel_name,
                    "content": f"/hazbin {text}",
                })
                try:
                    await interaction.response.send_message(
                        "This server/user isn't whitelisted to use this bot.", ephemeral=True
                    )
                except Exception:
                    pass
                return

            log(f"[COMMAND] Bot {token_id} received /hazbin: {text}")

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

        guild_id = message.guild.id if message.guild else None
        location = f"DM with {message.author}" if message.guild is None else \
            f"#{message.channel} in {message.guild.name}"

        content = message.content if message.content else "[no text content]"
        if message.attachments:
            content += f" [attachments: {', '.join(a.filename for a in message.attachments)}]"

        if not is_whitelisted(guild_id, message.author.id):
            log(f"[BLOCKED] Bot {self.token_id} | {location} | {message.author}: {content}")
            record_activity({
                "type": "blocked",
                "bot_id": self.token_id,
                "bot_name": str(self.user),
                "bot_avatar": self.user.display_avatar.url if self.user else None,
                "author": str(message.author),
                "author_avatar": message.author.display_avatar.url,
                "guild": message.guild.name if message.guild else "Direct Message",
                "channel": str(message.channel),
                "content": content,
            })
            return  # don't process commands for non-whitelisted senders

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
    position: relative;
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
  .badge.blocked { background: #da373c; }
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

  /* --- Admin panel --- */
  #admin {
    max-width: 820px;
    margin: 16px auto 0;
    padding: 14px 18px;
    background: var(--bg-secondary);
    border-radius: 8px;
    border: 1px solid var(--divider);
  }
  #admin h2 {
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.02em;
    color: var(--text-muted);
    margin: 0 0 10px;
  }
  .admin-row {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 10px;
  }
  .switch {
    position: relative;
    width: 40px;
    height: 22px;
    flex-shrink: 0;
  }
  .switch input { opacity: 0; width: 0; height: 0; }
  .slider {
    position: absolute;
    cursor: pointer;
    top: 0; left: 0; right: 0; bottom: 0;
    background-color: #80848e;
    transition: 0.15s;
    border-radius: 22px;
  }
  .slider:before {
    position: absolute;
    content: "";
    height: 18px; width: 18px;
    left: 2px; bottom: 2px;
    background-color: white;
    transition: 0.15s;
    border-radius: 50%;
  }
  input:checked + .slider { background-color: #23a55a; }
  input:checked + .slider:before { transform: translateX(18px); }
  .wl-label { font-size: 14px; color: var(--text-bright); font-weight: 500; }
  .admin-row input[type=text] {
    background: var(--bg-tertiary);
    border: 1px solid var(--divider);
    border-radius: 4px;
    color: var(--text-normal);
    padding: 6px 8px;
    font-size: 13px;
    flex: 1;
    min-width: 120px;
  }
  select.kind {
    background: var(--bg-tertiary);
    border: 1px solid var(--divider);
    border-radius: 4px;
    color: var(--text-normal);
    padding: 6px 8px;
    font-size: 13px;
  }
  button.btn {
    background: var(--brand);
    color: white;
    border: none;
    border-radius: 4px;
    padding: 6px 12px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
  }
  button.btn.danger { background: #da373c; }
  button.btn.ghost { background: transparent; border: 1px solid var(--divider); color: var(--text-muted); }
  #wlEntries { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip {
    background: var(--bg-tertiary);
    border: 1px solid var(--divider);
    border-radius: 12px;
    padding: 3px 8px;
    font-size: 12px;
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--text-normal);
  }
  .chip button {
    background: none; border: none; color: var(--text-muted);
    cursor: pointer; font-size: 12px; line-height: 1;
  }
  .del-btn {
    display: none;
    position: absolute;
    right: 4px;
    top: 6px;
    background: var(--bg-tertiary);
    border: 1px solid var(--divider);
    color: var(--text-muted);
    border-radius: 4px;
    width: 24px; height: 24px;
    cursor: pointer;
    font-size: 13px;
  }
  .msg:hover .del-btn { display: block; }
  .del-btn:hover { color: #da373c; border-color: #da373c; }
</style>
</head>
<body>
  <header>
    <h1>bot-activity</h1>
    <div id="status"><span class="dot"></span>live</div>
  </header>
  <div id="admin">
    <h2>Admin</h2>
    <div class="admin-row">
      <label class="switch">
        <input type="checkbox" id="wlToggle" onchange="toggleWhitelist()">
        <span class="slider"></span>
      </label>
      <span class="wl-label" id="wlLabel">Whitelist: OFF (everyone can use the bots)</span>
    </div>
    <div class="admin-row">
      <select class="kind" id="wlKind">
        <option value="guild">Server ID</option>
        <option value="user">User ID (for DMs)</option>
      </select>
      <input type="text" id="wlValue" placeholder="Paste a numeric Discord ID">
      <button class="btn" onclick="addWhitelist()">Add</button>
      <button class="btn danger" onclick="clearActivity()">Clear all activity</button>
    </div>
    <div id="wlEntries"></div>
  </div>
  <div id="feed"><div id="empty">Waiting for activity...</div></div>

<script>
function escapeHtml(str) {
  const d = document.createElement("div");
  d.innerText = str == null ? "" : str;
  return d.innerHTML;
}

function badgeFor(type) {
  if (type === "command") return '<span class="badge command">command</span>';
  if (type === "blocked") return '<span class="badge blocked">blocked</span>';
  return '<span class="badge">message</span>';
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
      const avatar = item.author_avatar || "https://cdn.discordapp.com/embed/avatars/0.png";
      const botAvatar = item.bot_avatar || "https://cdn.discordapp.com/embed/avatars/0.png";
      return `
        <div class="msg" data-id="${item.id}">
          <button class="del-btn" title="Delete from dashboard" onclick="deleteMessage('${item.id}')">&times;</button>
          <img class="avatar" src="${avatar}" alt="">
          <div class="body">
            <div class="line1">
              <span class="username">${escapeHtml(item.author)}</span>
              ${badgeFor(item.type)}
              <span class="meta">${escapeHtml(item.guild)} · #${escapeHtml(item.channel)}</span>
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

async function deleteMessage(id) {
  await fetch("/api/activity/" + id, { method: "DELETE" });
  refresh();
}

async function clearActivity() {
  if (!confirm("Clear all activity from the dashboard? This only clears the dashboard view, not Discord.")) return;
  await fetch("/api/activity/clear", { method: "POST" });
  refresh();
}

async function refreshWhitelist() {
  const res = await fetch("/api/whitelist");
  const wl = await res.json();
  document.getElementById("wlToggle").checked = wl.enabled;
  document.getElementById("wlLabel").textContent = wl.enabled
    ? "Whitelist: ON (only listed servers/users can use the bots)"
    : "Whitelist: OFF (everyone can use the bots)";

  const chips = [];
  wl.guilds.forEach(id => chips.push({ kind: "guild", id }));
  wl.users.forEach(id => chips.push({ kind: "user", id }));

  document.getElementById("wlEntries").innerHTML = chips.map(c => `
    <span class="chip">${c.kind === "guild" ? "Server" : "User"}: ${c.id}
      <button onclick="removeWhitelist('${c.kind}','${c.id}')">&times;</button>
    </span>
  `).join("") || '<span class="meta">No whitelist entries yet.</span>';
}

async function toggleWhitelist() {
  await fetch("/api/whitelist/toggle", { method: "POST" });
  refreshWhitelist();
}

async function addWhitelist() {
  const kind = document.getElementById("wlKind").value;
  const value = document.getElementById("wlValue").value.trim();
  if (!value) return;
  await fetch("/api/whitelist/add", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, value })
  });
  document.getElementById("wlValue").value = "";
  refreshWhitelist();
}

async function removeWhitelist(kind, value) {
  await fetch("/api/whitelist/remove", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, value })
  });
  refreshWhitelist();
}

refresh();
refreshWhitelist();
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
