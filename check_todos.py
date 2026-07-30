#!/usr/bin/env python3
"""
待办提醒检查脚本 - 由 GitHub Actions 定时调用
读取 todos.json，检查到期待办，通过 Bark 推送到手机
"""
import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

# 中国时区 UTC+8
CST = timezone(timedelta(hours=8))

BARK_KEY = os.environ.get('BARK_KEY', '')
GH_TOKEN = os.environ.get('GH_TOKEN', '')
REPO = 'Z1byu/workbench'
TODOS_FILE = 'todos.json'

def log(msg):
    now = datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{now}] {msg}')

def send_bark(title, body, group='待办提醒'):
    """通过 Bark 发送推送"""
    if not BARK_KEY:
        log('BARK_KEY 未设置，跳过推送')
        return False
    url = f'https://api.day.app/{BARK_KEY}/{urllib.parse.quote(title)}/{urllib.parse.quote(body)}?group={urllib.parse.quote(group)}&sound=bell&icon=https://cdn-icons-png.flaticon.com/512/2997/2997491.png'
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            log(f'Bark 推送结果: {result}')
            return result.get('code') == 200
    except Exception as e:
        log(f'Bark 推送失败: {e}')
        return False

def load_todos():
    """从 GitHub 仓库读取 todos.json"""
    url = f'https://api.github.com/repos/{REPO}/contents/{TODOS_FILE}'
    headers = {'Authorization': f'token {GH_TOKEN}', 'Accept': 'application/vnd.github.v3+json'}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            content = json.loads(__import__('base64').b64decode(data['content']).decode('utf-8'))
            return content, data.get('sha', '')
    except Exception as e:
        log(f'读取 todos.json 失败: {e}')
        return None, ''

def save_todos(todos_data, sha):
    """保存 todos.json 到 GitHub 仓库"""
    url = f'https://api.github.com/repos/{REPO}/contents/{TODOS_FILE}'
    headers = {'Authorization': f'token {GH_TOKEN}', 'Accept': 'application/vnd.github.v3+json'}
    content_b64 = __import__('base64').b64encode(json.dumps(todos_data, ensure_ascii=False, indent=2).encode('utf-8')).decode('utf-8')
    payload = json.dumps({
        'message': 'Auto: update todo notified status',
        'content': content_b64,
        'sha': sha
    }).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={**headers, 'Content-Type': 'application/json'}, method='PUT')
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            log('todos.json 已更新')
            return True
    except Exception as e:
        log(f'保存 todos.json 失败: {e}')
        return False

def is_todo_due(todo, now):
    """检查待办是否在当前时间窗口内到期（30分钟窗口）"""
    if not todo.get('reminder', False):
        return False
    if todo.get('done', False):
        return False
    if todo.get('notified', False):
        return False

    todo_time = todo.get('time', '09:00')
    try:
        hour, minute = map(int, todo_time.split(':'))
    except:
        hour, minute = 9, 0

    todo_type = todo.get('type', 'daily')
    today_str = now.strftime('%Y-%m-%d')

    # 检查时间是否匹配（30分钟窗口）
    todo_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    diff_minutes = (now - todo_dt).total_seconds() / 60

    # 如果当前时间在待办时间的0~30分钟内，算作到期
    if diff_minutes < 0 or diff_minutes > 30:
        return False

    # 检查日期匹配
    if todo_type == 'daily':
        return True
    elif todo_type == 'weekly':
        weekdays = todo.get('weekdays', [])
        # Python weekday: Monday=0, Sunday=6
        # 数据中 weekdays 用 0=Sunday, 1=Monday...6=Saturday
        py_weekday = now.weekday()  # Monday=0
        # 转换数据格式: 1=Monday -> py 0, 0=Sunday -> py 6
        data_weekday = py_weekday + 1 if py_weekday < 6 else 0
        return data_weekday in weekdays
    elif todo_type == 'monthly':
        month_day = todo.get('monthDay', 1)
        return now.day == month_day
    elif todo_type == 'oneshot':
        todo_date = todo.get('date', '')
        if todo_date:
            return today_str == todo_date
        return True
    return False

def should_reset(todo, now):
    """检查是否应该重置待办（新的一天）"""
    today_str = now.strftime('%Y-%m-%d')
    last_reset = todo.get('lastResetDate', '')
    return last_reset != today_str

def main():
    log('=== 开始检查待办提醒 ===')

    if not BARK_KEY:
        log('错误: BARK_KEY 环境变量未设置')
        return

    todos_data, sha = load_todos()
    if todos_data is None:
        log('无法读取 todos.json，可能是首次运行，创建空文件')
        todos_data = {"work": [], "life": [], "fitness": [], "study": []}
        sha = ''

    now = datetime.now(CST)
    log(f'当前时间: {now.strftime("%Y-%m-%d %H:%M:%S")} (CST)')

    today_str = now.strftime('%Y-%m-%d')
    reset_count = 0
    notify_count = 0
    has_changes = False

    for category, todo_list in todos_data.items():
        if not isinstance(todo_list, list):
            continue
        for todo in todo_list:
            if not isinstance(todo, dict):
                continue

            # 每日重置
            if should_reset(todo, now) and todo.get('type') in ('daily', 'weekly', 'monthly'):
                todo['lastResetDate'] = today_str
                todo['notified'] = False
                todo['done'] = False
                todo['delayCount'] = 0
                reset_count += 1
                has_changes = True

            # 检查是否到期需要推送
            if is_todo_due(todo, now):
                priority = todo.get('priority', 'normal')
                priority_emoji = {'urgent': '🔴', 'important': '🟡', 'normal': '🟢'}.get(priority, '🟢')
                cat_name = {'work': '工作', 'life': '生活', 'fitness': '健身', 'study': '学习'}.get(category, category)
                title = f'{priority_emoji} {cat_name}提醒'
                body = f'{todo.get("text", "待办事项")}\n⏰ {todo.get("time", "")}'

                log(f'推送提醒: {title} - {body}')
                if send_bark(title, body):
                    todo['notified'] = True
                    notify_count += 1
                    has_changes = True

    log(f'重置: {reset_count} 条, 推送: {notify_count} 条')

    if has_changes:
        save_todos(todos_data, sha)
        log('已保存更新到 GitHub')
    else:
        log('无需更新')

    log('=== 检查完成 ===')

if __name__ == '__main__':
    main()
