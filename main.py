#!/usr/bin/env python3.7
# -*- coding: utf-8 -*-

import hashlib
import json
import math
import os
import re
import requests
import shlex
import signal
import struct
import sys
import threading
import time
import types
from PIL import Image
from io import BytesIO
from bilibili import Bilibili
#from picture import Encoder

bundle_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
default_url = lambda sha1: f"http://i0.hdslb.com/bfs/album/{sha1}.png"
meta_string = lambda url: ("bd:pg:" + re.findall(r"[a-fA-F0-9]{40}", url)[0]) if re.match(r"^http(s?)://i0.hdslb.com/bfs/album/[a-fA-F0-9]{40}.png$", url) else url
size_string = lambda byte: f"{byte / 1024 / 1024 / 1024:.2f} GB" if byte > 1024 * 1024 * 1024 else f"{byte / 1024 / 1024:.2f} MB" if byte > 1024 * 1024 else f"{byte / 1024:.2f} KB" if byte > 1024 else f"{int(byte)} B"

def log(message):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}] {message}")

def encode_png(data):
        minw = 2048
        minh = 1080
        dep = 3
        mode = 'RGB'
    
        data = struct.pack('<I', len(data)) + data
        
        minsz = minw * minh * dep
        if len(data) < minsz:
            data = data + b'\0' * (minsz - len(data))
        
        rem = len(data) % (minw * dep)
        if rem != 0:
            data = data + b'\0' * (minw * dep - rem)
        hei = len(data) // (minw * dep)
        
        img = Image.frombytes(mode, (minw, hei), data)
        bio = BytesIO()
        img.save(bio, 'png')
        return bio.getvalue()

def calc_sha1(data, hexdigest=False):
    sha1 = hashlib.sha1()
    if isinstance(data, types.GeneratorType):
        for chunk in data:
            sha1.update(chunk)
    else:
        sha1.update(data)
    return sha1.hexdigest() if hexdigest else sha1.digest()

def read_in_chunk(file_name, chunk_size=16 * 1024 * 1024, chunk_number=-1):
    chunk_counter = 0
    with open(file_name, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if data != b"" and (chunk_number == -1 or chunk_counter < chunk_number):
                yield data
                chunk_counter += 1
            else:
                return

def read_history(dirs,file):
    try:
        with open(os.path.join(dirs, file), "r", encoding="utf-8") as f:
            history = json.loads(f.read())
    except:
        history = {}
    return history

def get_file(root_path, all_files=[]):
        files = os.listdir(root_path)
        for file in files:
            if not os.path.isdir(root_path + '\\' + file):   # not a dir
               all_files.append(root_path + '\\' + file)
            else:  # is a dir
              get_file((root_path + '\\' + file), all_files)
        return all_files

def login():
    bilibili = Bilibili()
    username = input("username > ")
    password = input("password > ")
    if bilibili.login(username, password):
        bilibili.get_user_info()
        with open(os.path.join(bundle_dir, "cookies.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(bilibili.get_cookies(), ensure_ascii=False, indent=2))

def image_upload(data, cookies):
    url = "https://api.vc.bilibili.com/api/v1/drawImage/upload"
    headers = {
        'Origin': "https://t.bilibili.com",
        'Referer': "https://t.bilibili.com/",
        'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.79 Safari/537.36",
    }
    files = {
        'file_up': (f"{int(time.time() * 1000)}.png", data),
    }
    data = {
        'biz': "draw",
        'category': "daily",
    }
    try:
        response = requests.post(url, data=data, headers=headers, cookies=cookies, files=files, timeout=300).json()
    except:
        response = None
    return response

def upload(file_name, thread, block_size,folder,write):
    def core(index, block):
        try:
            block_sha1 = calc_sha1(block, hexdigest=True)
            full_block = encode_png(block)
            full_block_sha1 = calc_sha1(full_block, hexdigest=True)
            url = is_skippable(full_block_sha1)
            if url:
                log(f"分块{index + 1}/{block_num}上传完毕")
                block_dict[index] = {
                    'url': url,
                    'size': len(block),
                    'sha1': block_sha1,
                }
            else:
                # log(f"分块{index + 1}/{block_num}开始上传")
                for _ in range(10):
                    if terminate_flag.is_set():
                        return
                    response = image_upload(full_block, cookies)
                    if response:
                        if response['code'] == 0:
                            url = response['data']['image_url']
                            log(f"分块{index + 1}/{block_num}上传完毕")
                            block_dict[index] = {
                                'url': url,
                                'size': len(block),
                                'sha1': block_sha1,
                            }
                            return
                        elif response['code'] == -4:
                            terminate_flag.set()
                            log(f"分块{index + 1}/{block_num}第{_ + 1}次上传失败, 请重新登录")
                            return
                    log(f"分块{index + 1}/{block_num}第{_ + 1}次上传失败")
                else:
                    terminate_flag.set()
        except:
            terminate_flag.set()
        finally:
            done_flag.release()

    def is_skippable(sha1):
        url = default_url(sha1)
        headers = {
            'Referer': "http://t.bilibili.com/",
            'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.79 Safari/537.36",
        }
        for _ in range(5):
            try:
                response = requests.head(url, headers=headers, timeout=13)
                return url if response.status_code == 200 else None
            except:
                pass
        return None

    def write_history(first_4mb_sha1, meta_dict, url,write):
        history = read_history(bundle_dir,write)
        history[first_4mb_sha1] = meta_dict
        history[first_4mb_sha1]['url'] = url
        dirs = os.path.dirname(file_name) if write[-7:]==".bdsync" else bundle_dir
        with open(os.path.join(dirs, write), "w", encoding="utf-8") as f:
            f.write(json.dumps(history, ensure_ascii=False, indent=2))

    start_time = time.time()
    if not os.path.exists(file_name):
        log(f"文件{file_name}不存在")
        return None
    if os.path.isdir(file_name):
        log("上传文件夹请至uploadall")
        return None
    log(f"上传: {os.path.basename(file_name)} ({size_string(os.path.getsize(file_name))})")
    
    if os.path.getsize(file_name)<=80*1024*1024: #80MB
        if block_size==0 : block_size=4
        if thread==0 : thread=8  
    if os.path.getsize(file_name)>80*1024*1024 and os.path.getsize(file_name)<=500*1024*1024: #500MB
        if block_size==0 : block_size=8
        if thread==0 : thread=8
    if os.path.getsize(file_name)>500*1024*1024:
        if block_size==0 : block_size=16
        if thread==0 : thread=8    
    
    first_4mb_sha1 = calc_sha1(read_in_chunk(file_name, chunk_size=4 * 1024 * 1024, chunk_number=1), hexdigest=True)
    history = read_history(bundle_dir,"history.json") if write[-7:]!=".bdsync" else read_history(os.path.dirname(file_name),write)
    if first_4mb_sha1 in history:
        url = history[first_4mb_sha1]['url']
        log(f"文件已于{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(history[first_4mb_sha1]['time']))}上传, 共有{len(history[first_4mb_sha1]['block'])}个分块")
        log(f"META URL -> {meta_string(url)}")
        return url
    try:
        with open(os.path.join(bundle_dir, "cookies.json"), "r", encoding="utf-8") as f:
            cookies = json.loads(f.read())
    except:
        log("Cookies加载失败, 请先登录")
        return None
    log(f"线程数: {thread}")
    done_flag = threading.Semaphore(0)
    terminate_flag = threading.Event()
    thread_pool = []
    block_dict = {}
    block_num = math.ceil(os.path.getsize(file_name) / (block_size * 1024 * 1024))
    log(f"分块大小: {block_size} MB")
    log(f"分块数: {block_num}")
    for index, block in enumerate(read_in_chunk(file_name, chunk_size=block_size * 1024 * 1024)):
        if len(thread_pool) >= thread:
            done_flag.acquire()
        if not terminate_flag.is_set():
            thread_pool.append(threading.Thread(target=core, args=(index, block)))
            thread_pool[-1].start()
        else:
            log("已终止上传, 等待线程回收")
            break
    for thread in thread_pool:
        thread.join()
    if terminate_flag.is_set():
        return None
    sha1 = calc_sha1(read_in_chunk(file_name), hexdigest=True)
    fn = os.path.abspath(file_name) if folder else os.path.basename(file_name)
    meta_dict = {
        'time': int(time.time()),
        'filename': fn,
        'size': os.path.getsize(file_name),
        'sha1': sha1,
        'block': [block_dict[i] for i in range(len(block_dict))],
    }
    meta = json.dumps(meta_dict, ensure_ascii=False).encode("utf-8")
    full_meta = encode_png(meta)
    for _ in range(10):
        response = image_upload(full_meta, cookies)
        if response and response['code'] == 0:
            url = response['data']['image_url']
            log("元数据上传完毕")
            log(f"{meta_dict['filename']} ({size_string(meta_dict['size'])}) 上传完毕, 用时{time.time() - start_time:.1f}秒, 平均速度{size_string(meta_dict['size'] / (time.time() - start_time))}/s")
            log(f"META URL -> {meta_string(url)}")
            write_history(first_4mb_sha1, meta_dict, url,write)
            return url
        log(f"元数据第{_ + 1}次上传失败")
    else:
        return None

def decode_png(data):
        img = Image.open(BytesIO(data))
        data = img.tobytes()
        
        sz = struct.unpack('<I', data[:4])[0]
        data = data[4:4+sz]
        return data

def image_download(url):
    headers = {
        'Referer': "http://t.bilibili.com/",
        'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.79 Safari/537.36",
    }
    content = []
    last_chunk_time = None
    try:
        for chunk in requests.get(url, headers=headers, timeout=10, stream=True).iter_content(128 * 1024):
            if last_chunk_time is not None and time.time() - last_chunk_time > 5:
                return None
            content.append(chunk)
            last_chunk_time = time.time()
        return b"".join(content)
    except:
        return None

def fetch_meta(string):
    try:
        sha1 = re.search(r"[a-fA-F0-9]{40}", string)
        full_meta = image_download(f"http://i0.hdslb.com/bfs/album/{sha1.group(0)}.png")
        meta_dict = json.loads(decode_png(full_meta).decode("utf-8"))
        return meta_dict
    except:
        return None

def download(meta, file, thread, folder):
    def core(index, block_dict):
        try:
            # log(f"分块{index + 1}/{len(meta_dict['block'])}开始下载")
            for _ in range(10):
                if terminate_flag.is_set():
                    return
                block = image_download(block_dict['url'])
                if block:
                    block = decode_png(block)
                    if calc_sha1(block, hexdigest=True) == block_dict['sha1']:
                        file_lock.acquire()
                        f.seek(block_offset(index))
                        f.write(block)
                        file_lock.release()
                        log(f"分块{index + 1}/{len(meta_dict['block'])}下载完毕")
                        return
                    else:
                        log(f"分块{index + 1}/{len(meta_dict['block'])}校验未通过")
                else:
                    log(f"分块{index + 1}/{len(meta_dict['block'])}第{_ + 1}次下载失败")
            else:
                terminate_flag.set()
        except:
            terminate_flag.set()
        finally:
            done_flag.release()

    def block_offset(index):
        return sum(meta_dict['block'][i]['size'] for i in range(index))

    def is_overwritable(file_name):
        return (input("文件已存在, 是否覆盖? [y/N] ") in ["y", "Y"])

    start_time = time.time()
    meta_dict = fetch_meta(meta)
    if meta_dict:
        if ('end' in meta_dict):
            downloadall("","",meta)
            return None
        else:
            file_name = file if file else meta_dict['filename']
            log(f"下载: {os.path.basename(file_name)} ({size_string(meta_dict['size'])}), 共有{len(meta_dict['block'])}个分块, 上传于{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(meta_dict['time']))}")
    else:
        log("元数据解析失败")
        return None
    log(f"线程数: {thread}")
    download_block_list = []
    if os.path.exists(file_name):
        if os.path.getsize(file_name) == meta_dict['size'] and calc_sha1(read_in_chunk(file_name), hexdigest=True) == meta_dict['sha1']:
            log("文件已存在, 且与服务器端内容一致")
            return file_name
        elif is_overwritable(file_name):
            with open(file_name, "rb") as f:
                for index, block_dict in enumerate(meta_dict['block']):
                    f.seek(block_offset(index))
                    if calc_sha1(f.read(block_dict['size']), hexdigest=True) == block_dict['sha1']:
                        # log(f"分块{index + 1}/{len(meta_dict['block'])}校验通过")
                        pass
                    else:
                        # log(f"分块{index + 1}/{len(meta_dict['block'])}校验未通过")
                        download_block_list.append(index)
            log(f"{len(download_block_list)}/{len(meta_dict['block'])}个分块待下载")
        else:
            return None
    else:
        download_block_list = list(range(len(meta_dict['block'])))
    done_flag = threading.Semaphore(0)
    terminate_flag = threading.Event()
    file_lock = threading.Lock()
    thread_pool = []

    if folder :
        if os.path.exists(os.path.dirname(file_name))==False :  # 还原目录的文件下载
            os.makedirs(os.path.dirname(file_name))
    with open(file_name, "r+b" if os.path.exists(file_name) else "wb") as f:
        for index in download_block_list:
            if len(thread_pool) >= thread:
                done_flag.acquire()
            if not terminate_flag.is_set():
                thread_pool.append(threading.Thread(target=core, args=(index, meta_dict['block'][index])))
                thread_pool[-1].start()
            else:
                log("已终止下载, 等待线程回收")
                break
        for thread in thread_pool:
            thread.join()
        if terminate_flag.is_set():
            return None
        f.truncate(sum(block['size'] for block in meta_dict['block']))
    log(f"{os.path.basename(file_name)} ({size_string(meta_dict['size'])}) 下载完毕, 用时{time.time() - start_time:.1f}秒, 平均速度{size_string(meta_dict['size'] / (time.time() - start_time))}/s")
    sha1 = calc_sha1(read_in_chunk(file_name), hexdigest=True)
    if sha1 == meta_dict['sha1']:
        log("文件校验通过")
        return file_name
    else:
        log("文件校验未通过")
        return None

def uploadall(path):
    def write_history(first_4mb_sha1, meta_dict, url, write):
        history = read_history(bundle_dir,write)
        history[first_4mb_sha1] = meta_dict
        if url:
            history[first_4mb_sha1]['url'] = url
        with open(os.path.join(bundle_dir, write), "w", encoding="utf-8") as f:
            f.write(json.dumps(history, ensure_ascii=False, indent=2))

    if not os.path.exists(path):
        print("目录不存在")
        return None
    torrent = f"upload-{time.strftime('%Y%m%d-%H%M%S', time.localtime(time.time()))}.bd"
    with open(os.path.join(bundle_dir, torrent), "a", encoding="utf-8") as f:
        f.write(json.dumps({}, ensure_ascii=False, indent=2))
    index = 0
    files_num = len(get_file(path,[]))
    for i in get_file(path,[]):
        index += 1
        log(f"=== 正在上传 {index}/{files_num} {i} ===")
        upload(i,0,0,True,torrent)
    # 编码数据集上传
    try:
        with open(os.path.join(bundle_dir, "cookies.json"), "r", encoding="utf-8") as f:
            cookies = json.loads(f.read())
    except:
        log("Cookies加载失败, 请先登录")
        return None
    
    end = {
        'time': int(time.time()),
        'root_path': path,
        'files_num': files_num
    }
    write_history('end',end,"",torrent)
    meta = json.dumps(read_history(bundle_dir,torrent), ensure_ascii=False).encode("utf-8")
    full_meta = encode_png(meta)
    for _ in range(10):
        response = image_upload(full_meta, cookies)
        if response and response['code'] == 0:
            url = response['data']['image_url']
            log("所有文件元数据上传完毕")
            log(f"META URL -> {meta_string(url)}")
            write_history('end',end,url,torrent)
            return url
        log(f"元数据第{_ + 1}次上传失败")
    else:
        return None


def downloadall(jsonfile,bdfile,meta):
    if jsonfile:
        if not os.path.exists(jsonfile):
            print('无history.json文件')
            return None
        else:
            if not os.path.exists(bundle_dir + "\\download"):
                os.makedirs(bundle_dir + "\\download")
            os.chdir(bundle_dir + "\\download")
            with open(os.path.join(jsonfile), "r", encoding="utf-8") as f:
                history = json.loads(f.read())
            num = 0
            for i in history :
                num += 1
                file = history[i]["filename"]
                log(f"=== 正在下载 {num}/{len(history)} {file} ===")
                download(history[i]["url"],file,8,False)
    elif bdfile:
        if not os.path.exists(bdfile):
            print('无upload.bd文件')
            return None
        else:
            with open(os.path.join(bdfile), "r", encoding="utf-8") as f:
                history = json.loads(f.read())
            num = 0
            for i in history :
                num += 1
                if i=="end": return None
                file = history[i]["filename"]
                file = file.replace(os.path.dirname(os.path.dirname(history["end"]["root_path"])),"")
                log(f"=== 正在下载 {num}/{len(history)-1} {file} ===")
                download(history[i]["url"],file,8,True)
    elif meta:
        history = fetch_meta(meta)
        num = 0
        for i in history :
            num += 1
            if i=="end": return None
            file = history[i]["filename"]
            file = file.replace(os.path.dirname(os.path.dirname(history["end"]["root_path"])),"")
            log(f"=== 正在下载 {num}/{len(history)-1} {file} ===")
            download(history[i]["url"],file,8,True)

def basemeta():
    meta = input("meta > ")
    sha1 = re.search(r"[a-fA-F0-9]{40}", meta)
    meta_dict = fetch_meta(meta)
    txt = f"{sha1.group(0)}.txt"
    with open(os.path.join(bundle_dir, f"{sha1.group(0)}.txt"), "w", encoding="utf-8") as f:
        f.write(json.dumps(meta_dict, ensure_ascii=False, indent=2))
    print(f"元数据导出到 {sha1.group(0)}.txt ")

def output():
    file = input("history_file > ")
    if file:
        try:
            with open(os.path.join(file), "r", encoding="utf-8") as f:
                history = json.loads(f.read())
        except:
            history = {}
    else:
        history = read_history(bundle_dir,"history.json")
    if history:
        txt = f"history-{time.strftime('%Y%m%d-%H%M%S', time.localtime(time.time()))}.txt"
        for meta_dict in history:
            with open(os.path.join(bundle_dir, txt), "a", encoding="utf-8") as f:
                f.write(f"文件名: {history[meta_dict]['filename']}\n")
                f.write(f"大小: {size_string(history[meta_dict]['size'])}\n")
                f.write(f"SHA-1: {history[meta_dict]['sha1']}\n")
                f.write(f"上传时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(history[meta_dict]['time']))}\n")
                f.write(f"分块数: {len(history[meta_dict]['block'])}\n")
                f.write(f"分块大小：{size_string(history[meta_dict]['block'][0]['size'])}\n")
                f.write(f"META URL -> {meta_string(history[meta_dict]['url'])}\n")
                f.write(f"\n")
                f.write(f"\n")
        print(f"导出完成")
    else:
        print(f"暂无历史记录")

def syncup(path):
    for i in get_file(path,[]):
        if i[-7:]!=".bdsync":
            log(f"=== 正在上传 {os.path.basename(i)} ===")
            upload(i,0,0,False,f"{os.path.basename(i)}.bdsync")
            os.system('attrib +h ' + f'"{i}.bdsync"')


def syncdel(path):
    for i in get_file(path,[]):
        history = read_history(os.path.dirname(i),f"{(os.path.basename(i))}.bdsync")
        for j in history:
            if history[j]["sha1"] == calc_sha1(read_in_chunk(i), hexdigest=True) :
                os.remove(i)
                log(f"释放文件 {(os.path.basename(i))}")
            else:
                log(f"改动的文件 {(os.path.basename(i))}")

def syncdown(path):
    for i in get_file(path,[]):
        if i[-7:]==".bdsync":
            history = read_history(os.path.dirname(i),f"{(os.path.basename(i))}")
            for j in history:
                os.chdir(os.path.dirname(i))
                download(history[j]["url"],"",8,False)


def main():
    print("Welcome to Bilibili Drive")
    print("软件交流QQ群  ⁹²⁷²⁵⁶⁰⁹⁰")
    print()
    print("login           登录哔哩哔哩")
    print("upload          上传单个文件")
    print("download        下载单个文件")
    print("uploadall       批量上传文件")
    print("downloadall     批量下载文件")
    print("info            查看数据信息")
    print("output          导出历史记录")
    print("syncup          上传同步文件")
    print("syncdel         清理同步文件")
    print("syncdown        下载同步文件")
    while True:
        action = input("BiliDrive > ")
        if action == "login":
            login()
        if action == "upload":
            file_name = input("filename > ")
            thread = input("thread > ")
            thread = 0 if thread=="" else int(thread)
            block_size = input("block_size(MB) > ")
            block_size = 0 if block_size=="" else int(block_size)
            upload(file_name,thread,block_size,False,"history.json")
        if action == "uploadall":
            path = input("folder_path > ")
            uploadall(path)
        if action == "download":
            meta = input("meta > ")
            file = input("rename > ")
            thread = input("thread > ")
            thread = 8 if thread=="" else int(thread)
            download(meta, file, thread, False)
        if action == "downloadall":
            print("history_file,bd_file,meta三选一")
            jsonfile = input("history_file > ")
            bdfile = input("bd_file > ")
            meta = input("meta > ")
            downloadall(jsonfile,bdfile,meta)
        if action == "info":
            basemeta()
        if action == "output":
            output()
        if action == "syncup":
            folder = input("folder > ")
            syncup(folder)
        if action == "syncdel":
            folder = input("folder > ")
            if (input("原始文件将被删除，确认吗? [y/N] ") in ["y", "Y"]) :
                syncdel(folder)
        if action == "syncdown":
            folder = input("folder > ")
            syncdown(folder)
        if action == "exit":
            exit()


if __name__ == '__main__':
    main()
