---
title: Диагностика по request_id (очередь/воркер/LLM)
tags: [диагностика, rq, llm, pipeline, telegram]
---

## Назначение
Быстро получить технический отчёт по обработке конкретного запроса (request_id): что пришло, что сохранилось, где упало, какие файлы реально обработались, какие были LLM токены.

## Вход
- request_id целиком (например `20260308_000736_800_6106711925`)
- или фрагмент (например `000736_800`)

## Шаги
1) Запусти диагностический скрипт:

```powershell
.\.venv\Scripts\python.exe scripts\diagnose_request.py 000736_800
```

2) Открой JSON-отчёт:
- `tmp/diagnose_<request_id>.json`

3) Если нужно выгрузить итоговый `result_json` в удобном виде:

```powershell
.\.venv\Scripts\python.exe scripts\dump_task_results.py 20260308_000736_800_6106711925
```

Выход будет в `tmp/task_<request_id>.json`.

## Что смотреть в отчёте
- `payload.batch` и `payload.files[]` — сколько файлов реально передали
- `job_files[]` — сколько файлов реально лежит на диске (важно: перезапись имён)
- `task_record.status/error/error_code/message`
- `llm_costs.output_tokens` — близко ли к лимиту

## Интерпретация типовых проблем
- `job_files` содержит 1 файл при `payload.files=3` → перезапись имён при batch
- `error_code=llm_bad_response` → LLM вернул невалидный function_call/обрезанный JSON
- `error_code=llm_garbage` → LLM вернул мусор (повторы/нули/стоп-слова)
- `status=queued` и нет TaskRecord → воркер/очередь не обработали, смотреть `rqinfo` и `worker` stdout
