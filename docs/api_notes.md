# Kufar API notes

Дата проверки: 2026-07-03.

## Search endpoint

Базовый endpoint:

```text
GET https://api.kufar.by/search-api/v2/search/rendered-paginated
```

Проверенный пример для аренды 2-комнатных квартир в Минске до 450 USD:

```text
cat=1010
cur=USD
gtsy=country-belarus~province-minsk~locality-minsk
lang=ru
prc=r:0,450
rms=v.or:2
size=3
typ=let
```

Корневые поля ответа на момент проверки:

```text
ads,page_type,pagination,total
```

`ads` содержит список объявлений. В объявлении подтверждены поля `ad_id`, `ad_link`, `subject`, `price_usd`, `price_byn`, `currency`, `category`, `type`, `list_time`, `images`, `ad_parameters`.

## Pagination

Пагинация приходит в `pagination.pages[]`.

Пример:

```json
{
  "label": "next",
  "num": 2,
  "token": "eyJ0IjoiYWJzIiwiZiI6dHJ1ZSwicCI6MiwicGl0IjoiMjk3MTc3MjcifQ=="
}
```

Для второй страницы нужно передать token как query-параметр `cursor`.

Проверка:

```text
...&size=3&typ=let&cursor=<next-token>
```

Вторая страница вернула другой первый `ad_id`, значит `cursor` работает.

## Images

Для объявлений с `images[].media_storage = rms` рабочий URL превью:

```text
https://rms.kufar.by/v1/list_thumbs_2x/{images[].path}
```

Проверенный пример:

```text
https://rms.kufar.by/v1/list_thumbs_2x/adim1/d8dcac19-1087-4d45-88cd-0080ddaf6b04.jpg
```

Ответ CDN: `200`, `Content-Type: image/jpeg`.

URL из первоначального ТЗ `https://yams.kufar.by/api/v1/kufar-ads/images/{path}` в этой среде не резолвился для `media_storage=rms`, поэтому для MVP используется `rms.kufar.by`.

## MVP categories

Пользователь не указал отдельные категории, поэтому для MVP берётся недвижимость.

Проверенные варианты:

```text
cat=1010&typ=let   -> Квартиры, долгосрочная аренда
cat=1010&typ=sell  -> Квартиры, покупка
cat=1020&typ=sell  -> Дома, агроусадьбы, коттеджи, покупка
```

В `ad_parameters` для квартир и домов подтверждены:

```text
type     -> pu=typ
category -> pu=cat
rooms    -> pu=rms
size     -> pu=st
```

Для фильтра количества комнат используется query-параметр:

```text
rms=v.or:<rooms>
```

Для цены:

```text
cur=USD
prc=r:<from>,<to>
```

Для города:

```text
gtsy=<location-token>
```

