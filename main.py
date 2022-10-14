import os
from cogs import helpers
import time
import datetime
import random
import pickle
import asyncio

from dotenv import load_dotenv

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

import pyrankvote
from pyrankvote import Candidate, Ballot

from discord.ext import commands
from discord.channel import DMChannel
from discord import Intents

from cogs import society_members

# Workflow
# See current members:   \members
# Setup the post:        \setup <POST NAME>
# Rename a post:         \rename <OLD NAME (in quotes)> <NEW NAME>
# Setup the referendum:  \referendum <TITLE (in quotes)> <DESCRIPTION>
# Check the setup:       \posts
# Check the referenda:   \referenda
# Members register:      \register
# Members stand:         \stand <POST NAME>
# List candidates:       \candidates <POST NAME>
# Voting begins:         \begin <POST NAME>
# Voters vote:           Reacts
# Voters submit:         \submit
# Voting ends + results: \end


# Set the command prefix to be '\'
PREFIX = '\\'

# Create the bot and specify to only look for messages starting with the PREFIX
intents = Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)


@bot.event
async def on_ready():
    helpers.init_helpers()
    print(f'{bot.user.name} has connected to Discord and is in the following channels:')
    for guild in bot.guilds:
        print(' -', guild.name)

@bot.event
async def on_command_error(context, error):
    if isinstance(error, commands.errors.CommandNotFound):
        helpers.log(error)
        await context.channel.send(f'I couldn\'t find that command, please use {PREFIX}help for a list of commands.')

async def main():
    load_dotenv()
    TOKEN = os.getenv('DISCORD_TOKEN')
    async with bot:
        await bot.load_extension('cogs.admin')
        await bot.load_extension('cogs.info')
        await bot.load_extension('cogs.running')
        await bot.load_extension('cogs.voting')
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
