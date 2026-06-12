#!/usr/bin/env python3
"""
Grok SuperGrok Manager - GUI для управления Grok ACP сервером и прокси
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import subprocess
import threading
import time
import os
import sys

class GrokManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Grok SuperGrok Manager")
        self.root.geometry("650x550")
        self.root.resizable(True, True)

        # Определяем пути (скрипт в scripts/, корень проекта — на уровень выше)
        self.grok_proxy_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.base_dir = self.grok_proxy_dir

        self.grok_process = None
        self.proxy_process = None

        # Фрейм для статуса
        status_frame = ttk.LabelFrame(root, text="Статус", padding=10)
        status_frame.pack(fill="x", padx=10, pady=5)

        self.grok_status = ttk.Label(status_frame, text="🔴 Grok ACP: Остановлен", foreground="red")
        self.grok_status.pack(anchor="w")

        self.proxy_status = ttk.Label(status_frame, text="🔴 OpenAI Proxy: Остановлен", foreground="red")
        self.proxy_status.pack(anchor="w")

        self.http_status = ttk.Label(status_frame, text="🔴 HTTP 8080: Не отвечает", foreground="red")
        self.http_status.pack(anchor="w")

        self.model_status = ttk.Label(status_frame, text="⚙️ Модель: grok", foreground="blue")
        self.model_status.pack(anchor="w")

        # Прогресс-бар
        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.pack(fill="x", padx=10, pady=5)

        # Кнопки
        btn_frame = ttk.Frame(root)
        btn_frame.pack(pady=10)

        self.start_btn = ttk.Button(btn_frame, text="▶ Запустить всё", command=self.start_all)
        self.start_btn.pack(side="left", padx=5)

        self.stop_btn = ttk.Button(btn_frame, text="⏹ Остановить всё", command=self.stop_all, state="disabled")
        self.stop_btn.pack(side="left", padx=5)

        self.status_btn = ttk.Button(btn_frame, text="🔄 Проверить статус", command=self.update_status)
        self.status_btn.pack(side="left", padx=5)

        self.open_config_btn = ttk.Button(btn_frame, text="⚙️ Kilo Code настройки", command=self.show_config)
        self.open_config_btn.pack(side="left", padx=5)

        # Инструкция
        info_frame = ttk.LabelFrame(root, text="Настройки Kilo Code", padding=10)
        info_frame.pack(fill="x", padx=10, pady=5)

        info_text = tk.Text(info_frame, height=5, wrap="word", bg="#f0f0f0", borderwidth=0)
        info_text.insert("1.0",
            "API Provider: OpenAI Compatible\n"
            "Base URL: http://localhost:8080/v1\n"
            "API Key: dummy\n"
            "Model ID: grok\n\n"
            "После запуска менеджера выбери эту модель в чате Kilo Code")
        info_text.config(state="disabled")
        info_text.pack(fill="both", padx=5, pady=5)

        # Лог-окно
        log_frame = ttk.LabelFrame(root, text="Логи", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, width=70)
        self.log_text.pack(fill="both", expand=True)

        # Автообновление статуса
        self.update_status()
        self.check_http_status()

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)

    def show_config(self):
        """Показать окно с настройками Kilo Code"""
        config_window = tk.Toplevel(self.root)
        config_window.title("Kilo Code Настройки")
        config_window.geometry("400x250")
        config_window.resizable(False, False)

        text = tk.Text(config_window, wrap="word", padx=10, pady=10)
        text.insert("1.0",
            "1. Открой Kilo Code\n"
            "2. Нажми на шестерёнку (Settings)\n"
            "3. Выбери API Provider: OpenAI Compatible\n"
            "4. Заполни поля:\n"
            "   - Base URL: http://localhost:8080/v1\n"
            "   - API Key: dummy\n"
            "   - Model ID: grok\n"
            "5. Сохрани и выбери модель 'grok' в чате\n\n"
            "После запуска менеджера нажми '▶ Запустить всё'")
        text.config(state="disabled")
        text.pack(fill="both", expand=True)

        ttk.Button(config_window, text="Закрыть", command=config_window.destroy).pack(pady=10)

    def update_status(self):
        # Проверяем Grok процесс
        result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq grok.exe"],
                                capture_output=True, text=True)
        grok_running = "grok.exe" in result.stdout.lower()

        # Также проверяем grok-* (разные версии)
        if not grok_running:
            result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq grok-*"],
                                    capture_output=True, text=True)
            grok_running = "grok-" in result.stdout.lower()

        if grok_running:
            self.grok_status.config(text="🟢 Grok ACP: Запущен", foreground="green")
        else:
            self.grok_status.config(text="🔴 Grok ACP: Остановлен", foreground="red")

        # Проверяем прокси процесс (python.exe)
        result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe"],
                                capture_output=True, text=True)
        proxy_running = "python.exe" in result.stdout.lower()

        if proxy_running:
            self.proxy_status.config(text="🟢 OpenAI Proxy: Запущен", foreground="green")
        else:
            self.proxy_status.config(text="🔴 OpenAI Proxy: Остановлен", foreground="red")

        # Обновляем состояние кнопок
        if grok_running or proxy_running:
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
        else:
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")

        self.root.after(5000, self.update_status)

    def check_http_status(self):
        try:
            import urllib.request
            urllib.request.urlopen("http://localhost:8080/v1/models", timeout=2)
            self.http_status.config(text="🟢 HTTP 8080: Отвечает", foreground="green")
        except:
            self.http_status.config(text="🔴 HTTP 8080: Не отвечает", foreground="red")

        self.root.after(3000, self.check_http_status)

    def start_all(self):
        self.log("▶ Запуск всех компонентов...")
        self.progress.start(10)

        # Проверяем, существует ли папка Groq Proxy
        if not os.path.exists(self.grok_proxy_dir):
            self.log(f"❌ Папка не найдена: {self.grok_proxy_dir}")
            self.progress.stop()
            return

        # Запуск Grok ACP сервера
        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            grok_flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.grok_process = subprocess.Popen(
                ["grok", "agent", "stdio"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=grok_flags,
                close_fds=True,
                env=env
            )
            self.log("✅ Grok ACP сервер запущен")
        except FileNotFoundError:
            self.log("❌ Ошибка: grok не найден в PATH")
        except Exception as e:
            self.log(f"❌ Ошибка запуска Grok: {e}")

        time.sleep(2)

        # Запуск прокси (с логированием + -u)
        try:
            proxy_path = os.path.join(self.grok_proxy_dir, "openai_proxy.py")
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            proxy_flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.proxy_process = subprocess.Popen(
                [sys.executable, "-u", proxy_path],
                stdout=open(os.path.join(self.grok_proxy_dir, "logs", "proxy.out.log"), "w", encoding="utf-8"),
                stderr=open(os.path.join(self.grok_proxy_dir, "logs", "proxy.err.log"), "w", encoding="utf-8"),
                creationflags=proxy_flags,
                close_fds=True,
                env=env
            )
            self.log(f"✅ OpenAI прокси запущен из {proxy_path}")
            self.log("   Логи: logs/proxy_requests.log, logs/proxy.out.log, logs/proxy.err.log")
        except Exception as e:
            self.log(f"❌ Ошибка запуска прокси: {e}")

        time.sleep(3)
        self.progress.stop()
        self.log("✅ Готово! Настройки Kilo Code:")
        self.log("   Base URL: http://localhost:8080/v1, Model: grok, API Key: dummy")
        self.update_status()

    def stop_all(self):
        self.log("⏹ Остановка всех компонентов...")
        self.progress.start(10)

        # Убиваем Grok
        subprocess.run(["taskkill", "/F", "/IM", "grok.exe"],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["taskkill", "/F", "/FI", "IMAGENAME eq grok-*"],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.log("✅ Grok ACP остановлен")

        # Убиваем Python процессы (только прокси, осторожно)
        subprocess.run(["taskkill", "/F", "/IM", "python.exe"],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.log("✅ OpenAI прокси остановлен")

        time.sleep(1)
        self.progress.stop()
        self.update_status()

def main():
    root = tk.Tk()
    app = GrokManager(root)
    root.mainloop()

if __name__ == "__main__":
    main()
