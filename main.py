import discord
from discord.ext import commands, tasks
import feedparser
import json
import os
import aiohttp
from bs4 import BeautifulSoup
import hashlib
import re

# ================= CONFIG =================

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

USER = "RLCS_CarDesigns"
STATE_FILE = "state.json"

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ================= STATE =================

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"enabled": True, "seen": []}
    return json.load(open(STATE_FILE, "r"))

def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

state = load_state()

# ================= NORMALISATION =================

def normalize(text):
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text

def fingerprint(tweet):
    base = f"{tweet.get('id','')}|{tweet.get('link','')}|{normalize(tweet.get('text',''))}"
    return hashlib.sha256(base.encode()).hexdigest()

# ================= ANTI DOUBLON =================

def is_duplicate(tweet):
    fp = fingerprint(tweet)

    if fp in state["seen"]:
        return True

    state["seen"].append(fp)

    if len(state["seen"]) > 100:
        state["seen"] = state["seen"][-100:]

    save_state()
    return False

# ================= TWITTER FETCH =================

def fetch_latest():
    urls = [
        f"https://nitter.net/{USER}/rss",
        f"https://nitter.poast.org/{USER}/rss"
    ]

    for url in urls:
        try:
            feed = feedparser.parse(url)
            if feed.entries:
                t = feed.entries[0]
                return {
                    "id": t.id,
                    "text": t.title,
                    "link": t.link
                }
        except:
            continue

    return None

# ================= IMAGE EXTRACTION =================

async def get_images(url):
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as r:
                html = await r.text()

        soup = BeautifulSoup(html, "html.parser")

        images = []
        for meta in soup.find_all("meta"):
            if meta.get("property") in ["og:image", "og:image:secure_url"]:
                images.append(meta.get("content"))

        return list(dict.fromkeys(images))

    except:
        return []

# ================= LOOP =================

@tasks.loop(seconds=60)
async def twitter_loop():

    if not state["enabled"]:
        return

    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return

    tweet = fetch_latest()
    if not tweet:
        return

    if is_duplicate(tweet):
        return

    images = await get_images(tweet["link"])

    embed = discord.Embed(
        title="🆕 RLCS Car Design",
        description=tweet["text"][:3000],
        url=tweet["link"],
        color=0x1DA1F2
    )

    if images:
        embed.set_image(url=images[0])

    await channel.send(embed=embed)

# ================= EVENTS =================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    twitter_loop.start()
    await bot.tree.sync()

# ================= ADMIN PANEL =================

admin = discord.app_commands.Group(name="admin", description="Panel admin")

@admin.command(name="toggle")
async def toggle(interaction: discord.Interaction):
    state["enabled"] = not state["enabled"]
    save_state()
    await interaction.response.send_message(f"Feed: {'ON' if state['enabled'] else 'OFF'}")

@admin.command(name="status")
async def status(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Enabled: {state['enabled']}\nSeen: {len(state['seen'])}"
    )

@admin.command(name="force")
async def force(interaction: discord.Interaction):
    state["seen"] = []
    save_state()
    await interaction.response.send_message("Cache reset OK")

bot.tree.add_command(admin)

# ================= RUN =================

bot.run(TOKEN)
