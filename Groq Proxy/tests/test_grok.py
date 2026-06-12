#!/usr/bin/env python3
"""
Тест прямого вызова Grok через acpx
"""

import subprocess
import sys

def test_grok():
    print("=" * 50)
    print("Тест Grok SuperGrok")
    print("=" * 50)
    
    # Тест 1: простой запрос
    print("\n1. Простой запрос 'say hi':")
    result = subprocess.run(
        ["acpx", "exec", "grok", "say hi"],
        capture_output=True,
        text=True
    )
    print(f"   Ответ: {result.stdout.strip()}")
    
    # Тест 2: запрос на русском
    print("\n2. Запрос на русском 'привет, как дела?':")
    result = subprocess.run(
        ["acpx", "exec", "grok", "привет, как дела?"],
        capture_output=True,
        text=True
    )
    print(f"   Ответ: {result.stdout.strip()}")
    
    # Тест 3: запрос кода
    print("\n3. Запрос кода 'hello world на Python':")
    result = subprocess.run(
        ["acpx", "exec", "grok", "напиши hello world на Python"],
        capture_output=True,
        text=True
    )
    print(f"   Ответ:\n{result.stdout.strip()}")
    
    print("\n" + "=" * 50)
    print("✅ Тест завершён")
    print("=" * 50)

if __name__ == "__main__":
    try:
        test_grok()
    except FileNotFoundError:
        print("❌ Ошибка: acpx не найден. Убедись, что acpx установлен и в PATH.")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
