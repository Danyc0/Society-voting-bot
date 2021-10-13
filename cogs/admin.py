# A Cog for admin only commands #

import random
import asyncio
import pyrankvote

from pyrankvote import Candidate

from discord.ext import commands
from cogs import helpers, checkers


class Admin(commands.Cog):
    # Initialisation #

    def __init__(self, bot):
        self.bot = bot

    # Commands for Initialising Elections #

    @commands.command(name='referendum', help='Creates the specified referendum. '
                                         'Note that both fields MUST be passed within quotes - Committee Only. '
                                         f'Usage: {helpers.PREFIX}referendum <TITLE> <DESCRIPTION>', usage='<TITLE> <DESCRIPTION>')
    @checkers.committee_channel_check()
    async def referendum(self, context, title, *description):
        description = ' '.join(description)
        if description.startswith('\''):
            description = description.strip('\'')

        matching_referenda = helpers.match_referendum(title)
        if matching_referenda:
            await context.send(f'{title} already exists')
            return

        helpers.referenda[title] = description

        helpers.save_referenda()

        helpers.log(f'The referendum for \"{title}\" has been created')
        await context.send(f'The referendum for \"{title}\" has been created')

    @commands.command(name='setup', help=f'Creates the specified post - Committee Only. Usage: {helpers.PREFIX}setup <POST>',
                 usage='<POST>')
    @checkers.committee_channel_check()
    async def setup(self, context, *post):
        post = ' '.join(post)
        matching_posts = helpers.match_post(post)
        if matching_posts:
            await context.send(f'{post} already exists')
            return

        helpers.standing[post] = {0: (Candidate('RON (Re-Open Nominations)'), 'ron@example.com', 42)}

        helpers.save_standing()

        helpers.log(f'The post of {post} has been created')
        await context.send(f'The post of {post} has been created')

    @commands.command(name='begin', help='Begins the election for the specified post/referendum - Committee Only. '
                                    f'Usage: {helpers.PREFIX}begin <POST/TITLE>', usage='<POST/TITLE>')
    @checkers.voting_channel_only()
    @checkers.committee_member_check()
    async def begin(self, context, *post):
        post = ' '.join(post)
        if not post:
            await context.send('Must supply the post/referendum title you are starting the vote for, usage:'
                               f'`{helpers.PREFIX}begin <POST/TITLE>`')
            return
        matching_posts = helpers.match_post(post)
        type = 'POST'
        if not matching_posts:
            matching_posts = helpers.match_referendum(post)
            type = 'REFERENDUM'
            if not matching_posts:
                await context.send('Looks like that post/referendum isn\'t available for this election, '
                                   f'use `{helpers.PREFIX}posts` to see the posts up for election or '
                                   f'or use `{helpers.PREFIX}referenda` to see the referenda that will be voted upon')
                return

        async with helpers.current_live_post_lock.writer_lock:
            if helpers.current_live_post:
                await context.send('You can\'t start a new vote until the last one has finished')
                return
            post = matching_posts[0]

            helpers.current_live_post = (type, post)
        helpers.log(f'Voting has now begun for: {post}')

        if type == 'POST':
            num_candidates = len(helpers.standing[post])
            max_react = list(helpers.EMOJI_LOOKUP)[num_candidates-1]

            for voter in helpers.registered_members:
                user = await self.bot.fetch_user(voter)
                await user.send(f'Ballot paper for: {post}, there are {num_candidates} candidates. '
                                f'(Please react to the messages below with :one:-{max_react}). '
                                f'**Don\'t forget to **`{helpers.PREFIX}submit <CODE>`** when you\'re done**:\n')
                # Make sure the header arrives before the ballot paper
                await asyncio.sleep(0.2)

                # Message the member with the shuffled candidate list, each in a separate message, record the message ID
                candidates = list(helpers.standing[post].items())
                random.shuffle(candidates)
                helpers.voting_messages[user.id] = []
                for student_id, details in candidates:
                    message = await user.send(f' - {str(details[0])}')
                    # Need to store A. the user it was sent to, B. Which candidate is in the message, C. The message ID
                    helpers.voting_messages[user.id].append((student_id, message.id))

            await context.send(f'Voting has now begun for: {post}\n'
                               'All registered voters will have just received a message from me. '
                               'Please vote by reacting to the candidates listed in your DMs where '
                               ':one: is your top candidate, :two: is your second top candidate, etc. '
                               'You do not need to put a ranking in for every candidate')
        else:
            for voter in helpers.registered_members:
                user = await self.bot.fetch_user(voter)
                await user.send(f'Ballot paper for: {post}. Please react to the message for your choice below with '
                                ':ballot_box_with_check: (\\:ballot_box_with_check\\:). '
                                f'**Don\'t forget to **`{helpers.PREFIX}submit <CODE>`** when you\'re done**:\n')
                # Make sure the header arrives before the ballot paper
                await asyncio.sleep(0.2)

                # Message the member with the options list, each in a separate message, record the ID of the message
                helpers.voting_messages[user.id] = []
                for option in helpers.referendum_options:
                    message = await user.send(f' - {str(option)}')
                    # Need to store A. the user it was sent to, B. Which candidate is in the message, C. The message ID
                    helpers.voting_messages[user.id].append((option, message.id))

            await context.send(f'Voting has now begun for: {post}\n'
                               'All registered voters will have just received a message from me. Please vote by '
                               'reacting :ballot_box_with_check: to either the \'For\' or \'Against\' message '
                               'in your DMs')
            
    @commands.command(name='end', help=f'Ends the election for the currently live post - Committee Only. Usage: {helpers.PREFIX}end')
    @checkers.voting_channel_only()
    @checkers.committee_member_check()
    async def end(self, context):
        voting_channel = await self.bot.fetch_channel(helpers.VOTING_CHANNEL_ID)
        committee_channel = await self.bot.fetch_channel(helpers.COMMITTEE_CHANNEL_ID)
    
        last_live_post = helpers.current_live_post
        async with helpers.current_live_post_lock.writer_lock:
            helpers.current_live_post = None
        helpers.voting_messages.clear()
        async with helpers.voted_lock:
            helpers.voted.clear()
    
        await voting_channel.send(f'Voting has now ended for: {last_live_post[1]}')
    
        async with helpers.votes_lock.writer_lock:
            if last_live_post[0] == 'POST':
                results = pyrankvote.instant_runoff_voting([i for i, _, _ in helpers.standing[last_live_post[1]].values()],
                                                           helpers.votes)
            else:
                results = pyrankvote.instant_runoff_voting(helpers.referendum_options, helpers.votes)
    
            helpers.votes.clear()
    
        # Announce the scores and the winner to the committee
        winner = results.get_winners()[0]
    
        helpers.log(f'Result: {results}')
        helpers.log(f'Winner: {winner}')
    
        if last_live_post[0] == 'POST':
            await committee_channel.send('The votes were tallied as follows:\n'
                                         f'```{results}```\n'
                                         f'The winning candidate for the post of {last_live_post[1]} is: {winner}')
        else:
            await committee_channel.send('The votes were tallied as follows:\n'
                                         f'```{results}```\n'
                                         f'The result for the referendum on {last_live_post[1]} is: {winner}')
    
        helpers.log(f'Voting has now ended for: {last_live_post[1]}')
        for voter in helpers.registered_members:
            user = await self.bot.fetch_user(voter)
            await user.send(f'Voting has now ended for: {last_live_post[1]}')
        
    # Additional Commands for editing elections #

    @commands.command(name='rename', help='Renames the specified post. '
                                     'Note that both post names MUST be passed within quotes - Committee Only. '
                                     f'Usage: {helpers.PREFIX}rename <OLD POST> <NEW POST>', usage='<OLD POST> <NEW POST>')
    @checkers.committee_channel_check()
    async def rename(self, context, old_post, new_post):
        matching_posts = helpers.match_post(old_post)
        if not matching_posts:
            await context.send(f'{old_post} doesn\'t exist')
            return

        helpers.standing[new_post] = helpers.standing.pop(matching_posts[0])

        helpers.save_standing()

        helpers.log(f'The post of {matching_posts[0]} has been renamed to {new_post}')
        await context.send(f'The post of {matching_posts[0]} has been renamed to {new_post}')

    @commands.command(name='delete', help='Deletes the specified post. '
                                     'Note that both post names MUST be passed within quotes - Committee Only. '
                                     f'Usage: {helpers.PREFIX}delete <POST>', usage='<POST>')
    @checkers.committee_channel_check()
    async def delete(self, context, *, post):
        def check(msg):
            return msg.author == context.author and msg.channel == context.channel

        matching_posts = helpers.match_post(post)
        if not matching_posts:
            await context.send(f'{post} doesn\'t exist')
            return

        post = matching_posts[0]

        if helpers.standing[post].items():
            if not (len(helpers.standing[post]) == 1 and helpers.standing[post][0]):
                await context.send(f'Members are already running for {post}, would you like to delete it? [(y)es/(n)o]')
                while True:
                    msg = await self.bot.wait_for('message', check=check, timeout=60)
                    if msg.content.lower() in ['y', 'yes']:
                        break
                    elif msg.content.lower() in ['n', 'no']:
                        await context.send('Delete cancelled')
                        return
                    else:
                        await context.send('I didn\'t understand that, please answer (y)es or (n)o')

        helpers.standing.pop(post)
        await context.send(f'{post} deleted')
        return

    @commands.command(name='takedown', help='Stands a specific user down on their behalf - Committee Only. '
                                       f'Usage: {helpers.PREFIX}takedown <STUDENT ID> <POST>', usage='<STUDENT ID> <POST>')
    @checkers.committee_channel_check()
    async def takedown(self, context, student_id: int, *post):
        post = ' '.join(post)
        if not post:
            await context.send('You must supply the user to stand down and the post you are standing them down from, '
                               f'usage: `{helpers.PREFIX}takedown <STUDENT NUMBER> <POST>`')
            return
        matching_posts = helpers.match_post(post)
        if not matching_posts:
            await context.send('Looks like that post isn\'t available for this election, '
                               f'use `{helpers.PREFIX}posts` to see the posts up for election`')
            return
        post = matching_posts[0]

        if student_id not in helpers.standing[post]:
            await context.send('Looks like this user isn\'t standing for this post')
            return

        helpers.email_secretary(str(helpers.standing[post][student_id][0]), post, stood_down=True)
        del helpers.standing[post][student_id]

        helpers.save_standing()

        helpers.log(f'{student_id} has been stood down from standing for {post}')
        await context.send(f'{student_id} has been stood down from running for {post}')


    @commands.command(name='resetname', help='Resets the name of the person with a given student number - Committee Only. '
                                        f'Usage: {helpers.PREFIX}resetname <STUDENT NUMBER>', usage='<STUDENT NUMBER>')
    @checkers.committee_channel_check()
    async def resetname(self, context, student_id: int):
        if student_id not in helpers.preferred_names:
            await context.send('The supplied student ID has not updated their name')
            return

        async with helpers.current_live_post_lock.reader_lock:
            if helpers.current_live_post:
                await context.send('I\'m afraid you can\'t reset a name whilst a vote is ongoing, '
                                   f'please wait until the vote has finished, or end it early using `{helpers.PREFIX}end`')
                return

            del helpers.preferred_names[student_id]

            union_name = helpers.get_members()[student_id]

            for post in helpers.standing:
                if student_id in helpers.standing[post]:
                    helpers.standing[post][student_id] = (Candidate(union_name), helpers.standing[post][student_id][1], context.author.id)
        helpers.save_names()
        helpers.save_standing()

        helpers.log(f'The name used for {student_id} has been reset')
        await context.send(f'The name used for {student_id} has been reset')

# Error Handling #

    # Returns a value so we can check if that check has failed before potentially
    # Exposing command structure to unverified users
    async def committee_channel_error(self, context, error):
        if isinstance(error, commands.errors.NoPrivateMessage) or isinstance(error, commands.errors.CheckFailure):
            await context.send('This command is for committee only, please run in the designated committee channel')
            return True

    async def voting_channel_error(self, context, error):
        if isinstance(error, commands.errors.NoPrivateMessage) or isinstance(error, commands.errors.CheckFailure):
            await context.send('This command is for committee only, please run in the designated voting channel')
            return True

    @referendum.error
    async def referendum_error(self, context, error):
        if not await self.committee_channel_error(context, error):
            if isinstance(error, commands.errors.MissingRequiredArgument):
                await context.send(f'Must supply a name and description for the new referendum. Usage: `{helpers.PREFIX}referendum <TITLE> <DESCRIPTION>`')

    @setup.error
    async def setup_error(self, context, error):
        if not await self.committee_channel_error(context, error):
            if isinstance(error, commands.errors.MissingRequiredArgument):
                await context.send(f'Must supply a name for the new post. Usage: `{helpers.PREFIX}setup <NEW_POST>`')

    @begin.error
    async def begin_error(self, context, error):
        if not await self.voting_channel_error(context, error):
            if isinstance(error, commands.errors.MissingRequiredArgument):
                await context.send('Must supply the post/referendum title you are starting the vote for, usage:'
                                    f'`{helpers.PREFIX}begin <POST/TITLE>`')

    @end.error
    async def end_error(self, context, error):
        await self.voting_channel_error(context, error)

    @rename.error
    async def rename_error(self, context, error):
        if not await self.committee_channel_error(context, error):
            if isinstance(error, commands.errors.MissingRequiredArgument):
                await context.send(f'You must supply a post and the new name. Usage: `{helpers.PREFIX}rename <OLD_POST> <NEW_POST>`')

    @delete.error
    async def delete_error(self, context, error):
        if not await self.committee_channel_error(context, error):
            if isinstance(error, commands.errors.MissingRequiredArgument):
                await context.send(f'You must supply a post to delete. Usage: `{helpers.PREFIX}delete <POST>`')

    @takedown.error
    async def takedown_error(self, context, error):
        if not await self.committee_channel_error(context, error):
            if isinstance(error, commands.errors.MissingRequiredArgument):
                await context.send(f'You must supply a student ID and post to standdown a user. Usage: `{helpers.PREFIX}takedown <STUDENT_NUMBER> <POST>`')
            if isinstance(error, commands.errors.BadArgument):
                await context.send(f'Please make sure you send a student number with the post to standdown a user. Usage: `{helpers.PREFIX}takedown <STUDENT_NUMBER> <POST>`')

    @resetname.error
    async def resetname_error(self, context, error):
        if not await self.committee_channel_error(context, error):
            if isinstance(error, commands.errors.MissingRequiredArgument) or isinstance(error, commands.errors.BadArgument):
                await context.send(f'You must supply a student ID. Usage: `{helpers.PREFIX}resetname <STUDENT NUMBER>`')


def setup(bot):
    bot.add_cog(Admin(bot))
