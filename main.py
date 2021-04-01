import os
import time
import random
import requests
import re
import pickle
import smtplib
import ssl

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

import pyrankvote
from pyrankvote import Candidate, Ballot

from discord.ext import commands
from discord.channel import DMChannel

# Workflow
# See current members:   \members
# Setup the post:        \setup <POST NAME>
# Check the setup:       \posts
# Members register:      \register
# Members stand:         \stand <POST NAME>
# List candidates:       \candidates <POST NAME>
# Voting begins:         \begin <POST NAME>
# Voters vote:           Reacts
# Voters submit:         \submit
# Voting ends + results: \end

random.seed(time.time())

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
COMMITTEE_CHANNEL_ID = int(os.getenv('COMMITTEE_CHANNEL_ID'))
VOTING_CHANNEL_ID = int(os.getenv('VOTING_CHANNEL_ID'))

URL = os.getenv('GUILD_URL')
# This should be extracted from your .ASPXAUTH cookie
COOKIE = os.getenv('GUILD_COOKIE')

VOTERS_FILE = os.getenv('VOTERS_FILE')
STANDING_FILE = os.getenv('STANDING_FILE')

SHEET_ID = os.getenv('SHEET_ID')

SECRETARY_NAME = os.getenv('SECRETARY_NAME')
SECRETARY_EMAIL = os.getenv('SECRETARY_EMAIL')

SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT'))
SENDER_EMAIL = os.getenv('SENDER_EMAIL')
SENDER_PASSWORD = os.getenv('SENDER_PASSWORD')

VOTING_CODE = os.getenv('VOTING_CODE').upper()


GOOGLE_SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Set the command prefix to be '\'
PREFIX = '\\'

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


# Create the bot and specify to only look for messages starting with the PREFIX
bot = commands.Bot(command_prefix=PREFIX)

# Name of the post that is currently live
current_live_post = None
# Format = [<Ballot>]
votes = []
# Format = [<Student Number>]
voted = []
# Format = {<Discord Username>: <Student Number>}
registered_members = {}
# Format = {<Post>: {<Student Number>: (<Candidate Object>, <Email>), ...}, ...}
standing = {}
# Format = {<User ID>: [(<Candidate Student ID>, <Message ID>), ...], ...}
voting_messages = {}

# Populate registered_members and standing from backups
try:
    with open(VOTERS_FILE, 'rb') as in_file:
        registered_members = pickle.load(in_file)
except IOError:
    print('No registered_members file:', VOTERS_FILE)
try:
    with open(STANDING_FILE, 'rb') as in_file:
        standing = pickle.load(in_file)
except IOError:
    print('No standing file:', STANDING_FILE)

# Read in the Google Sheets API token
creds = Credentials.from_authorized_user_file('token.json', GOOGLE_SCOPES)
# Connect to the sheets API
service = build('sheets', 'v4', credentials=creds)


def get_members():
    page = requests.get(URL, cookies={'.ASPXAUTH': COOKIE}).content.decode('utf-8')

    table = re.search(r'All Members[\s\S]*?\d+ member[\s\S]*?<table[\s\S]*?>([\s\S]+?)</table>', page).group(1)
    members_parse = re.findall(r'/profile/\d+/\">([\s\S]+?), ([\s\S]+?)</a></td><td>(\d+)', table)
    all_members = {int(member[2]): (f'{member[1]} {member[0]}') for member in members_parse}

    table = re.search(r'Standard Membership[\s\S]*?\d+ member[\s\S]*?<table[\s\S]*?>([\s\S]+?)</table>', page).group(1)
    members_parse = re.findall(r'/profile/\d+/\">([\s\S]+?), ([\s\S]+?)</a></td><td>(\d+)', table)
    standard_membership = {int(member[2]): (f'{member[1]} {member[0]}') for member in members_parse}

    # Format = {<Student Number>: <Name>}
    members = {**all_members, **standard_membership}
    members[0] = 'RON (Re-Open-Nominations)'
    return members


def email_secretary(candidate, post, stood_down=False):
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)

        message = MIMEMultipart('alternative')
        message['From'] = SENDER_EMAIL
        message['To'] = SECRETARY_EMAIL

        if not stood_down:
            message['Subject'] = 'New candidate standing in the upcoming CSS election'
            text = ('Hello,\n'
                    f'{candidate} has just stood for the position of {post} '
                    'in the upcoming CSS election,\n'
                    'Goodbye')
        else:
            message['Subject'] = 'Candidate no longer standing in the upcoming CSS election'
            text = ('Hello,\n'
                    f'{candidate} has just stood down from standing for the position of {post} '
                    'in the upcoming CSS election,\n'
                    'Goodbye')

        # Turn the message text into a MIMEText object and add it to the MIMEMultipart message
        message.attach(MIMEText(text, 'plain'))
        server.sendmail(SENDER_EMAIL, SECRETARY_EMAIL, message.as_string())


def save_voters():
    with open(VOTERS_FILE, 'wb') as out_file:
        pickle.dump(registered_members, out_file)


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


def is_dm(channel):
    return isinstance(channel, DMChannel)


def is_voting_channel(channel):
    return channel.id == VOTING_CHANNEL_ID


def is_committee_channel(channel):
    return channel.id == COMMITTEE_CHANNEL_ID


def is_committee_member(user):
    return any([True for role in user.roles if str(role) == 'Committee'])


def match_post(post):
    return [a for a in standing if a.lower() == post.lower()]


@bot.event
async def on_ready():
    global committee_channel
    global voting_channel
    committee_channel = bot.get_channel(COMMITTEE_CHANNEL_ID)
    voting_channel = bot.get_channel(VOTING_CHANNEL_ID)

    print(f'{bot.user.name} has connected to Discord and is in the following channels:')
    for guild in bot.guilds:
        print(' -', guild.name)


@bot.command(name='members')
async def members(context):
    if not is_committee_channel(context.channel):
        return

    members = get_members()
    output_str = '```'
    for member in members.items():
        if (len(output_str) + len(str(member)) + 5) > 2000:
            output_str += '```'
            await context.send(output_str)
            output_str = '```'
        output_str += f'{member}\n'
    output_str += '```'
    await context.send(output_str)


@bot.command(name='register', help='Register to vote')
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
            print(context.author, 'tried to register student ID', student_number,
                  'but it is already registered to', other_user)
        else:
            registered_members[author] = student_number
            output_str = f'Thank you {members[registered_members[author]]}, you are now registered\n\n{RULES_STRING}'
            print(registered_members[author], 'is now registered')
    else:
        output_str = 'Looks like you\'re not a member yet, please become a member here: https://cssbham.com/join'
        print(context.author.name, 'has failed to register')

    save_voters()
    await context.send(output_str)


@bot.command(name='stand', help='Stand for a post')
async def stand(context, *input):
    if not is_dm(context.channel):
        await context.send('You need to DM me for this instead')
        return
    email = input[-1]
    post = ' '.join(input[:-1])
    if not post:
        await context.send('Must supply the post you are running for and your email address, '
                           f'usage:`{PREFIX}stand <POST> <EMAIL>`')
        return
    matching_posts = match_post(post)
    if not matching_posts:
        await context.send('Looks like that post isn\'t available for this election, '
                           f'use `{PREFIX}posts` to see the posts up for election')
        return
    post = matching_posts[0]
    if post == current_live_post:
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
            standing[post][registered_members[author]] = (Candidate(members[registered_members[author]]), email)
            output_str = (f'Congratulations {members[registered_members[author]]}, '
                          f'you are now standing for the position of {post}.\n\n'
                          'Now you\'ll need to prepare a 2 minute speech to be given in the election call.\n'
                          f'If you have any questions please contact the secretary {SECRETARY_NAME}'
                          f'({SECRETARY_EMAIL}), or someone else on the committee.\n'
                          'If you can\'t make it to the actual election call, you must get in touch with the secretary '
                          'ASAP to sort out alternative arrangements.')
            print(registered_members[author], 'is now standing for', post)
            email_secretary(members[registered_members[author]], post)
    else:
        output_str = f'Looks like you\'re not registered yet, please register using `{PREFIX}register <STUDENT NUMBER>`'
        print(context.author.name, 'has failed to stand for', post)

    save_standing()
    await context.send(output_str)


@bot.command(name='standdown', help='Stand down from running for a post')
async def standdown(context, *post):
    if not is_dm(context.channel):
        await context.send('You need to DM me for this instead')
        return

    post = ' '.join(post)
    if not post:
        await context.send(f'Must supply the post you are standing down from, usage: `{PREFIX}standdown <post>`')
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

    print(registered_members[author], 'has stood down from standing for', post)
    await context.send(f'You have stood down from running for {post}')


@bot.command(name='posts', help='Prints the posts available to stand for in this election')
async def posts(context):
    if not is_dm(context.channel) and not is_voting_channel(context.channel):
        return

    output_str = '```'
    for post in standing:
        output_str += post + '\n'
    output_str += '```'
    await context.send(output_str)


@bot.command(name='candidates',
             help='Prints the candidates for the specified post (or all posts if no post is given)')
async def list_candidates(context, *post):
    if not is_voting_channel(context.channel):
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
            candidates = [str(candidate) for candidate, _ in standing[post].values()]
            random.shuffle(candidates)
            output_str += f'Candidates standing for {post}:\n'
            for candidate in candidates:
                output_str += f' - {candidate}\n'
            output_str += '--------\n'
        else:
            output_str = ('Looks like that post isn\'t in this election, '
                          f'use `{PREFIX}posts` to see the posts up for election`')
    else:
        for post in standing:
            candidates = [str(candidate) for candidate, _ in standing[post].values()]
            random.shuffle(candidates)
            output_str += f'Candidates standing for {post}:\n'
            for candidate in candidates:
                output_str += f' - {candidate}\n'
            output_str += '--------\n'

    if output_str:
        await context.send(output_str)


@bot.command(name='rules', help='Prints the rules and procedures for the election')
async def rules(context):
    if not is_voting_channel(context.channel) and not is_dm(context.author):
        return

    await context.send(f'To register to vote, DM me with `{PREFIX}register <YOUR STUDENT ID NUMBER>` '
                       f'(without the \'<>\')\n{RULES_STRING}')


@bot.command(name='setup', help='Creates the specified post')
async def setup(context, *post):
    if not is_committee_channel(context.channel):
        return

    post = ' '.join(post)
    matching_posts = match_post(post)
    if matching_posts:
        await context.send(f'{post} already exists')
        return

    standing[post] = {0: (Candidate('RON (Re-Open Nominations)'), 'ron@example.com')}

    save_standing()

    await context.send(f'{post} post created')


@bot.command(name='begin', help='Begins the election for the specified post')
async def begin(context, *post):
    global current_live_post

    if not is_voting_channel(context.channel):
        return
    if not is_committee_member(context.author):
        return

    post = ' '.join(post)
    if not post:
        await context.send(f'Must supply the post you are starting the vote for, usage:`{PREFIX}begin <post>`')
        return
    if current_live_post:
        await context.send('You can\'t start a new vote until the last one has finished')
        return
    matching_posts = match_post(post)
    if not matching_posts:
        await context.send('Looks like that post isn\'t available for this election, '
                           f'use `{PREFIX}posts` to see the posts up for election`')
        return
    post = matching_posts[0]

    current_live_post = post
    print('Voting has now begun for post:', post)

    num_candidates = len(standing[post])
    max_react = list(EMOJI_LOOKUP)[num_candidates-1]

    for voter in registered_members:
        user = await bot.fetch_user(voter)
        await user.send(f'Ballot paper for {post}, there are {num_candidates} candidates. '
                        f'(Please react to the messages below with :one:-{max_react}). '
                        f'**Don\'t forget to **`{PREFIX}submit <CODE>`** when you\'re done**:\n')

        # Message the member with the shuffled candidate list, each in a separate message, record the ID of the message
        candidates = list(standing[post].items())
        random.shuffle(candidates)
        voting_messages[user.id] = []
        for student_id, details in candidates:
            message = await user.send(f' - {str(details[0])}')
            # Need to store A. the user it was sent to, B. Which candidate is in the message, C. The message ID
            voting_messages[user.id].append((student_id, message.id))
        await user.send(f'End of Ballot Paper for {post}')

    await context.send(f'Voting has now begun for {post}\n'
                       'All registered voters will have just received a message from me. '
                       'Please vote by reacting to the candidates listed in your DMs where '
                       ':one: is your top candidate, :two: is your second top candidate, etc. '
                       'You do not need to put a ranking in for every candidate')


@bot.command(name='validate', help='Checks to see if your vote will be accepted')
async def validate(context):
    if not is_dm(context.channel):
        return False
    # Only work for users who got sent messages
    author = context.author.id
    if author not in voting_messages:
        return False

    await context.send('Checking vote validity ...')
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
        if max_value >= len(standing[current_live_post]):
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


@bot.command(name='submit', help='Submits your vote')
async def submit(context, code=None):
    if not is_dm(context.channel):
        await context.send('You need to DM this to me instead')
        return
    # Only work for users who got sent messages
    author = context.author.id
    if author not in voting_messages:
        return
    if author in voted:
        await context.send('You have already cast your vote and it cannot be changed')
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

    ballot_list = [''] * len(standing[current_live_post])

    # Create ballot
    for candidate, message_id in voting_messages[author]:
        message = await context.author.fetch_message(message_id)
        if message.reactions:
            reaction = message.reactions[0].emoji
            ballot_list[EMOJI_LOOKUP[reaction]] = standing[current_live_post][candidate][0]

    votes.append(Ballot(ranked_candidates=[ballot for ballot in ballot_list if str(ballot) != '']))
    voted.append(author)
    await context.send('Your vote was successfully cast')
    print('Votes cast:', len(votes), '- Votes not yet cast:', len(registered_members)-len(votes))


@bot.command(name='end', help='Ends the election for the currently live post')
async def end(context):
    global current_live_post

    if not is_voting_channel(context.channel):
        return
    if not is_committee_member(context.author):
        return

    last_live_post = current_live_post
    current_live_post = None
    voting_messages.clear()
    voted.clear()

    print('Voting has now ended for post:', last_live_post)
    for voter in registered_members:
        user = await bot.fetch_user(voter)
        await user.send(f'Voting has now ended for post: {last_live_post}')

    results = pyrankvote.instant_runoff_voting([candidate for candidate, _ in standing[last_live_post].values()], votes)
    votes.clear()

    # Announce the scores and the winner to the committee
    winner = results.get_winners()[0]

    print('Result:', results)
    print('Winner:', winner)

    await committee_channel.send('The votes were tallied as follows:\n'
                                 f'```{results}```\n'
                                 f'The winning candidate for the post of {last_live_post} is: {winner}')


bot.run(TOKEN)
