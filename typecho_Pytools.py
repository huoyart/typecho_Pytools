import json
import re
import datetime
import sys
import os
import shutil
import requests
from pytypecho import Typecho, Attachment, Post

# ─── Imgbb 上传相关 ───────────────────────────────────────

# 在此填入你的 Imgbb API Key
IMGBB_API_KEY = ""

def upload_to_imgbb(image_path, api_key):
    """
    上传单张图片到 Imgbb，返回外链 URL 或 None。
    """
    with open(image_path, 'rb') as f:
        resp = requests.post(
            f"https://api.imgbb.com/1/upload?key={api_key}",
            files={'image': f}
        )
    try:
        data = resp.json()
        if data.get('success'):
            return data['data']['url']
        else:
            print(f"[Imgbb 上传失败] {image_path} → {data.get('error', {}).get('message')}")
    except Exception as e:
        print(f"[Imgbb 响应解析失败] {e}")
    return None

def replace_images_in_markdown(md_path, api_key):
    """
    1) 读取 md 文件内容
    2) 用正则匹配所有 ![alt](path)
    3) 对本地路径调用 upload_to_imgbb 上传，拿到新 URL
    4) 替换原文本并返回新的 Markdown 字符串
    """
    text = open(md_path, 'r', encoding='utf-8').read()
    dirname = os.path.dirname(md_path)
    pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

    def repl(m):
        alt, src = m.group(1), m.group(2)
        # 已是远程链接就跳过
        if src.startswith('http'):
            return m.group(0)
        local_file = os.path.join(dirname, src)
        if not os.path.isfile(local_file):
            print(f"[跳过] 本地图片不存在: {local_file}")
            return m.group(0)
        print(f"[上传] {local_file} …")
        new_url = upload_to_imgbb(local_file, api_key)
        if new_url:
            print(f"[替换] {src} → {new_url}")
            return f'![{alt}]({new_url})'
        else:
            return m.group(0)

    return pattern.sub(repl, text)

# ─── 原脚本其余函数 ────────────────────────────────────

def create_config():
    """如果不存在 config.json 则创建，写入默认 URL/用户名/密码"""
    file_path = 'config.json'
    if not os.path.exists(file_path):
        config_data = {
            "url": "http://192.168.188.137",
            "username": "admin",
            "password": "123456"
        }
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
            print(f"文件 {file_path} 已创建并写入配置信息。")
        except Exception as e:
            print(f"创建文件 {file_path} 并写入内容时出错: {e}")

def create_directories():
    """创建 md、hexo_md、ok_md 及 ok_md 下子目录 md、hexo_md"""
    top_dirs = ['md', 'hexo_md', 'ok_md']
    for d in top_dirs:
        try:
            os.makedirs(d, exist_ok=True)
        except Exception as e:
            print(f"创建目录 {d} 时发生错误: {e}")
    for sub in ['md', 'hexo_md']:
        path = os.path.join('ok_md', sub)
        try:
            os.makedirs(path, exist_ok=True)
        except Exception as e:
            print(f"创建目录 {path} 时发生错误: {e}")

def move_file_with_confirmation(source_file, target_folder="ok_md/md"):
    """
    将 source_file 移动到 target_folder，存在时询问是否覆盖
    """
    os.makedirs(target_folder, exist_ok=True)
    if not os.path.isfile(source_file):
        print(f"源文件 {source_file} 不存在，请检查文件路径。")
        return
    dest = os.path.join(target_folder, os.path.basename(source_file))
    if os.path.exists(dest):
        while True:
            yn = input(f"目标文件 {dest} 已存在，是否替换？(y/n): ").strip().lower()
            if yn == 'y':
                try:
                    shutil.move(source_file, dest)
                    print(f"已替换并移动到 {dest}")
                except Exception as e:
                    print(f"移动时出错: {e}")
                break
            elif yn == 'n':
                print("取消移动")
                break
            else:
                print("请输入 y 或 n")
    else:
        try:
            shutil.move(source_file, dest)
            print(f"已移动到 {dest}")
        except Exception as e:
            print(f"移动时出错: {e}")

def read_config():
    """读取 config.json，返回 (xmlrpc_url, username, password)"""
    with open('config.json', 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    url = cfg.get('url', '').rstrip('/')
    url = url + "/index.php/action/xmlrpc"
    return url, cfg.get('username'), cfg.get('password')

def extract_metadata(file_path):
    """
    从 Hexo 风格的 md 文件中提取 title, date, categories, tags
    """
    meta = {'title':'', 'date':'', 'categories':[], 'tags':[]}
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    in_cat = in_tag = False
    for line in lines:
        line = line.strip()
        if line.startswith('title:'):
            meta['title'] = line.split('title:')[1].strip()
        elif line.startswith('date:'):
            meta['date'] = line.split('date:')[1].strip()
        elif line.startswith('categories:'):
            in_cat, in_tag = True, False
        elif line.startswith('tags:'):
            in_cat, in_tag = False, True
        elif line.startswith('-') and in_cat:
            meta['categories'].append(line[1:].strip())
        elif line.startswith('-') and in_tag:
            meta['tags'].append(line[1:].strip())
        elif line and not line.startswith('-'):
            in_cat = in_tag = False
    return meta

def extract_primary(file_path):
    """
    提取 md 内容主体，去掉 Hexo Front Matter 和 [toc]
    """
    content = open(file_path, 'r', encoding='utf-8').read()
    # 去除 --- ... ---
    body = re.sub(r'---.*?---', '', content, flags=re.DOTALL)
    body = re.sub(r'\[toc\]', '', body, flags=re.IGNORECASE)
    return "<!--markdown-->" + body

def check_string_in_array(input_string):
    """
    判断分类名大小写冲突，如果博客已有同名（忽略大小写）分类则返回已有准确名称
    """
    names = [c["categoryName"] for c in te.get_categories()]
    low_names = [n.lower() for n in names]
    if input_string.lower() in low_names:
        return names[low_names.index(input_string.lower())]
    return input_string

def find_md_files(directory):
    """递归查找所有 .md 文件"""
    result = []
    for root, dirs, files in os.walk(directory):
        for fn in files:
            if fn.lower().endswith('.md'):
                result.append(os.path.join(root, fn))
    return result

# ─── 主程序 ───────────────────────────────────────────

# 初始化配置与目录
create_config()
create_directories()
url, username, password = read_config()
te = Typecho(url, username=username, password=password)

while True:
    print("\n----- typecho_Pytools -----")
    print("1、md导入typecho")
    print("2、查看博客数据")
    print("3、删除博客数据")
    print("4、退出")
    try:
        choice = int(input("输入序号: "))
    except:
        continue

    if choice == 1:
        print("1、传统md导入typecho\n2、hexo格式md导入typecho")
        try:
            sub = int(input("输入序号: "))
        except:
            continue

        if sub == 1:
            md_files = find_md_files('md')
            if not md_files:
                input("md 文件夹没有数据，按回车返回")
                continue
            input("检查文件列表后按回车开始导入")
            for idx, md in enumerate(md_files, 1):
                print(f"\n[{idx}/{len(md_files)}] 导入: {md}")
                # 上传图片并替换
                new_md = replace_images_in_markdown(md, IMGBB_API_KEY)
                description = "<!--markdown-->" + new_md

                title = input("输入文章标题: ")
                dateCreated = datetime.datetime.now()
                cat = check_string_in_array(input("输入分类: "))
                tags = input("输入标签(逗号分隔): ").split(',')

                post = Post(
                    title=title,
                    description=description,
                    dateCreated=dateCreated,
                    categories=[cat],
                    mt_keywords=tags
                )
                try:
                    te.new_post(post, publish=True)
                    print("发布成功")
                    move_file_with_confirmation(md, "ok_md/md")
                except Exception as e:
                    print(f"发布失败: {e}")

        elif sub == 2:
            md_files = find_md_files('hexo_md')
            if not md_files:
                input("hexo_md 文件夹没有数据，按回车返回")
                continue
            input("检查文件列表后按回车开始导入")
            for idx, md in enumerate(md_files, 1):
                print(f"\n[{idx}/{len(md_files)}] 导入: {md}")
                # 上传图片并替换
                new_md = replace_images_in_markdown(md, IMGBB_API_KEY)
                description = "<!--markdown-->" + new_md

                meta = extract_metadata(md)
                title = meta['title'] or input("输入文章标题: ")
                try:
                    dateCreated = datetime.datetime.strptime(meta['date'], "%Y-%m-%d %H:%M:%S")
                except:
                    dateCreated = datetime.datetime.now()
                cats = [check_string_in_array(c) for c in meta['categories']]
                tags = meta['tags']

                post = Post(
                    title=title,
                    description=description,
                    dateCreated=dateCreated,
                    categories=cats,
                    mt_keywords=tags
                )
                try:
                    te.new_post(post, publish=True)
                    print("发布成功")
                    move_file_with_confirmation(md, "ok_md/hexo_md")
                except Exception as e:
                    print(f"发布失败: {e}")

        else:
            print("无效选项")

    elif choice == 2:
        # 查看博客数据
        print("功能待实现：查看分类、查看文章、查看评论等")
        input("按回车返回")

    elif choice == 3:
        # 删除博客数据
        print("功能待实现：删除文章、删除评论")
        input("按回车返回")

    elif choice == 4:
        print("退出程序")
        sys.exit(0)

    else:
        continue
