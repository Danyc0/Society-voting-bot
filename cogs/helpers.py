import time
import datetime
import random
import pickle
import smtplib
import ssl

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiorwlock

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from cogs import society_members

import pyrankvote
from pyrankvote import Candidate, Ballot

from discord.ext import commands
from discord.channel import DMChannel

import os
import datetime
import random
import pickle
import asyncio

from dotenv import load_dotenv

from pyrankvote import Candidate

from discord.ext import commands

# ENVIRONMENTAL VARIABLES #
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

current_live_post_lock = aiorwlock.RWLock()
votes_lock = aiorwlock.RWLock()
voted_lock = asyncio.Lock()

def get_members():
    members = society_members.get_members()
    members[0] = 'RON (Re-Open-Nominations)'

    # Substitute preferred names
    for id in preferred_names:
        members[id] = preferred_names[id]

    return members


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


def log(output_str):
    print(datetime.datetime.now().strftime('%d/%m/%y %H:%M:%S:'), output_str)


def match_post(post):
    return [a for a in standing if a.lower() == post.lower()]


def match_referendum(referendum):
    return [a for a in referenda if a.lower() == referendum.lower()]


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


random.seed(time.time())

load_dotenv()
COMMITTEE_CHANNEL_ID = int(os.getenv('COMMITTEE_CHANNEL_ID'))
VOTING_CHANNEL_ID = int(os.getenv('VOTING_CHANNEL_ID'))
COMMITTEE_ROLE_ID = os.getenv('COMMITTEE_ROLE_ID')

VOTERS_FILE = os.getenv('VOTERS_FILE')
STANDING_FILE = os.getenv('STANDING_FILE')
REFERENDA_FILE = os.getenv('REFERENDA_FILE')
NAMES_FILE = os.getenv('NAMES_FILE')

SHEET_ID = os.getenv('SHEET_ID')

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
