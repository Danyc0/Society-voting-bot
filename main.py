import os
import time
import datetime
import json
import random
import urllib.request
from dotenv import load_dotenv
import re
import pickle

import pyrankvote
from pyrankvote import Candidate, Ballot

from discord.ext import commands
from discord.channel import DMChannel

## Workflow
# Setup the post:        ?setup PGR
# Check the setup:       ?posts
# Members register:      ?register
# Members stand:         ?stand PGR 
# List candidates:       ?candidates PGR
# Voting begins:         ?begin PGR
# Voters vote:           Reacts
# Voting ends + results: ?end




load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
URL = os.getenv('GUILD_URL')
# This should be extracted from your .ASPXAUTH cookie
COOKIE = os.getenv('GUILD_COOKIE')

VOTERS_FILE = 'voters.bak'

# Create the bot and specify to only look for messages starting with '?'
bot = commands.Bot(command_prefix='?')

# Don't forget to fix RON
# Format = {<DiscordUsername>: <StudentNumber>}
registered_members = {"danyc0#7106": 1733780, "RON": 0}
registered_members = {}
try:
	with open(VOTERS_FILE,'rb') as infile:
		registered_members = pickle.load(infile)
except IOError:
    print("No registered_members file:", VOTERS_FILE)

# Format = {<Post>: [(<StudentNumber>, <Bio>, <Image>), ...]}
standing = {'pgr': [(1733780, "I'm Great", None)]}
standing = {}

current_live_post = None

random.seed(time.time())


def get_members():
    req = urllib.request.Request(URL)
    req.add_header('Cookie', '.ASPXAUTH=' + COOKIE)
    page = str(urllib.request.urlopen(req).read())
    first_parse = re.search("All Members[\s\S]*?(\d+) member[\s\S]*?<table[\s\S]*?>([\s\S]+?)</table>", page)
    num_members = first_parse.group(1)
    table = first_parse.group(2)

    members_parse = re.findall("/profile/\d+/\">([\s\S]+?), ([\s\S]+?)</a></td><td>(\d+)", table)

    # Format = {<StudentNumber>: <Name>}
    members = {int(member[2]): (member[1] + " " + member[0]) for member in members_parse}
    members[0] = "RON (Re-Open-Nominations)"
    return members


@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord and is in the following channels:')
    for guild in bot.guilds:
        print('  ', guild.name)


# Prototyped
@bot.command(name='members', help='Prints all CSS members')
async def members(context):
    # Only respond if used in a channel called 'voting'
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
            output_str = 'Looks like your student ID is already registered to ' + bot.get_user([key for key, value in registered_members.items() if value == student_number][0]).name
        else:
            registered_members[author] = student_number
            output_str = 'Thank you ' + members[registered_members[author]] + ', you are now registered'
            print(registered_members[author], "is now registered")
    else:
        output_str = 'Looks like you\'re not a member yet, please become a member here: https://cssbham.com/join'
        print(author, "has failed to register")

    with open(VOTERS_FILE,'wb') as outfile:
        pickle.dump(registered_members, outfile)
        
    await context.send(output_str)


# Prototyped # make the post .tolower ed
@bot.command(name='stand', help='Stand for a post')
async def stand(context, post=None, *bio):
    # Only respond if used in a DM
    if not isinstance(context.channel, DMChannel):
        await context.send('You need to DM me for this instead')
        return
    elif not post:
        await context.send('Must supply the post you are running for, usage:\n`?stand <post> <bio>`, you may also attach an optional image of yourself to the message')
        return
    elif post not in standing:
        await context.send('Looks like that post isn\'t available for this election, use ?posts to see the posts up for election')
        return
    elif not bio:
        await context.send('Must supply a bio (even a simple one will do), usage:\n`?stand <post> <bio>`')
        return

    bio = ' '.join(bio)
    image = None
    if context.message.attachments:
        image = await context.message.attachments[0].to_file()
    author = context.author.id
    members = get_members()

    output_str = 'Error'
    if author in registered_members:
        if [i for i in standing[post] if i[0] == registered_members[author]]:
            output_str = 'It looks like you, ' + members[registered_members[author]] + ' are already standing for the position of: ' + post
        else: 
            standing[post].append((registered_members[author], bio, image))
            output_str = 'Congratulations ' + members[registered_members[author]] + ', you are now standing for the position of: ' + post
            print(registered_members[author], "is now standing for", post)
    else:
        output_str = 'Looks like you\'re not registered yet, please register using \"?register <STUDENT NUMBER>\"'
        print(author, "has failed to stand for", post)
        
    await context.send(output_str)


# Prototyped
@bot.command(name='standdown', help='Stand down from running for a post')
async def standdown(context, post=None):
    # Only respond if used in a DM
    if not isinstance(context.channel, DMChannel):
        await context.send('You need to DM me for this instead')
        return
    elif not post:
        await context.send('Must supply the post you are standing down from, usage:\n`?standdown <post>`')
        return
    elif post not in standing:
        await context.send('Looks like that post isn\'t available for this election, use ?posts to see the posts up for election`')
        return

    author = context.author.id

    output_str = ''
    for i, standing_member in enumerate(standing[post]):
        if standing_member[0] == registered_members[author]:
            standing[post].pop(i)
            output_str = 'You have stood down from running for ' + post
            print(registered_members[author], 'has stood down from standing for', post)
            break

    if not output_str:        
        output_str = 'Looks like you weren\'t standing for this post'
        
    await context.send(output_str)


# Prototyped
@bot.command(name='posts', help='Prints the posts available to stand for in this election')
async def posts(context):
    # Only respond if used in a channel called 'voting'
    if isinstance(context.channel, DMChannel) or context.channel.name != 'voting':
        return
    output_str = '```'
    for post in standing:
        output_str += post + '\n'
    output_str += '```'
    await context.send(output_str)


# Prototyped
@bot.command(name='candidates', help='Prints the candidates and their intros')
async def candidates(context, post=None):
    # Only respond if used in a channel called 'voting'
    if context.channel.name != 'voting':
        return

    members = get_members()
    if post:
        if post in standing:
            random.shuffle(standing[post])
            await context.send("Candidates standing for " + post + ":")
            for candidate in standing[post]:
                if not candidate[2]:
                    await context.send(content=" - " + members[candidate[0]] + ": " + candidate[1])
                else:
                    await context.send(content=" - " + members[candidate[0]] + ": " + candidate[1], file=candidate[2])
            await context.send('--------')
        else:
            await context.send('Looks like that post isn\'t in this election, use ?posts to see the posts up for election`')
    else:
        for post in standing:
            random.shuffle(standing[post])
            await context.send("Candidates standing for " + post + ":")
            for candidate in standing[post]:
                if not candidate[2]:
                    await context.send(content=" - " + members[candidate[0]] + ":" + candidate[1])
                else:
                    await context.send(content=" - " + members[candidate[0]] + ":" + candidate[1], file=candidate[2])
            await context.send('--------')


@bot.command(name='rules', help='Prints the rules and procedures for the election')
async def rules(context):
    # Only respond if used in a channel called 'voting'
    if context.channel.name != 'voting':
        return


# Prototyped # make the post .tolower ed
@bot.command(name='setup', help='Creates the specified post')
async def setup(context, *post):
    # FIX THIS
    ron = True
    post = ' '.join(post)
    # Only respond if used in a channel called 'committee-general'
    if context.channel.name != 'committee-general':
        return
    if ron:
        standing[post] = [(0, "I am not satisfied with any of the candidates", None)]
    await context.send(post + " post created")

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

@bot.event
async def on_reaction_add(reaction, user):
    if current_live_post:
        # Check if react is not valid, and if so, tell them they fucked up
        if reaction.emoji not in lookup:
            await user.send("You can't react with that emoji, you must remove it else your ballot will not be counted")
            return

        # Check if ranking is higher than the total number of positions
        if lookup[reaction.emoji] + 1 > len(standing[current_live_post]):
            await user.send("You can't react with a higher ranking than the number of candidates up for election,"
                            "you must fix this else your ballot will not be counted")
            return
        # Check if there is more than one react, and if so, tell them they fucked up
        if len(reaction.message.reactions) > 1:
            await user.send("You can't react to each candidate with more than one value, you must fix this else your ballot will not be counted")

        all_reactions = []
        for _, message_id in voting_messages[user.id]:
            message = await bot.get_user(user.id).fetch_message(message_id)
            all_reactions.extend([react.emoji for react in message.reactions])
            
        # Check if they put the same ranking to more than one candidate, and if so, tell them they fucked up
        if all_reactions.count(reaction) > 1:
            await user.send("You can't react to more than one candidate with the same value, you must fix this else your ballot will not be counted")
            
        # Check if they try to do :three: before :two:, etc, and if so, tell them they fucked up
        for i in range(lookup[reaction.emoji]):
            react_to_check = list(lookup.keys())[i]
            if react_to_check not in all_reactions:
                await user.send("Looks like you've skipped ranking " + react_to_check + ", you must fix this else your ballot will not be counted")


# Format -> {<User ID>: [(<Candidate Student ID>, <Message ID>), ...]}
voting_messages = {}

rules_string = ("Do not react with any reactions other than the number reacts 1️⃣  - 9️⃣\n"
               "Do not react with the ranking higher than the number of candidates (e.g. if there are three candidates, don't react 4️⃣ to any candidates)\n"
               "Do not vote for one candidate multiple times\n"
               "Do not give the same ranking to multiple candidates\n"
               "Do not skip rankings (e.g. give a candidate a '3️⃣' without giving any candidate a '2️⃣')\n"
               "If you do not follow these rules, your vote will not be counted\n"
)
@bot.command(name='begin', help='Begins the election for the specified post')
async def begin(context, post):
    global current_live_post
    # Only respond if used in a channel called 'voting'
    if context.channel.name != 'voting':
        return
    # Only available to committee members
    if not any([True for role in context.author.roles if str(role) == "committee"]):
        return
    if current_live_post:
        await context.send('You can\'t start a new vote until the last one has finished')
        return

    members = get_members()
    # Prints the candidates for each post in a seperate message
    await candidates(context, post)

    current_live_post = post
    print("Voting has now begun for post:", post)
    for voter in registered_members:
        user = bot.get_user(voter)
        await user.send("Voting has now begun for post: " + post)
        await user.send(rules_string)
        await user.send("Ballot Paper for " + post + " (Please react to the messages below):")
        await user.send("\*\*\*\*\*\*\*\*\*\*")
        random.shuffle(standing[post])
        # Message the member with the shuffled candidate list, each candidate in a seperate message, record the ID of the message
        if user.id not in voting_messages:
            voting_messages[user.id] = []

        for candidate in standing[post]:
            message = await user.send(" - " + members[candidate[0]])
            #need to store A. the user it was sent to, B. Which candidate is in the message, C. The message ID
            voting_messages[user.id].append((candidate[0], message.id))
        await user.send("\*\*\*\*\*\*\*\*\*\*")
        await user.send("End of Ballot Paper for " + post)

    await context.send("All registered voters will have just recieved a message from me. Please vote by reacting to the candidates listed in your DMs where :one: is your top candidate, :two: is your second top candidate, etc")

    print(voting_messages)
       
    # People react with their ranking number for each candidate

@bot.command(name='validate', help='Checks to see if your vote will be accepted')
async def validate(context):
    # THIS SHOULD PROBABLY REPLACE ALL THE STUFF THAT HAPPENS ON EACH REACT
    pass

def calculate_results(candidates, ballots_in):
    ballots = [Ballot(ranked_candidates=[vote for vote in ballot if str(vote) != '']) for ballot in ballots_in]
    election_result = pyrankvote.instant_runoff_voting(candidates, ballots)
    return election_result

@bot.command(name='end', help='Ends the election for the currently live post')
async def end(context):
    global current_live_post
    global voting_messages
    # Only respond if used in a channel called 'voting'
    if context.channel.name != 'voting':
        return
    # Only available to committee members
    if not any([True for role in context.author.roles if str(role) == "committee"]):
        return
    
    last_live_post = current_live_post
    current_live_post = None
    print("Voting has now ended for post:", last_live_post)
    for voter in registered_members:
        if voter != "RON":
            user = bot.get_user(voter)
            await user.send("Voting has now ended for post: " + last_live_post)

    votes = {}
    for candidate in standing[last_live_post]:
        votes[candidate[0]] = [0] * len(standing[last_live_post])

    # Count reacts for each candidate and calculate scores
    for user_id, data in voting_messages.items():
        for candidate, message_id in data:
            message = await bot.get_user(user_id).fetch_message(message_id)
            for reaction in message.reactions:
                votes[candidate][lookup[reaction.emoji]] += 1

    new_votes = []
    members = get_members()
    candidates = {candidate[0]: Candidate(members[candidate[0]]) for candidate in standing[last_live_post]}
    candidates[0] = Candidate('RON (Re-Open-Nominations)')

    for user_id, data in voting_messages.items():
        new_votes.append([''] * len(standing[last_live_post]))
        for candidate, message_id in data:
            message = await bot.get_user(user_id).fetch_message(message_id)
            if len(message.reactions) > 0:
                new_votes[-1][lookup[message.reactions[0].emoji]] = candidates[candidate]
    results = calculate_results(list(candidates.values()), new_votes)

    # Announce the scores and the winner (I guess this could be a message to the committee instead, who could then announce it?)
    winner = results.get_winners()[0]

    print("Result:", results)
    print("Winner:", winner)
    
    await context.send("The votes are tallied as follows:")
    await context.send("```" + str(results) + "```")
    await context.send("The winning candidate for " + last_live_post + " is: " + str(winner))

    voting_messages = {}
        

bot.run(TOKEN)

