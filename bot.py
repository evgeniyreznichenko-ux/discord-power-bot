import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv


load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GOOGLE_CREDS_PATH = os.getenv("GOOGLE_CREDS_PATH", "credentials.json")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def require_env(name: str, value: str | None) -> str:
    if not value:
        raise RuntimeError(f"{name} is missing")
    return value


TOKEN = require_env("DISCORD_BOT_TOKEN", TOKEN)
SPREADSHEET_ID = require_env("SPREADSHEET_ID", SPREADSHEET_ID)

creds = Credentials.from_service_account_file(
    GOOGLE_CREDS_PATH,
    scopes=SCOPES
)

gc = gspread.authorize(creds)
sheet = gc.open_by_key(SPREADSHEET_ID).sheet1

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def get_all_records() -> list[dict]:
    return sheet.get_all_records()


def get_user_records(user_id: int) -> list[dict]:
    records = get_all_records()
    return [r for r in records if str(r["user_id"]) == str(user_id)]


def get_last_user_value(user_id: int) -> float | None:
    user_records = get_user_records(user_id)
    if not user_records:
        return None

    try:
        return float(user_records[-1]["power"])
    except (KeyError, TypeError, ValueError):
        return None


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as exc:
        print(f"Sync error: {exc}")


@bot.tree.command(name="add", description="Add your power value")
@app_commands.describe(value="Your new power value, for example 45.5")
async def add(interaction: discord.Interaction, value: float):
    last_value = get_last_user_value(interaction.user.id)

    if last_value is not None and value < last_value:
        await interaction.response.send_message(
            f"Rejected. Your new value ({value:g}) cannot be lower than your previous value ({last_value:g}).",
            ephemeral=True
        )
        return

    row = [
        datetime.now(timezone.utc).isoformat(),
        str(interaction.user.id),
        interaction.user.display_name,
        str(value),
    ]

    try:
        sheet.append_row(row)
    except Exception as exc:
        await interaction.response.send_message(
            f"Failed to save data: {exc}",
            ephemeral=True
        )
        return

    if last_value is None:
        await interaction.response.send_message(
            f"Saved: {value:g}"
        )
    else:
        await interaction.response.send_message(
            f"Saved: {value:g} (previous: {last_value:g})"
        )


@bot.tree.command(name="show", description="Show your last 4 values")
async def show(interaction: discord.Interaction):
    user_records = get_user_records(interaction.user.id)

    if not user_records:
        await interaction.response.send_message("No data yet.", ephemeral=True)
        return

    last_four = user_records[-4:]
    lines = [f"Last values for {interaction.user.display_name}:"]

    for i, record in enumerate(reversed(last_four), start=1):
        timestamp = str(record.get("timestamp", ""))
        power = str(record.get("power", ""))
        lines.append(f"{i}. {power} | {timestamp}")

    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="list", description="Show current value for each user")
async def list_cmd(interaction: discord.Interaction):
    records = get_all_records()

    if not records:
        await interaction.response.send_message("No data yet.", ephemeral=True)
        return

    latest_by_user: dict[str, dict] = {}

    for record in records:
        user_id = str(record.get("user_id", "")).strip()
        if user_id:
            latest_by_user[user_id] = record

    if not latest_by_user:
        await interaction.response.send_message("No data yet.", ephemeral=True)
        return

    def power_as_float(record: dict) -> float:
        try:
            return float(record["power"])
        except (KeyError, TypeError, ValueError):
            return -1.0

    sorted_rows = sorted(
        latest_by_user.values(),
        key=power_as_float,
        reverse=True
    )

    lines = ["Current values:"]
    for i, record in enumerate(sorted_rows, start=1):
        username = str(record.get("username", "Unknown"))
        power = str(record.get("power", "N/A"))
        lines.append(f"{i}. {username} — {power}")

    message = "\n".join(lines)

    if len(message) <= 2000:
        await interaction.response.send_message(message)
        return

    await interaction.response.send_message("The list is too long, sending it in parts...")

    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > 2000:
            await interaction.followup.send(chunk)
            chunk = line
        else:
            chunk = f"{chunk}\n{line}" if chunk else line

    if chunk:
        await interaction.followup.send(chunk)


if __name__ == "__main__":
    bot.run(TOKEN)