import os
from datetime import datetime, UTC

import discord
from discord import app_commands
from discord.ext import commands

import gspread
from google.oauth2.service_account import Credentials

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

SPREADSHEET_ID = "1hD2mJ98jbvshpcv0aUHWreiHoLJQx-1EQz7f5NG0jNc"

creds = Credentials.from_service_account_file(
    "credentials.json",
    scopes=SCOPES
)

gc = gspread.authorize(creds)
sheet = gc.open_by_key(SPREADSHEET_ID).sheet1

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Sync error: {e}")


@bot.tree.command(name="add", description="Add your power value")
@app_commands.describe(value="Your power value, for example 45.5")
async def add(interaction: discord.Interaction, value: float):
    row = [
        datetime.now(UTC).isoformat(),
        str(interaction.user.id),
        interaction.user.display_name,
        str(value),
    ]

    sheet.append_row(row)
    await interaction.response.send_message(f"Saved: {value}")


@bot.tree.command(name="show", description="Show your last 4 values")
async def show(interaction: discord.Interaction):
    records = sheet.get_all_records()

    user_records = [
        r for r in records
        if str(r["user_id"]) == str(interaction.user.id)
    ]

    if not user_records:
        await interaction.response.send_message("No data yet.")
        return

    last_four = user_records[-4:]
    lines = ["Your last 4 values:"]

    for i, record in enumerate(reversed(last_four), start=1):
        lines.append(f"{i}. {record['power']}")

    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="list", description="Show current value for each user")
async def list_cmd(interaction: discord.Interaction):
    records = sheet.get_all_records()

    latest_by_user = {}
    for record in records:
        latest_by_user[record["user_id"]] = record

    if not latest_by_user:
        await interaction.response.send_message("No data yet.")
        return

    sorted_rows = sorted(
        latest_by_user.values(),
        key=lambda x: float(x["power"]),
        reverse=True
    )

    lines = ["Current values:"]
    for i, record in enumerate(sorted_rows, start=1):
        lines.append(f"{i}. {record['username']} — {record['power']}")

    await interaction.response.send_message("\n".join(lines))


if not TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN is missing")

bot.run(TOKEN)