# Post-Audit Remediation Plan (2026-04-26)

Источник аудита: `docs/COMPREHENSIVE_AUDIT.md`.

Этот документ фиксирует:
- что исправляем сразу;
- что переносим в ближайший спринт;
- какие процессные контрольные меры вводим, чтобы ошибки не повторялись.

## 1) Что правим сейчас (в этом цикле)

### Git hygiene и артефакты
- [x] Добавлен ignore для локальных dump-артефактов формата `dump stage*` (`.gitignore`).
- [x] `COMPREHENSIVE_AUDIT.md` перенесён в `docs/` (канон по `docs/AGENTS.md`).
- [ ] Удалить локальный `dump stage6` из рабочей директории (не runtime-артефакт).
- [ ] Закоммитить `must-commit` группу (post-recognition UX, тесты, `invoice_keyboards.py`, `invoice_posting.py`).
- [ ] Разнести оставшиеся untracked по `must-commit` / `local-only`.

### Security baseline
- [x] Добавить `SECURITY.md` (канал репорта уязвимостей + SLA реакции).
- [x] Добавить `LICENSE` (MIT/Apache-2.0; выбрать одну).

### Governance baseline
- [x] Добавить `CONTRIBUTING.md` (минимальные правила PR/commit/test).
- [x] Добавить `.github/pull_request_template.md`.
- [x] Добавить `CODEOWNERS` (минимум на `app/`, `docs/`, `tests/`).

## 2) Что переносим на ближайший спринт

### CI и quality gate
- [ ] Ввести CI: `tests + lint + format check` на push/PR.
- [ ] Добавить `requirements-dev.txt` (ruff, black, mypy, pytest, coverage, pre-commit).
- [ ] Включить coverage-отчет (порог для fail можно добавить позже).

### Репозиторий и GitHub настройки
- [ ] Branch protection: обязательный PR + required checks.
- [ ] Минимум 1 review до merge.
- [ ] Запрет direct push в protected branch.

### Документация и структура
- [ ] Зафиксировать статус документов: canonical / historical / experimental.
- [x] Для `prompts/` добавить явное описание назначения и правил изменений (`docs/README.md`, раздел Prompts).
- [x] Добавить отдельный blueprint-док с prompt для переносимого high-standard skeleton (`docs/PROJECT_CLONE_PROMPT.md`).

## 3) Что делать, чтобы ошибки не повторялись

## 3.1 Управление риском destructive-операций
- Не выполнять массовые удаления без явного dry-run и списка целевых путей.
- Для cleanup использовать отдельные скрипты из `scripts/` с whitelist-подходом.
- Перед удалением вне git обязательно создавать snapshot (архив/копия) локальных ключевых файлов.

## 3.2 Контроль изменений
- Любая новая ветка: короткий `plan + scope` в PR описании.
- Любое изменение в UX/бот-потоке: обязательный тест на callback/идемпотентность.
- Любое изменение интеграции (iiko/LLM): обязательный negative-case тест.

## 3.3 Контроль документации
- Один source of truth для пост-аудитных задач: этот файл.
- `docs/TODO.md` хранит только summary/приоритеты и ссылку на этот трек.
- `docs/AGENT_HANDOFF.md` фиксирует только факт внедрения (без дублирования чеклистов).

## 4) Решение по формату: отдельный документ или раздел в TODO

Решение для high-standard:
- Детальный post-audit трек ведем в отдельном документе (`AUDIT_REMEDIATION_PLAN.md`).
- В `docs/TODO.md` держим короткий раздел-указатель и статус прогресса.

Почему так лучше:
- нет размазывания governance-задач по продуктовым этапам;
- меньше риска расхождений между чеклистами;
- проще аудировать прогресс и ответственность.

## 5) Матрица ответственности (минимум)

- Репозиторные стандарты (CI, PR template, CODEOWNERS): Tech lead/maintainer.
- Security baseline (SECURITY.md, policy): maintainer + owner.
- Документация и структура docs: maintainer + feature owner.
- Hardening пайплайна (из `docs/OPTIMIZATION.md`): backend owner.

## 6) Критерий завершения post-audit трека

Считаем трек закрытым, когда:
- есть базовые governance-файлы (`LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `CODEOWNERS`);
- CI обязателен для merge;
- branch protection включен;
- все runtime-untracked артефакты либо закоммичены по назначению, либо явно исключены;
- в `docs/TODO.md` раздел post-audit помечен как закрытый.
