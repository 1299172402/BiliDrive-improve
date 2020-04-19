import requests
from bs4 import BeautifulSoup
import urllib.request
from lxml import html
import json
import re
import os
import sys
a=[20218053,20262893,20314699,20370473,20421609,20463468,20494170,20519964,20548639,20586603,20642564,20697958,20750297,20802453,20957203,21022328,21082712,21147491,21216105,21274015,21331650,21389039,21447403,21504238]

bundle_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
txt = f"刀剑神域2-源2.txt"
with open(os.path.join(bundle_dir, txt), "a", encoding="utf-8") as f:

    for i in a:
        src='https://v.jialingmm.net/mmletv/mms.php?vid='+str(i)+'&type=letv'
        s = requests.session()
        response = s.get(src).content
        s = BeautifulSoup(response, 'lxml')
        s = s.find_all('script')
        m = str(s[2])
        m = re.search(r"var video =  '(.*?)' ;", m)
        f.write(m.group(1))
        f.write(f"\n")
    
print(f"导出完成")