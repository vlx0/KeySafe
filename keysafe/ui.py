"""KeySafe GUI."""

from __future__ import annotations

import ctypes
import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import __version__
from .instance import WINDOW_TITLE
from .settings import TIMEOUT_CHOICES, load_timeout_minutes, save_timeout_minutes, timeout_label
from .store import PROVIDERS, KeyEntry, KeyStore

BG = "#111111"
FG = "#ffffff"
MUTED = "#999999"
CARD = "#1a1a1a"
CARD_HOVER = "#222222"
BTN = "#333333"
BTN_HOVER = "#444444"
OK = "#86efac"
DANGER = "#fca5a5"
DOT_IDLE = "#1a1a1a"
DOT_SHOW = "#cccccc"


class KeySafeApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(WINDOW_TITLE)
        self.geometry("720x520")
        self.minsize(560, 400)
        self.configure(bg=BG)

        self.store = KeyStore()
        self._revealed: set[str] = set()
        self._rows: dict[str, tk.Frame] = {}
        self._popup: tk.Menu | None = None
        self._timeout_min = load_timeout_minutes()
        self._idle_after: str | None = None
        self._idle_armed_at = 0.0
        self._unlocked_ui = False
        self._flash_after: str | None = None
        self._edit_id: str | None = None
        self._form_open = False

        self._gate = tk.Frame(self, bg=BG)
        self._main = tk.Frame(self, bg=BG)
        self._build_gate()
        self._build_main()
        self._gate.pack(fill="both", expand=True)

        for seq in ("<Any-KeyPress>", "<Any-Button>", "<Motion>"):
            self.bind_all(seq, self._on_activity, add="+")

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(20, self._place)
        self.after(40, self._focus_gate)

    def _place(self) -> None:
        self.update_idletasks()
        w, h = self.winfo_width() or 720, self.winfo_height() or 520
        sw = ctypes.windll.user32.GetSystemMetrics(0)
        sh = ctypes.windll.user32.GetSystemMetrics(1)
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 4}")

    def _mk_btn(self, parent, text, cmd, danger: bool = False) -> tk.Label:
        lbl = tk.Label(
            parent,
            text=text,
            bg=BTN,
            fg=DANGER if danger else FG,
            font=("Segoe UI", 10),
            padx=12,
            pady=7,
            cursor="hand2",
        )
        lbl.bind("<Button-1>", lambda _e: cmd())
        lbl.bind("<Enter>", lambda _e: lbl.configure(bg=BTN_HOVER))
        lbl.bind("<Leave>", lambda _e: lbl.configure(bg=BTN))
        return lbl

    # --- gate (password) -------------------------------------------------
    def _build_gate(self) -> None:
        wrap = tk.Frame(self._gate, bg=BG)
        wrap.place(relx=0.5, rely=0.45, anchor="center")

        tk.Label(wrap, text="KeySafe", bg=BG, fg=FG, font=("Segoe UI Semibold", 22)).pack()
        self._gate_sub = tk.Label(wrap, text="", bg=BG, fg=MUTED, font=("Segoe UI", 10))
        self._gate_sub.pack(pady=(8, 18))

        self._pwd = tk.StringVar()
        self._pwd2 = tk.StringVar()

        self._pwd_entry = tk.Entry(
            wrap,
            textvariable=self._pwd,
            show="•",
            bg=CARD,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            font=("Segoe UI", 12),
            width=28,
        )
        self._pwd_entry.pack(ipady=8, pady=(0, 8))

        self._pwd2_entry = tk.Entry(
            wrap,
            textvariable=self._pwd2,
            show="•",
            bg=CARD,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            font=("Segoe UI", 12),
            width=28,
        )

        self._gate_err = tk.Label(wrap, text="", bg=BG, fg=DANGER, font=("Segoe UI", 9))
        self._gate_err.pack(pady=(0, 10))

        self._gate_btn_row = tk.Frame(wrap, bg=BG)
        self._gate_btn_row.pack()

        self._refresh_gate_mode()

    def _refresh_gate_mode(self) -> None:
        for w in self._gate_btn_row.winfo_children():
            w.destroy()
        self._pwd.set("")
        self._pwd2.set("")
        self._gate_err.configure(text="")

        if not self.store.exists():
            self._gate_mode = "create"
            self._gate_sub.configure(text="Придумай пароль для сейфа API-ключей")
            self._pwd2_entry.pack(ipady=8, pady=(0, 8), after=self._pwd_entry)
            self._mk_btn(self._gate_btn_row, "Создать сейф", self._gate_submit).pack()
            self.bind("<Return>", lambda _e: self._gate_submit())
        elif self.store.is_legacy_dpapi():
            self._gate_mode = "migrate"
            self._gate_sub.configure(
                text="Найден старый сейф — задай пароль, чтобы защитить ключи"
            )
            self._pwd2_entry.pack(ipady=8, pady=(0, 8), after=self._pwd_entry)
            self._mk_btn(self._gate_btn_row, "Защитить паролем", self._gate_submit).pack()
            self.bind("<Return>", lambda _e: self._gate_submit())
        else:
            self._gate_mode = "unlock"
            self._gate_sub.configure(text="Введи пароль сейфа")
            self._pwd2_entry.pack_forget()
            self._mk_btn(self._gate_btn_row, "Войти", self._gate_submit).pack()
            self.bind("<Return>", lambda _e: self._gate_submit())

    def _focus_gate(self) -> None:
        self._pwd_entry.focus_set()

    def _gate_submit(self) -> None:
        p1 = self._pwd.get()
        p2 = self._pwd2.get()
        try:
            if self._gate_mode == "create":
                if p1 != p2:
                    raise ValueError("Пароли не совпадают")
                self.store.create(p1)
            elif self._gate_mode == "migrate":
                if p1 != p2:
                    raise ValueError("Пароли не совпадают")
                n = self.store.migrate_from_dpapi(p1)
                self._open_main()
                self._flash(f"перенесено: {n}")
                return
            else:
                self.store.unlock(p1)
        except ValueError as e:
            self._gate_err.configure(text=str(e))
            return
        except OSError as e:
            self._gate_err.configure(text=str(e))
            return

        self._open_main()

    def _open_main(self) -> None:
        self._gate.pack_forget()
        self._main.pack(fill="both", expand=True)
        self._unlocked_ui = True
        self._reload()
        self._sync_timeout_btn()
        self.unbind("<Return>")
        self._arm_idle(force=True)

    def _close_transients(self) -> None:
        for w in list(self.winfo_children()):
            if isinstance(w, tk.Toplevel):
                try:
                    w.grab_release()
                except tk.TclError:
                    pass
                try:
                    w.destroy()
                except (tk.TclError, TypeError):
                    try:
                        w.withdraw()
                    except tk.TclError:
                        pass
        self._popup = None

    def _lock_now(self) -> None:
        self._cancel_idle()
        self._close_transients()
        self._hide_form()
        self._unlocked_ui = False
        try:
            self.clipboard_clear()
        except tk.TclError:
            pass
        self.store.lock()
        self._revealed.clear()
        self._main.pack_forget()
        self._gate.pack(fill="both", expand=True)
        self._refresh_gate_mode()
        self.after(20, self._focus_gate)

    def _on_close(self) -> None:
        self._cancel_idle()
        self._close_transients()
        if self._unlocked_ui:
            try:
                self.clipboard_clear()
            except tk.TclError:
                pass
            self.store.lock()
        for seq in ("<Any-KeyPress>", "<Any-Button>", "<Motion>"):
            try:
                self.unbind_all(seq)
            except tk.TclError:
                pass
        self.destroy()

    def _on_activity(self, _event=None) -> None:
        if self._unlocked_ui:
            self._arm_idle(force=False)

    def _cancel_idle(self) -> None:
        if self._idle_after is not None:
            try:
                self.after_cancel(self._idle_after)
            except tk.TclError:
                pass
            self._idle_after = None
        self._idle_armed_at = 0.0

    def _arm_idle(self, *, force: bool = True) -> None:
        if not self._unlocked_ui or self._timeout_min <= 0:
            self._cancel_idle()
            return
        now = time.monotonic()
        # Motion сыпется часто — не пересоздаём after каждые миллисекунды
        if not force and self._idle_after is not None and (now - self._idle_armed_at) < 1.0:
            return
        self._cancel_idle()
        ms = self._timeout_min * 60_000
        self._idle_armed_at = now
        self._idle_after = self.after(ms, self._idle_lock)

    def _idle_lock(self) -> None:
        self._idle_after = None
        if self._unlocked_ui:
            self._lock_now()
            self._gate_err.configure(text="сейф закрыт по таймауту")

    def _pick_timeout(self) -> None:
        menu = tk.Menu(
            self,
            tearoff=0,
            bg="#1e1e1e",
            fg=FG,
            activebackground="#2c2c2c",
            activeforeground=FG,
            bd=0,
            relief="flat",
            font=("Segoe UI", 10),
        )
        for m in TIMEOUT_CHOICES:
            label = "Выкл" if m == 0 else f"{m} мин"
            if m == self._timeout_min:
                label = f"✓ {label}"
            menu.add_command(label=label, command=lambda minutes=m: self._set_timeout(minutes))
        try:
            x, y = self.winfo_pointerxy()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _set_timeout(self, minutes: int) -> None:
        self._timeout_min = minutes
        save_timeout_minutes(minutes)
        self._sync_timeout_btn()
        self._arm_idle(force=True)
        self._flash(timeout_label(minutes).lower())

    def _sync_timeout_btn(self) -> None:
        self._timeout_btn.configure(text=timeout_label(self._timeout_min))

    # --- main ------------------------------------------------------------
    def _build_main(self) -> None:
        pad = tk.Frame(self._main, bg=BG)
        pad.pack(fill="both", expand=True, padx=22, pady=18)

        head = tk.Frame(pad, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="KeySafe", bg=BG, fg=FG, font=("Segoe UI Semibold", 18)).pack(
            side="left"
        )
        self._mk_btn(head, "Добавить", self._add).pack(side="right")
        self._mk_btn(head, "Выйти", self._lock_now).pack(side="right", padx=(0, 8))
        self._timeout_btn = self._mk_btn(head, timeout_label(self._timeout_min), self._pick_timeout)
        self._timeout_btn.pack(side="right", padx=(0, 8))
        tk.Label(
            head,
            text="неделя 7 · ИИ · день 44",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(side="right", padx=(0, 12))

        tk.Label(
            pad,
            text="Ключи под паролем · наведи на строку → ⋯",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(4, 12))

        self._body = tk.Frame(pad, bg=BG)
        self._body.pack(fill="both", expand=True)

        self._list_wrap = tk.Frame(self._body, bg=CARD)
        self._list_wrap.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(self._list_wrap, bg=CARD, highlightthickness=0, bd=0)
        self._scroll = tk.Scrollbar(self._list_wrap, orient="vertical", command=self._canvas.yview)
        self._list = tk.Frame(self._canvas, bg=CARD)
        self._list_id = self._canvas.create_window((0, 0), window=self._list, anchor="nw")
        self._canvas.configure(yscrollcommand=self._scroll.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._scroll.pack(side="right", fill="y")

        self._list.bind("<Configure>", self._on_list_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._list.bind("<MouseWheel>", self._on_wheel)

        self._form = tk.Frame(self._body, bg=CARD)
        self._build_form()

        foot = tk.Frame(pad, bg=BG)
        foot.pack(fill="x", pady=(10, 0))
        self._hint = tk.Label(foot, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self._hint.pack(side="left")
        self._status = tk.Label(foot, text="", bg=BG, fg=OK, font=("Segoe UI", 9))
        self._status.pack(side="left", padx=(12, 0))
        tk.Label(
            foot,
            text=f"v{__version__} · darkshade",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(side="right")

    def _build_form(self) -> None:
        inner = tk.Frame(self._form, bg=CARD)
        inner.pack(fill="both", expand=True, padx=20, pady=18)

        self._form_title = tk.Label(
            inner, text="Новый ключ", bg=CARD, fg=FG, font=("Segoe UI Semibold", 14)
        )
        self._form_title.pack(anchor="w", pady=(0, 14))

        self._form_provider = tk.StringVar(value="OpenAI")
        self._form_name = tk.StringVar()
        self._form_key = tk.StringVar()
        self._form_note = tk.StringVar()

        def field(label: str, widget: tk.Widget) -> None:
            tk.Label(inner, text=label, bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
            widget.pack(fill="x", pady=(4, 12), ipady=6)

        field(
            "Провайдер",
            ttk.Combobox(
                inner,
                textvariable=self._form_provider,
                values=PROVIDERS,
                state="readonly",
                font=("Segoe UI", 10),
            ),
        )
        field(
            "Имя",
            tk.Entry(
                inner,
                textvariable=self._form_name,
                bg="#111111",
                fg=FG,
                insertbackground=FG,
                relief="flat",
                font=("Segoe UI", 10),
            ),
        )
        self._form_key_entry = tk.Entry(
            inner,
            textvariable=self._form_key,
            bg="#111111",
            fg=FG,
            insertbackground=FG,
            relief="flat",
            font=("Consolas", 10),
            show="•",
        )
        field("Ключ", self._form_key_entry)
        field(
            "Заметка",
            tk.Entry(
                inner,
                textvariable=self._form_note,
                bg="#111111",
                fg=FG,
                insertbackground=FG,
                relief="flat",
                font=("Segoe UI", 10),
            ),
        )

        self._form_err = tk.Label(inner, text="", bg=CARD, fg=DANGER, font=("Segoe UI", 9))
        self._form_err.pack(anchor="w", pady=(0, 8))

        row = tk.Frame(inner, bg=CARD)
        row.pack(fill="x")
        self._mk_btn(row, "Сохранить", self._save_form).pack(side="left")
        self._mk_btn(row, "Отмена", self._hide_form).pack(side="left", padx=(8, 0))

    def _show_form(self, *, title: str, entry: KeyEntry | None = None) -> None:
        self._form_open = True
        self._edit_id = entry.id if entry else None
        self._form_title.configure(text=title)
        self._form_err.configure(text="")
        if entry:
            self._form_provider.set(entry.provider if entry.provider in PROVIDERS else "Other")
            self._form_name.set(entry.name)
            self._form_key.set(entry.key)
            self._form_note.set(entry.note)
        else:
            self._form_provider.set("OpenAI")
            self._form_name.set("")
            self._form_key.set("")
            self._form_note.set("")
        self._list_wrap.pack_forget()
        self._form.pack(fill="both", expand=True)
        self.bind("<Return>", lambda _e: self._save_form())
        self.bind("<Escape>", lambda _e: self._hide_form())
        self.after(30, self._form_key_entry.focus_set)

    def _hide_form(self) -> None:
        if not getattr(self, "_form_open", False):
            return
        self._form_open = False
        self._edit_id = None
        self._form.pack_forget()
        self._list_wrap.pack(fill="both", expand=True)
        self.unbind("<Return>")
        self.unbind("<Escape>")

    def _save_form(self) -> None:
        if not self._form_open:
            return
        provider = self._form_provider.get()
        name = self._form_name.get()
        key = self._form_key.get()
        note = self._form_note.get()
        if not key.strip():
            self._form_err.configure(text="ключ пустой")
            return
        try:
            if self._edit_id:
                entry = self.store.get(self._edit_id)
                if not entry:
                    self._form_err.configure(text="запись не найдена")
                    return
                entry.provider = provider
                entry.name = name.strip() or "без имени"
                entry.key = key.strip()
                entry.note = note.strip()
                self.store.update(entry)
                msg = "сохранено"
            else:
                self.store.add(KeyEntry.create(provider, name, key, note))
                msg = "добавлено"
        except OSError as e:
            self._form_err.configure(text=str(e))
            return
        self._hide_form()
        self._reload()
        self._flash(msg)
    def _on_list_configure(self, _event=None) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self._canvas.itemconfigure(self._list_id, width=event.width)

    def _on_wheel(self, event) -> None:
        self._canvas.yview_scroll(int(-event.delta / 120), "units")

    def _flash(self, text: str) -> None:
        if self._flash_after is not None:
            try:
                self.after_cancel(self._flash_after)
            except tk.TclError:
                pass
            self._flash_after = None
        try:
            self._status.configure(text=text)
        except tk.TclError:
            return

        def _clear() -> None:
            self._flash_after = None
            try:
                self._status.configure(text="")
            except tk.TclError:
                pass

        self._flash_after = self.after(1800, _clear)

    def _plural_keys(self, n: int) -> str:
        if n % 100 in (11, 12, 13, 14):
            return "ключей"
        r = n % 10
        if r == 1:
            return "ключ"
        if 2 <= r <= 4:
            return "ключа"
        return "ключей"

    def _reload(self) -> None:
        for child in self._list.winfo_children():
            child.destroy()
        self._rows.clear()

        if not self.store.entries:
            tk.Label(
                self._list,
                text="Пока пусто — нажми «Добавить»",
                bg=CARD,
                fg=MUTED,
                font=("Segoe UI", 11),
                pady=40,
            ).pack(fill="x")
        else:
            for e in self.store.entries:
                self._rows[e.id] = self._make_row(e)

        n = len(self.store.entries)
        self._hint.configure(
            text=f"{n} {self._plural_keys(n)} · баланс позже · ~/.keysafe/keys.bin"
        )
        self.after(10, self._on_list_configure)

    def _bind_tree(self, widget: tk.Misc, sequence: str, handler) -> None:
        widget.bind(sequence, handler)
        for child in widget.winfo_children():
            self._bind_tree(child, sequence, handler)

    def _make_row(self, entry: KeyEntry) -> tk.Frame:
        row = tk.Frame(self._list, bg=CARD)
        row.pack(fill="x", padx=8, pady=3)

        inner = tk.Frame(row, bg=CARD)
        inner.pack(fill="x", padx=8, pady=10)

        more = tk.Label(
            inner,
            text="⋯",
            bg=CARD,
            fg=DOT_IDLE,
            font=("Segoe UI Semibold", 18),
            width=2,
            cursor="hand2",
        )
        more.pack(side="right", padx=(8, 0))

        left = tk.Frame(inner, bg=CARD)
        left.pack(side="left", fill="x", expand=True)

        top = tk.Frame(left, bg=CARD)
        top.pack(fill="x")
        tk.Label(top, text=entry.provider, bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(
            side="left"
        )
        tk.Label(
            top,
            text=entry.name,
            bg=CARD,
            fg=FG,
            font=("Segoe UI Semibold", 11),
        ).pack(side="left", padx=(10, 0))

        shown = entry.key if entry.id in self._revealed else entry.masked()
        key_lbl = tk.Label(
            left,
            text=shown,
            bg=CARD,
            fg=MUTED,
            font=("Consolas", 10),
            anchor="w",
        )
        key_lbl.pack(fill="x", pady=(4, 0))
        if entry.note:
            tk.Label(
                left,
                text=entry.note,
                bg=CARD,
                fg=MUTED,
                font=("Segoe UI", 9),
                anchor="w",
            ).pack(fill="x", pady=(2, 0))

        def paint(bg: str, dot: str) -> None:
            for w in (row, inner, left, top, more):
                w.configure(bg=bg)
            more.configure(fg=dot)
            for w in left.winfo_children():
                try:
                    w.configure(bg=bg)
                except tk.TclError:
                    pass
            for w in top.winfo_children():
                try:
                    w.configure(bg=bg)
                except tk.TclError:
                    pass

        def on_enter(_e=None) -> None:
            paint(CARD_HOVER, DOT_SHOW)

        def on_leave(_e=None) -> None:
            x, y = self.winfo_pointerxy()
            under = self.winfo_containing(x, y)
            if under is not None and str(under).startswith(str(row)):
                return
            paint(CARD, DOT_IDLE)

        def open_menu(event=None):
            self._open_row_menu(entry, event)
            return "break"

        def copy_quick(_e=None):
            self._copy_entry(entry)
            return "break"

        self._bind_tree(row, "<Enter>", on_enter)
        self._bind_tree(row, "<Leave>", on_leave)
        more.bind("<Button-1>", open_menu)
        self._bind_tree(row, "<Button-3>", open_menu)
        key_lbl.bind("<Double-Button-1>", copy_quick)
        left.bind("<Double-Button-1>", copy_quick)
        return row

    def _open_row_menu(self, entry: KeyEntry, event=None) -> None:
        menu = tk.Menu(
            self,
            tearoff=0,
            bg="#1e1e1e",
            fg=FG,
            activebackground="#2c2c2c",
            activeforeground=FG,
            bd=0,
            relief="flat",
            font=("Segoe UI", 10),
        )
        revealed = entry.id in self._revealed
        menu.add_command(label="Копировать", command=lambda: self._copy_entry(entry))
        menu.add_command(
            label="Скрыть" if revealed else "Показать",
            command=lambda: self._toggle_entry(entry),
        )
        menu.add_command(label="Изменить", command=lambda: self._edit_entry(entry))
        menu.add_separator()
        menu.add_command(label="Удалить", command=lambda: self._delete_entry(entry))
        self._popup = menu
        try:
            if event is not None and getattr(event, "x_root", None):
                x, y = int(event.x_root), int(event.y_root)
            else:
                x, y = self.winfo_pointerxy()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _add(self) -> None:
        self._show_form(title="Новый ключ")

    def _edit_entry(self, entry: KeyEntry) -> None:
        self._show_form(title="Изменить ключ", entry=entry)

    def _copy_entry(self, entry: KeyEntry) -> None:
        self.clipboard_clear()
        self.clipboard_append(entry.key)
        self._flash("скопировано")

    def _toggle_entry(self, entry: KeyEntry) -> None:
        if entry.id in self._revealed:
            self._revealed.discard(entry.id)
            self._flash("скрыто")
        else:
            self._revealed.add(entry.id)
            self._flash("показано")
        self._reload()

    def _delete_entry(self, entry: KeyEntry) -> None:
        if not messagebox.askyesno("KeySafe", f"Удалить «{entry.name}» ({entry.provider})?"):
            return
        try:
            self.store.remove(entry.id)
        except OSError as e:
            messagebox.showerror("KeySafe", f"Не удалось сохранить:\n{e}")
            return
        self._revealed.discard(entry.id)
        self._reload()
        self._flash("удалено")


def run() -> None:
    KeySafeApp().mainloop()
