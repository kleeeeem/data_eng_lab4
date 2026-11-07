import json
import os
import subprocess
import sys
import time

import psutil
from kazoo.client import KazooClient

RUN, FENCING = sys.argv[1], sys.argv[2]
PAUSE_AT = 400
PAUSE_SEC = 40
ROOT = f"/hw4/{RUN}"
os.makedirs("logs", exist_ok=True)
logf = open(f"logs/{RUN}_runner.log", "w", encoding="utf-8")


def log(msg):
    line = f"{time.strftime('%H:%M:%S')}.{int(time.time() * 1000) % 1000:03d} [runner] {msg}"
    print(line, flush=True)
    logf.write(line + "\n")
    logf.flush()


def start(name):
    env = dict(os.environ, NAME=name, RUN=RUN, FENCING=FENCING, PYTHONIOENCODING="utf-8")
    return subprocess.Popen([sys.executable, "coordinator.py"], env=env,
                            stdout=subprocess.DEVNULL, stderr=open(f"logs/{RUN}_{name}.stderr", "w"))


zk = KazooClient(hosts="127.0.0.1:2181,127.0.0.1:2182,127.0.0.1:2183")
zk.start()
if zk.exists(ROOT):
    zk.delete(ROOT, recursive=True)


def get(node):
    try:
        return zk.get(f"{ROOT}/{node}")[0].decode()
    except Exception:
        return ""


log(f"RUN={RUN} FENCING={FENCING}: запускаю coordinator-A")
a = start("coordinator-A")
while get("leader") != "coordinator-A":
    time.sleep(0.1)
log("coordinator-A - лидер; запускаю запасной coordinator-B")
b = start("coordinator-B")

while True:
    ck = get("checkpoint")
    if ck and json.loads(ck)["offset"] >= PAUSE_AT:
        break
    time.sleep(0.05)
pa = psutil.Process(a.pid)
pa.suspend()
t0 = time.time()
log(f"ПРИОСТАНОВИЛ лидера coordinator-A (pid {a.pid}) посреди расчёта: {get('checkpoint')}")

while get("leader") != "coordinator-B":
    time.sleep(0.05)
t1 = time.time()
log(f"ЛИДЕР СМЕНИЛСЯ на coordinator-B через {t1 - t0:.2f} с после приостановки A")

b.wait()
log(f"coordinator-B завершил работу через {time.time() - t0:.1f} с после приостановки A")
rest = PAUSE_SEC - (time.time() - t0)
if rest > 0:
    time.sleep(rest)
pa.resume()
log(f"ВОЗОБНОВИЛ coordinator-A через {time.time() - t0:.1f} с паузы")
a.wait(timeout=180)
log("coordinator-A завершил работу")

data, stat = zk.get(f"{ROOT}/result")
log(f"ИТОГ: указатель {ROOT}/result версия={stat.version} значение={data.decode()}")
_, est = zk.get(f"{ROOT}/epoch")
log(f"ИТОГ: эпоха (версия {ROOT}/epoch) = {est.version}")
log(f"ИТОГ: время смены лидера = {t1 - t0:.2f} с (тайм-аут сессии 10 с)")
zk.stop()
