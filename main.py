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


# Set the default prefix to be '\'
DEFAULT_PREFIX = '\\'

def get_prefix(bot_obj, message) -> str:
    # a custom prefix can be retrieved with the guild's ID
    try:
        with open("prefixes.json", 'r') as f:
            prefixes = json.load(f)

        return prefixes[str(message.guild.id)]

    except AttributeError:  # triggered when command is invoked in dms
        return DEFAULT_PREFIX

    except KeyError:  # triggered when the server prefix has never been changed
        return DEFAULT_PREFIX

client = commands.Bot(command_prefix=get_prefix, intents=intents)


@client.event
async def on_guild_remove(guild):
    try:
        with open("prefixes.json", 'r') as f:
            prefixes = json.load(f)

        prefixes.pop(str(guild.id))

        with open("prefixes.json", 'w') as f:
            json.dump(prefixes, f, indent=2)
    except KeyError:  # the server never changed the default prefix
        pass

@client.command(aliases=["PREFIX", "Prefix", "pREFIX"])
@has_permissions(administrator=True)
async def prefix(ctx, new_prefix: str):

    if ctx.guild is None:
        await ctx.reply("**You cannot change the prefix outside of a server!**")
        return

    with open("prefixes.json", 'r') as f:
        prefixes = json.load(f)

    prefixes[str(ctx.guild.id)] = new_prefix

    with open("prefixes.json", 'w') as f:
        json.dump(prefixes, f, indent=2)

    await ctx.send(f"**Prefix changed to {new_prefix}**")

@prefix.error
async def prefix_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply("**Incorrect usage!\n"
                        f"Example: {get_prefix(client, ctx)}prefix .**")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.reply("**You do not have the permission to change the server prefix!**")

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
        await message.channel.send(f'I couldn\'t find that command, please use {PREFIX}help for a list of commands.')


if __name__ == "__main__":

    load_dotenv()
    TOKEN = os.getenv('DISCORD_TOKEN')

    bot.load_extension('cogs.admin')
    bot.load_extension('cogs.info')
    bot.load_extension('cogs.running')
    bot.load_extension('cogs.voting')
    bot.run(TOKEN)
