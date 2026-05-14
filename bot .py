import discord
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timezone

# ============================================================
#  CONFIGURATION — fill these in before running
# ============================================================

TOKEN = os.environ.get("token")

# Paste your server's Role IDs here (right-click role > Copy ID)
RANKS = [
    {"name": "Private",               "role_id": 1500663756982714428},  # rank 1  — day 0
    {"name": "Staff Sergeant",        "role_id": 1504245302071394516},  # rank 6  — day 7
    {"name": "2nd Lieutenant",        "role_id": 1504245749461024798},  # rank 10 — day 16
    {"name": "Captain",               "role_id": 1504245764652535808},  # rank 13 — day 25
    {"name": "Colonel",               "role_id": 1504245850736427109},  # rank 15 — day 34
    {"name": "General",               "role_id": 1504245958081384538},  # rank 19 — day 43
    {"name": "Marshal",               "role_id": 1504246036674252933},  # rank 21 — day 52
    {"name": "Grand Lord",            "role_id": 1504246152910995567},  # rank 25 — day 61
    {"name": "Hero of the Sector",    "role_id": 1504246213212508243},  # rank 30 — day 70
    {"name": "Admiral of Super Earth","role_id": 1504457817849860217},  # rank 50 — day 80 (permanent)
]

# Days required in server to reach each rank
# Starts at 7 days, +2 days added for each step
THRESHOLDS = [
    0,   # Private          — given immediately on join
    7,   # Staff Sergeant   — 7 days
    16,  # 2nd Lieutenant   — 7+9
    25,  # Captain          — +9... continuing +2 pattern across the gaps
    34,  # Colonel
    43,  # General
    52,  # Marshal
    61,  # Grand Lord
    70,  # Hero of the Sector
    79,  # Admiral of Super Earth
]

# File to save member join dates so they survive bot restarts
DATA_FILE = "members.json"

# ============================================================
#  BOT SETUP
# ============================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ============================================================
#  DATA HELPERS
# ============================================================

def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_correct_rank_index(days_in_server: int) -> int:
    """Return which rank index a member should have based on days in server."""
    index = 0
    for i, threshold in enumerate(THRESHOLDS):
        if days_in_server >= threshold:
            index = i
    return index

# ============================================================
#  RANK ASSIGNMENT
# ============================================================

async def assign_rank(member: discord.Member, rank_index: int):
    """Strip all rank roles then give the correct one."""
    all_rank_ids = {r["role_id"] for r in RANKS}
    roles_to_remove = [r for r in member.roles if r.id in all_rank_ids]
    if roles_to_remove:
        await member.remove_roles(*roles_to_remove, reason="Helldivers rank update")

    new_role = member.guild.get_role(RANKS[rank_index]["role_id"])
    if new_role:
        await member.add_roles(new_role, reason=f"Helldivers rank: {RANKS[rank_index]['name']}")
    return new_role

async def check_and_promote(member: discord.Member, data: dict):
    """Promote a member if they've passed a threshold."""
    entry = data.get(str(member.id))
    if not entry:
        return

    joined = datetime.fromisoformat(entry["joined"])
    days_in_server = (datetime.now(timezone.utc) - joined).days
    correct_index = get_correct_rank_index(days_in_server)

    # Find their current rank index (-1 if they have none)
    current_index = -1
    for i, rank in enumerate(RANKS):
        if member.get_role(rank["role_id"]):
            current_index = i
            break

    if correct_index > current_index:
        await assign_rank(member, correct_index)
        print(f"Promoted {member.display_name} to {RANKS[correct_index]['name']} ({days_in_server} days)")

# ============================================================
#  EVENTS
# ============================================================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} — Helldivers rank bot ready")
    rank_check_loop.start()

@bot.event
async def on_member_join(member: discord.Member):
    """Log join time and give Private immediately."""
    data = load_data()
    if str(member.id) not in data:
        data[str(member.id)] = {
            "joined": datetime.now(timezone.utc).isoformat(),
            "name": member.display_name,
        }
        save_data(data)
    await assign_rank(member, 0)
    print(f"{member.display_name} joined — assigned Private")

@bot.event
async def on_member_remove(member: discord.Member):
    """Remove member data when they leave."""
    data = load_data()
    data.pop(str(member.id), None)
    save_data(data)

# ============================================================
#  24 HOUR CHECK LOOP
# ============================================================

@tasks.loop(hours=24)
async def rank_check_loop():
    """Check every member every 24 hours and promote if due."""
    data = load_data()
    for guild in bot.guilds:
        for member in guild.members:
            if member.bot:
                continue
            # Catch members who joined before the bot was set up
            if str(member.id) not in data:
                data[str(member.id)] = {
                    "joined": member.joined_at.isoformat() if member.joined_at else datetime.now(timezone.utc).isoformat(),
                    "name": member.display_name,
                }
            await check_and_promote(member, data)
    save_data(data)
    print(f"Daily rank check done — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

# ============================================================
#  COMMANDS
# ============================================================

@bot.command(name="checkranks")
@commands.has_permissions(administrator=True)
async def force_check(ctx):
    """Force an immediate rank check — admin only."""
    await ctx.send("Running rank check now...")
    data = load_data()
    for member in ctx.guild.members:
        if not member.bot:
            if str(member.id) not in data:
                data[str(member.id)] = {
                    "joined": member.joined_at.isoformat() if member.joined_at else datetime.now(timezone.utc).isoformat(),
                    "name": member.display_name,
                }
            await check_and_promote(member, data)
    save_data(data)
    await ctx.send("Done! All ranks are up to date.")

@bot.command(name="rankinfo")
async def rank_info(ctx, member: discord.Member = None):
    """Check your rank and time until next — !rankinfo or !rankinfo @user"""
    member = member or ctx.author
    data = load_data()
    entry = data.get(str(member.id))

    if not entry:
        await ctx.send(f"No data found for {member.display_name}.")
        return

    joined = datetime.fromisoformat(entry["joined"])
    days_in_server = (datetime.now(timezone.utc) - joined).days
    current_index = get_correct_rank_index(days_in_server)
    current_rank = RANKS[current_index]["name"]

    if current_index < len(RANKS) - 1:
        next_threshold = THRESHOLDS[current_index + 1]
        days_to_next = next_threshold - days_in_server
        next_rank = RANKS[current_index + 1]["name"]
        await ctx.send(
            f"🪖 **{member.display_name}** — **{current_rank}**\n"
            f"Days in server: {days_in_server}\n"
            f"Next rank: **{next_rank}** in {days_to_next} day(s)"
        )
    else:
        await ctx.send(
            f"🦅 **{member.display_name}** — **{current_rank}**\n"
            f"Maximum rank achieved. For Super Earth!"
        )

# ============================================================
#  RUN
# ============================================================

bot.run(TOKEN)
