import os

from dotenv import load_dotenv
from discord.ext import commands
from discord.channel import DMChannel

load_dotenv()



def public_check():
    def predicate(context):
        return context.channel.id == int(os.getenv('VOTING_CHANNEL_ID')) or isinstance(context.channel, DMChannel)
    return commands.check(predicate)


def public_admin_check():
    def predicate(context):
        return (context.channel.id == int(os.getenv('VOTING_CHANNEL_ID')) and 
                int(os.getenv('COMMITTEE_ROLE_ID')) in [role.id for role in context.author.roles])
    return commands.check(predicate)


def private_admin_check():
    def predicate(context):
        return context.channel.id == int(os.getenv('COMMITTEE_CHANNEL_ID'))
    return commands.check(predicate)

