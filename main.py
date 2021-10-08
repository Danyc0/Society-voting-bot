import os
import time
import datetime
import random
import pickle
import asyncio

import aiorwlock

from dotenv import load_dotenv

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

import pyrankvote
from pyrankvote import Candidate, Ballot

from discord.ext import commands
from discord.channel import DMChannel

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
bot = commands.Bot(command_prefix=PREFIX)


@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord and is in the following channels:')
    for guild in bot.guilds:
        print(' -', guild.name)


@bot.event
async def on_message(message):
    try:
        await bot.process_commands(message)
    except commands.errors.CommandNotFound:
        await message.channel.send(f'I could not find that command, please use {PREFIX}help for a list of commands')


if __name__ == "__main__":

    load_dotenv()
    TOKEN = os.getenv('DISCORD_TOKEN')

    bot.run(TOKEN)
