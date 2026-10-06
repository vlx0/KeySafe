# KeySafe

Локальный сейф **API-ключей** для ИИ (OpenAI, Anthropic, Google…).

**Автор:** darkshade ([@vlx0](https://github.com/vlx0))

**365 дней open source** · **неделя 7 — «ИИ»** · **день 44**.

---

## Что умеет (v1)

- мастер-пароль (PBKDF2 + Fernet)
- добавить / изменить / удалить ключ
- маска по умолчанию, показать через ⋯
- копировать в буфер (двойной клик / ⋯)
- пресеты провайдеров
- хранилище: `%USERPROFILE%\.keysafe\keys.bin`

Баланс / usage провайдеров — **в следующих версиях**.

Не путать с [PassVault](https://github.com/vlx0/PassVault): там общий менеджер паролей; KeySafe заточен под API-ключи ИИ.

## Запуск

```bat
start.bat
```

или `python -m pip install -r requirements.txt` затем `python -m keysafe` / `run_keysafe.pyw`.

Нужен **Python 3.10+** (Windows) с tkinter.

## Лицензия

MIT. См. [LICENSE](LICENSE).
