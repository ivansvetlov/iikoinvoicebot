# КОДИРОВКИ: UTF-8 стандарт, mojibake детекция, план перекодирования

## 1. ЕДИНЫЙ СТАНДАРТ: UTF-8 (без BOM) + LF

### Требования (STRICT)

**Для .sh файлов:**
- ✓ Encoding: UTF-8 (без BOM)
- ✓ Line endings: LF (0x0A), не CRLF
- ✓ Русский текст в комментариях и строках
- ✓ Поддержка UTF-8 при передаче через PowerShell SSH

**Для .md/.txt документов:**
- ✓ Encoding: UTF-8 (без BOM)
- ✓ Line endings: LF (0x0A)
- ✓ Русский текст в заголовках и контенте
- ✓ Читаемость в GitHub, VS Code, Termux

**Для PowerShell-скриптов (.ps1):**
- ✓ Encoding: UTF-8-sig (с BOM) ИЛИ UTF-8 (без BOM)
  - PowerShell предпочитает UTF-8-sig, но UTF-8 тоже работает
  - Если BOM: берите без BOM для git-совместимости
- ✓ Line endings: CRLF (0x0D0x0A) на Windows, но git с core.autocrlf=true конвертирует в LF
- ✓ Русский текст поддерживается встроенно

---

## 2. ГДЕ В ПРОЕКТЕ ЕСТЬ MOJIBAKE (из дампов чата)

### Выявленные проблемы

**A. В текущем 02_add_aliases.sh (строки 127-166)**

Встроенный русский текст в heredoc:
```bash
wsets() {
  cat <<'SETS'
НАБОРЫ КОМАНД (готовые сценарии)
...
SETS
}
```

**Проблема:** Если файл сохранён в Windows-1251 или смешанной кодировке:
- При передаче через SSH могут быть мусор
- В Termux может вывести `РќРђР'РћР Р« РљРћРњРђРќР"` (UTF-8 как Windows-1251)

**Статус:** ✗ Требует проверки + возможно перекодирования

---

**B. В whelp_ru.txt (строка 1)**

```
ТЕЛЕФОН -> ПК: ПОЛНАЯ СПРАВКА
```

**Проблема:** 
- Если BOM присутствует: при `cat whelp_ru.txt | whelp` будут бинарные символы в начале
- Если CRLF: на Termux будет `^M` в конце строк

**Статус:** ✓ Проверить на BOM

---

**C. В документах (TERMUX_MAILBOX_STABLE_WORKFLOW_2026-03-16.md и др.)**

Русский текст в примерах:
```markdown
## Известные проблемы

- Если видите мусор вроде "Масса брутто" — это признак...
```

**Проблема:**
- Если файл UTF-8 с BOM: GitHub покажет BOM символ
- Если CRLF: git diff будет шумным

**Статус:** ? Требует проверки

---

**D. Потенциальные проблемы в PowerShell-скриптах**

Files like `10_mailbox.ps1`, `06_run_vibe_wrapper.ps1`:
- Русские строки в комментариях
- Output кириллицей

**Проблема:** 
- Если PowerShell скрипт сохранён в Windows-1251: `[Console]::OutputEncoding` не поможет
- PowerShell на Windows может автоматически конвертировать UTF-8→UTF-16 (двойное кодирование)

**Статус:** ? Требует проверки

---

## 3. КАК ДЕТЕКТИРОВАТЬ MOJIBAKE

### Способ 1: file команда (Termux/Linux)

```bash
file -i 02_add_aliases.sh
# Должно вывести: charset=utf-8

file -i whelp_ru.txt
# Должно вывести: charset=utf-8
```

**Если выведет:**
- `charset=iso-8859-1` → Windows-1251 (проблема!)
- `charset=utf-16` → Двойное кодирование (проблема!)

### Способ 2: Проверка на BOM

```bash
# Проверить первые 3 байта на BOM (EF BB BF)
xxd -l 3 whelp_ru.txt
# Если выведет: ef bb bf — есть BOM (нежелателен для .sh/.md)

# Или через od
od -N 3 -t x1 whelp_ru.txt
# Если выведет: 357 273 277 — есть BOM (octal), конвертируем в hex: EF BB BF
```

### Способ 3: Проверка line endings

```bash
# UNIX line endings (LF = 0x0A)
od -c 02_add_aliases.sh | grep '\\n' | head -1
# Должно выявить \n

# Windows line endings (CRLF = 0x0D 0x0A)
od -c 02_add_aliases.sh | grep '\\r' 
# Если есть \r — проблема (на Unix это вызывает ^M)

# Или через dos2unix
file 02_add_aliases.sh
# Если выведет "CRLF" — проблема
```

### Способ 4: Русский текст специфично

```bash
# Проверить, что русский текст кодируется правильно
grep "НАБОРЫ\|Справка\|Mailbox" 02_add_aliases.sh | od -c | head -20
# Должны быть UTF-8 байты (для "Н": d0 9d d0 9e d1 82)

# Если видите ef bf bd (replacement character U+FFFD) → кодировка поломана
```

### Способ 5: Попытка source + вывод

```bash
bash -c "source 02_add_aliases.sh 2>&1 | grep -E '[а-яА-Я]' | head -5"
# Если вывод нечитаемый (мусор) → проблема с кодировкой
```

---

## 4. СПИСОК ФАЙЛОВ ДЛЯ ПРОВЕРКИ И ПЕРЕКОДИРОВАНИЯ

### Обязательно проверить (bash/shell scripts)

```
scripts/termux_ssh_toolkit/termux/install.sh
scripts/termux_ssh_toolkit/termux/01_setup_termux.sh
scripts/termux_ssh_toolkit/termux/02_add_aliases.sh        ← КРИТИЧНО (русский текст в heredoc)
scripts/termux_ssh_toolkit/termux/02_add_aliases_v2.sh     ← Новый (проверить)
scripts/termux_ssh_toolkit/shared/toolkit_functions.sh     ← Новый (проверить)
```

### Обязательно проверить (shared config files)

```
scripts/termux_ssh_toolkit/shared/whelp_ru.txt             ← КРИТИЧНО (весь файл русский)
scripts/termux_ssh_toolkit/shared/whelp_sets_ru.txt        ← КРИТИЧНО (весь файл русский)
```

### Обязательно проверить (документация)

```
docs/AGENTS.md                                               ← Русский текст в примерах
docs/AGENT_HANDOFF.md                                        ← Русский текст в примерах
docs/TERMUX_MAILBOX_STABLE_WORKFLOW_2026-03-16.md          ← Русский в примерах
docs/TERMUX_WINDOWS_VIBE_RUNBOOK.md                        ← Русский в примерах
docs/TERMUX_VIBE_WRAPPER_PLAYBOOK.md                       ← Русский в примерах
VIBE.md                                                      ← Может содержать русский
```

### Дополнительно проверить (PowerShell)

```
scripts/termux_ssh_toolkit/windows/10_mailbox.ps1          ← Русский в output strings
scripts/termux_ssh_toolkit/windows/06_run_vibe_wrapper.ps1 ← Комментарии русские
scripts/termux_ssh_toolkit/windows/05_phone_process_control.ps1
```

### Новые файлы (уже созданы, проверить)

```
docs/BASHRC_REFACTOR_GUIDE.md                   ← Русский текст
BASHRC_REFACTOR_ANALYSIS.md                     ← Русский текст
AGENT_HANDOFF_NEW_SECTION.md                    ← Английский (OK)
toolkit_functions.sh                            ← Проверить русский в комментариях
```

---

## 5. КОМАНДЫ ДЛЯ АВТОМАТИЧЕСКОГО ПЕРЕКОДИРОВАНИЯ

### Шаг 1: Проверить текущее состояние

```bash
cd /path/to/repo

# Проверить все .sh файлы на BOM и кодировку
for f in scripts/termux_ssh_toolkit/**/*.sh; do
  echo "=== $f ==="
  file -i "$f"
  xxd -l 3 "$f" | grep "ef bb bf" && echo "HAS BOM!" || echo "No BOM (OK)"
done

# Проверить все .txt и .md файлы
for f in scripts/termux_ssh_toolkit/**/*.txt docs/*.md; do
  [ -f "$f" ] || continue
  echo "=== $f ==="
  file -i "$f"
  # Проверить на CRLF
  grep -l $'\r' "$f" && echo "HAS CRLF!" || echo "LF only (OK)"
done
```

### Шаг 2: Удалить BOM (если есть)

```bash
# Использовать sed для удаления BOM (EF BB BF в UTF-8)
for f in scripts/termux_ssh_toolkit/**/*.sh scripts/termux_ssh_toolkit/**/*.txt; do
  [ -f "$f" ] || continue
  sed -i '1s/^\xEF\xBB\xBF//' "$f"
done

echo "BOM removed from all files"
```

### Шаг 3: Конвертировать CRLF → LF

```bash
# Использовать dos2unix если установлен
if command -v dos2unix >/dev/null; then
  dos2unix scripts/termux_ssh_toolkit/**/*.sh
  dos2unix scripts/termux_ssh_toolkit/**/*.txt
  dos2unix docs/*.md
else
  # Fallback: используя sed
  for f in scripts/termux_ssh_toolkit/**/*.sh scripts/termux_ssh_toolkit/**/*.txt docs/*.md; do
    [ -f "$f" ] || continue
    sed -i 's/\r$//' "$f"
  done
fi

echo "CRLF converted to LF"
```

### Шаг 4: Убедиться что кодировка UTF-8

```bash
# Конвертировать из Windows-1251 в UTF-8 (если нужно)
for f in scripts/termux_ssh_toolkit/**/*.sh; do
  [ -f "$f" ] || continue
  encoding=$(file -b --mime-encoding "$f")
  if [ "$encoding" != "utf-8" ]; then
    echo "Converting $f from $encoding to UTF-8"
    iconv -f "$encoding" -t UTF-8 "$f" > "$f.tmp"
    mv "$f.tmp" "$f"
  fi
done
```

### Шаг 5: Финальная проверка

```bash
# Проверить что все файлы UTF-8, без BOM, с LF
for f in scripts/termux_ssh_toolkit/**/*.sh scripts/termux_ssh_toolkit/**/*.txt docs/*.md; do
  [ -f "$f" ] || continue
  encoding=$(file -b --mime-encoding "$f")
  bom=$(xxd -l 3 "$f" | grep -o "ef bb bf")
  crlf=$(grep -l $'\r' "$f" 2>/dev/null)
  
  if [ "$encoding" = "utf-8" ] && [ -z "$bom" ] && [ -z "$crlf" ]; then
    echo "✓ $f: OK (UTF-8, no BOM, LF)"
  else
    echo "✗ $f: PROBLEM (encoding=$encoding, bom=$bom, crlf=$crlf)"
  fi
done
```

---

## 6. ПРОВЕРКА РУССКОГО ТЕКСТА В TERMUX И POWERSHELL

### Termux: Проверить что русский выводится правильно

```bash
# 1. Проверить локаль
locale
# Должно быть en_US.UTF-8 или similar (UTF-8)

# 2. Проверить что можем читать русский текст из файла
cat scripts/termux_ssh_toolkit/shared/whelp_ru.txt | head -5
# Должно выводить читаемый русский текст

# 3. Проверить что функции выводят русский текст
source ~/.bashrc
whelp | head -10
# Должен быть русский текст, без мусора

# 4. Проверить что окружение поддерживает UTF-8
echo $LANG
# Должно содержать UTF-8
```

### PowerShell: Проверить что русский работает в скриптах

```powershell
# 1. Проверить input/output encoding
[Console]::InputEncoding
[Console]::OutputEncoding
# Должны быть System.Text.UTF8Encoding или System.Text.UnicodeEncoding

# 2. Проверить русский текст в переменной
$text = "Привет мир"
Write-Host $text
# Должно вывести читаемый русский

# 3. Проверить что база64-декодирование сохраняет UTF-8
$base64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes("Привет"))
$decoded = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($base64))
Write-Host $decoded
# Должно вывести "Привет" без мусора

# 4. Проверить что PowerShell скрипт сохранён в UTF-8
# (VS Code: File → Save with Encoding → UTF-8)
```

### SSH transport (Termux → Windows): Проверить е2е

```bash
# На Termux:
wcmd "Write-Host 'Привет из Termux'"
# Должно вывести читаемый русский

# Если выведет мусор → проблема в:
# - Кодировке .sh скрипта
# - PowerShell encoding на Windows
# - SSH transport (исправляется _wps функцией с base64)
```

---

## 7. ИТОГОВЫЙ ЧЕК-ЛИСТ ПЕРЕКОДИРОВАНИЯ

### Перед merge в repo:

- [ ] Проверить все .sh файлы на BOM: `xxd -l 3 file.sh`
  - Если есть EF BB BF → удалить: `sed -i '1s/^\xEF\xBB\xBF//' file.sh`
  
- [ ] Проверить все файлы на CRLF: `file file.sh` или `grep -l $'\r' file.sh`
  - Если CRLF найден → конвертировать: `dos2unix file.sh` или `sed -i 's/\r$//' file.sh`
  
- [ ] Проверить кодировку: `file -i file.sh` должно быть `charset=utf-8`
  - Если не UTF-8 → конвертировать: `iconv -f WINDOWS-1251 -t UTF-8 file.sh > file.sh.tmp && mv file.sh.tmp file.sh`
  
- [ ] Проверить русский текст в Termux:
  ```bash
  source ~/.bashrc
  whelp | head -20
  # Должен быть читаемый русский текст
  ```
  
- [ ] Проверить русский текст в PowerShell:
  ```powershell
  wcmd "Write-Host 'Проверка русского'"
  # Должен быть читаемый русский
  ```
  
- [ ] Проверить что вновь созданные файлы (toolkit_functions.sh, BASHRC_REFACTOR_GUIDE.md и т.д.):
  - Сохранены в UTF-8 (без BOM)
  - LF line endings
  - Русский текст читается корректно

### Git конфиг (per repo):

```bash
cd /path/to/repo

# Убедиться что core.autocrlf=false (не конвертировать LF ↔ CRLF)
git config core.autocrlf false

# Убедиться что safecrlf=false (не блокировать смешанные endings)
git config core.safecrlf false

# Добавить .gitattributes для enforcing LF
cat > .gitattributes <<'EOF'
* text=auto
*.sh text eol=lf
*.md text eol=lf
*.txt text eol=lf
*.ps1 text eol=crlf
EOF

git add .gitattributes
git commit -m "chore: enforce UTF-8 + LF line endings"
```

---

## 8. БЫСТРАЯ ДИАГНОСТИКА MOJIBAKE

Если оператор видит странные символы в output:

```bash
# 1. Проверить что file кодируется правильно
file -i /path/to/suspicious/file

# 2. Проверить locale в Termux
locale

# 3. Проверить конкретную функцию
bash -c "source ~/.bashrc && whelp 2>&1 | od -c | head -20"
# Должны быть UTF-8 байты (d0 9d = Н на русском)

# 4. Если видит ef bf bd (replacement char) → данные потеряны (critica!)
bash -c "source ~/.bashrc && whelp 2>&1 | od -c" | grep "ef bf bd" && echo "MOJIBAKE DETECTED!"

# 5. Откатить на бэкап
cp ~/.bashrc.bak ~/.bashrc
source ~/.bashrc
```

---

## SUMMARY

✅ **Единый стандарт:** UTF-8 (без BOM) + LF  
✅ **Где mojibake:** В 02_add_aliases.sh (heredoc русский текст) и возможно в .txt files  
✅ **Как детектировать:** `file -i`, `xxd`, `grep -l $'\r'`  
✅ **Как исправить:** `sed`, `dos2unix`, `iconv`  
✅ **После исправления:** Тестировать в Termux (`whelp`) и PowerShell (`wcmd`)

