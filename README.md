# last-items — «последние штуки» для polkachudes.ru/sale

Раз в неделю (четверг, 06:00 UTC = 09:00 МСК) GitHub Actions забирает каталог
магазина из публичного API Tilda Store, выбирает товары с остатком 1 или 2 шт.
и публикует `last-items.json` через GitHub Pages. Блок `sale-idle` на странице
`/sale` читает этот файл. Данных покупателей здесь нет.

## Формат

```json
{"generated":"2026-11-13T08:55:31Z","count":12,
 "items":[{"uid":"804283999152","title":"...","author":"...","price":500,
           "img":"https://static.tildacdn.com/.../-/resize/400x/....jpg",
           "url":"https://polkachudes.ru/catalog/tproduct/...","qty":1}]}
```

`price` — число в рублях (без знака валюты), `author` — поле `brand` товара,
`img` — превью 400px с tildacdn.com, `url` — ссылка на товар на polkachudes.ru.

## Правила отбора

- остаток (`quantity`) ровно 1 или 2; пустой, 0 и нечисловой — пропуск;
- товары с несколькими вариантами (editions) берутся, только если остаток задан у
  всех вариантов и цена одинакова (тогда остаток = сумма); иначе пропуск;
- пропуск товаров без картинки, без цены или со ссылкой не на polkachudes.ru;
  отдельного флага «скрыт/недоступен» API не отдаёт — недоступные это `quantity` 0;
- сначала qty 1, потом qty 2; авторы чередуются, не больше 2 карточек одного
  автора подряд (если иначе нельзя — приоритет у правила про авторов);
- порядок внутри группы случайный, но стабильный в пределах недели;
- максимум `CAP` = 12 карточек.

Защита: если API вернул ошибку или меньше 100 товаров, скрипт завершается с
кодом 2 и **не перезаписывает** файл (джоб падает, публикация не происходит).
Если данные здоровы, но подходящих товаров нет — `count: 0`, `items: []`.

## Запуск локально

```
python3 fetch_last_items.py                  # запишет ./last-items.json
python3 fetch_last_items.py --out site/last-items.json
python3 fetch_last_items.py --cap 8          # одноразово другой лимит
python3 fetch_last_items.py --dump-dir DIR   # брать catalog-N.json из папки (тест)
```

Нужен Python 3.10+, сторонних библиотек нет. Пауза между запросами 0,3 с, один проход (~17 запросов).

## Как изменить лимит

В `fetch_last_items.py` поменяйте константу `CAP = 12` (рядом — `QTYS`,
`MAX_SAME_AUTHOR_ADJ`, `MIN_PRODUCTS`). Закоммитьте и запустите workflow вручную.

## Как включить Pages

1. Репозиторий → Settings → Pages → Build and deployment → Source: **GitHub Actions**.
2. Actions → last-items → Run workflow (`workflow_dispatch`) для первого запуска.
3. Файл будет по адресу `https://<user>.github.io/<repo>/last-items.json`.

GitHub Pages отдаёт `Access-Control-Allow-Origin: *`, поэтому страница
polkachudes.ru может читать JSON через `fetch()` без доп. настроек.

Примечание: cron в Actions отключается в репозиториях без активности 60 дней —
в этом случае включите workflow заново во вкладке Actions.

## Файлы

- `fetch_last_items.py` — сборщик;
- `.github/workflows/last-items.yml` — расписание и деплой;
- `site/index.html` — заглушка страницы Pages;
- `last-items.json` — пример результата.
