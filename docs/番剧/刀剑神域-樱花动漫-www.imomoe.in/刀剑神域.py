import requests
from bs4 import BeautifulSoup
import urllib.request
from lxml import html
import json
i=1

while i<=1:
    src='http://www.imomoe.in/player/1615-0-'+str(i)+'.html'
    s = requests.session()
    response = s.get(src).content
    s = BeautifulSoup(response, 'lxml')
    s = s.find_all('script')
    s = s[10]
    s = s.get('src')
    s = 'http://www.imomoe.in' + s

    src = s
    s = requests.session()
    response = s.get(src).content
    s = BeautifulSoup(response, 'lxml')
    s = s.find('p').text
    s = s[18:][:-57]
    s = s.replace('\'','\"')
    s = json.loads(s)
    for i in s[0][1]:
        print(i)
    for i in s[1][1]:
        print(i)
       
    i=3
