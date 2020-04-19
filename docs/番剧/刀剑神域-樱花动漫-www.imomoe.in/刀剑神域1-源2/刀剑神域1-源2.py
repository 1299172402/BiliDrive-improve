import requests
from bs4 import BeautifulSoup
import urllib.request
from lxml import html
import json
import re
import os
import sys
a=[1657627,1664753,1674220,1690644,1699610,1708232,1714700,1720861,1727274,1735604,1742536,1749231,1757060,1761437,1769133,1775424,1782492,1789523,1796361,1802232,1807504,1827417,1842160,1848393,1854529]

bundle_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
txt = f"刀剑神域1-源2.txt"
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