# carplus_manager.py
# CarPlus Manager - versione stabile per Pydroid 3
# Tema: viola + oro. Offline (SQLite). Backup JSON su /sdcard/CarPlus_backup.json (fallback in home).
# Nota: le notifiche locali richiedono 'plyer' (opzionale).

import os
import sqlite3
import json
import traceback
from datetime import datetime, timedelta

from kivy.app import App
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition

# ---------------- CONFIG ----------------
DB_FILENAME = "carplus.db"
DB_PATH = os.path.join(os.path.expanduser("~"), DB_FILENAME)

EXT_BACKUP_PATH = "/sdcard/CarPlus_backup.json"
FALLBACK_BACKUP_PATH = os.path.join(os.path.expanduser("~"), "CarPlus_backup.json")

# Theme colors (RGBA)
COLOR_VIOLET = (0.35, 0.15, 0.45, 1)   # viola
COLOR_GOLD = (0.96, 0.76, 0.12, 1)     # oro
COLOR_BG = (0.99, 0.98, 0.995, 1)      # avorio molto chiaro
COLOR_TEXT = (0.06, 0.06, 0.06, 1)     # quasi nero

Window.clearcolor = COLOR_BG  # do NOT set Window.size -> keeps full screen on Android

# Optional notifications
try:
    from plyer import notification
    HAVE_PLYER = True
except Exception:
    HAVE_PLYER = False

# ---------------- Helper UI ----------------
def show_msg(title, text, wide=False):
    box = BoxLayout(orientation="vertical", padding=12, spacing=12)
    lbl = Label(text=text, halign="left", valign="top", color=COLOR_TEXT)
    lbl.bind(size=lambda w, h: setattr(lbl, 'text_size', (lbl.width, None)))
    box.add_widget(lbl)
    btn = Button(text="OK", size_hint_y=None, height=dp(44),
                 background_color=COLOR_VIOLET, color=(1,1,1,1))
    box.add_widget(btn)
    popup = Popup(title=title, content=box, size_hint=(0.9, 0.75) if wide else (0.85, 0.45), auto_dismiss=False)
    btn.bind(on_release=popup.dismiss)
    popup.open()

# ---------------- Database init & migration ----------------
def ensure_db_and_columns():
    """Create DB and required tables; attempt to add missing columns if present in older DB."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # products (inventory)
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            qty REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            threshold REAL DEFAULT 0
        )
    """)
    # appointments
    c.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client TEXT,
            address TEXT,
            datetime TEXT,
            service TEXT,
            price REAL DEFAULT 0,
            consumption TEXT DEFAULT ''
        )
    """)
    conn.commit()

    # Defensive migrations for appointments (price, consumption)
    try:
        c.execute("PRAGMA table_info(appointments)")
        cols = [r[1] for r in c.fetchall()]
        if "price" not in cols:
            try:
                c.execute("ALTER TABLE appointments ADD COLUMN price REAL DEFAULT 0")
                conn.commit()
            except Exception:
                pass
        if "consumption" not in cols:
            try:
                c.execute("ALTER TABLE appointments ADD COLUMN consumption TEXT DEFAULT ''")
                conn.commit()
            except Exception:
                pass
    except Exception:
        pass

    # Defensive migrations for products
    try:
        c.execute("PRAGMA table_info(products)")
        cols_p = [r[1] for r in c.fetchall()]
        if "unit_price" not in cols_p:
            try:
                c.execute("ALTER TABLE products ADD COLUMN unit_price REAL DEFAULT 0")
                conn.commit()
            except Exception:
                pass
        if "threshold" not in cols_p:
            try:
                c.execute("ALTER TABLE products ADD COLUMN threshold REAL DEFAULT 0")
                conn.commit()
            except Exception:
                pass
    except Exception:
        pass

    conn.close()

# Ensure DB exists/migrated at module import
try:
    ensure_db_and_columns()
except Exception as e:
    print("DB init error:", e)

# ---------------- Small KV for header ----------------
KV = """
<Header@BoxLayout>:
    size_hint_y: None
    height: dp(56)
    padding: dp(8)
    spacing: dp(8)
    canvas.before:
        Color:
            rgba: %f, %f, %f, %f
        Rectangle:
            pos: self.pos
            size: self.size
    Button:
        text: "☰"
        size_hint_x: None
        width: dp(56)
        background_normal: ''
        background_color: 1,1,1,0
        on_release: app.open_menu()
    Label:
        text: app.title
        color: 1, 0.95, 0.7, 1
        bold: True
    Widget:
""" % (COLOR_VIOLET[0], COLOR_VIOLET[1], COLOR_VIOLET[2], COLOR_VIOLET[3])

Builder.load_string(KV)

# ---------------- Screens ----------------
class Dashboard(Screen):
    def on_pre_enter(self):
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", spacing=10, padding=10)
        # header title
        root.add_widget(Label(text="CarPlus Manager", font_size="24sp", color=COLOR_VIOLET, size_hint_y=None, height=dp(40)))
        # quick stats
        stats = BoxLayout(orientation="vertical", spacing=6)
        try:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT COUNT(*), COALESCE(SUM(price),0) FROM appointments")
            tot_app, tot_inc = c.fetchone()
            tot_app = tot_app or 0; tot_inc = tot_inc or 0.0
            c.execute("SELECT COUNT(*) FROM products")
            tot_prod = c.fetchone()[0] or 0
            conn.close()
            stats.add_widget(Label(text=f"Appuntamenti registrati: {tot_app}", color=COLOR_TEXT))
            stats.add_widget(Label(text=f"Incasso totale stimato: €{tot_inc:.2f}", color=COLOR_TEXT))
            stats.add_widget(Label(text=f"Prodotti in inventario: {tot_prod}", color=COLOR_TEXT))
        except Exception:
            stats.add_widget(Label(text="Errore lettura dati", color=COLOR_TEXT))
        root.add_widget(stats)

        # navigation buttons
        nav = BoxLayout(size_hint_y=None, height=dp(56), spacing=8)
        b1 = Button(text="📦 Inventario", background_color=COLOR_VIOLET, color=(1,1,1,1))
        b2 = Button(text="📅 Appuntamenti", background_color=COLOR_VIOLET, color=(1,1,1,1))
        b3 = Button(text="📊 Statistiche", background_color=COLOR_VIOLET, color=(1,1,1,1))
        b4 = Button(text="📁 Backup", background_color=COLOR_VIOLET, color=(1,1,1,1))
        b1.bind(on_release=lambda *a: self.manager.go("inventory"))
        b2.bind(on_release=lambda *a: self.manager.go("appointments"))
        b3.bind(on_release=lambda *a: self.manager.go("stats"))
        b4.bind(on_release=lambda *a: self.manager.go("backup"))
        nav.add_widget(b1); nav.add_widget(b2); nav.add_widget(b3); nav.add_widget(b4)
        root.add_widget(nav)

        # upcoming appointments preview
        try:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            now_iso = datetime.now().isoformat()
            c.execute("SELECT client, datetime, service FROM appointments WHERE datetime >= ? ORDER BY datetime(datetime) ASC LIMIT 5", (now_iso,))
            rows = c.fetchall()
            conn.close()
            if rows:
                preview = "\n".join([f"{r[1][:16]} — {r[0]} — {r[2]}" for r in rows])
            else:
                preview = "Nessun appuntamento imminente"
        except Exception:
            preview = "Errore lettura appuntamenti"
        root.add_widget(Label(text="Prossimi appuntamenti:", color=COLOR_VIOLET, size_hint_y=None, height=dp(24)))
        root.add_widget(Label(text=preview, color=COLOR_TEXT))

        self.add_widget(root)

class Inventory(Screen):
    def on_pre_enter(self):
        self.refresh()

    def refresh(self):
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=8, spacing=8)
        root.add_widget(Label(text="📦 Inventario", font_size="20sp", color=COLOR_VIOLET, size_hint_y=None, height=dp(36)))

        top = BoxLayout(size_hint_y=None, height=dp(44), spacing=8)
        self.search = TextInput(hint_text="Cerca prodotto...", multiline=False)
        add_btn = Button(text="➕", size_hint_x=None, width=dp(56), background_color=COLOR_GOLD, color=(0,0,0,1))
        add_btn.bind(on_release=lambda *a: self.open_add())
        top.add_widget(self.search); top.add_widget(add_btn)
        root.add_widget(top)

        scroll = ScrollView()
        grid = GridLayout(cols=1, spacing=8, size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))

        try:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            q = self.search.text.strip().lower()
            if q:
                c.execute("SELECT id, name, qty, unit_price, threshold FROM products WHERE lower(name) LIKE ? ORDER BY name", (f"%{q}%",))
            else:
                c.execute("SELECT id, name, qty, unit_price, threshold FROM products ORDER BY name")
            rows = c.fetchall()
            conn.close()
            if not rows:
                grid.add_widget(Label(text="Nessun prodotto registrato", color=COLOR_TEXT))
            else:
                for pid, name, qty, price, thr in rows:
                    row = BoxLayout(size_hint_y=None, height=dp(70), padding=6)
                    left = BoxLayout(orientation='vertical')
                    left.add_widget(Label(text=name, color=COLOR_TEXT, halign='left'))
                    left.add_widget(Label(text=f"Quantità: {qty}   Prezzo: €{(price or 0):.2f}   Soglia: {thr}", font_size='12sp', color=COLOR_TEXT, halign='left'))
                    row.add_widget(left)
                    right = BoxLayout(orientation='vertical', size_hint_x=None, width=dp(120))
                    be = Button(text="✏️ Modifica", size_hint_y=None, height=dp(30), background_color=COLOR_VIOLET, color=(1,1,1,1))
                    bd = Button(text="🗑️ Elimina", size_hint_y=None, height=dp(30), background_color=(0.85,0.15,0.15,1), color=(1,1,1,1))
                    be.bind(on_release=lambda btn, pid=pid: self.open_edit(pid))
                    bd.bind(on_release=lambda btn, pid=pid: self.confirm_delete(pid))
                    right.add_widget(be); right.add_widget(bd)
                    row.add_widget(right)
                    grid.add_widget(row)
        except Exception as e:
            grid.add_widget(Label(text="Errore caricamento inventario", color=COLOR_TEXT))
        scroll.add_widget(grid)
        root.add_widget(scroll)
        root.add_widget(Button(text="← Torna", size_hint_y=None, height=dp(44), on_release=lambda *a: self.manager.go("dashboard"), background_color=COLOR_VIOLET, color=(1,1,1,1)))
        self.add_widget(root)

    def open_add(self):
        content = BoxLayout(orientation='vertical', padding=8, spacing=8)
        name = TextInput(hint_text="Nome prodotto", multiline=False)
        qty = TextInput(hint_text="Quantità", input_filter='float', multiline=False)
        price = TextInput(hint_text="Prezzo unitario (€)", input_filter='float', multiline=False)
        thr = TextInput(hint_text="Soglia scorte (es. 1)", input_filter='float', multiline=False)
        content.add_widget(name); content.add_widget(qty); content.add_widget(price); content.add_widget(thr)
        btns = BoxLayout(size_hint_y=None, height=dp(44), spacing=8)
        save = Button(text="Salva", background_color=COLOR_GOLD, color=(0,0,0,1))
        cancel = Button(text="Annulla", background_color=(0.7,0.7,0.7,1))
        btns.add_widget(save); btns.add_widget(cancel)
        content.add_widget(btns)
        popup = Popup(title="Aggiungi prodotto", content=content, size_hint=(0.95, 0.7))
        def do_save(*a):
            try:
                n = name.text.strip()
                if not n:
                    show_msg("Errore", "Il nome è obbligatorio")
                    return
                qv = float(qty.text.strip() or "0")
                pr = float(price.text.strip() or "0")
                thv = float(thr.text.strip() or "0")
                conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                c.execute("INSERT INTO products (name, qty, unit_price, threshold) VALUES (?,?,?,?)", (n, qv, pr, thv))
                conn.commit(); conn.close()
                popup.dismiss(); self.refresh()
            except sqlite3.IntegrityError:
                show_msg("Errore", "Prodotto con questo nome già esistente")
            except Exception as e:
                show_msg("Errore", str(e))
        save.bind(on_release=do_save); cancel.bind(on_release=popup.dismiss)
        popup.open()

    def open_edit(self, pid):
        try:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT name, qty, unit_price, threshold FROM products WHERE id=?", (pid,))
            r = c.fetchone(); conn.close()
            if not r:
                show_msg("Errore", "Prodotto non trovato"); return
            content = BoxLayout(orientation='vertical', padding=8, spacing=8)
            name = TextInput(text=r[0], multiline=False)
            qty = TextInput(text=str(r[1] or 0), input_filter='float', multiline=False)
            price = TextInput(text=str(r[2] or 0), input_filter='float', multiline=False)
            thr = TextInput(text=str(r[3] or 0), input_filter='float', multiline=False)
            content.add_widget(name); content.add_widget(qty); content.add_widget(price); content.add_widget(thr)
            btns = BoxLayout(size_hint_y=None, height=dp(44), spacing=8)
            upd = Button(text="Aggiorna", background_color=COLOR_GOLD, color=(0,0,0,1))
            cancel = Button(text="Annulla", background_color=(0.7,0.7,0.7,1))
            btns.add_widget(upd); btns.add_widget(cancel)
            content.add_widget(btns)
            popup = Popup(title="Modifica prodotto", content=content, size_hint=(0.95, 0.7))
            def do_upd(*a):
                try:
                    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                    c.execute("UPDATE products SET name=?, qty=?, unit_price=?, threshold=? WHERE id=?", (name.text.strip(), float(qty.text.strip() or "0"), float(price.text.strip() or "0"), float(thr.text.strip() or "0"), pid))
                    conn.commit(); conn.close()
                    popup.dismiss(); self.refresh()
                except sqlite3.IntegrityError:
                    show_msg("Errore", "Nome duplicato")
                except Exception as e:
                    show_msg("Errore", str(e))
            upd.bind(on_release=do_upd); cancel.bind(on_release=popup.dismiss)
            popup.open()
        except Exception as e:
            show_msg("Errore", str(e))

    def confirm_delete(self, pid):
        content = BoxLayout(orientation='vertical', padding=8, spacing=8)
        content.add_widget(Label(text="Confermi eliminazione prodotto?", color=COLOR_TEXT))
        hb = BoxLayout(size_hint_y=None, height=dp(44), spacing=8)
        yes = Button(text="Sì", background_color=COLOR_VIOLET, color=(1,1,1,1))
        no = Button(text="No", background_color=(0.7,0.7,0.7,1))
        hb.add_widget(yes); hb.add_widget(no)
        content.add_widget(hb)
        popup = Popup(title="Conferma", content=content, size_hint=(0.8,0.4))
        def do_delete(*a):
            try:
                conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                c.execute("DELETE FROM products WHERE id=?", (pid,)); conn.commit(); conn.close()
                popup.dismiss(); self.refresh()
            except Exception as e:
                show_msg("Errore", str(e))
        yes.bind(on_release=do_delete); no.bind(on_release=popup.dismiss)
        popup.open()

class Appointments(Screen):
    def on_pre_enter(self):
        self.refresh()

    def refresh(self):
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=8, spacing=8)
        root.add_widget(Label(text="📅 Appuntamenti", font_size="20sp", color=COLOR_VIOLET, size_hint_y=None, height=dp(36)))

        top = BoxLayout(size_hint_y=None, height=dp(44), spacing=8)
        self.search = TextInput(hint_text="Cerca cliente o indirizzo...", multiline=False)
        add = Button(text="➕", size_hint_x=None, width=dp(56), background_color=COLOR_GOLD, color=(0,0,0,1))
        add.bind(on_release=lambda *a: self.open_add())
        top.add_widget(self.search); top.add_widget(add)
        root.add_widget(top)

        scroll = ScrollView()
        grid = GridLayout(cols=1, spacing=8, size_hint_y=None, padding=4)
        grid.bind(minimum_height=grid.setter('height'))

        try:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            q = self.search.text.strip().lower()
            if q:
                c.execute("""SELECT id, client, address, datetime, service, price FROM appointments
                             WHERE lower(client) LIKE ? OR lower(address) LIKE ? ORDER BY datetime(datetime) ASC""", (f"%{q}%", f"%{q}%"))
            else:
                c.execute("SELECT id, client, address, datetime, service, price FROM appointments ORDER BY datetime(datetime) ASC")
            rows = c.fetchall()
            conn.close()
            if not rows:
                grid.add_widget(Label(text="Nessun appuntamento registrato", color=COLOR_TEXT, size_hint_y=None, height=dp(40)))
            else:
                for aid, client, address, dt, service, price in rows:
                    card = BoxLayout(size_hint_y=None, height=dp(82), padding=8, spacing=8)
                    left = BoxLayout(orientation='vertical')
                    dt_display = dt[:16] if isinstance(dt, str) else str(dt)
                    left.add_widget(Label(text=f"👤 {client}  —  {service}", color=COLOR_TEXT))
                    left.add_widget(Label(text=f"📍 {address}", color=(0.25,0.25,0.25,1), font_size='12sp'))
                    left.add_widget(Label(text=f"🕓 {dt_display}   💶 €{(price or 0):.2f}", color=(0.2,0.4,0.6,1), font_size='12sp'))
                    card.add_widget(left)
                    right = BoxLayout(orientation='vertical', size_hint_x=None, width=dp(120), spacing=6)
                    be = Button(text="✏️ Modifica", size_hint_y=None, height=dp(34), background_color=COLOR_VIOLET, color=(1,1,1,1))
                    bd = Button(text="🗑️ Elimina", size_hint_y=None, height=dp(34), background_color=(0.85,0.15,0.15,1), color=(1,1,1,1))
                    be.bind(on_release=lambda btn, aid=aid: self.open_edit(aid))
                    bd.bind(on_release=lambda btn, aid=aid: self.confirm_delete(aid))
                    right.add_widget(be); right.add_widget(bd)
                    card.add_widget(right)
                    grid.add_widget(card)
        except Exception as e:
            grid.add_widget(Label(text="Errore caricamento appuntamenti", color=(1,0,0,1)))

        scroll.add_widget(grid)
        root.add_widget(scroll)
        root.add_widget(Button(text="← Torna", size_hint_y=None, height=dp(44), background_color=COLOR_VIOLET, color=(1,1,1,1), on_release=lambda *a: self.manager.go("dashboard")))
        self.add_widget(root)

    def open_add(self):
        content = BoxLayout(orientation='vertical', padding=8, spacing=8)
        client = TextInput(hint_text="Nome cliente", multiline=False)
        address = TextInput(hint_text="Indirizzo", multiline=False)
        dt = TextInput(hint_text="Data e ora (YYYY-MM-DD HH:MM)", multiline=False)
        service = TextInput(hint_text="Servizio", multiline=False)
        price = TextInput(hint_text="Prezzo (€)", input_filter='float', multiline=False)
        consumption = TextInput(hint_text="Consumo prodotti (es. Shampoo:1,Cera:0.2) - opzionale", multiline=False)
        content.add_widget(client); content.add_widget(address); content.add_widget(dt); content.add_widget(service); content.add_widget(price); content.add_widget(consumption)
        hb = BoxLayout(size_hint_y=None, height=dp(44), spacing=8)
        save = Button(text="Salva", background_color=COLOR_GOLD, color=(0,0,0,1))
        cancel = Button(text="Annulla", background_color=(0.7,0.7,0.7,1))
        hb.add_widget(save); hb.add_widget(cancel)
        content.add_widget(hb)
        popup = Popup(title="Nuovo appuntamento", content=content, size_hint=(0.95, 0.9))
        def do_save(*a):
            try:
                cl = client.text.strip(); ad = address.text.strip(); dt_txt = dt.text.strip(); srv = service.text.strip()
                pr = float(price.text.strip() or "0"); cons = consumption.text.strip() or ""
                if not cl or not dt_txt:
                    show_msg("Errore", "Compila almeno cliente e data/ora"); return
                # validate datetime format
                try:
                    _ = datetime.strptime(dt_txt, "%Y-%m-%d %H:%M")
                except Exception:
                    show_msg("Errore", "Formato data/ora non valido. Usa YYYY-MM-DD HH:MM"); return
                conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                c.execute("INSERT INTO appointments (client, address, datetime, service, price, consumption) VALUES (?,?,?,?,?,?)", (cl, ad, dt_txt, srv, pr, cons))
                conn.commit()
                # apply consumption (reduce inventory) if possible
                if cons:
                    try:
                        parts = [p.strip() for p in cons.split(",") if p.strip()]
                        for part in parts:
                            if ":" in part:
                                pname, pqty = part.split(":",1)
                                pname = pname.strip(); pqty = float(pqty.strip())
                                c.execute("SELECT id, qty FROM products WHERE lower(name)=?", (pname.lower(),))
                                prd = c.fetchone()
                                if prd:
                                    new_q = prd[1] - pqty
                                    c.execute("UPDATE products SET qty=? WHERE id=?", (new_q, prd[0]))
                        conn.commit()
                    except Exception:
                        pass
                conn.close()
                popup.dismiss(); self.refresh()
            except Exception as e:
                show_msg("Errore", str(e))
        save.bind(on_release=do_save); cancel.bind(on_release=popup.dismiss)
        popup.open()

    def open_edit(self, aid):
        try:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT client, address, datetime, service, price, consumption FROM appointments WHERE id=?", (aid,))
            r = c.fetchone(); conn.close()
            if not r:
                show_msg("Errore", "Appuntamento non trovato"); return
            content = BoxLayout(orientation='vertical', padding=8, spacing=8)
            client = TextInput(text=r[0], multiline=False); address = TextInput(text=r[1], multiline=False)
            dt = TextInput(text=r[2], multiline=False); service = TextInput(text=r[3], multiline=False)
            price = TextInput(text=str(r[4] or 0), input_filter='float', multiline=False)
            consumption = TextInput(text=r[5] or "", multiline=False)
            content.add_widget(client); content.add_widget(address); content.add_widget(dt); content.add_widget(service); content.add_widget(price); content.add_widget(consumption)
            hb = BoxLayout(size_hint_y=None, height=dp(44), spacing=8)
            upd = Button(text="Aggiorna", background_color=COLOR_GOLD, color=(0,0,0,1))
            cancel = Button(text="Annulla", background_color=(0.7,0.7,0.7,1))
            hb.add_widget(upd); hb.add_widget(cancel)
            content.add_widget(hb)
            popup = Popup(title="Modifica appuntamento", content=content, size_hint=(0.95, 0.9))
            def do_upd(*a):
                try:
                    cl = client.text.strip(); ad = address.text.strip(); dt_txt = dt.text.strip(); srv = service.text.strip()
                    pr = float(price.text.strip() or "0"); cons = consumption.text.strip() or ""
                    try:
                        _ = datetime.strptime(dt_txt, "%Y-%m-%d %H:%M")
                    except Exception:
                        show_msg("Errore", "Formato data/ora non valido. Usa YYYY-MM-DD HH:MM"); return
                    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                    c.execute("UPDATE appointments SET client=?, address=?, datetime=?, service=?, price=?, consumption=? WHERE id=?", (cl, ad, dt_txt, srv, pr, cons, aid))
                    conn.commit(); conn.close()
                    popup.dismiss(); self.refresh()
                except Exception as e:
                    show_msg("Errore", str(e))
            upd.bind(on_release=do_upd); cancel.bind(on_release=popup.dismiss)
            popup.open()
        except Exception as e:
            show_msg("Errore", str(e))

    def confirm_delete(self, aid):
        content = BoxLayout(orientation='vertical', padding=8, spacing=8)
        content.add_widget(Label(text="Confermi eliminazione appuntamento?", color=COLOR_TEXT))
        hb = BoxLayout(size_hint_y=None, height=dp(44), spacing=8)
        yes = Button(text="Sì", background_color=COLOR_VIOLET, color=(1,1,1,1)); no = Button(text="No", background_color=(0.7,0.7,0.7,1))
        hb.add_widget(yes); hb.add_widget(no)
        content.add_widget(hb)
        popup = Popup(title="Conferma", content=content, size_hint=(0.8,0.4))
        def do_del(*a):
            try:
                conn = sqlite3.connect(DB_PATH); c = conn.cursor()
                c.execute("DELETE FROM appointments WHERE id=?", (aid,)); conn.commit(); conn.close()
                popup.dismiss(); self.refresh()
            except Exception as e:
                show_msg("Errore", str(e))
        yes.bind(on_release=do_del); no.bind(on_release=popup.dismiss)
        popup.open()

class Stats(Screen):
    def on_pre_enter(self):
        self.clear_widgets()
        root = BoxLayout(orientation='vertical', padding=8, spacing=8)
        root.add_widget(Label(text="📊 Statistiche", font_size="20sp", color=COLOR_VIOLET, size_hint_y=None, height=dp(36)))
        try:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT COUNT(*), COALESCE(SUM(price),0) FROM appointments")
            tot_app, tot_inc = c.fetchone()
            tot_app = tot_app or 0; tot_inc = tot_inc or 0.0
            c.execute("SELECT COUNT(*) FROM products")
            tot_prod = c.fetchone()[0] or 0
            c.execute("SELECT service, COUNT(*) as cnt FROM appointments GROUP BY service ORDER BY cnt DESC LIMIT 1")
            top = c.fetchone(); top_service = top[0] if top else "—"
            conn.close()
            root.add_widget(Label(text=f"Totale appuntamenti: {tot_app}", color=COLOR_TEXT))
            root.add_widget(Label(text=f"Incasso totale: €{tot_inc:.2f}", color=COLOR_TEXT))
            root.add_widget(Label(text=f"Prodotti in inventario: {tot_prod}", color=COLOR_TEXT))
            root.add_widget(Label(text=f"Servizio più richiesto: {top_service}", color=COLOR_TEXT))
        except Exception as e:
            root.add_widget(Label(text="Errore lettura statistiche", color=COLOR_TEXT))
        root.add_widget(Button(text="← Torna", size_hint_y=None, height=dp(44), background_color=COLOR_VIOLET, color=(1,1,1,1), on_release=lambda *a: self.manager.go("dashboard")))
        self.add_widget(root)

class Backup(Screen):
    def on_pre_enter(self):
        self.clear_widgets()
        root = BoxLayout(orientation='vertical', padding=8, spacing=8)
        root.add_widget(Label(text="📁 Backup e Ripristino", font_size="20sp", color=COLOR_VIOLET, size_hint_y=None, height=dp(36)))
        root.add_widget(Label(text=f"DB path: {DB_PATH}", color=COLOR_TEXT))
        be = Button(text="Esporta backup JSON (memoria esterna se disponibile)", size_hint_y=None, height=dp(48))
        bi = Button(text="Importa backup JSON (sovrascrivi DB)", size_hint_y=None, height=dp(48))
        be.bind(on_release=lambda *a: self.export_backup()); bi.bind(on_release=lambda *a: self.import_backup())
        root.add_widget(be); root.add_widget(bi)
        root.add_widget(Button(text="← Torna", size_hint_y=None, height=dp(44), background_color=COLOR_VIOLET, color=(1,1,1,1), on_release=lambda *a: self.manager.go("dashboard")))
        self.add_widget(root)

    def export_backup(self):
        target = EXT_BACKUP_PATH if os.path.isdir("/sdcard") else FALLBACK_BACKUP_PATH
        try:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT id, name, qty, unit_price, threshold FROM products")
            prods = [dict(id=r[0], name=r[1], qty=r[2], unit_price=r[3], threshold=r[4]) for r in c.fetchall()]
            c.execute("SELECT id, client, address, datetime, service, price, consumption FROM appointments")
            appts = [dict(id=r[0], client=r[1], address=r[2], datetime=r[3], service=r[4], price=r[5], consumption=r[6]) for r in c.fetchall()]
            conn.close()
            payload = {"exported_at": datetime.now().isoformat(), "products": prods, "appointments": appts}
            with open(target, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            show_msg("Backup", f"Backup salvato in:\n{target}")
        except Exception as e:
            show_msg("Errore backup", str(e))

    def import_backup(self):
        target = EXT_BACKUP_PATH if os.path.exists(EXT_BACKUP_PATH) else FALLBACK_BACKUP_PATH
        if not os.path.exists(target):
            show_msg("Errore", f"File non trovato: {target}")
            return
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("DELETE FROM products"); c.execute("DELETE FROM appointments")
            for p in data.get("products", []):
                c.execute("INSERT INTO products (name, qty, unit_price, threshold) VALUES (?,?,?,?)", (p.get("name"), p.get("qty", 0), p.get("unit_price", 0.0), p.get("threshold", 0)))
            for a in data.get("appointments", []):
                c.execute("INSERT INTO appointments (client, address, datetime, service, price, consumption) VALUES (?,?,?,?,?,?)", (a.get("client"), a.get("address"), a.get("datetime"), a.get("service"), a.get("price", 0.0), a.get("consumption", "")))
            conn.commit(); conn.close()
            show_msg("Import", "Import completato (DB sovrascritto)")
        except Exception as e:
            show_msg("Errore import", str(e))


# ---------------- Screen Manager ----------------
class RootManager(ScreenManager):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.transition = SlideTransition(duration=0.18)

    def go(self, name):
        if name in self.screen_names:
            self.current = name

# ---------------- App ----------------
class CarPlusApp(App):
    title = "CarPlus Manager"
    menu_popup = None

    def build(self):
        # ensure DB structure before building UI
        try:
            ensure_db_and_columns()
        except Exception as e:
            show_msg("Errore DB", str(e))

        rm = RootManager()
        rm.add_widget(Dashboard(name="dashboard"))
        rm.add_widget(Inventory(name="inventory"))
        rm.add_widget(Appointments(name="appointments"))
        rm.add_widget(Stats(name="stats"))
        rm.add_widget(Backup(name="backup"))
        return rm

    def open_menu(self):
        # simple popup menu
        if self.menu_popup and getattr(self.menu_popup, "_window", None):
            self.menu_popup.dismiss(); self.menu_popup = None; return
        box = BoxLayout(orientation='vertical', padding=8, spacing=8)
        b1 = Button(text="Dashboard", size_hint_y=None, height=dp(44))
        b2 = Button(text="Inventario", size_hint_y=None, height=dp(44))
        b3 = Button(text="Appuntamenti", size_hint_y=None, height=dp(44))
        b4 = Button(text="Statistiche", size_hint_y=None, height=dp(44))
        b5 = Button(text="Backup", size_hint_y=None, height=dp(44))
        for b in (b1,b2,b3,b4,b5): box.add_widget(b)
        popup = Popup(title="Menu", content=box, size_hint=(0.75, 0.6))
        b1.bind(on_release=lambda *a: (self.root.go("dashboard"), popup.dismiss()))
        b2.bind(on_release=lambda *a: (self.root.go("inventory"), popup.dismiss()))
        b3.bind(on_release=lambda *a: (self.root.go("appointments"), popup.dismiss()))
        b4.bind(on_release=lambda *a: (self.root.go("stats"), popup.dismiss()))
        b5.bind(on_release=lambda *a: (self.root.go("backup"), popup.dismiss()))
        self.menu_popup = popup
        popup.open()

# ---------------- Run with safety ----------------
if __name__ == "__main__":
    try:
        CarPlusApp().run()
    except Exception:
        tb = traceback.format_exc()
        try:
            show_msg("Errore imprevisto", tb, wide=True)
        except Exception:
            print(tb)
            try:
                input("Premi INVIO per chiudere...")
            except Exception:
                pass