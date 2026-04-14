import os
from enum import Enum
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

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
    1427698576066084985,
}

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

DISPLAY_TZ = ZoneInfo("Europe/Berlin")


class UnitType(str, Enum):
    tank = "tank"
    air = "air"
    missile = "missile"


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
    return [r for r in records if str(r.get("user_id", "")) == str(user_id)]


def get_last_user_record(user_id: int) -> dict | None:
    user_records = get_user_records(user_id)
    if not user_records:
        return None
    return user_records[-1]


def get_last_user_value(user_id: int) -> float | None:
    last_record = get_last_user_record(user_id)
    if not last_record:
        return None

    try:
        return float(last_record["power"])
    except:
        return None


# ---------- Time formatting (CET / CEST) ----------

def format_time(ts: str) -> str:
    try:
        dt_utc = datetime.fromisoformat(ts)
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)

        dt_local = dt_utc.astimezone(DISPLAY_TZ)
        now_local = datetime.now(DISPLAY_TZ)
        diff = now_local - dt_local

        seconds = int(diff.total_seconds())
        minutes = seconds // 60
        hours = minutes // 60

        formatted = dt_local.strftime("%d.%m.%Y %H:%M")
        tz_name = dt_local.tzname()  # CET або CEST

        if seconds < 60:
            rel = f"{seconds}s ago"
        elif minutes < 60:
            rel = f"{minutes} min ago"
        elif hours < 24:
            rel = f"{hours}h ago"
        else:
            rel = dt_local.strftime("%d.%m.%Y")

        return f"{formatted} {tz_name} ({rel})"
    except:
        return ts


def unit_label(value: str) -> str:
    return str(value)


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
@app_commands.describe(
    value="Your new power value",
    unit_type="Your troop type"
)
async def add(
    interaction: discord.Interaction,
    value: float,
    unit_type: UnitType
):
    if await reject_wrong_channel(interaction):
        return

    last_record = get_last_user_record(interaction.user.id)
    last_value = None

    if last_record:
        try:
            last_value = float(last_record["power"])
        except:
            last_value = None

    # строго більше
    if last_value is not None and value <= last_value:
        await interaction.response.send_message(
            f"❌ New value must be higher than your previous one: {last_value:g}",
            ephemeral=True
        )
        return

    row = [
        datetime.now(timezone.utc).isoformat(),
        str(interaction.user.id),
        interaction.user.display_name,
        str(value),
        unit_type.value,
    ]

    sheet.append_row(row)

    if last_value is None:
        await interaction.response.send_message(
            f"✅ Saved: **{value:g}** [{unit_type.value}]"
        )
    else:
        diff = value - last_value
        await interaction.response.send_message(
            f"✅ Saved: **{value:g}** [{unit_type.value}]  ( +{diff:.2f} )"
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
        unit_type = unit_label(record.get("type", "?"))
        timestamp = format_time(record.get("timestamp", ""))
        lines.append(f"• **{power}** [{unit_type}] — {timestamp}")

    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="list", description="Show current power values")
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

    lines = ["📊 Current power:\n"]

    for r in sorted_rows:
        username = r.get("username", "Unknown")
        power = r.get("power", "?")
        unit_type = unit_label(r.get("type", "?"))
        lines.append(f"• {username} — **{power}** [{unit_type}]")

    message = "\n".join(lines)

    if len(message) <= 2000:
        await interaction.response.send_message(message)
        return

    await interaction.response.send_message("List is long, sending in parts...")

    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > 2000:
            await interaction.followup.send(chunk)
            chunk = line
        else:
            chunk = f"{chunk}\n{line}" if chunk else line

    if chunk:
        await interaction.followup.send(chunk)


# ---------- Start ----------

if __name__ == "__main__":
    bot.run(TOKEN)