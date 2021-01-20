import os
import time
import datetime
import json
import random
import requests
from dotenv import load_dotenv
import re
import pickle

import pyrankvote
from pyrankvote import Candidate, Ballot

from discord.ext import commands
from discord.channel import DMChannel

## Workflow
# Setup the post:        \setup PGR
# Check the setup:       \posts
# Members register:      \register
# Members stand:         \stand PGR 
# List candidates:       \candidates PGR
# Voting begins:         \begin PGR
# Voters vote:           Reacts
# Voters submit:         \submit
# Voting ends + results: \end

#TODO: Allow resubmitting a ballot, by storing an anonymised token alongside the vote, which is the hash of their userID+a password, the password can either be made by them or by the system, but then when they resubmit, they must provide the password. Alongside this there must be a list of users that have voted. If they've voted and the hash doesn't exist, incorrect password, if they've voted and the hash already exist, then update the vote, if they haven't voted and the hash doesn't exist, add the hash, if they haven't voted and the hash exists, error.


load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
URL = os.getenv('GUILD_URL')
# This should be extracted from your .ASPXAUTH cookie
COOKIE = os.getenv('GUILD_COOKIE')
COMMITTEE_CHANNEL = int(os.getenv('COMMITTEE_CHANNEL'))

VOTERS_FILE = 'voters.bak'
STANDING_FILE = 'standing.bak'

# Create the bot and specify to only look for messages starting with '\'
bot = commands.Bot(command_prefix='\\')

# Don't forget to fix RON
# Format = {<DiscordUsername>: <StudentNumber>}
registered_members = {}
try:
	with open(VOTERS_FILE,'rb') as infile:
		registered_members = pickle.load(infile)
except IOError:
    print("No registered_members file:", VOTERS_FILE)

# Format = {<Post>: [<StudentNumber>, ...]}
standing = {}
try:
	with open(STANDING_FILE,'rb') as infile:
		standing = pickle.load(infile)
except IOError:
    print("No standing file:", STANDING_FILE)

current_live_post = None
votes = []
voted = []
candidate_objects = {}

committee_channel = ''
random.seed(time.time())


def get_members():
    page = requests.get(URL, cookies={'.ASPXAUTH': COOKIE}).content.decode("utf-8")

    first_parse = re.search("All Members[\s\S]*?(\d+) member[\s\S]*?<table[\s\S]*?>([\s\S]+?)</table>", page)
    num_members = first_parse.group(1)
    table = first_parse.group(2)
    members_parse = re.findall("/profile/\d+/\">([\s\S]+?), ([\s\S]+?)</a></td><td>(\d+)", table)
    all_members = {int(member[2]): (member[1] + " " + member[0]) for member in members_parse}

    first_parse = re.search("Standard Membership[\s\S]*?(\d+) member[\s\S]*?<table[\s\S]*?>([\s\S]+?)</table>", page)
    num_members = first_parse.group(1)
    table = first_parse.group(2)
    members_parse = re.findall("/profile/\d+/\">([\s\S]+?), ([\s\S]+?)</a></td><td>(\d+)", table)
    standard_membership = {int(member[2]): (member[1] + " " + member[0]) for member in members_parse}

    # Format = {<StudentNumber>: <Name>}
    members = {**all_members, **standard_membership}
    members[0] = "RON (Re-Open-Nominations)"
    return members


@bot.event
async def on_ready():
    global committee_channel
    committee_channel = bot.get_channel(COMMITTEE_CHANNEL)
    print(f'{bot.user.name} has connected to Discord and is in the following channels:')
    for guild in bot.guilds:
        print('  ', guild.name)


# Prototyped
@bot.command(name='members')
async def members(context):
    # Only respond if used in a channel called 'committee-general'
    if context.channel.name != 'committee-general':
        return
    members = get_members()
    output_str = '```'
    for member in members.items():
        if (len(output_str) + len(str(member)) + 5) > 2000:
            output_str += '```'
            await(context.send(output_str))
            output_str = '```'
        output_str += str(member) + '\n'
    output_str += '```'
    await context.send(output_str)


# Prototyped, need to not output the offender when erroring (in both cases), instead post in the committee channel
@bot.command(name='register', help='Register to vote')
async def register(context, student_number: int):
    # Only respond if used in a DM
    if not isinstance(context.channel, DMChannel):
        await context.send('You need to DM me for this instead')
        return

    author = context.author.id
    members = get_members()

    output_str = 'Error'
    if student_number in members:
        if author in registered_members:
            output_str = 'Looks like your Discord username is already registered to ' + str(registered_members[author])
        elif student_number in registered_members.values():
            output_str = 'Looks like your student ID is already registered to someone else, please contact a committee member'
            other_user = await bot.fetch_user([key for key, value in registered_members.items() if value == student_number][0]).name
            print(context.author, "tried to register student ID", student_number, "but it is already registered to", other_user)
        else:
            registered_members[author] = student_number
            output_str = 'Thank you ' + members[registered_members[author]] + ', you are now registered'
            print(registered_members[author], "is now registered")
    else:
        output_str = 'Looks like you\'re not a member yet, please become a member here: https://cssbham.com/join'
        print(context.author.name, "has failed to register")

    with open(VOTERS_FILE,'wb') as outfile:
        pickle.dump(registered_members, outfile)
        
    await context.send(output_str)


# Prototyped # make the post .tolower ed
@bot.command(name='stand', help='Stand for a post')
async def stand(context, *post):
    post = ' '.join(post)
    matching_posts = [a for a in standing.keys() if a.lower() == post.lower()]

    # Only respond if used in a DM
    if not isinstance(context.channel, DMChannel):
        await context.send('You need to DM me for this instead')
        return
    elif not post:
        await context.send('Must supply the post you are running for, usage:\n`\\stand <post>`')
        return
    elif not matching_posts:
        await context.send('Looks like that post isn\'t available for this election, use `\\posts` to see the posts up for election')
        return
    post = matching_posts[0]
    if post == current_live_post:
        await context.send('I\'m afraid voting for ' + post + ' has already begun, you cannot stand for this post')
        return

    author = context.author.id
    members = get_members()

    output_str = 'Error'
    if author in registered_members:
        if [i for i in standing[post] if i == registered_members[author]]:
            output_str = 'It looks like you, ' + members[registered_members[author]] + ' are already standing for the position of: ' + post
        else: 
            standing[post].append(registered_members[author])
            output_str = 'Congratulations ' + members[registered_members[author]] + ', you are now standing for the position of: ' + post
            print(registered_members[author], "is now standing for", post)
    else:
        output_str = 'Looks like you\'re not registered yet, please register using \"\\register <STUDENT NUMBER>\"'
        print(context.author.name, "has failed to stand for", post)
        
    with open(STANDING_FILE,'wb') as outfile:
        pickle.dump(standing, outfile)

    await context.send(output_str)


# Prototyped
@bot.command(name='standdown', help='Stand down from running for a post')
async def standdown(context, *post):
    post = ' '.join(post)
    matching_posts = [a for a in standing.keys() if a.lower() == post.lower()]

    # Only respond if used in a DM
    if not isinstance(context.channel, DMChannel):
        await context.send('You need to DM me for this instead')
        return
    elif not post:
        await context.send('Must supply the post you are standing down from, usage:\n`\\standdown <post>`')
        return
    elif not matching_posts:
        await context.send('Looks like that post isn\'t available for this election, use `\\posts` to see the posts up for election`')
        return
    post = matching_posts[0]

    author = context.author.id

    output_str = ''
    for i, standing_member in enumerate(standing[post]):
        if standing_member == registered_members[author]:
            standing[post].pop(i)
            output_str = 'You have stood down from running for ' + post
            print(registered_members[author], 'has stood down from standing for', post)
            break

    if not output_str:        
        output_str = 'Looks like you weren\'t standing for this post'

    with open(STANDING_FILE,'wb') as outfile:
        pickle.dump(standing, outfile)
        
    await context.send(output_str)


# Prototyped
@bot.command(name='posts', help='Prints the posts available to stand for in this election')
async def posts(context):
    # Only respond if used in a channel called 'voting' or in a DM
    if not isinstance(context.channel, DMChannel) and context.channel.name != 'voting':
        return
    output_str = '```'
    for post in standing:
        output_str += post + '\n'
    output_str += '```'
    await context.send(output_str)


# Prototyped
@bot.command(name='candidates', help='Prints the candidates for the specified post (or all posts if no post is given)')
async def candidates(context, *post):
    post = ' '.join(post)
    matching_posts = [a for a in standing.keys() if a.lower() == post.lower()]

    # Only respond if used in a channel called 'voting'
    if context.channel.name != 'voting':
        return

    members = get_members()
    if post:
        if matching_posts:
            post = matching_posts[0]
            
            random.shuffle(standing[post])
            await context.send("Candidates standing for " + post + ":")
            for candidate in standing[post]:
                await context.send(content=" - " + members[candidate])
            await context.send('--------')
        else:
            await context.send('Looks like that post isn\'t in this election, use `\\posts` to see the posts up for election`')
    else:
        for post in standing:
            random.shuffle(standing[post])
            await context.send("Candidates standing for " + post + ":")
            for candidate in standing[post]:
                await context.send(content=" - " + members[candidate])
            await context.send('--------')


@bot.command(name='rules', help='Prints the rules and procedures for the election')
async def rules(context):
    # Only respond if used in a channel called 'voting'
    if context.channel.name != 'voting':
        return
    rules_string = (
                "To register to vote, DM me with `\\register <YOUR STUDENT ID NUMBER>` (without the '<>')\n"
                "To stand for a position, DM me with `\\stand <POST>`, where <POST> is the post you wish to stand for (without the '<>'), you can see all posts available by sending `\\posts`\n"
                "When voting begins, I will DM you a ballot paper. To vote, you'll need to react to the candidates in that ballot paper, where :one: is your top candidate, :two: is your second top candidate, etc\n"
                "The rules for filling in the ballot are as follows:\n"
                "- You don't have to use all your rankings, but don't leave any gaps (e.g. you can't give a candidate 3️⃣ without giving some candidate 2️⃣)\n"
                "- Don't react with any reactions other than the number reacts 1️⃣  - 9️⃣\n"
                "- Don't react with a ranking higher than the number of candidates (e.g. if there are three candidates, don't react 4️⃣ to any candidates)\n"
                "- Don't vote for one candidate multiple times\n"
                "- Don't give the same ranking to multiple candidates\n\n"
                "**Once you are happy with your ballot, please submit your vote by sending** `\\submit`\n"
                "When you submit your ballot, it will be checked against the rules and if something's not right, you'll be asked to fix it and will need to submit again"
    )
    await context.send(rules_string)


# Prototyped # make the post .tolower ed
@bot.command(name='setup', help='Creates the specified post')
async def setup(context, *post):
    # FIX THIS
    ron = True
    post = ' '.join(post)
    matching_posts = [a for a in standing.keys() if a.lower() == post.lower()]

    # Only respond if used in a channel called 'committee-general'
    if context.channel.name != 'committee-general':
        return
    elif matching_posts:
        await context.send(post + " already exists")
        return

    if ron:
        standing[post] = [0]

    with open(STANDING_FILE,'wb') as outfile:
        pickle.dump(standing, outfile)

    await context.send(post + " post created")

# Format -> {<User ID>: [(<Candidate Student ID>, <Message ID>), ...]}
voting_messages = {}

voter_rules_string = (
                "Please vote by reacting to the candidates listed below where :one: is your top candidate, :two: is your second top candidate, etc\n"
                "**Once you are happy with your ballot, please submit your vote by sending** `\\submit`\n\n"
                "You must abide by the following rules:\n"
                "- Do not react with any reactions other than the number reacts 1️⃣  - 9️⃣\n"
                "- Do not react with a ranking higher than the number of candidates (e.g. if there are three candidates, don't react 4️⃣ to any candidates)\n"
                "- Do not vote for one candidate multiple times\n"
                "- Do not give the same ranking to multiple candidates\n"
                "- Do not skip rankings (e.g. give a candidate 3️⃣ without giving any candidate 2️⃣)\n"
                "If you do not follow these rules, your vote will not be counted (they will be validated when you submit, and you will be asked to fix any issues and you'll then need to resubmit)\n"
)

lookup = {
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

@bot.command(name='begin', help='Begins the election for the specified post')
async def begin(context, *post):
    global current_live_post
    global votes
    global candidate_objects

    post = ' '.join(post)
    matching_posts = [a for a in standing.keys() if a.lower() == post.lower()]

    # Only respond if used in a channel called 'voting'
    if isinstance(context.channel, DMChannel) or context.channel.name != 'voting':
        return
    # Only available to committee members
    elif not any([True for role in context.author.roles if str(role) == "Committee"]):
        return
    elif not post:
        await context.send('Must supply the post you are starting the vote for, usage:\n`\\begin <post>`')
        return
    elif current_live_post:
        await context.send('You can\'t start a new vote until the last one has finished')
        return

    post = matching_posts[0]

    members = get_members()
    candidate_objects = {candidate: Candidate(members[candidate]) for candidate in standing[post]}
    candidate_objects[0] = Candidate('RON (Re-Open-Nominations)')

    users = []
    for voter in registered_members:
        user = await bot.fetch_user(voter)
        users.append(user)

    # Prints the candidates for each post in a seperate message
    #await candidates(context, post)

    current_live_post = post
    print("Voting has now begun for post:", post)

    num_candidates = len(standing[post])
    max_react = list(lookup.keys())[num_candidates-1]
    for user in users:
        await user.send(voter_rules_string + "\nBallot Paper for " + post + ", there are " + str(num_candidates) + " candidates. (Please react to the messages below with 1️⃣ -" + max_react + ". You do not need to put a ranking in for every candidate) **Don't forget to **`\\submit`** when you're done**:\n\*\*\*\*\*\*\*\*\*\*")
        random.shuffle(standing[post])
        # Message the member with the shuffled candidate list, each candidate in a seperate message, record the ID of the message
        if user.id not in voting_messages:
            voting_messages[user.id] = []

        for candidate in standing[post]:
            message = await user.send(" - " + members[candidate])
            #need to store A. the user it was sent to, B. Which candidate is in the message, C. The message ID
            voting_messages[user.id].append((candidate, message.id))
        #await user.send("\*\*\*\*\*\*\*\*\*\*\nEnd of Ballot Paper for " + post)

    await context.send("Voting has now begun for " + post)
    await context.send("All registered voters will have just recieved a message from me. Please vote by reacting to the candidates listed in your DMs where :one: is your top candidate, :two: is your second top candidate, etc. You do not need to put a ranking in for every candidate")


@bot.command(name='validate', help='Checks to see if your vote will be accepted')
async def validate(context):
    author = context.author.id
    # Only work in DM and only for registered users
    if not isinstance(context.channel, DMChannel) or author not in voting_messages:
        return False
    
    await context.send("Checking vote validity ...")
    valid = True
    all_reactions = []
    for candidate, message_id in voting_messages[author]:
        message = await context.author.fetch_message(message_id)

        # Check if there is more than one react, and if so, tell them they fucked up
        if len(message.reactions) > 1:
            await context.send("You can't react to each candidate with more than one emoji")
            valid = False

        for reaction in message.reactions:
            # Check if react is not valid, and if so, tell them they fucked up
            if reaction.emoji not in lookup:
                await context.send("You have reacted with an invalid emoji")
                valid = False
            else:
                all_reactions.append(reaction.emoji)


    for reaction in lookup.keys():
        # Check if they put the same ranking to more than one candidate, and if so, tell them they fucked up
        if all_reactions.count(reaction) > 1:
            await context.send("You can't react to more than one candidate with the same value")
            valid = False

    # Check if they try to do :three: before :two:, etc, and if so, tell them they fucked up
    if len(all_reactions) != 0:
        max_value = lookup[max(all_reactions, key=lambda x: lookup[x])]
        if max_value > len(standing[current_live_post]):
            await context.send("You've given a ranking that is higher than the number of candidates")
            valid = False
        else:
            for i in range(max_value):
                react_to_check = list(lookup.keys())[i]
                if react_to_check not in all_reactions:
                    await context.send("Looks like you've skipped ranking " + react_to_check)
                    valid = False

    return valid

@bot.command(name='submit', help='Submits your vote')
async def submit(context):
    author = context.author.id
    # Only work in DM and only for registered users
    if not isinstance(context.channel, DMChannel):
        await context.send("You need to DM this to me instead")
        return
    elif author not in voting_messages:
        return
    elif author in voted:
        await context.send("You have already cast your vote and it cannot be changed")
        return

    
    valid = await validate(context)
    if not valid:
        await context.send("Your vote was not valid, so was not cast, please correct your ballot and resubmit")
        return

    voted.append(author)
    ballot_list = [''] * len(standing[current_live_post])

    # Create ballot
    for candidate, message_id in voting_messages[author]:
        message = await context.author.fetch_message(message_id)
        if message.reactions:
            reaction = message.reactions[0].emoji
            ballot_list[lookup[reaction]] = candidate_objects[candidate]

    votes.append(Ballot(ranked_candidates=[ballot for ballot in ballot_list if str(ballot) != '']))
    await context.send("Your vote was valid and was successfully cast")
    print("Votes cast:", len(votes), "- Votes not yet cast:", len(registered_members)-len(votes))

@bot.command(name='end', help='Ends the election for the currently live post')
async def end(context):
    global current_live_post
    global voting_messages
    global votes
    global candidate_objects
    global voted

    # Only respond if used in a channel called 'voting'
    if context.channel.name != 'voting':
        return
    # Only available to committee members
    if not any([True for role in context.author.roles if str(role) == "Committee"]):
        return
    
    last_live_post = current_live_post
    current_live_post = None
    print("Voting has now ended for post:", last_live_post)
    for voter in registered_members:
        user = await bot.fetch_user(voter)
        await user.send("Voting has now ended for post: " + last_live_post)

    results = pyrankvote.instant_runoff_voting(list(candidate_objects.values()), votes)

    # Announce the scores and the winner to the committee
    winner = results.get_winners()[0]

    print("Result:", results)
    print("Winner:", winner)
    
    
    await committee_channel.send("The votes were tallied as follows:")
    await committee_channel.send("```" + str(results) + "```")
    await committee_channel.send("The winning candidate for " + last_live_post + " is: " + str(winner))

    voting_messages = {}
    votes = []
    candidate_objects = {}
    voted = []
        

bot.run(TOKEN)

