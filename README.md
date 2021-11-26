# Society voting-bot
A Discord bot for doing society elections. The voting system used is Instant Runoff Voting.

## Dependencies
    pip install -U Discord.py python-dotenv pyrankvote aiorwlock

## Setup

You'll need to create a discord bot of your own in the [Discord Developer Portal](https://discord.com/developers/applications) with View Channels and Read Messages permissions. It's also handy if you have an empty server (or "guild") for you to test in. This section of [this guide](https://realpython.com/how-to-make-a-discord-bot-python/#how-to-make-a-discord-bot-in-the-developer-portal) may be helpful to set that up.

You'll need to set seven environment variables:
* DISCORD_TOKEN -> The Discord token for the bot you created (available on your bot page in the developer portal).
* COMMITTEE_CHANNEL_ID -> The Discord channel ID for the committee channel, this is where you setup new posts, get the members list and see results. This should be a channel only available to committee members.
* VOTING_CHANNEL_ID -> The Discord channel ID for the voting channel, this is where elections are started by committee members. This should be a channel only available to members.
* COMMITTEE_ROLE_ID -> The role ID for committee members (who are the only people who can start/end voting)

* UNION_URL -> The URL of the Students Union/Guild of Students members page (make sure it's listed by group).
* UNION_COOKIE -> Your Students Union/Guild of Students session cookie so the bot has permission to view your members list (You can extract this from your web browser after signing in to the Students Union/Guild of Students website. You must be a committee member).

* VOTERS_FILE -> The file that the registered voter list is backed up to.
* STANDING_FILE -> The file that the standing candidates list is backed up to.
* REFERENDA_FILE -> The file that the list of referenda is backed up to.
* NAMES_FILE -> The file that the list of preferred names is backed up to.

* SHEET_ID -> The ID for the spreadsheet in which to enter details of the standing candidates. This should only be accessible to the committee, or better yet, just the secretary.

* SECRETARY_NAME -> The name of the current secretary.
* SECRETARY_EMAIL -> The email address of the secretary. This is needed in case a candidate cannot make the live election call, and to notify the secretary of new candidates.

* SMTP_SERVER -> The SMTP server to use when sending emails.
* SMTP_PORT -> The SMTP port to use when sending emails.
* SENDER_EMAIL -> The email from which to send emails.
* SENDER_PASSWORD -> The password for the SENDER_EMAIL. If using gmail you'll need to enable insecure apps and set up an app-specific password.


* VOTING_CODE -> The code required to submit a vote, used to ensure only people in the live election call are able to vote. This is not case sensitive and must be given out during the call. 

You can put these in a .env file in the repo directory as it uses dotenv (see [here](https://pypi.org/project/python-dotenv/) for usage) so you don't have to keep them in your environment.

You will also need a token.json file to authorise access to the Google Sheets API and a Google account with access to the candidates spreadsheet. [This guide](https://developers.google.com/sheets/api/quickstart/python) will generate the correct token, as long as you set it up to use the "auth/spreadsheets" scope, in both the OAuth Credentials step, and the example code.

Bot requires send message and edit message permissions for full functionality
## Contributions

In short, patches welcome. If you raise a PR, I'll review it, test it, and (probably) merge it.
If you find any bugs/problems or have any suggestions, please raise an issue.
