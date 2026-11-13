#!/usr/bin/env python3
"""Собирает «последние штуки» магазина polkachudes.ru в last-items.json.

Только стандартная библиотека, Python 3.10+.
Источник: публичный API Tilda Store (без авторизации).

Коды выхода: 0 - файл записан; 2 - ошибка API / данные нездоровы
(файл НЕ перезаписывается).
"""
from __future__ import annotations

import argparse
import html
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ---------------- настройки ----------------
CAP = 12                    # максимум карточек в итоговом файле
MAX_SAME_AUTHOR_ADJ = 2     # не больше стольких карточек одного автора подряд
QTYS = (1, 2)               # какие остатки считаем «последними штуками»
MIN_PRODUCTS = 100          # меньше товаров в ответе API -> считаем сбоем
SLICE_SIZE = 200
MAX_SLICES = 40             # предохранитель от бесконечного цикла
PAUSE = 0.3                 # пауза между запросами, сек
THUMB = "/-/resize/400x/"   # превью Tilda; для static.tildacdn.com работает
SHOP = "https://polkachudes.ru"
API = ("https://store.tildaapi.com/api/getproductslist/"
       "?storepartuid=848566607491&recid=5552273801&slice={n}&size=%d" % SLICE_SIZE)
HEADERS = {"Referer": SHOP + "/", "User-Agent": "last-items-fetcher/1.0"}
# -------------------------------------------


def fetch_slice(n: int) -> dict:
    req = urllib.request.Request(API.format(n=n), headers=HEADERS)
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"slice {n}: {last}")


def load_products(dump_dir: str | None) -> list[dict]:
    out: list[dict] = []
    for n in range(1, MAX_SLICES + 1):
        if dump_dir:
            f = Path(dump_dir) / f"catalog-{n}.json"
            if not f.exists():
                break
            data = json.loads(f.read_text(encoding="utf-8"))
        else:
            if n > 1:
                time.sleep(PAUSE)
            data = fetch_slice(n)
        prods = data.get("products")
        if not isinstance(prods, list):
            raise RuntimeError(f"slice {n}: нет поля products")
        if not prods:
            break
        out.extend(prods)
    return out


def clean_text(s) -> str:
    s = re.sub(r"<[^>]+>", " ", html.unescape(str(s or "")))
    return re.sub(r"\s+", " ", s).strip()


def to_int(v):
    s = str(v if v is not None else "").strip()
    return int(s) if re.fullmatch(r"\d+", s) else None


def to_price(v):
    try:
        x = float(str(v).replace(" ", "").replace(",", "."))
    except ValueError:
        return None
    if x <= 0:
        return None
    return int(x) if x == int(x) else round(x, 2)


def total_qty(p: dict):
    """Остаток товара или None, если его нельзя определить однозначно."""
    eds = p.get("editions") or []
    if len(eds) <= 1:
        return to_int(p.get("quantity"))
    # несколько вариантов: остаток по каждому; берём сумму, только если
    # у всех он числовой и цена у всех вариантов одинакова
    qs = [to_int(e.get("quantity")) for e in eds]
    prices = {to_price(e.get("price")) for e in eds}
    if None in qs or len(prices) != 1 or None in prices:
        return None
    return sum(qs)


def thumb(url: str) -> str | None:
    if not re.match(r"https://([a-z0-9-]+\.)?tildacdn\.com/", url):
        return None
    if url.startswith("https://static.tildacdn.com/") and "/-/" not in url:
        head, _, name = url.rpartition("/")
        return head + THUMB + name
    return url


def first_image(p: dict):
    try:
        g = json.loads(p.get("gallery") or "[]")
    except json.JSONDecodeError:
        return None
    for it in g:
        u = (it or {}).get("img") if isinstance(it, dict) else None
        if u:
            return thumb(u)
    return None


def to_item(p: dict):
    q = total_qty(p)
    if q not in QTYS:
        return None
    price = to_price(p.get("price"))
    title = clean_text(p.get("title"))
    url = str(p.get("url") or "")
    if not url.startswith(SHOP + "/") or not title or price is None:
        return None
    img = first_image(p)
    if not img:
        return None
    return {"uid": str(p["uid"]), "title": title,
            "author": clean_text(p.get("brand")), "price": price,
            "img": img, "url": url, "qty": q}


def arrange(items: list[dict], cap: int, seed: int) -> list[dict]:
    """qty 1 сначала, затем 2; внутри группы авторы чередуются
    (round-robin со случайным, но воспроизводимым по неделе порядком),
    не более MAX_SAME_AUTHOR_ADJ карточек одного автора подряд."""
    rnd = random.Random(seed)
    seq: list[dict] = []
    for q in QTYS:
        by_author: dict[str, list[dict]] = defaultdict(list)
        for it in items:
            if it["qty"] == q:
                by_author[it["author"]].append(it)
        authors = sorted(by_author)
        rnd.shuffle(authors)
        for a in authors:
            rnd.shuffle(by_author[a])
        rr: list[dict] = []
        while any(by_author.values()):
            for a in authors:
                if by_author[a]:
                    rr.append(by_author[a].pop())
        seq.extend(rr)
    seq = seq[:cap]
    # страховка: передвинуть карточки, нарушающие правило «подряд»
    res: list[dict] = []
    rest = seq[:]
    while rest:
        for i, it in enumerate(rest):
            tail = [x["author"] for x in res[-MAX_SAME_AUTHOR_ADJ:]]
            if not (len(tail) == MAX_SAME_AUTHOR_ADJ and all(a == it["author"] for a in tail)):
                res.append(rest.pop(i))
                break
        else:  # иначе нельзя - оставляем как есть
            res.extend(rest)
            break
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="last-items.json")
    ap.add_argument("--dump-dir", help="брать catalog-N.json из папки вместо сети (тест)")
    ap.add_argument("--cap", type=int, default=CAP)
    a = ap.parse_args()

    try:
        products = load_products(a.dump_dir)
    except Exception as e:  # noqa: BLE001
        print(f"ОШИБКА API: {e}", file=sys.stderr)
        return 2
    if len(products) < MIN_PRODUCTS:
        print(f"ОШИБКА: получено {len(products)} товаров (< {MIN_PRODUCTS}), файл не тронут",
              file=sys.stderr)
        return 2

    seen, items = set(), []
    for p in products:
        it = to_item(p)
        if it and it["uid"] not in seen:
            seen.add(it["uid"])
            items.append(it)
    now = datetime.now(timezone.utc)
    chosen = arrange(items, a.cap, seed=now.isocalendar()[0] * 100 + now.isocalendar()[1])

    doc = {"generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "count": len(chosen), "items": chosen}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, out)
    print(f"товаров в API: {len(products)}; подошло (qty {QTYS}): {len(items)}; "
          f"записано: {len(chosen)} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
