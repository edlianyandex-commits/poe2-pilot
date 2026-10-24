# PoE2 Pilot — архитектура

Оверлей поверх Path of Exile 2 для быстрого прохождения кампании: маршрут, сплиты, план прокачки из билда.
Python 3.13 + PySide6. Windows. Без бота: только чтение `Client.txt` и отображение.

## Правила (не обсуждаются)
- Никакой эмуляции ввода в игру, чтения памяти, инъекций. Только `Client.txt`, файлы данных, глобальные хоткеи-слушатели.
- Оверлей прозрачен для кликов (click-through) всегда, кроме режима редактирования позиции.
- Любой текст на HUD ≤ 40 символов. Подробности — только по хоткею. См. `docs/UX.md`.

## Модули и владельцы
| Путь | Команда | Что |
|---|---|---|
| `src/pilot/contracts.py` | lead | общие типы. Менять только через lead |
| `src/pilot/core/` | core (Sonnet) | parser, logwatch, route model, splits, RunEngine |
| `src/pilot/overlay/` | overlay (Sonnet) | HUD на PySide6, хоткеи, конфиг-UI, demo-режим |
| `src/pilot/planner/` | planner (Opus) | автобилдер: PoB-код → LevelPlan |
| `data/` | data (Haiku) | маршруты, зоны, имена ru/en |
| `src/pilot/app.py`, `config` | lead | сборка всего вместе |

Каждая команда пишет **только в свои пути** и свои тесты `tests/<команда>/`. Не коммитить — коммитит lead.

## Поток данных
```
Client.txt ──LogWatcher(thread)──► parse_line() ──Event──► RunEngine.feed()
                                                             │  Route (data/routes/*.json)
                                                             │  LevelPlan (planner)
                                                             │  SplitStore (%APPDATA%/poe2-pilot/runs)
                                                             ▼
                                   overlay QTimer 10Hz ◄── RunEngine.snapshot() -> HudState
                                   hotkeys ──► Actions (next_step / prev_step / reset_run)
```

## Интерфейсы (сигнатуры фиксированы)
- `core/parser.py`: `parse_line(line: str) -> Event | None` — ru и en клиент.
- `core/logwatch.py`: `LogWatcher(path, on_line, from_end=True).start()/.stop()`; `replay(path, on_line, speed=50.0)` — воспроизведение лога с ускорением по таймстемпам (для demo и тестов).
- `core/logpath.py`: `find_client_log() -> Path | None` (Steam + standalone пути).
- `core/route.py`: `load_route(path) -> Route`, валидация длин.
- `core/engine.py`: `RunEngine(route, plan=None, store=None)` реализует `SnapshotSource` и `Actions`; `.feed(event)`.
- `planner/__init__.py`: `build_plan(pob_code: str) -> LevelPlan`.
- `overlay/__init__.py`: `run_overlay(source: SnapshotSource, actions: Actions, config: dict) -> int`.

## Факты из реального лога (ru-клиент, патч 0.4/0.5)
Фикстура: `tests/fixtures/campaign_ru.log` (1824 строки, полная кампания + интерлюдии, ник заменён на `TestExile`,
в середине перезапуск клиента — PID меняется). Таблица зон: `data/areas/seen_areas_ru.tsv`.
- `Generating level N area "ID" with seed S` → затем `[SCENE] Set Source [Имя]` (бывает `(null)`, `(unknown)`).
- `[LOADING SCREEN] (Имя) Duration = X seconds` — вычитать из игрового времени.
- `: Ник (Класс) достигает N уровня`, `: Ник был повержен.`
- `Successfully allocated passive skill id: ID, name: Имя` / `Successfully unallocated ...`
- `[WINDOW] Lost focus` / `Gained focus`, `Closing game gracefully`.
- ID зон: `G{акт}_{n}` (акты 1–4), `G{акт}_town`, `P{1-3}_*` интерлюдии, `G_Endgame_Town` = конец кампании.
  Хайдауты `Hideout*` — не сегменты. Город может иметь уровень выше зоны (G1_town=15) — не использовать уровень города.

## Сплиты
- Ран стартует на `AreaGenerated(G1_1)` при персонаже уровня 1 (или хоткей reset). Финиш — `G_Endgame_Town`.
- Сплит = первый вход в зону-маркер маршрута (step с `split: true`), по умолчанию — первый вход в каждый новый акт/интерлюдию.
- Игровое время = реальное − загрузки − время, пока игра закрыта.
- PB и история — JSON в `%APPDATA%/poe2-pilot/runs/`.
