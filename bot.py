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

ALLOWED_CHANNELS = {
    1493604626803593313,
}

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


# ---------- Channel restriction ----------

def is_allowed_channel(interaction: discord.Interaction) -> bool:
    return interaction.channel_id in ALLOWED_CHANNELS


async def reject_wrong_channel(interaction: discord.Interaction) -> bool:
    if is_allowed_channel(interaction):
        return False

    await interaction.response.send_message(
        "This command is only available in the designated channel.",
        ephemeral=True
    )
    return True


# ---------- Data helpers ----------

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
    except:
        return None


# ---------- Time formatting ----------

def format_time(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts)
        now = datetime.now(timezone.utc)
        diff = now - dt

        seconds = int(diff.total_seconds())
        minutes = seconds // 60
        hours = minutes // 60

        formatted = dt.strftime("%d.%m.%Y %H:%M")

        if seconds < 60:
            rel = f"{seconds}s ago"
        elif minutes < 60:
            rel = f"{minutes} min ago"
        elif hours < 24:
            rel = f"{hours}h ago"
        else:
            rel = dt.strftime("%d.%m.%Y")

        return f"{formatted} ({rel})"
    except:
        return ts


# ---------- Events ----------

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as exc:
        print(f"Sync error: {exc}")


# ---------- Commands ----------

@bot.tree.command(name="add", description="Add your power value")
@app_commands.describe(value="Your new power value")
async def add(interaction: discord.Interaction, value: float):
    if await reject_wrong_channel(interaction):
        return

    last_value = get_last_user_value(interaction.user.id)

    if last_value is not None and value < last_value:
        await interaction.response.send_message(
            f"❌ Rejected: {value:g} < {last_value:g}",
            ephemeral=True
        )
        return

    row = [
        datetime.now(timezone.utc).isoformat(),
        str(interaction.user.id),
        interaction.user.display_name,
        str(value),
    ]

    sheet.append_row(row)

    if last_value is None:
        await interaction.response.send_message(f"✅ Saved: **{value:g}**")
    else:
        diff = value - last_value
        await interaction.response.send_message(
            f"✅ Saved: **{value:g}**  ( +{diff:.2f} )"
        )


@bot.tree.command(name="show", description="Show your last 4 values")
async def show(interaction: discord.Interaction):
    if await reject_wrong_channel(interaction):
        return

    user_records = get_user_records(interaction.user.id)

    if not user_records:
        await interaction.response.send_message("No data yet.", ephemeral=True)
        return

    last_four = user_records[-4:]

    lines = [f"📊 {interaction.user.display_name} — last values:\n"]

    for record in reversed(last_four):
        power = record.get("power", "?")
        timestamp = format_time(record.get("timestamp", ""))
        lines.append(f"• **{power}** — {timestamp}")

    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="list", description="Show current values ranking")
async def list_cmd(interaction: discord.Interaction):
    if await reject_wrong_channel(interaction):
        return

    records = get_all_records()

    if not records:
        await interaction.response.send_message("No data yet.", ephemeral=True)
        return

    latest_by_user = {}

    for record in records:
        user_id = str(record.get("user_id", "")).strip()
        if user_id:
            latest_by_user[user_id] = record

    def power_float(r):
        try:
            return float(r["power"])
        except:
            return -1

    sorted_rows = sorted(latest_by_user.values(), key=power_float, reverse=True)

    medals = ["🥇", "🥈", "🥉"]

    lines = ["🏆 Current ranking:\n"]

    for i, r in enumerate(sorted_rows, start=1):
        username = r.get("username", "Unknown")
        power = r.get("power", "?")

        medal = medals[i - 1] if i <= 3 else f"{i}."

        lines.append(f"{medal} {username} — **{power}**")

    await interaction.response.send_message("\n".join(lines))


# ---------- Start ----------

if __name__ == "__main__":
    bot.run(TOKEN)