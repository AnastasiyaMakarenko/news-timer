"""Таймер: на каждом тике проверяет расписание и, если пора, запускает workflow в другом репозитории.

Куда смотреть и что запускать — в секретах репозитория (TARGET_REPO, FEED_URL, TOKEN), в логах они скрыты.
Время — SLOTS (по Москве). Если после очередного слота запуск уже был (по времени последней записи в FEED_URL),
ничего не делаем; пропущенный слот догоняется на следующем тике.
"""
import datetime as dt
import json
import os
import subprocess
import urllib.request
from zoneinfo import ZoneInfo

REPO = os.environ["TARGET_REPO"]
FEED = os.environ["FEED_URL"]
WORKFLOW = "news.yml"
MSK = ZoneInfo("Europe/Moscow")

# 10 раз в день, равномерно с 9:00 до 22:00 по Москве
SLOTS = ["09:00", "10:25", "11:55", "13:20", "14:45", "16:15", "17:40", "19:05", "20:35", "22:00"]
# особые дни: дата → свои слоты (пустой список — в этот день больше не запускать)
SPECIAL = {"2026-11-19": []}


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout.strip()


# проверка доступа на каждом тике: если токен сломался — в логе сразу видно
gh("run", "list", "-R", REPO, "--workflow", WORKFLOW, "--limit", "1")
print("Доступ есть")

now = dt.datetime.now(MSK)
slots = [dt.datetime.combine(now.date(), dt.time(*map(int, t.split(":"))), MSK)
         for t in SPECIAL.get(now.date().isoformat(), SLOTS)]
due = [t for t in slots if t <= now]
if not due:
    print("Слотов пока не было — ждём")
    raise SystemExit

req = urllib.request.Request(f"{FEED}?t={int(now.timestamp())}", headers={"Cache-Control": "no-cache"})
items = json.load(urllib.request.urlopen(req, timeout=30))["items"]
last = max(dt.datetime.fromisoformat(n["published"]) for n in items)
if last >= due[-1]:
    print(f"Слот {due[-1]:%H:%M} уже отработан ({last.astimezone(MSK):%H:%M}) — ждём следующий")
    raise SystemExit

busy = gh("run", "list", "-R", REPO, "--workflow", WORKFLOW, "--limit", "5", "--json", "status",
          "-q", '[.[] | select(.status != "completed")] | length')
if busy != "0":
    print("Запуск уже идёт — ждём")
    raise SystemExit

gh("workflow", "run", WORKFLOW, "-R", REPO, "-f", "count=1")
print(f"Слот {due[-1]:%H:%M}: запуск поставлен")
