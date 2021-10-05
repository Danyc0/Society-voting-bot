import os
import time
import datetime
import random
import pickle
import smtplib
import ssl
import asyncio

import aiorwlock

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

import pyrankvote
from pyrankvote import Candidate, Ballot

from discord.ext import commands
from discord.channel import DMChannel

import society_members

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

RULES_STRING = (
                f'To stand for a position, DM me with `{PREFIX}stand <POST> <EMAIL>`, where <POST> is the post you '
                'wish to stand for and <EMAIL> is your email address (both without the \'<>\') , you can see all '
                f'posts available by sending `{PREFIX}posts`\n\n'
                'When voting begins, I will DM you a ballot paper. To vote, you\'ll need to react to the candidates '
                'in that ballot paper, where :one: is your top candidate, :two: is your second top candidate, etc\n'
                'The rules for filling in the ballot are as follows:\n'
                '- You don\'t have to use all your rankings, but don\'t leave any gaps '
                '(e.g. you can\'t give a candidate :three: without giving some candidate :two:)\n'
                '- Don\'t react with any reactions other than the number reacts :one: - :nine:\n'
                '- Don\'t react with a ranking higher than the number of candidates '
                '(e.g. if there are three candidates, don\'t react :four: to any candidates)\n'
                '- Don\'t vote for one candidate multiple times\n'
                '- Don\'t give the same ranking to multiple candidates\n\n'
                f'**Once you are happy with your ballot, please submit your vote by sending **`{PREFIX}submit <CODE>` '
                'where <CODE> is the code given out in the election call\n'
                'When you submit your ballot, it will be checked against the rules and if something\'s not right, '
                'you\'ll be asked to fix it and will need to submit again'
)

EMOJI_LOOKUP = {
    '1️⃣': 0,
    '2️⃣': 1,
    '3️⃣': 2,
    '4️⃣': 3,
    '5️⃣': 4,
    '6️⃣': 5,
    '7️⃣': 6,
    '8️⃣': 7,
    '9️⃣': 8,
}

GOOGLE_SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


# Name of the post that is currently live. Format = (<'POST'/'REFERENDUM'>, <Post Name/Referendum Title>)
current_live_post = None

# Format = [<Ballot>]
votes = []

# Format = [<Student Number>]
voted = []

# Format = {<Discord Username>: <Student Number>}
registered_members = {}

# Format = {<Post>: {<Student Number>: (<Candidate Object>, <Email>), ...}, ...}
standing = {}

# Format = {<Title>: <Description>, ...}
referenda = {}
referendum_options = [Candidate('For'), Candidate('Against')]

# Format = {<Student Number>: <Preferred Name>, ...}
preferred_names = {}

# Format = {<User ID>: [(<Candidate Student ID>, <Message ID>), ...], ...}
voting_messages = {}


def log(output_str):
    print(datetime.datetime.now().strftime('%d/%m/%y %H:%M:%S: ') + output_str)


def get_members():
    members = society_members.get_members()
    members[0] = 'RON (Re-Open-Nominations)'

    # Substitute preferred names
    for id in preferred_names:
        members[id] = preferred_names[id]

    return members


def email_secretary(candidate, post, stood_down=False):
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)

        message = MIMEMultipart('alternative')
        message['From'] = SENDER_EMAIL
        message['To'] = SECRETARY_EMAIL

        if not stood_down:
            message['Subject'] = 'New candidate standing in the upcoming election'
            text = ('Hello,\n'
                    f'{candidate} has just stood for the position of {post} '
                    'in the upcoming election,\n'
                    'Goodbye')
        else:
            message['Subject'] = 'Candidate no longer standing in the upcoming election'
            text = ('Hello,\n'
                    f'{candidate} has just stood down from standing for the position of {post} '
                    'in the upcoming election,\n'
                    'Goodbye')

        # Turn the message text into a MIMEText object and add it to the MIMEMultipart message
        message.attach(MIMEText(text, 'plain'))
        server.sendmail(SENDER_EMAIL, SECRETARY_EMAIL, message.as_string())


def save_voters():
    with open(VOTERS_FILE, 'wb') as out_file:
        pickle.dump(registered_members, out_file)


def save_names():
    with open(NAMES_FILE, 'wb') as out_file:
        pickle.dump(preferred_names, out_file)


def save_standing():
    with open(STANDING_FILE, 'wb') as out_file:
        pickle.dump(standing, out_file)

    service.spreadsheets().values().clear(spreadsheetId=SHEET_ID, range='A2:D100').execute()
    values = []
    for post, candidates in standing.items():
        for student_id, candidate in candidates.items():
            if student_id == 0:
                continue
            values.append([str(candidate[0]), candidate[1], str(student_id), post])

    body = {
        'values': values
    }
    service.spreadsheets().values().update(spreadsheetId=SHEET_ID, range='A2',
                                           valueInputOption='RAW', body=body).execute()


def save_referenda():
    with open(REFERENDA_FILE, 'wb') as out_file:
        pickle.dump(referenda, out_file)


def is_dm(channel):
    return isinstance(channel, DMChannel)


def is_voting_channel(channel):
    return channel.id == VOTING_CHANNEL_ID


def is_committee_channel(channel):
    return channel.id == COMMITTEE_CHANNEL_ID


def is_committee_member(user):
    return any([True for role in user.roles if str(role) == COMMITTEE_ROLE])


def match_post(post):
    return [a for a in standing if a.lower() == post.lower()]


def match_referendum(referendum):
    return [a for a in referenda if a.lower() == referendum.lower()]


@bot.event
async def on_ready():
    global committee_channel
    global voting_channel
    committee_channel = bot.get_channel(COMMITTEE_CHANNEL_ID)
    voting_channel = bot.get_channel(VOTING_CHANNEL_ID)

    global current_live_post_lock
    global votes_lock
    global voted_lock
    current_live_post_lock = aiorwlock.RWLock()
    votes_lock = aiorwlock.RWLock()
    voted_lock = asyncio.Lock()

    print(f'{bot.user.name} has connected to Discord and is in the following channels:')
    for guild in bot.guilds:
        print(' -', guild.name)


@bot.command(name='members', help=f'List current members - Committee Only. Usage: {PREFIX}members')
async def members(context):
    if not is_committee_channel(context.channel):
        return

    members = get_members()
    output_str = '```\n'
    for member in members.items():
        if (len(output_str) + len(str(member)) + 5) > 2000:
            output_str += '```'
            await context.send(output_str)
            output_str = '```\n'
        output_str += f'{member}\n'
    output_str += '```'
    await context.send(output_str)


@bot.command(name='register', help=f'Register to vote - DM Only. Usage: {PREFIX}register <STUDENT NUMBER>',
             usage='<STUDENT NUMBER>')
async def register(context, student_number: int):
    if not is_dm(context.channel):
        await context.send('You need to DM me for this instead')
        return

    author = context.author.id
    members = get_members()

    output_str = 'Error'
    if student_number in members:
        if author in registered_members:
            output_str = f'Looks like your Discord username is already registered to {registered_members[author]}'
        elif student_number in registered_members.values():
            output_str = ('Looks like your student ID is already registered to someone else, '
                          'please contact a committee member')
            other_user_id = [key for key, value in registered_members.items() if value == student_number][0]
            other_user = await bot.fetch_user(other_user_id).name
            log(f'{context.author} tried to register student ID {student_number}, '
                f'but it\'s already registered to {other_user}')
        else:
            registered_members[author] = student_number
            output_str = f'Thank you {members[registered_members[author]]}, you are now registered\n\n{RULES_STRING}'
            log(f'{registered_members[author]} is now registered')
    else:
        output_str = f'Looks like you\'re not a member yet, please become a member here: {JOIN_LINK}'
        log(f'{context.author.name} has failed to register because they are not a member')

    save_voters()
    await context.send(output_str)


@bot.command(name='stand', help=f'Stand for a post - DM Only. Usage: {PREFIX}stand <POST> <EMAIL ADDRESS>',
             usage='<POST> <EMAIL ADDRESS>')
async def stand(context, *input):
    if not is_dm(context.channel):
        await context.send('You need to DM me for this instead')
        return
    if not input:
        await context.send('Must supply the post you are running for and a valid email address, '
                           f'usage:`{PREFIX}stand <POST> <EMAIL>`')
        return
    email = input[-1]
    post = ' '.join(input[:-1])
    if not post:
        await context.send('Must supply the post you are running for and a valid email address, '
                           f'usage:`{PREFIX}stand <POST> <EMAIL>`')
        return
    if '@' not in email:
        await context.send('Must supply the post you are running for and a valid email address, '
                           f'usage:`{PREFIX}stand <POST> <EMAIL>`')
        return

    matching_posts = match_post(post)
    if not matching_posts:
        await context.send('Looks like that post isn\'t available for this election, '
                           f'use `{PREFIX}posts` to see the posts up for election')
        return
    post = matching_posts[0]
    async with current_live_post_lock.reader_lock:
        if current_live_post:
            if post == current_live_post[1]:
                await context.send(f'I\'m afraid voting for {post} has already begun, you cannot stand for this post')
                return

        author = context.author.id
        members = get_members()

        output_str = 'Error'
        if author in registered_members:
            if [i for i in standing[post] if i == registered_members[author]]:
                output_str = (f'It looks like you, {members[registered_members[author]]} are already '
                              f'standing for the position of: {post}')
            else:
                standing[post][registered_members[author]] = (Candidate(members[registered_members[author]]), email, author)
                output_str = (f'Congratulations {members[registered_members[author]]}, '
                              f'you are now standing for the position of {post}. If you no longer wish to stand, you '
                              f'can send `{PREFIX}standdown {post}`\n\n'
                              'Now you\'ll need to prepare a 2 minute speech to be given in the election call.\n'
                              f'If you have any questions please contact the secretary {SECRETARY_NAME}'
                              f'({SECRETARY_EMAIL}), or someone else on the committee.\n'
                              'If you can\'t make it to the actual election call, you must get in touch with the '
                              'secretary ASAP to sort out alternative arrangements.')
                log(f'{context.author.name}({registered_members[author]}) is now standing for {post}')
                email_secretary(members[registered_members[author]], post)
        else:
            output_str = ('Looks like you\'re not registered yet, '
                          f'please register using `{PREFIX}register <STUDENT NUMBER>`')
            log(f'{context.author.name} has failed to stand for {post} because they are not registered')

    save_standing()
    await context.send(output_str)


@bot.command(name='standdown', help=f'Stand down from running for a post - DM Only. Usage: {PREFIX}standdown <POST>',
             usage='<POST>')
async def standdown(context, *post):
    if not is_dm(context.channel):
        await context.send('You need to DM me for this instead')
        return

    post = ' '.join(post)
    if not post:
        await context.send(f'Must supply the post you are standing down from, usage: `{PREFIX}standdown <POST>`')
        return
    matching_posts = match_post(post)
    if not matching_posts:
        await context.send('Looks like that post isn\'t available for this election, '
                           f'use `{PREFIX}posts` to see the posts up for election`')
        return
    post = matching_posts[0]

    author = context.author.id

    if registered_members[author] not in standing[post]:
        await context.send('Looks like you weren\'t standing for this post')
        return

    email_secretary(str(standing[post][registered_members[author]][0]), post, stood_down=True)
    del standing[post][registered_members[author]]

    save_standing()

    log(f'{registered_members[author]} has stood down from standing for {post}')
    await context.send(f'You have stood down from running for {post}')


@bot.command(name='takedown', help='Stands a specific user down on their behalf - Committee Only. '
                                   f'Usage: {PREFIX}takedown <STUDENT ID> <POST>', usage='<STUDENT ID> <POST>')
async def takedown(context, student_id: int, *post):
    if not is_committee_member(context.author):
        return

    post = ' '.join(post)
    if not post:
        await context.send('You must supply the user to stand down and the post you are standing them down from, '
                           f'usage: `{PREFIX}takedown <STUDENT NUMBER> <POST>`')
        return
    matching_posts = match_post(post)
    if not matching_posts:
        await context.send('Looks like that post isn\'t available for this election, '
                           f'use `{PREFIX}posts` to see the posts up for election`')
        return
    post = matching_posts[0]

    if student_id not in standing[post]:
        await context.send('Looks like this user isn\'t standing for this post')
        return

    email_secretary(str(standing[post][student_id][0]), post, stood_down=True)
    del standing[post][student_id]

    save_standing()

    log(f'{student_id} has been stood down from standing for {post}')
    await context.send(f'{student_id} has been stood down from running for {post}')


@bot.command(name='changename', help='Change your name as used by the bot - DM Only. '
                                     f'Usage: {PREFIX}changename <NAME>', usage='<NAME>')
async def changename(context, *name):
    if not is_dm(context.channel):
        await context.send('You need to DM me for this instead')
        return

    name = ' '.join(name)
    if not name:
        await context.send(f'Must supply the name you are wanting to change to, usage: `{PREFIX}changename <NAME>`')
        return
    if name.startswith('\''):
        name = name.strip('\'')

    author = context.author.id
    if author not in registered_members:
        await context.send('It looks like you\'re not registered yet, you must first register using '
                           f'`{PREFIX}register <STUDENT NUMBER>` before you can update your name')
        return

    async with current_live_post_lock.reader_lock:
        if current_live_post:
            await context.send('I\'m afraid you can\'t change your name whilst a vote is ongoing, '
                               'please wait until the vote has finished')
            return

        author_id = registered_members[author]
        preferred_names[author_id] = name

        for post in standing:
            if author_id in standing[post]:
                standing[post][author_id] = (Candidate(name), standing[post][author_id][1], author)
    save_names()
    save_standing()

    await context.send(f'The bot now recognises your name to be {name}')
    log(f'{context.author.name}({author_id}) has changed their name to {name}')


@bot.command(name='resetname', help='Resets the name of the person with a given student number - Committee Only. '
                                    f'Usage: {PREFIX}resetname <STUDENT NUMBER>', usage='<STUDENT NUMBER>')
async def resetname(context, student_id: int):
    if not is_committee_channel(context.channel):
        return

    if not student_id:
        await context.send(f'You must supply a student ID. Usage: `{PREFIX}resetname <STUDENT NUMBER>`')
        return

    if student_id not in preferred_names:
        await context.send('The supplied student ID has not updated their name')
        return

    async with current_live_post_lock.reader_lock:
        if current_live_post:
            await context.send('I\'m afraid you can\'t reset a name whilst a vote is ongoing, '
                               f'please wait until the vote has finished, or end it early using `{PREFIX}end`')
            return

        del preferred_names[student_id]

        union_name = get_members()[student_id]

        for post in standing:
            if student_id in standing[post]:
                standing[post][student_id] = (Candidate(union_name), standing[post][student_id][1], context.author.id)
    save_names()
    save_standing()

    log(f'The name used for {student_id} has been reset')
    await context.send(f'The name used for {student_id} has been reset')


@bot.command(name='posts', help=f'Prints the posts available to stand for in this election. Usage: {PREFIX}posts')
async def posts(context):
    if not is_dm(context.channel) and not is_voting_channel(context.channel):
        return

    if standing:
        output_str = '```\n'
        for post in standing:
            output_str += post + '\n'
        output_str += '```'
    else:
        output_str = 'There are currently no posts set up in this election'
    await context.send(output_str)


@bot.command(name='referenda', help=f'Prints the referenda to be voted on in this election. Usage: {PREFIX}referenda')
async def list_referenda(context):
    if not is_dm(context.channel) and not is_voting_channel(context.channel):
        return

    if referenda:
        output_str = '```\n'
        for title, description in referenda.items():
            output_str += f'{title}: {description}\n'
        output_str += '```'
    else:
        output_str = 'There are currently no referenda set up in this election'
    await context.send(output_str)


@bot.command(name='candidates',
             help='Prints the candidates for the specified post (or all posts if no post is given). '
                  f'Usage: {PREFIX}candidates [POST]', usage='[POST]')
async def list_candidates(context, *post):
    if not is_dm(context.channel) and not is_voting_channel(context.channel):
        return
    if not standing:
        await context.send('There are currently no posts set up in this election')
        return

    post = ' '.join(post)

    output_str = ''
    if post:
        matching_posts = match_post(post)
        if matching_posts:
            post = matching_posts[0]
            candidates = [(str(candidate), discordid) for candidate, _, discordid in standing[post].values()]
            random.shuffle(candidates)
            output_str += f'Candidates standing for {post}:\n'
            for candidate in candidates:
                output_str += f' - {candidate[0]} - {(await bot.fetch_user(candidate[1])).display_name}\n'
            output_str += '--------\n'
        else:
            output_str = ('Looks like that post isn\'t in this election, '
                          f'use `{PREFIX}posts` to see the posts up for election`')
    else:
        for post in standing:
            candidates = [(str(candidate), discordid) for candidate, _, discordid in standing[post].values()]
            random.shuffle(candidates)
            output_str += f'Candidates standing for {post}:\n'
            for candidate in candidates:
                output_str += f' - {candidate} - {(await bot.fetch_user(candidate[1])).display_name}\n'
            output_str += '--------\n'

    if output_str:
        await context.send(output_str)


@bot.command(name='rules', help=f'Prints the rules and procedures for the election. Usage: {PREFIX}rules')
async def rules(context):
    if not is_voting_channel(context.channel) and not is_dm(context.author):
        return

    await context.send(f'To register to vote, DM me with `{PREFIX}register <STUDENT NUMBER>` '
                       f'(without the \'<>\')\n{RULES_STRING}')


@bot.command(name='setup', help=f'Creates the specified post - Committee Only. Usage: {PREFIX}setup <POST>',
             usage='<POST>')
async def setup(context, *post):
    if not is_committee_channel(context.channel):
        return

    post = ' '.join(post)
    matching_posts = match_post(post)
    if matching_posts:
        await context.send(f'{post} already exists')
        return

    standing[post] = {0: (Candidate('RON (Re-Open Nominations)'), 'ron@example.com', 42)}

    save_standing()

    log(f'The post of {post} has been created')
    await context.send(f'The post of {post} has been created')


@bot.command(name='rename', help='Renames the specified post. '
                                 'Note that both post names MUST be passed within quotes - Committee Only. '
                                 f'Usage: {PREFIX}rename <OLD POST> <NEW POST>', usage='<OLD POST> <NEW POST>')
async def rename(context, old_post, new_post):
    if not is_committee_channel(context.channel):
        return

    matching_posts = match_post(old_post)
    if not matching_posts:
        await context.send(f'{old_post} doesn\'t exist')
        return

    standing[new_post] = standing.pop(matching_posts[0])

    save_standing()

    log(f'The post of {matching_posts[0]} has been renamed to {new_post}')
    await context.send(f'The post of {matching_posts[0]} has been renamed to {new_post}')


@bot.command(name='referendum', help='Creates the specified referendum. '
                                     'Note that both fields MUST be passed within quotes - Committee Only. '
                                     f'Usage: {PREFIX}referendum <TITLE> <DESCRIPTION>', usage='<TITLE> <DESCRIPTION>')
async def referendum(context, title, *description):
    if not is_committee_channel(context.channel):
        return

    description = ' '.join(description)
    if description.startswith('\''):
        description = description.strip('\'')

    matching_referenda = match_referendum(title)
    if matching_referenda:
        await context.send(f'{title} already exists')
        return

    referenda[title] = description

    save_referenda()

    log(f'The referendum for \"{title}\" has been created')
    await context.send(f'The referendum for \"{title}\" has been created')


@bot.command(name='begin', help='Begins the election for the specified post/referendum - Committee Only. '
                                f'Usage: {PREFIX}begin <POST/TITLE>', usage='<POST/TITLE>')
async def begin(context, *post):
    global current_live_post

    if not is_voting_channel(context.channel):
        return
    if not is_committee_member(context.author):
        return

    post = ' '.join(post)
    if not post:
        await context.send('Must supply the post/referendum title you are starting the vote for, usage:'
                           f'`{PREFIX}begin <POST/TITLE>`')
        return

    matching_posts = match_post(post)
    type = 'POST'
    if not matching_posts:
        matching_posts = match_referendum(post)
        type = 'REFERENDUM'
        if not matching_posts:
            await context.send('Looks like that post/referendum isn\'t available for this election, '
                               f'use `{PREFIX}posts` to see the posts up for election or '
                               f'or use `{PREFIX}referenda` to see the referenda that will be voted upon')
            return

    async with current_live_post_lock.writer_lock:
        if current_live_post:
            await context.send('You can\'t start a new vote until the last one has finished')
            return
        post = matching_posts[0]

        current_live_post = (type, post)
    log(f'Voting has now begun for: {post}')

    if type == 'POST':
        num_candidates = len(standing[post])
        max_react = list(EMOJI_LOOKUP)[num_candidates-1]

        for voter in registered_members:
            user = await bot.fetch_user(voter)
            await user.send(f'Ballot paper for: {post}, there are {num_candidates} candidates. '
                            f'(Please react to the messages below with :one:-{max_react}). '
                            f'**Don\'t forget to **`{PREFIX}submit <CODE>`** when you\'re done**:\n')
            # Make sure the header arrives before the ballot paper
            await asyncio.sleep(0.2)

            # Message the member with the shuffled candidate list, each in a separate message, record the message ID
            candidates = list(standing[post].items())
            random.shuffle(candidates)
            voting_messages[user.id] = []
            for student_id, details in candidates:
                message = await user.send(f' - {str(details[0])}')
                # Need to store A. the user it was sent to, B. Which candidate is in the message, C. The message ID
                voting_messages[user.id].append((student_id, message.id))

        await context.send(f'Voting has now begun for: {post}\n'
                           'All registered voters will have just received a message from me. '
                           'Please vote by reacting to the candidates listed in your DMs where '
                           ':one: is your top candidate, :two: is your second top candidate, etc. '
                           'You do not need to put a ranking in for every candidate')
    else:
        for voter in registered_members:
            user = await bot.fetch_user(voter)
            await user.send(f'Ballot paper for: {post}. Please react to the message for your choice below with '
                            ':ballot_box_with_check: (\\:ballot_box_with_check\\:). '
                            f'**Don\'t forget to **`{PREFIX}submit <CODE>`** when you\'re done**:\n')
            # Make sure the header arrives before the ballot paper
            await asyncio.sleep(0.2)

            # Message the member with the options list, each in a separate message, record the ID of the message
            voting_messages[user.id] = []
            for option in referendum_options:
                message = await user.send(f' - {str(option)}')
                # Need to store A. the user it was sent to, B. Which candidate is in the message, C. The message ID
                voting_messages[user.id].append((option, message.id))

        await context.send(f'Voting has now begun for: {post}\n'
                           'All registered voters will have just received a message from me. Please vote by '
                           'reacting :ballot_box_with_check: to either the \'For\' or \'Against\' message '
                           'in your DMs')


@bot.command(name='validate', help=f'Checks to see if your vote will be accepted - DM Only. Usage: {PREFIX}validate')
async def validate(context):
    if not is_dm(context.channel):
        return False
    # Only work for users who got sent messages
    author = context.author.id
    if author not in voting_messages:
        return False

    await context.send('Checking vote validity ...')
    async with current_live_post_lock.reader_lock:
        if current_live_post[0] == 'POST':
            return await validate_post(context, author)
        else:
            return await validate_referendum(context, author)


async def validate_post(context, author):
    valid = True
    all_reactions = []
    output_str = ''
    for candidate, message_id in voting_messages[author]:
        message = await context.author.fetch_message(message_id)

        # Check if there is more than one react
        if len(message.reactions) > 1:
            output_str += 'You can\'t react to each candidate with more than one emoji\n'
            valid = False

        for reaction in message.reactions:
            # Check if react is not valid
            if reaction.emoji not in EMOJI_LOOKUP:
                output_str += f'You have reacted with an invalid emoji: {reaction.emoji}\n'
                valid = False
            else:
                all_reactions.append(reaction.emoji)

    for reaction in EMOJI_LOOKUP:
        # Check if they put the same ranking to more than one candidate
        if all_reactions.count(reaction) > 1:
            output_str += 'You can\'t react to more than one candidate with the same value\n'
            valid = False

    # Check if they try to do :three: before :two:, etc
    if len(all_reactions) != 0:
        max_value = EMOJI_LOOKUP[max(all_reactions, key=lambda x: EMOJI_LOOKUP[x])]
        if max_value >= len(standing[current_live_post[1]]):
            output_str += 'You\'ve given a ranking that is higher than the number of candidates\n'
            valid = False
        else:
            for i in range(max_value):
                react_to_check = list(EMOJI_LOOKUP)[i]
                if react_to_check not in all_reactions:
                    output_str += f'Looks like you\'ve skipped ranking {react_to_check}\n'
                    valid = False

    if not output_str:
        output_str = 'Your vote was valid'
    await context.send(output_str)
    return valid


async def validate_referendum(context, author):
    valid = True
    all_reactions = []
    output_str = ''
    for candidate, message_id in voting_messages[author]:
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


@bot.command(name='submit', help=f'Submits your vote - DM Only. Usage: {PREFIX}submit <VOTING CODE>',
             usage='<VOTING CODE>')
async def submit(context, code=None):
    if not is_dm(context.channel):
        await context.send('You need to DM this to me instead')
        return
    # Only work for users who got sent messages
    author = context.author.id
    if author not in voting_messages:
        return
    if not code:
        await context.send('You must supply the code given out in the election call, your vote was not cast')
        return

    if code.upper() != VOTING_CODE:
        await context.send('The code you have supplied is incorrect, '
                           'you must use the one given out in the election call, your vote was not cast')
        return

    valid = await validate(context)
    if not valid:
        await context.send('Your vote was not cast, please correct your ballot and resubmit')
        return

    async with voted_lock:
        if author in voted:
            await context.send('You have already cast your vote and it cannot be changed')
            return

        async with votes_lock.reader_lock:
            async with current_live_post_lock.reader_lock:
                if current_live_post[0] == 'POST':
                    ballot_list = [''] * len(standing[current_live_post[1]])

                    # Create ballot
                    for candidate, message_id in voting_messages[author]:
                        message = await context.author.fetch_message(message_id)
                        if message.reactions:
                            reaction = message.reactions[0].emoji
                            ballot_list[EMOJI_LOOKUP[reaction]] = standing[current_live_post[1]][candidate][0]

                    votes.append(Ballot(ranked_candidates=[ballot for ballot in ballot_list if str(ballot) != '']))
                else:
                    # Create ballot
                    for option, message_id in voting_messages[author]:
                        message = await context.author.fetch_message(message_id)
                        if message.reactions:
                            votes.append(Ballot(ranked_candidates=[option]))
                            break
                    else:
                        votes.append(Ballot(ranked_candidates=[]))

                voted.append(author)
            await context.send('Your vote was successfully cast')
            log(f'Votes cast: {len(votes)} - Votes not yet cast: {len(registered_members)-len(votes)}')


@bot.command(name='end', help=f'Ends the election for the currently live post - Committee Only. Usage: {PREFIX}end')
async def end(context):
    global current_live_post

    if not is_voting_channel(context.channel):
        return
    if not is_committee_member(context.author):
        return

    last_live_post = current_live_post
    async with current_live_post_lock.writer_lock:
        current_live_post = None
    voting_messages.clear()
    async with voted_lock:
        voted.clear()

    await voting_channel.send(f'Voting has now ended for: {last_live_post[1]}')

    async with votes_lock.writer_lock:
        if last_live_post[0] == 'POST':
            results = pyrankvote.instant_runoff_voting([i for i, _, _ in standing[last_live_post[1]].values()],
                                                       votes)
        else:
            results = pyrankvote.instant_runoff_voting(referendum_options, votes)

        votes.clear()

    # Announce the scores and the winner to the committee
    winner = results.get_winners()[0]

    log(f'Result: {results}')
    log(f'Winner: {winner}')

    if last_live_post[0] == 'POST':
        await committee_channel.send('The votes were tallied as follows:\n'
                                     f'```{results}```\n'
                                     f'The winning candidate for the post of {last_live_post[1]} is: {winner}')
    else:
        await committee_channel.send('The votes were tallied as follows:\n'
                                     f'```{results}```\n'
                                     f'The result for the referendum on {last_live_post[1]} is: {winner}')

    log(f'Voting has now ended for: {last_live_post[1]}')
    for voter in registered_members:
        user = await bot.fetch_user(voter)
        await user.send(f'Voting has now ended for: {last_live_post[1]}')


if __name__ == "__main__":
    random.seed(time.time())

    load_dotenv()
    TOKEN = os.getenv('DISCORD_TOKEN')
    COMMITTEE_CHANNEL_ID = int(os.getenv('COMMITTEE_CHANNEL_ID'))
    VOTING_CHANNEL_ID = int(os.getenv('VOTING_CHANNEL_ID'))

    VOTERS_FILE = os.getenv('VOTERS_FILE')
    STANDING_FILE = os.getenv('STANDING_FILE')
    REFERENDA_FILE = os.getenv('REFERENDA_FILE')
    NAMES_FILE = os.getenv('NAMES_FILE')

    SHEET_ID = os.getenv('SHEET_ID')

    COMMITTEE_ROLE = os.getenv('COMMITTEE_ROLE')
    SECRETARY_NAME = os.getenv('SECRETARY_NAME')
    SECRETARY_EMAIL = os.getenv('SECRETARY_EMAIL')

    JOIN_LINK = os.getenv('JOIN_LINK')

    SMTP_SERVER = os.getenv('SMTP_SERVER')
    SMTP_PORT = int(os.getenv('SMTP_PORT'))
    SENDER_EMAIL = os.getenv('SENDER_EMAIL')
    SENDER_PASSWORD = os.getenv('SENDER_PASSWORD')

    VOTING_CODE = os.getenv('VOTING_CODE').upper()

    # Populate registered_members and standing from backups
    try:
        with open(VOTERS_FILE, 'rb') as in_file:
            registered_members = pickle.load(in_file)
    except IOError:
        log(f'No registered_members file: {VOTERS_FILE}')
    try:
        with open(STANDING_FILE, 'rb') as in_file:
            standing = pickle.load(in_file)
    except IOError:
        log(f'No standing file: {STANDING_FILE}')
    try:
        with open(REFERENDA_FILE, 'rb') as in_file:
            referenda = pickle.load(in_file)
    except IOError:
        log(f'No referenda file: {REFERENDA_FILE}')
    try:
        with open(NAMES_FILE, 'rb') as in_file:
            preferred_names = pickle.load(in_file)
    except IOError:
        log(f'No preferred_names file: {NAMES_FILE}')

    # Read in the Google Sheets API token
    creds = Credentials.from_authorized_user_file('token.json', GOOGLE_SCOPES)
    # Connect to the sheets API
    service = build('sheets', 'v4', credentials=creds)

    bot.run(TOKEN)
