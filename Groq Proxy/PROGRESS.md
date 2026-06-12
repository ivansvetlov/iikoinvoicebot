# Groq Proxy × Kilo Code — Progress

**Цель:** полноценный agent mode (Grok = мозг, Kilo = руки)

**Обновлено:** 2026-06-12 00:12

---

## Progress Bar

```
[████████████████░░░░] 75%  — стриминг исправлен, тестируй в Kilo
```

| Фаза | Статус | Вес |
|------|--------|-----|
| 0 Research spike | ✅ DONE | 10% |
| 1 LLM-only backend | ✅ DONE | 20% |
| 2 Kilo prompt pipeline | ✅ DONE | 20% |
| 3 JSON tool calls | ✅ DONE | 20% |
| 4 Response pipeline | 🔄 IN PROGRESS | 15% |
| 5 Multi-turn loop | ⬜ TODO | 10% |
| 6 Production | ⬜ TODO | 5% |

---

## Ключевые результаты

| Тест | Результат |
|------|-----------|
| «работаешь?» | ✅ ~15s, «Да, работаю.», 0 tool_calls |
| `read_file` tool | ✅ grok-cli 16s → валидный JSON tool_call |
| ThreadingHTTPServer | ✅ параллельные запросы |
| SSE stream hang | ✅ `Connection: close` + `[DONE]` — диалог завершается |
| Двойной ответ Kilo | ✅ attempt_completion + кэш (без пустых ответов) |

## Архитектура (текущая)

```
Kilo Code → openai_proxy.py
              ├─ prompt_pipeline.py  (сжатие + offload inline)
              ├─ backend.py          (grok --prompt-file, max-turns 1)
              └─ response_pipeline.py (JSON parse → OpenAI tool_calls)
```

**Backend:** `grok --prompt-file` (primary), `acpx --allowed-tools ""` (fallback)

---

## Файлы

| Файл | Назначение |
|------|------------|
| `PROGRESS.md` | прогресс + бар |
| `backend.py` | LLM-only Grok |
| `prompt_pipeline.py` | Kilo prompt compression |
| `response_pipeline.py` | JSON tool call parsing |

---

## Лог решений

| Дата | Решение |
|------|---------|
| 2026-06-11 | Старт по плану |
| 2026-06-11 | `--disallowed-tools` ломает grok CLI → убрали |
| 2026-06-11 | `_has_useful_output` отбрасывал JSON `{` → исправлено |
| 2026-06-11 | grok-cli возвращает чистый JSON tool_call за 16s ✅ |
| 2026-06-12 | БАГ: Kilo «загрузка» после ответа → `Connection: close` после SSE |
| 2026-06-12 | tool_calls стримятся name + arguments отдельными delta |
| 2026-06-12 | Kilo шлёт 2–3 запроса на «работаешь?» → suppress duplicate turns |
| 2026-06-12 | Kilo agent требует tool → attempt_completion вместо текста |
| 2026-06-12 | Пустой suppress → Provider Error; теперь кэшированный tool_call |
| 2026-06-12 | Seamless intent routing: analysis→read_file, grok-cli only, no acpx |
