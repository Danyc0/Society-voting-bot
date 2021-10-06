import os 
import re
import requests

from dotenv import load_dotenv

load_dotenv()
URL = os.getenv('UNION_URL')
# This should be extracted from your .ASPXAUTH cookie
COOKIE = os.getenv('UNION_COOKIE')

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

    return members


if __name__ == '__main__':
	print(get_members())
