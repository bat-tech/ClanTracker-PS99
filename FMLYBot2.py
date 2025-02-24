import os
import discord
import requests
import json
import asyncio
from discord.ext import commands, tasks

TOKEN = os.getenv("DISCORD_TOKEN_FMLY")
CHANNEL_ID = 1255555435906465803

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

CLAN_API = "https://ps99.biggamesapi.io/api/clan/FMLY"
CLANS_API = "https://ps99.biggamesapi.io/api/clans?page=1&pageSize=100&sort=Points&sortOrder=desc"
ROBLOX_USER_API = "https://users.roblox.com/v1/users"

PREVIOUS_POINTS_FILE = "previous_points_fmly.json"
previous_points = {}

# 🔹 Load previous points from JSON file
def load_previous_points():
    global previous_points
    if os.path.exists(PREVIOUS_POINTS_FILE):
        with open(PREVIOUS_POINTS_FILE, "r") as f:
            try:
                previous_points = json.load(f)
            except json.JSONDecodeError:
                print("⚠ Error loading JSON, resetting previous points.")
                previous_points = {}
    else:
        previous_points = {}

# 🔹 Save updated points to JSON file
def save_previous_points():
    with open(PREVIOUS_POINTS_FILE, "w") as f:
        json.dump(previous_points, f)

def fetch_clan_data():
    try:
        response = requests.get(CLAN_API)
        response.raise_for_status()
        data = response.json()
        battle = data.get("data", {}).get("Battles", {}).get("CardBattle", {})
        if not battle:
            return None
        return {
            "Place": battle.get("Place"),
            "Points": battle.get("Points"),
            "PointContributions": battle.get("PointContributions", [])
        }
    except requests.RequestException:
        return None

def fetch_clans_data():
    try:
        response = requests.get(CLANS_API)
        response.raise_for_status()
        return response.json().get("data", []) if response.status_code == 200 else None
    except requests.RequestException:
        return None

def get_roblox_usernames(user_ids):
    try:
        data = {"userIds": user_ids, "excludeBannedUsers": True}
        response = requests.post(ROBLOX_USER_API, json=data)
        response.raise_for_status()
        return {int(user["id"]): (user["name"], user["displayName"]) for user in response.json().get("data", [])}
    except requests.RequestException:
        return {}

@tasks.loop(minutes=10)
async def update_clan_stats():
    global previous_points
    load_previous_points()

    clan_data = fetch_clan_data()
    clans_data = fetch_clans_data()
    if not clan_data or not clans_data:
        print("⚠ Clan data or clans data is missing! Skipping update.")
        return
    
    place = clan_data["Place"]
    total_points = clan_data["Points"]
    contributions = clan_data["PointContributions"]
    
    if not contributions:
        print("⚠ No contributions found! Skipping update.")
        return

    user_ids = [user["UserID"] for user in contributions]
    user_data = get_roblox_usernames(user_ids)
    
    changes = {}
    for user in contributions:
        user_id = str(user["UserID"])
        current_points = user["Points"]
        
        previous = previous_points.get(user_id, current_points)
        change = current_points - previous
        estimated_hourly = change * 6
        changes[user_id] = (change, estimated_hourly)
        previous_points[user_id] = current_points
    
    save_previous_points()

    sorted_members = sorted(contributions, key=lambda x: x["Points"], reverse=True)
    
    clan_names = [clan for clan in clans_data if clan.get("Name") == "FMLY"]
    if not clan_names:
        print("⚠ No clan names found, skipping update.")
        return
    
    index = clans_data.index(clan_names[0]) if clan_names else -1
    clan_above = clans_data[index - 1] if index > 0 else None
    clan_below = clans_data[index + 1] if index + 1 < len(clans_data) else None
    
    points_above = clan_above["Points"] - total_points if clan_above else "N/A"
    points_below = total_points - clan_below["Points"] if clan_below else "N/A"
    
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        embed = discord.Embed(title="🏆 **FMLY Clan Stats**", color=0xFFD700)
        embed.add_field(name="🥇 Placement", value=f"{place}" if place else "Unknown", inline=True)
        embed.add_field(name="⭐ Total Points", value=f"{total_points:,}" if total_points else "0", inline=True)
        embed.add_field(name="🟩 Points to Pass", value=f"{points_above:,} ({clan_above['Name']})" if clan_above else "N/A", inline=False)
        embed.add_field(name="🟥 Points for Lower Clan to Surpass", value=f"{points_below:,} ({clan_below['Name']})" if clan_below else "N/A", inline=False)
        
        sent_message = await channel.send(embed=embed)
        print(f"✅ Sent main clan stats message: {sent_message.id}")
        
        for i in range(0, len(sorted_members), 25):
            member_embed = discord.Embed(title=f"👥 **Top Clan Members ({i+1}-{min(i+25, len(sorted_members))})**", color=0x00FF00)
            batch = sorted_members[i:i+25]
            
            for rank, user in enumerate(batch, start=i+1):
                user_id = str(user["UserID"])
                username, display_name = user_data.get(int(user_id), ("Unknown", "Unknown"))
                total_user_points = user["Points"]
                point_change, est_hourly = changes.get(user_id, (0, 0))
                
                member_embed.add_field(
                    name=f"{rank}. {display_name} (@{username})",
                    value=f"⭐ {total_user_points:,} 🔼 {point_change:,} / 10min ⏰ {est_hourly:,} / hr",
                    inline=False
                )
            
            sent_member_message = await channel.send(embed=member_embed)
            print(f"✅ Sent member leaderboard batch: {sent_member_message.id}")
            await asyncio.sleep(1)

@bot.event
async def on_ready():
    await bot.wait_until_ready()
    print(f"{bot.user.name} is online!")
    update_clan_stats.start()

bot.run(TOKEN)
