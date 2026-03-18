# BASHRC Refactor Guide (2026-03-18)

## Что изменилось

### Проблема (старая архитектура)

В прошлой версии `02_add_aliases.sh` встраивал **все 1300+ строк функций** прямо в `~/.bashrc` через большой heredoc-блок:

```bash
cat >> "$BASHRC" <<__WINDEV_BASH_BLOCK__
# Весь инструментарий (wmailbox, wring, wvibe, etc.)
__WINDEV_BASH_BLOCK__
```

**Почему это ломалось:**

1. **EOF-коллизия в heredoc** — если в теле блока встречалась строка `__WINDEV_BASH_BLOCK__`, bash закрывал heredoc раньше времени
2. **Монолитный блок** — любая синтаксическая ошибка в одной функции ломала весь `~/.bashrc`
3. **Дублирование** — `whelp()` и `wsets()` определялись дважды с разными реализациями
4. **Нет идемпотентности** — переустановка могла оставить `~/.bashrc` в поломанном состоянии
5. **Ненужный вывод** — функции выполнялись при `source ~/.bashrc`

### Решение (новая архитектура, v2)

**Минимальный bootstrap в `~/.bashrc`:**
```bash
TOOLKIT_PATH="${HOME}/.config/windev/toolkit.sh"
if [ -f "$TOOLKIT_PATH" ]; then
  source "$TOOLKIT_PATH"
fi
```

**Все функции в отдельном файле:**
```
~/.config/windev/toolkit.sh  (все w* команды, сгенерировано скриптом)
```

**Преимущества:**

✓ **Синтаксис проверяется** перед установкой (`bash -n`)  
✓ **Атомарная установка** (невозможно оставить broken state)  
✓ **Идемпотентна** (безопасно переустановить 2-3 раза)  
✓ **Чистое `~/.bashrc`** (только 10-20 строк вместо 1300)  
✓ **Легко откатить** (backup в `~/.bashrc.bak` и `toolkit.sh.bak`)  

---

## Как переустановить (для оператора)

### Шаг 1: Обновить repo

```bash
cd ~/iikoinvoicebot
git pull --ff-only
```

### Шаг 2: Запустить новый installer

```bash
bash scripts/termux_ssh_toolkit/termux/install.sh \
  --win-user MiBookPro \
  --win-host 192.168.1.100 \
  --alias windev \
  --skip-keygen
```

**Или используйте wrefresh** (если уже установлено):
```bash
wrefresh
```

### Шаг 3: Перезагрузить shell

```bash
source ~/.bashrc
```

### Шаг 4: Проверить

```bash
whelp | head -20   # Справка работает
wstatus             # SSH работает
```

---

## Если что-то сломалось

### Сценарий 1: "command not found: wmailbox"

**Причина:** Toolkit не загрузился из `~/.config/windev/toolkit.sh`

**Решение:**
```bash
# Проверить, что файл существует
ls -la ~/.config/windev/toolkit.sh

# Проверить синтаксис
bash -n ~/.config/windev/toolkit.sh

# Переустановить
bash ~/iikoinvoicebot/scripts/termux_ssh_toolkit/termux/install.sh \
  --win-host 192.168.1.100 --skip-keygen

source ~/.bashrc
```

### Сценарий 2: "source ~/.bashrc" выдаёт ошибки

**Причина:** Поломанный синтаксис в toolkit.sh или ~/.bashrc

**Решение:**
```bash
# Проверить синтаксис
bash -n ~/.bashrc
bash -n ~/.config/windev/toolkit.sh

# Восстановить из бэкапа
if [ -f ~/.bashrc.bak ]; then
  cp ~/.bashrc.bak ~/.bashrc
  echo "Restored ~/.bashrc from backup"
fi

if [ -f ~/.config/windev/toolkit.sh.bak ]; then
  cp ~/.config/windev/toolkit.sh.bak ~/.config/windev/toolkit.sh
  echo "Restored toolkit.sh from backup"
fi

source ~/.bashrc
```

### Сценарий 3: "Toolkit not found at ~/.config/windev/toolkit.sh"

**Причина:** Файл был удалён или установка не завершилась

**Решение:**
```bash
# Переустановить с нуля
bash ~/iikoinvoicebot/scripts/termux_ssh_toolkit/termux/install.sh \
  --win-host 192.168.1.100 \
  --win-user MiBookPro \
  --skip-keygen

source ~/.bashrc
```

### Сценарий 4: Вернуться на старый installer (legacy)

Если срочно нужна старая версия:
```bash
bash ~/iikoinvoicebot/scripts/termux_ssh_toolkit/termux/install.sh \
  --win-host 192.168.1.100 \
  --skip-keygen \
  --legacy
```

**Внимание:** Legacy path deprecated и будет удалён в будущем. Используйте только для критических ситуаций.

---

## Что произошло с функциями

### wmailbox, wring, wpaste, wclip (mailbox)

- **Было:** встроено в heredoc в ~/.bashrc
- **Стало:** в toolkit.sh, поведение неизменено
- **Улучшение:** `wring` теперь явно сообщает о коде выхода команды

### whelp, wsets (справка)

- **Было:** дублировалось (встроено + из файлов)
- **Стало:** одна реализация в toolkit.sh, читает из `scripts/termux_ssh_toolkit/shared/whelp_ru.txt`
- **Улучшение:** никакого дублирования, гарантирует консистентность

### wvibe, wmcp, waider (AI agents)

- **Было:** встроено в ~/.bashrc
- **Стало:** в toolkit.sh
- **Неизменено:** функционал и интерфейс

### Все w* команды (git, services, deployment)

- **Были:** встроены в ~/.bashrc (1300 строк)
- **Стали:** в toolkit.sh (отдельный файл, легче диагностировать)
- **Неизменено:** функционал и интерфейс

---

## Версионирование

Installer ведёт лог установки:

```bash
cat ~/.config/windev/.version
# Output:
# version: 2026-03-18_v2
# installed: 2026-03-18_143025
# host_alias: windev
# win_host: 192.168.1.100
# win_user: MiBookPro
```

Проверить версию toolkit:
```bash
head -5 ~/.config/windev/toolkit.sh
# Auto-generated from install.sh via template substitution
```

---

## FAQ

### Q: Может ли быть конфликт со старым ~/.bashrc?

**A:** Нет, новый installer удалит старый блок `# >>> windev-dev-toolkit >>>` перед добавлением bootstrap. Создаётся бэкап в `~/.bashrc.bak`.

### Q: Что если ~/.config/windev/ недоступна?

**A:** Bootstrap использует `${XDG_CONFIG_HOME:-$HOME/.config}`, поэтому если `XDG_CONFIG_HOME` переопределена в вашей системе, toolkit загрузится оттуда.

### Q: Можно ли отредактировать toolkit.sh вручную?

**A:** Можно, но при переустановке изменения будут перезаписаны. Если нужна кастомная функция, добавьте её в `~/.bashrc` отдельно.

### Q: Что делать, если installer не может создать ~/.config/windev/?

**A:** Проверьте права доступа:
```bash
ls -ld ~/.config
chmod 755 ~/.config
mkdir -p ~/.config/windev
chmod 700 ~/.config/windev
```

### Q: Почему toolkit.sh в ~/.config/windev/, а не в ~/...?

**A:** `~/.config/` — стандартная папка для конфигов приложений (XDG Base Directory spec). Это позволяет:
- Отделить конфиги от домашней папки
- Поддержать `XDG_CONFIG_HOME`
- Избежать беспорядка в `~/.bashrc.d/`

---

## Миграция (для текущих пользователей)

Если уже установлен старый installer, просто переустановите:

```bash
cd ~/iikoinvoicebot
git pull --ff-only

bash scripts/termux_ssh_toolkit/termux/install.sh \
  --win-user MiBookPro \
  --win-host 192.168.1.100 \
  --skip-keygen

source ~/.bashrc
whelp  # Проверить, что всё работает
```

Старый блок будет автоматически удалён, новый bootstrap добавлен.

---

## Что изменилось в коде

### Улучшение 1: wring - явный статус и return code

**Было:**
```bash
wring() {
  bash "$cmd_file" 2>&1 | tee "$out_file"
  run_rc=${PIPESTATUS[0]}
  
  if cat "$out_file" | wmailbox inbox; then
    echo "[ok] wring output pushed to inbox."
  else
    echo "[error] failed to push wring output to inbox."
    return 70  # Произвольный код
  fi
  
  return "$run_rc"  # Смешанная логика
}
```

**Стало:**
```bash
wring() {
  bash "$cmd_file" 2>&1 | tee "$out_file"
  run_rc=${PIPESTATUS[0]}
  
  if cat "$out_file" | wmailbox inbox; then
    echo "[ok] wring: command exit code $run_rc, output pushed to inbox."
  else
    echo "[error] wring: command exit code $run_rc, failed to push output to inbox."
  fi
  
  return "$run_rc"  # Всегда возвращаем exit код команды
}
```

**Почему это лучше:**
- Оператор видит exit код команды И статус push отдельно
- `return $run_rc` гарантирует, что exit code команды не теряется
- Явные сообщения помогают диагностировать проблемы

---

## Обратная совместимость

**Совместимо с:**
- Старые w* команды работают без изменений
- Mailbox workflow не изменился
- whelp и все справки работают как раньше
- wvibe и AI-интеграция не изменены

**Не совместимо:**
- Если вы вручную встраивали функции в ~/.bashrc, они не будут загружены (добавьте их в toolkit.sh вручную или отредактируйте bootstrap)

---

## Поддержка

Если возникли проблемы:

1. Проверьте syntax: `bash -n ~/.bashrc`
2. Посмотрите logs: `cat ~/.config/windev/.version`
3. Попробуйте переустановить: `bash scripts/termux_ssh_toolkit/termux/install.sh --win-host <ip> --skip-keygen`
4. Восстановитесь из бэкапа: `cp ~/.bashrc.bak ~/.bashrc`

