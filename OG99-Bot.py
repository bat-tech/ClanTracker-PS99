import os
import discord
import requests
import json
from discord.ext import commands, tasks

TOKEN = os.getenv("DISCORD_TOKEN_OG99")
CHANNEL_ID = 1334559499503013930

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

CLAN_API = "https://ps99.biggamesapi.io/api/clan/OG99"
CLANS_API = "https://ps99.biggamesapi.io/api/clans?page=1&pageSize=100&sort=Points&sortOrder=desc"
ROBLOX_USER_API = "https://users.roblox.com/v1/users"

PREVIOUS_POINTS_FILE = "previous_points_og99.json"
previous_points = {}

def save_previous_points():
    with open(PREVIOUS_POINTS_FILE, "w") as f:
        json.dump(previous_points, f)

def load_previous_points():
    global previous_points
    if os.path.exists(PREVIOUS_POINTS_FILE):
        with open(PREVIOUS_POINTS_FILE, "r") as f:
            previous_points = json.load(f)
    else:
        previous_points = {}

def fetch_clan_data():
    response = requests.get(CLAN_API)
    try:
        data = response.json()
        battle = data.get("data", {}).get("Battles", {}).get("ValBattle", {})
        if not battle:
            return None

        return {
            "Place": battle.get("Place"),
            "Points": battle.get("Points"),
            "PointContributions": battle.get("PointContributions", [])
        }

    except json.JSONDecodeError:
        return None

def fetch_clans_data():
    response = requests.get(CLANS_API)
    try:
        return response.json().get("data", []) if response.status_code == 200 else None
    except json.JSONDecodeError:
        return None

def get_roblox_usernames(user_ids):
    data = {"userIds": user_ids, "excludeBannedUsers": True}
    response = requests.post(ROBLOX_USER_API, json=data)
    if response.status_code == 200:
        return {user["id"]: (user["name"], user["displayName"]) for user in response.json().get("data", [])}
    return {}

@tasks.loop(minutes=10)
async def update_clan_stats():
    global previous_points
    load_previous_points()

    clan_data = fetch_clan_data()
    clans_data = fetch_clans_data()
    if not clan_data or not clans_data:
        return
    
    place = clan_data["Place"]
    total_points = clan_data["Points"]
    contributions = clan_data["PointContributions"]
    
    user_ids = [user["UserID"] for user in contributions]
    user_data = get_roblox_usernames(user_ids)

    changes = {}
    for user in contributions:
        user_id = user["UserID"]
        current_points = user["Points"]
        previous = previous_points.get(str(user_id), current_points)
        change = current_points - previous
        estimated_hourly = change * 6
        changes[user_id] = (change, estimated_hourly)
        previous_points[str(user_id)] = current_points

    save_previous_points()

    sorted_members = sorted(contributions, key=lambda x: x["Points"], reverse=True)
    
    clan_names = [clan for clan in clans_data if clan.get("Name") == "OG99"]
    if not clan_names:
        return
    
    index = clans_data.index(clan_names[0]) if clan_names else -1
    clan_above = clans_data[index - 1] if index > 0 else None
    clan_below = clans_data[index + 1] if index + 1 < len(clans_data) else None
    
    points_above = clan_above["Points"] - total_points if clan_above else "N/A"
    points_below = total_points - clan_below["Points"] if clan_below else "N/A"
    
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        embed = discord.Embed(title="🏆 **OG99 Clan Stats**", color=0xFFD700)
        embed.add_field(name="🥇 Placement", value=f"{place}" if place else "Unknown", inline=True)
        embed.add_field(name="⭐ Total Points", value=f"{total_points:,}" if total_points else "0", inline=True)
        embed.add_field(name="🟩 Points to Pass", value=f"{points_above:,} ({clan_above['Name']})" if clan_above else "N/A", inline=False)
        embed.add_field(name="🟥 Points for Lower Clan to Surpass", value=f"{points_below:,} ({clan_below['Name']})" if clan_below else "N/A", inline=False)
        await channel.send(embed=embed)

@bot.event
async def on_ready():
    print(f"{bot.user.name} is online!")
    update_clan_stats.start()

bot.run(TOKEN)
