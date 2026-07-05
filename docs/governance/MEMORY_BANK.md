# Memory Bank — continuity between agent threads

> **Для агентов:** читай этот файл **первым** в новом треде, если контекст перегружен или нет рабочего chat dump.
> **Для владельца:** смотри секцию «IDE / контекст» в трее (process monitor) — когда bank растёт, пора новый тред.

Chat dumps из Grok Build / Codex часто бесполезны: вместо текста — `kotlin.Unit` (см. `dump chat max theme`, `last chat`). Этот bank — **основной** переносимый контекст диалога.

---

## Правила для агентов

1. **В начале треда** (если пользователь продолжает работу или спрашивает «на чём остановились»):
   - прочитать этот файл;
   - прочитать верхние записи `docs/governance/AGENT_HANDOFF.md` (что изменилось в коде).
2. **После значимой сессии** — добавить запись в «Журнал» (новая сверху):
   - дата, ветка, что сделали / выяснили;
   - блокеры и открытые вопросы;
   - следующий шаг (одна строка).
3. **Не дублировать** AGENT_HANDOFF: handoff = изменения кода и команды; bank = решения, диагностика, договорённости с пользователем.
4. **Не писать секреты** (токены, ключи, пароли).
5. **Сжимать:** одна сессия ≈ 15–40 строк; старые записи можно сворачивать в «Архив» внизу.

### Шаблон записи

```markdown
### YYYY-MM-DD — краткий заголовок
- **Ветка:** `feature/...`
- **Сделано:** …
- **Выводы:** …
- **Блокеры:** …
- **Дальше:** …
```

---

## Текущий фокус

- **Ветка:** `feature/channel-max`
- **Канал:** MAX invoice bot (`experiments/max_invoice_bot/`), Telegram не трогаем
- **Распознавание:** parallel race — OpenAI vision vs SotaOCR hybrid (`recognition_race.py`)
- **Preflight перед upload:** **убран** (2026-07-03) — проверка upload ≈ реальный upload, лишняя задержка ~20 с
- **UX пачки файлов MAX:** design doc готов, код **не трогали** — `docs/planning/MAX_BATCH_UPLOAD_UX_DESIGN.md`

---

## Журнал (новые сверху)

### 2026-07-05 — MAX batch upload UX (design only)
- **Инцидент:** 10 файлов за 11 с (2026-07-05 22:21, `logs/dev_stack/5.log`) → лавина reply + blank-сообщений в MAX
- **Причина:** скопированы тексты TG, но не механика: `message.answer()` vs `send_message`+`delete_message`, нет debounce burst
- **Решение (согласовано):** «липкая карточка» — один draft, кнопки «Обработать все» / «Одна накладная», сводка пакета
- **Документ:** `docs/planning/MAX_BATCH_UPLOAD_UX_DESIGN.md` (FSM-таблица, макеты, PR1–PR6)
- **Дальше:** PR1 draft card infra в `experiments/max_invoice_bot/bot.py` (когда owner скажет «делай»)

### 2026-07-03 — dev_stack_ctl (быстрый restart 1/2/5)
- **Файлы:** `scripts/dev_stack_ctl.py`, `.agents/skills/dev-stack-restart/SKILL.md`
- **Почему долго было:** agent shell `(cd ; uvicorn --port 8000)` → PowerShell ParserError, несколько ретраев
- **Команда:** `.venv\Scripts\python.exe scripts\dev_stack_ctl.py restart` (~20 с)
- **Конфиги:** `.idea/runConfigurations/1__backend.xml`, `2__worker.xml`, `5__max_invoice_bot.xml`

### 2026-07-03 — диагностика последнего llm_timeout + preflight убран
- **Ветка:** `feature/channel-max`
- **Заявка:** `20260703_164149_100_____183900520` (MAX, ~47 с, `llm_timeout`)
- **Причина (две независимые):**
  1. **SotaOCR `upstream_unavailable`:** API `sotaocr.com` принимает запрос, но перенаправляет загрузку файла на внутренний worker `109.230.162.227:8090`, который отвечает `connection refused` (HTTP 502). Balance (`/v1/balance`) при этом может быть OK — поэтому preflight вводил в заблуждение.
  2. **OpenAI vision:** preflight timeout + vision path timeout 45 с (медленный/недоступный API через VPN).
- **Проверка:** `scripts/probe_sotaocr.py` — balance OK, upload FAIL с тем же upstream; `scripts/diagnose_request.py <request_id>`.
- **Решение пользователя:** убрать preflight перед отправкой файла в MAX — сразу нормальный upload, ошибки из worker.
- **Дальше:** дождаться починки SotaOCR upstream или полагаться на OpenAI; при повторе — смотреть `logs/worker.log` + race winner.

### 2026-07-03 — контекст до диагностики (из предыдущих тредов)
- MAX: чинили падения, дубли ответов, кнопки после «обработать сейчас», изоляция от TG.
- Добавлены SotaOCR client, VPN split-tunnel, `recognition_race` + preflight (preflight потом убран).
- iiko demo stand поднимали; полный E2E откладывали.
- Последний запрос до паузы: «параллельный тест OpenAI и SotaOCR» → реализован race.

---

## Справка: SotaOCR upstream_unavailable

Цепочка при upload:

1. Наш клиент шлёт файл на `https://sotaocr.com/...`
2. Шлюз SotaOCR выбирает backend и отдаёт задачу на **другой** хост (у нас: `109.230.162.227:8090`)
3. Если этот worker выключен — API возвращает 502 с кодом `upstream_unavailable`
4. Это **инфраструктура SotaOCR**, не баг парсера и не наш VPN (VPN нужен для доступа к `sotaocr.com` / OpenAI из РФ)

---

## Архив

_Старые записи переносить сюда при сжатии журнала._
