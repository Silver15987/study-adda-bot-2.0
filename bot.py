import discord
import os
import asyncio
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv(override=True)

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("BOT_PREFIX", "?")

if not TOKEN:
    print("ERROR: DISCORD_TOKEN is not being loaded from .env.")
    exit(1)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)
bot.task_queue = asyncio.PriorityQueue()  # Fix: Initialize task queue here

async def load_cogs():
    """Loads all cogs asynchronously"""
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and not filename.startswith("__"):
            try:
                await bot.load_extension(f"cogs.{filename[:-3]}")  # Await the loading
                print(f"Loaded cog: {filename}")
            except Exception as e:
                print(f"Failed to load {filename}: {e}")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

async def main():
    async with bot:
        await load_cogs()  # Load cogs before starting
        await bot.start(TOKEN)

# Run the bot
asyncio.run(main())
