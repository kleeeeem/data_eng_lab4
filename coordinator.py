import json
import logging
import os
import sys
import time
from collections import Counter

from kazoo.client import KazooClient, KazooState
from kazoo.exceptions import NoNodeError, NodeExistsError
from kazoo.recipe.election import Election
from kazoo.retry import KazooRetry

from skills import read_vacancies, process, control_line, top

NAME = os.environ.get("NAME", sys.argv[1] if len(sys.argv) > 1 else "coord")
RUN = os.environ.get("RUN", "run")
FENCING = os.environ.get("FENCING", "0") == "1"
HOSTS = os.environ.get("ZK_HOSTS", "127.0.0.1:2181,127.0.0.1:2182,127.0.0.1:2183")
SESSION_TIMEOUT = float(os.environ.get("SESSION_TIMEOUT", "10"))
CHUNK = int(os.environ.get("CHUNK", "50"))
CHUNK_DELAY = float(os.environ.get("CHUNK_DELAY", "1.2"))

ROOT = f"/hw4/{RUN}"
os.makedirs("logs", exist_ok=True)
os.makedirs("checkpoints", exist_ok=True)
os.makedirs("results", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format=f"%(asctime)s.%(msecs)03d [{NAME}] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler(f"logs/{RUN}_{NAME}.log", encoding="utf-8"),
              logging.StreamHandler(sys.stdout)],
)
logging.getLogger("kazoo").setLevel(logging.WARNING)
log = logging.info

zk = KazooClient(hosts=HOSTS, timeout=SESSION_TIMEOUT,
                 connection_retry=KazooRetry(max_tries=-1, max_delay=1),
                 command_retry=KazooRetry(max_tries=-1, max_delay=1))


def on_state(state):
    if state == KazooState.LOST:
        log("сессия ZooKeeper ПОТЕРЯНА (истёк тайм-аут), эфемерные узлы удалены")
    elif state == KazooState.SUSPENDED:
        log("связь с ZooKeeper прервана (SUSPENDED)")
    else:
        log("подключён к ZooKeeper (CONNECTED)")


def ensure(path, value=b""):
    try:
        zk.create(path, value, makepath=True)
    except NodeExistsError:
        pass


def save_checkpoint(offset, s, p, t, epoch):
    path = f"checkpoints/{RUN}.json"
    tmp = path + f".{NAME}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"offset": offset,
                   "skills": list(s.items()),
                   "pairs": [["|".join(k), v] for k, v in p.items()],
                   "triples": [["|".join(k), v] for k, v in t.items()]}, f, ensure_ascii=False)
    os.replace(tmp, path)
    meta = json.dumps({"offset": offset, "file": path, "by": NAME, "epoch": epoch}).encode()
    zk.retry(zk.set, f"{ROOT}/checkpoint", meta)


def load_checkpoint():
    try:
        data, _ = zk.retry(zk.get, f"{ROOT}/checkpoint")
    except NoNodeError:
        return 0, Counter(), Counter(), Counter(), None
    if not data:
        return 0, Counter(), Counter(), Counter(), None
    meta = json.loads(data)
    with open(meta["file"], encoding="utf-8") as f:
        ck = json.load(f)
    s = Counter(dict(ck["skills"]))
    p = Counter({tuple(k.split("|")): v for k, v in ck["pairs"]})
    t = Counter({tuple(k.split("|")): v for k, v in ck["triples"]})
    return ck["offset"], s, p, t, meta


def publish(n, s, p, t, epoch):
    control = control_line(n, s, p, t)
    out = f"results/{RUN}_{NAME}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"writer": NAME, "epoch": epoch, "control": control,
                   "top_skills": top(s), "top_pairs": top(p), "top_triples": top(t)},
                  f, ensure_ascii=False, indent=2)
    log(control)
    pointer = json.dumps({"writer": NAME, "epoch": epoch, "file": out}, ensure_ascii=False).encode()

    if FENCING:
        def tx():
            t_ = zk.transaction()
            t_.check(f"{ROOT}/epoch", epoch)
            t_.set_data(f"{ROOT}/result", pointer)
            return t_.commit()
        res = zk.retry(tx)
        if isinstance(res[0], Exception):
            _, cur = zk.retry(zk.get, f"{ROOT}/epoch")
            log(f"ОТКАЗ ЗАПИСИ: {type(res[0]).__name__} - моя эпоха {epoch}, текущая эпоха {cur.version}; "
                f"я больше не лидер, результат НЕ записан")
            return
        _, stat = zk.retry(zk.get, f"{ROOT}/result")
    else:
        stat = zk.retry(zk.set, f"{ROOT}/result", pointer)
    log(f"записал результат: {ROOT}/result -> {out}, версия указателя {stat.version}, эпоха {epoch}")


def lead():
    log("СТАЛ ЛИДЕРОМ")
    zk.retry(zk.set, f"{ROOT}/leader", NAME.encode())
    epoch = zk.retry(zk.set, f"{ROOT}/epoch", NAME.encode()).version
    log(f"моя эпоха = {epoch} (FENCING={'1' if FENCING else '0'})")

    vacancies = read_vacancies()
    offset, s, p, t, meta = load_checkpoint()
    if meta:
        log(f"продолжаю с чекпоинта: обработано {offset}/{len(vacancies)} (чекпоинт записал {meta['by']}, эпоха {meta['epoch']})")
    else:
        log(f"чекпоинта нет, начинаю с нуля: всего вакансий {len(vacancies)}")

    while offset < len(vacancies):
        for v in vacancies[offset:offset + CHUNK]:
            process(v, s, p, t)
        offset = min(offset + CHUNK, len(vacancies))
        time.sleep(CHUNK_DELAY)
        save_checkpoint(offset, s, p, t, epoch)
        log(f"чекпоинт: обработано {offset}/{len(vacancies)}")

    publish(len(vacancies), s, p, t, epoch)
    log("расчёт завершён, выхожу")


def main():
    zk.add_listener(on_state)
    zk.start()
    log(f"старт: ZK={HOSTS}, тайм-аут сессии {SESSION_TIMEOUT:.0f} с, RUN={RUN}")
    for node in ("leader", "epoch", "checkpoint", "result"):
        ensure(f"{ROOT}/{node}")
    log("встал в очередь на лидерство")
    Election(zk, f"{ROOT}/election", identifier=NAME).run(lead)
    zk.stop()


if __name__ == "__main__":
    main()
