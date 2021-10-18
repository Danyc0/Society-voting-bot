# A Cog for commands to register and vote in elections #

from pyrankvote import Ballot

from discord.ext import commands
from cogs import helpers


class Voting(commands.Cog):

    # Initialisation #

    def __init__(self, bot):
        self.bot = bot

    # Commands for Voting in Elections #

    @commands.command(name='register', help=f'Register to vote - DM Only. Usage: {helpers.PREFIX}register <STUDENT NUMBER>',
                 usage='<STUDENT NUMBER>')
    @commands.dm_only()
    async def register(self, context, student_number: int):

        author = context.author.id
        members = helpers.get_members()

        output_str = 'Error'
        if student_number in members:
            if author in helpers.registered_members:
                output_str = f'Looks like your Discord username is already registered to {helpers.registered_members[author]}'
            elif student_number in helpers.registered_members.values():
                output_str = ('Looks like your student ID is already registered to someone else, '
                              'please contact a committee member')
                other_user_id = [key for key, value in helpers.registered_members.items() if value == student_number][0]
                other_user = await self.bot.fetch_user(other_user_id).name
                helpers.log(f'{context.author} tried to register student ID {student_number}, '
                    f'but it\'s already registered to {other_user}')
            else:
                helpers.registered_members[author] = student_number
                output_str = f'Thank you {members[helpers.registered_members[author]]}, you are now registered\n\n{helpers.RULES_STRING}'
                helpers.log(f'{helpers.registered_members[author]} is now registered')
        else:
            output_str = f'Looks like you\'re not a member yet, please become a member here: {helpers.JOIN_LINK}'
            helpers.log(f'{context.author.name} has failed to register because they are not a member')

        helpers.save_voters()
        await context.send(output_str)

    @commands.command(name='submit', help=f'Submits your vote - DM Only. Usage: {helpers.PREFIX}submit <VOTING CODE>',
                 usage='<VOTING CODE>')
    @commands.dm_only()
    async def submit(self, context, code):
        # Only work for users who got sent messages
        author = context.author.id
        if author not in helpers.voting_messages:
            return

        if code.upper() != helpers.VOTING_CODE:
            await context.send('The code you have supplied is incorrect, '
                               'you must use the one given out in the election call, your vote was not cast')
            return

        valid = await self.validate(context)
        if not valid:
            await context.send('Your vote was not cast, please correct your ballot and resubmit')
            return

        async with helpers.voted_lock:
            if author in helpers.voted:
                await context.send('You have already cast your vote and it cannot be changed')
                return

            async with helpers.votes_lock.reader_lock:
                async with helpers.current_live_post_lock.reader_lock:
                    if helpers.current_live_post[0] == 'POST':
                        ballot_list = [''] * len(helpers.standing[helpers.current_live_post[1]])

                        # Create ballot
                        for candidate, message_id in helpers.voting_messages[author]:
                            message = await context.author.fetch_message(message_id)
                            if message.reactions:
                                reaction = message.reactions[0].emoji
                                ballot_list[helpers.EMOJI_LOOKUP[reaction]] = helpers.standing[helpers.current_live_post[1]][candidate][0]

                        helpers.votes.append(Ballot(ranked_candidates=[ballot for ballot in ballot_list if str(ballot) != '']))
                    else:
                        # Create ballot
                        for option, message_id in helpers.voting_messages[author]:
                            message = await context.author.fetch_message(message_id)
                            if message.reactions:
                                helpers.votes.append(Ballot(ranked_candidates=[option]))
                                break
                        else:
                            helpers.votes.append(Ballot(ranked_candidates=[]))

                    helpers.voted.append(author)
                await context.send('Your vote was successfully cast')
                helpers.log(f'Votes cast: {len(helpers.votes)} - Votes not yet cast: {len(helpers.registered_members)-len(helpers.votes)}')

    @commands.command(name='validate', help=f'Checks to see if your vote will be accepted - DM Only. Usage: {helpers.PREFIX}validate')
    @commands.dm_only()
    async def validate(self, context):
        # Only work for users who got sent messages
        author = context.author.id
        if author not in helpers.voting_messages:
            return False

        await context.send('Checking vote validity ...')
        async with helpers.current_live_post_lock.reader_lock:
            if helpers.current_live_post[0] == 'POST':
                return await self.validate_post(context, author)
            else:
                return await self.validate_referendum(context, author)

    async def validate_post(self, context, author):
        valid = True
        all_reactions = []
        output_str = ''
        for candidate, message_id in helpers.voting_messages[author]:
            message = await context.author.fetch_message(message_id)

            # Check if there is more than one react
            if len(message.reactions) > 1:
                output_str += 'You can\'t react to each candidate with more than one emoji\n'
                valid = False

            for reaction in message.reactions:
                # Check if react is not valid
                if reaction.emoji not in helpers.EMOJI_LOOKUP:
                    output_str += f'You have reacted with an invalid emoji: {reaction.emoji}\n'
                    valid = False
                else:
                    all_reactions.append(reaction.emoji)

        for reaction in helpers.EMOJI_LOOKUP:
            # Check if they put the same ranking to more than one candidate
            if all_reactions.count(reaction) > 1:
                output_str += 'You can\'t react to more than one candidate with the same value\n'
                valid = False

        # Check if they try to do :three: before :two:, etc
        if len(all_reactions) != 0:
            max_value = helpers.EMOJI_LOOKUP[max(all_reactions, key=lambda x: helpers.EMOJI_LOOKUP[x])]
            if max_value >= len(helpers.standing[helpers.current_live_post[1]]):
                output_str += 'You\'ve given a ranking that is higher than the number of candidates\n'
                valid = False
            else:
                for i in range(max_value):
                    react_to_check = list(helpers.EMOJI_LOOKUP)[i]
                    if react_to_check not in all_reactions:
                        output_str += f'Looks like you\'ve skipped ranking {react_to_check}\n'
                        valid = False

        if not output_str:
            output_str = 'Your vote was valid'
        await context.send(output_str)
        return valid

    async def validate_referendum(self, context, author):
        valid = True
        all_reactions = []
        output_str = ''
        for candidate, message_id in helpers.voting_messages[author]:
            message = await context.author.fetch_message(message_id)

            for reaction in message.reactions:
                # Check if react is not valid
                if reaction.emoji != '☑️':
                    output_str += (f'You have reacted with an invalid emoji: {reaction.emoji}, '
                                   'you need to use :ballot_box_with_check:\n')
                    valid = False
                else:
                    all_reactions.append(reaction.emoji)

        if len(all_reactions) > 1:
            output_str += 'You can\'t react with more than one emoji\n'
            valid = False

        if not output_str:
            output_str = 'Your vote was valid'
        await context.send(output_str)
        return valid

# Error handling #

    async def dm_error(self, context, error):
        if isinstance(error, commands.errors.PrivateMessageOnly):
            await context.send('This command is DM only, please try again in a private message to me.')
            return True

    @register.error
    async def register_error(self, context, error):
        helpers.log(error)
        if not await self.dm_error(context, error):
            if isinstance(error, commands.errors.MissingRequiredArgument):
                await context.send(f'Must supply a student number. Usage: {helpers.PREFIX}register <STUDENT NUMBER>')

    @submit.error
    async def submit_error(self, context, error):
        helpers.log(error)
        if not await self.dm_error(context, error):
            if isinstance(error, commands.errors.MissingRequiredArgument):
                await context.send(f'You must supply the code given out in the election call, your vote was not cast. Usage: {helpers.PREFIX}submit <VOTING CODE>')

    @validate.error
    async def validate_error(self, context, error):
        helpers.log(error)
        await self.dm_error(context, error)

def setup(bot):
    bot.add_cog(Voting(bot))
