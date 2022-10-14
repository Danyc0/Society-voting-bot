# A Cog for getting info about the election #

import random
import traceback

from discord.ext import commands
from cogs import helpers, checkers

class Info(commands.Cog):
    # Initialisation #

    def __init__(self, bot):
        self.bot = bot

    # Commands for Initialising Elections #

    @commands.command(name='posts', help=f'Prints the posts available to stand for in this election. Usage: {helpers.PREFIX}posts')
    @checkers.voting_channel_check()
    async def posts(self, context):
        if helpers.standing:
            output_str = '```\n'
            for post in helpers.standing:
                output_str += post + '\n'
            output_str += '```'
        else:
            output_str = 'There are currently no posts set up in this election'
        await context.send(output_str)

    @commands.command(name='referenda', help=f'Prints the referenda to be voted on in this election. Usage: {helpers.PREFIX}referenda')
    @checkers.voting_channel_check()
    async def list_referenda(self, context):
        if helpers.referenda:
            output_str = '```\n'
            for title, description in helpers.referenda.items():
                output_str += f'{title}: {description}\n'
            output_str += '```'
        else:
            output_str = 'There are currently no referenda set up in this election'
        await context.send(output_str)

    @commands.command(name='candidates',
                 help='Prints the candidates for the specified post (or all posts if no post is given). '
                      f'Usage: {helpers.PREFIX}candidates [POST]', usage='[POST]')
    @checkers.voting_channel_check()
    async def list_candidates(self, context, *post):
        if not helpers.standing:
            await context.send('There are currently no posts set up in this election')
            return

        post = ' '.join(post)

        output_str = ''
        if post:
            matching_posts = helpers.match_post(post)
            if matching_posts:
                post = matching_posts[0]
                candidates = [(str(candidate), discordid) for candidate, _, discordid in helpers.standing[post].values()]
                random.shuffle(candidates)
                output_str += f'Candidates standing for {post}:\n'
                for candidate in candidates:
                    if candidate[1] == 42:
                        output_str += f' - {candidate[0]}\n'
                    else:
                        output_str += f' - {candidate[0]} - {(await self.bot.fetch_user(candidate[1])).display_name}\n'
                output_str += '--------\n'
            else:
                output_str = ('Looks like that post isn\'t in this election, '
                              f'use `{helpers.PREFIX}posts` to see the posts up for election`')
        else:
            for post in helpers.standing:
                candidates = [(str(candidate), discordid) for candidate, _, discordid in helpers.standing[post].values()]
                random.shuffle(candidates)
                output_str += f'Candidates standing for {post}:\n'
                for candidate in candidates:
                    if candidate[1] == 42:
                        output_str += f' - {candidate[0]}\n'
                    else:
                        output_str += f' - {candidate[0]} - {(await self.bot.fetch_user(candidate[1])).display_name}\n'
                output_str += '--------\n'

        if output_str:
            await context.send(output_str)

    @commands.command(name='rules', help=f'Prints the rules and procedures for the election. Usage: {helpers.PREFIX}rules')
    @checkers.voting_channel_check()
    async def rules(self, context):
        await context.send(f'To register to vote, DM me with `{helpers.PREFIX}register <STUDENT NUMBER>` '
                           f'(without the \'<>\')\n{helpers.RULES_STRING}')

    @commands.command(name='members', help=f'List current members - Committee Only. Usage: {helpers.PREFIX}members')
    @checkers.committee_channel_check()
    async def members(self, context):

        members = helpers.get_members()
        output_str = '```\n'
        for member in members.items():
            if (len(output_str) + len(str(member)) + 5) > 2000:
                output_str += '```'
                await context.send(output_str)
                output_str = '```\n'
            output_str += f'{member}\n'
        output_str += '```'
        await context.send(output_str)

# Error handling #

    async def committee_channel_error(self, context, error):
        if isinstance(error, commands.errors.NoPrivateMessage) or isinstance(error, commands.errors.CheckFailure):
            await context.send('This command is for committee only, please run in the designated committee channel')
            return True

    async def voting_channel_error(self, context, error):
        if isinstance(error, commands.errors.CheckFailure):
            await context.send('Please only run this command in DMs, or in the voting channel')
            return True

    @posts.error
    async def posts_error(self, context, error):
        traceback.print_exception(type(error), error, error.__traceback__)
        await self.voting_channel_error(context, error)

    @list_referenda.error
    async def list_referenda_error(self, context, error):
        traceback.print_exception(type(error), error, error.__traceback__)
        await self.voting_channel_error(context, error)

    @list_candidates.error
    async def list_candidates_error(self, context, error):
        traceback.print_exception(type(error), error, error.__traceback__)
        await self.voting_channel_error(context, error)

    @rules.error
    async def rules_error(self, context, error):
        traceback.print_exception(type(error), error, error.__traceback__)
        await self.voting_channel_error(context, error)

    @members.error
    async def members_error(self, context, error):
        traceback.print_exception(type(error), error, error.__traceback__)
        await self.committee_channel_error(context, error)


async def setup(bot):
    await bot.add_cog(Info(bot))
