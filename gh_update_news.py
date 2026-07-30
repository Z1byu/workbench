#!/usr/bin/env python3
"""
Fetch fresh news from 60s.viki.moe and update index.html with embedded news data.
Designed to run in GitHub Actions environment.
"""
import json
import urllib.request
import urllib.parse
import re
import os

API_BASE = 'https://60s.viki.moe/v2'
SOURCES = [
    ('weibo',   '\U0001f50d', '\u5fae\u535a\u70ed\u641c',       '#E6162D', '/weibo'),
    ('douyin',  '\U0001f3b5', '\u6296\u97f3\u70ed\u70b9',       '#161823', '/douyin'),
    ('toutiao', '\U0001f4f0', '\u4eca\u65e5\u5934\u6761',       '#ED1C24', '/toutiao'),
    ('zhihu',   '\U0001f4a1', '\u77e5\u4e4e\u70ed\u699c',       '#0084FF', '/zhihu'),
    ('news60s', '\U0001f4e2', '\u6bcf\u592960\u79d2\u8bfb\u61c2\u4e16\u754c', '#FF6600', '/60s'),
]

HTML_FILE = 'index.html'

def fetch_news():
    result = {}
    for sid, icon, name, color, path in SOURCES:
        try:
            url = API_BASE + path
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = json.loads(resp.read().decode('utf-8'))
            if raw.get('code') != 200 or not raw.get('data'):
                continue
            items = []
            if sid == 'news60s':
                for i, text in enumerate(raw['data'].get('news', [])):
                    items.append({
                        'title': text,
                        'url': 'https://www.baidu.com/s?wd=' + urllib.parse.quote(text),
                        'sourceName': name,
                        'rank': i + 1,
                        'time': ''
                    })
            else:
                for i, item in enumerate(raw['data'][:20]):
                    title = item.get('title', '')
                    link = item.get('link') or ('https://www.baidu.com/s?wd=' + urllib.parse.quote(title))
                    hot = item.get('hot_value', 0)
                    items.append({
                        'title': title,
                        'url': link,
                        'sourceName': name,
                        'rank': i + 1,
                        'time': ('\U0001f525 ' + str(hot)) if hot else ''
                    })
            if items:
                result[sid] = {'icon': icon, 'name': name, 'color': color, 'items': items}
            print(f'  {name}: {len(items)} items')
        except Exception as e:
            print(f'  {name} FAILED: {e}')
    return result


def update_html(news_data):
    if not os.path.exists(HTML_FILE):
        print(f'ERROR: {HTML_FILE} not found')
        return False

    with open(HTML_FILE, 'r', encoding='utf-8') as f:
        html = f.read()

    news_json = json.dumps(news_data, ensure_ascii=False)

    # Replace EMBEDDED_NEWS data
    # Pattern: let EMBEDDED_NEWS = {...}; // 内嵌新闻数据
    pattern = r'let EMBEDDED_NEWS\s*=\s*\{.*?\};\s*//\s*内嵌新闻数据'
    replacement = f'let EMBEDDED_NEWS = {news_json}; // 内嵌新闻数据（自动更新）'

    new_html, count = re.subn(pattern, replacement, html, flags=re.DOTALL)

    if count == 0:
        # Try alternate pattern without comment
        pattern2 = r'let EMBEDDED_NEWS\s*=\s*\{.*?\};'
        new_html, count = re.subn(pattern2, replacement, html, flags=re.DOTALL)

    if count == 0:
        print('WARNING: Could not find EMBEDDED_NEWS pattern, trying to insert after newsData declaration')
        # Insert after "let newsData = null;"
        new_html = html.replace(
            'let newsData = null;',
            f'let newsData = null;\nlet EMBEDDED_NEWS = {news_json}; // 内嵌新闻数据（自动更新）',
            1
        )
        count = 1

    if count > 0:
        with open(HTML_FILE, 'w', encoding='utf-8') as f:
            f.write(new_html)
        print(f'  HTML updated: {len(new_html)} bytes')
        return True
    else:
        print('ERROR: Could not update EMBEDDED_NEWS in HTML')
        return False


def main():
    print('Fetching news from 60s.viki.moe...')
    news_data = fetch_news()
    print(f'Total: {len(news_data)} sources')

    if not news_data:
        print('ERROR: No news data fetched, aborting')
        return

    print('Updating HTML...')
    if update_html(news_data):
        print('Done! HTML updated with fresh news data.')
    else:
        print('Failed to update HTML.')


if __name__ == '__main__':
    main()
