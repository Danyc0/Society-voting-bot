# A Cog for running, and managing your run, in elections #

import traceback

from pyrankvote import Candidate

from discord.ext import commands
from cogs import helpers


class Running(commands.Cog):

    # Initialisation #

    def __init__(self, bot):
        self.bot = bot

    # Commands #

    @commands.command(name='stand', help=f'Stand for a post - DM Only. Usage: {helpers.PREFIX}stand <POST> <EMAIL ADDRESS>',
                 usage='<POST> <EMAIL ADDRESS>')
    @commands.dm_only()
    async def stand(self, context, *input):
        if not input:
            await context.send('Must supply the post you are running for and a valid email address, '
                               f'usage:`{helpers.PREFIX}stand <POST> <EMAIL>`')
            return
        email = input[-1]
        post = ' '.join(input[:-1])
        if not post:
            await context.send('Must supply the post you are running for and a valid email address, '
                               f'usage:`{helpers.PREFIX}stand <POST> <EMAIL>`')
            return
        if '@' not in email:
            await context.send('Must supply the post you are running for and a valid email address, '
                               f'usage:`{helpers.PREFIX}stand <POST> <EMAIL>`')
            return

        matching_posts = helpers.match_post(post)
        if not matching_posts:
            await context.send('Looks like that post isn\'t available for this election, '
                               f'use `{helpers.PREFIX}posts` to see the posts up for election')
            return
        post = matching_posts[0]
        async with helpers.current_live_post_lock.reader_lock:
            if helpers.current_live_post:
                if post == helpers.current_live_post[1]:
                    await context.send(f'I\'m afraid voting for {post} has already begun, you cannot stand for this post')
                    return

            author = context.author.id
            members = helpers.get_members()

            output_str = 'Error'
            if author in helpers.registered_members:
                if [i for i in helpers.standing[post] if i == helpers.registered_members[author]]:
                    output_str = (f'It looks like you, {members[helpers.registered_members[author]]} are already '
                                  f'standing for the position of: {post}')
                else:
                    helpers.standing[post][helpers.registered_members[author]] = (Candidate(members[helpers.registered_members[author]]), email, author)
                    output_str = (f'Congratulations {members[helpers.registered_members[author]]}, '
                                  f'you are now standing for the position of {post}. If you no longer wish to stand, you '
                                  f'can send `{helpers.PREFIX}standdown {post}`\n\n'
                                  'Now you\'ll need to prepare a 2 minute speech to be given in the election call.\n'
                                  f'If you have any questions please contact the secretary {helpers.SECRETARY_NAME}'
                                  f'({helpers.SECRETARY_EMAIL}), or someone else on the committee.\n'
                                  'If you can\'t make it to the actual election call, you must get in touch with the '
                                  'secretary ASAP to sort out alternative arrangements.')
                    helpers.log(f'{context.author.name}({helpers.registered_members[author]}) is now standing for {post}')
                    helpers.email_secretary(members[helpers.registered_members[author]], post)
            else:
                output_str = ('Looks like you\'re not registered yet, '
                              f'please register using `{helpers.PREFIX}register <STUDENT NUMBER>`')
                helpers.log(f'{context.author.name} has failed to stand for {post} because they are not registered')

        helpers.save_standing()
        await context.send(output_str)

    @commands.command(name='standdown', help=f'Stand down from running for a post - DM Only. Usage: {helpers.PREFIX}standdown <POST>',
                 usage='<POST>')
    @commands.dm_only()
    async def standdown(self, context, *post):
        post = ' '.join(post)
        if not post:
            await context.send(f'Must supply the post you are standing down from, usage: `{helpers.PREFIX}standdown <POST>`')
            return
        matching_posts = helpers.match_post(post)
        if not matching_posts:
            await context.send('Looks like that post isn\'t available for this election, '
                               f'use `{helpers.PREFIX}posts` to see the posts up for election`')
            return
        post = matching_posts[0]

        author = context.author.id

        if helpers.registered_members[author] not in helpers.standing[post]:
            await context.send('Looks like you weren\'t standing for this post')
            return

        helpers.email_secretary(str(helpers.standing[post][helpers.registered_members[author]][0]), post, stood_down=True)
        del helpers.standing[post][helpers.registered_members[author]]

        helpers.save_standing()

        helpers.log(f'{helpers.registered_members[author]} has stood down from standing for {post}')
        await context.send(f'You have stood down from running for {post}')

    @commands.command(name='changename', help='Change your name as used by the bot - DM Only. '
                                         f'Usage: {helpers.PREFIX}changename <NAME>', usage='<NAME>')
    @commands.dm_only()
    async def changename(self, context, *name):
    
        name = ' '.join(name)
        if not name:
            await context.send(f'Must supply the name you are wanting to change to, usage: `{helpers.PREFIX}changename <NAME>`')
            return
        if name.startswith('\''):
            name = name.strip('\'')
    
        author = context.author.id
        if author not in helpers.registered_members:
            await context.send('It looks like you\'re not registered yet, you must first register using '
                               f'`{helpers.PREFIX}register <STUDENT NUMBER>` before you can update your name')
            return
    
        async with helpers.current_live_post_lock.reader_lock:
            if helpers.current_live_post:
                await context.send('I\'m afraid you can\'t change your name whilst a vote is ongoing, '
                                   'please wait until the vote has finished')
                return
    
            author_id = helpers.registered_members[author]
            helpers.preferred_names[author_id] = name
    
            for post in helpers.standing:
                if author_id in helpers.standing[post]:
                    helpers.standing[post][author_id] = (Candidate(name), helpers.standing[post][author_id][1], author)
        helpers.save_names()
        helpers.save_standing()
    
        await context.send(f'The bot now recognises your name to be {name}')
        helpers.log(f'{context.author.name}({author_id}) has changed their name to {name}')

# Error handling #

    async def dm_error(self, context, error):
        if isinstance(error, commands.errors.PrivateMessageOnly):
            await context.send('This command is DM only, please try again in a private message to me.')
            return True

    @stand.error
    async def stand_error(self, context, error):
        traceback.print_exception(type(error), error, error.__traceback__)
        await self.dm_error(context, error)

    @standdown.error
    async def standdown_error(self, context, error):
        traceback.print_exception(type(error), error, error.__traceback__)
        await self.dm_error(context, error)

    @changename.error
    async def changename_error(self, context, error):
        traceback.print_exception(type(error), error, error.__traceback__)
        await self.dm_error(context, error)


async def setup(bot):
    await bot.add_cog(Running(bot))
