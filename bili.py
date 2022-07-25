import requests
import time
import qrcode
import json


def get_oauthKey():
    url = 'http://passport.bilibili.com/qrcode/getLoginUrl'
    res = requests.get(url).json()
    return res['data']['oauthKey']


def get_cookies(oauthKey):
    url = 'http://passport.bilibili.com/qrcode/getLoginInfo'
    data = {'oauthKey': oauthKey}

    for _ in range(180):
        res = requests.post(url, data=data).json()
        # print(res)
        if res['status']:
            url = res['data']['url']
            break
        time.sleep(1)

    params = url.split('?')[1]
    data = dict(k.split('=') for k in params.split('&'))
    return data


def save_cookies(cookies):
    with open('cookies.json', 'w', encoding='utf-8') as f:
        f.write(json.dumps(cookies, indent=4))


def main():
    oauthKey = get_oauthKey()

    url = f'https://passport.bilibili.com/qrcode/h5/login?oauthKey={oauthKey}'
    qr = qrcode.QRCode()
    qr.add_data(url)
    qr.print_ascii(invert=True)
    print('若二维码无法识别，请尝试更改终端字体')
    print('将此网址转为二维码，使用哔哩哔哩扫码登录，时限180秒')
    print(url)

    cookies = get_cookies(oauthKey)
    save_cookies(cookies)


if __name__ == '__main__':
    main()
