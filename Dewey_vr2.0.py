"""
🐾 Dewey_vr3.0 — PySide6 Edition
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Una mascota virtual que vive en tu escritorio.
Migración completa de tkinter a PySide6.
"""

import sys
import random
import math
import os
import threading
import sqlite3
import logging

# Configurar logging (solo a consola para evitar bloqueos de archivo)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def log_debug(msg):
    print(f"DEBUG: {msg}")
    sys.stdout.flush()

from PySide6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from PySide6.QtCore import Qt, QTimer, QPoint, QSize, Signal, QPropertyAnimation, QEasingCurve, QRectF
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QPolygon, QPen, QBrush, QPainterPath

# Intentar importar librerías para la IA
try:
    import ollama
    import psutil
    IA_DISPONIBLE = True
except ImportError:
    IA_DISPONIBLE = False

# Programas comunes a ignorar para el contexto
APPS_IGNORAR = {
    "System Settings", "Windows Explorer", "Task Manager", "ollama.exe",
    "python.exe", "conhost.exe", "svchost.exe", "runtimebroker.exe",
    "idle", "system", "searchhost.exe"
}

DB_PATH = "dewey_memoria.db"

# ══════════════════════════════════════════════════════════════════
#  BASE DE DATOS: SQLite
# ══════════════════════════════════════════════════════════════════
def iniciar_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS habitos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            aplicacion TEXT,
            estado_mascota TEXT
        )
    ''')
    conn.commit()
    conn.close()

def guardar_habito(app, estado):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO habitos (aplicacion, estado_mascota) VALUES (?, ?)", (app, estado))
        conn.commit()
        conn.close()
    except: pass

def obtener_resumen_habitos():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT aplicacion, COUNT(aplicacion) as freq 
            FROM habitos 
            GROUP BY aplicacion 
            ORDER BY freq DESC LIMIT 3
        ''')
        res = cursor.fetchall()
        conn.close()
        return ", ".join([f"{a} ({f} veces)" for a, f in res])
    except: return "ninguno todavía"

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# ── Imágenes de la mascota por estado ─────────────────────────────
IMAGENES = {
    "normal":   [resource_path("imagenes/Dewey-Base.png"), resource_path("imagenes/Dewey-Jump.png")],
    "feliz":    [resource_path("imagenes/Dewey-Happy.png"), resource_path("imagenes/Dewey-Happy-Jump.png")],
    "hambre":   [resource_path("imagenes/Dewey-Hungry.png"), resource_path("imagenes/Dewey-Hungry.png")],
    "gritando": [resource_path("imagenes/Dewey-Angry.png"), resource_path("imagenes/Dewey-Angry-Jump.png")],
}

MENSAJE_INTERVALO_MIN = 10_000
MENSAJE_INTERVALO_MAX = 20_000
MENSAJE_DURACION      = 6_000
COMIDAS = ["🍎", "🍕", "🍩", "🐟", "🍌", "🧀", "🍗", "🍓"]

CONFIG = {
    "hambre_max":          100,
    "hambre_velocidad":    0.05,
    "hambre_grito":        60,
    "comida_intervalo":    15_000,
    "comida_max":          3,
    "salto_altura":        18,
    "salto_velocidad":     0.15,
    "move_intervalo":      40,
    "nueva_dir_intervalo": 120,
    "pet_size":            140,
    "pet_img_size":        80,
    "comida_size":         40,
}

# ══════════════════════════════════════════════════════════════════
#  GLOBO DE DIÁLOGO (PySide6)
# ══════════════════════════════════════════════════════════════════
class GloboDialogo(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setStyleSheet("background: transparent; border: none;")
        
        self.texto = ""
        self.timer_ocultar = QTimer()
        self.timer_ocultar.timeout.connect(self.hide)
        
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("color: #111111; background: transparent; padding: 12px;")
        self.label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.label.setWordWrap(True)

    def mostrar(self, texto: str, x: int, y: int):
        if not texto or texto.strip() == "": return
        
        # Limpiar texto de basura común de los modelos
        texto = texto.split("\n")[0].strip()
        if len(texto) > 100: texto = texto[:97] + "..."

        self.texto = texto
        self.label.setText(texto)
        
        padding = 35
        max_w = 240
        metrics = self.label.fontMetrics()
        rect = metrics.boundingRect(0, 0, max_w - padding, 1000, Qt.AlignCenter | Qt.TextWordWrap, texto)
        
        tw = max(100, min(rect.width() + padding, max_w))
        th = max(60, rect.height() + padding + 15)
        
        self.resize(tw, th)
        self.label.setGeometry(0, 0, tw, th - 15)
        
        # Reposicionar para que no salga de pantalla
        screen = QApplication.primaryScreen().geometry()
        bx = max(10, min(x - tw // 2, screen.width() - tw - 10))
        by = max(10, min(y - th - 5, screen.height() - th - 50))
        
        self.move(bx, by)
        self.show()
        self.raise_()
        self.update()
        
        self.timer_ocultar.start(MENSAJE_DURACION)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w, h = self.width(), self.height()
        cola_w, cola_h = 16, 14
        radius = 15
        bh = h - cola_h
        
        path = QPainterPath()
        path.addRoundedRect(QRectF(2, 2, w - 4, bh - 4), radius, radius)
        
        # Cola centrada
        cx = w // 2
        path.moveTo(cx - cola_w // 2, bh - 4)
        path.lineTo(cx, h - 2)
        path.lineTo(cx + cola_w // 2, bh - 4)
        path.closeSubpath()
        
        painter.setBrush(QBrush(QColor(255, 253, 231, 255))) 
        painter.setPen(QPen(QColor(100, 100, 100, 200), 2))
        painter.drawPath(path)

    def mover(self, x: int, y: int):
        if self.isVisible():
            screen = QApplication.primaryScreen().geometry()
            bx = max(10, min(x - self.width() // 2, screen.width() - self.width() - 10))
            by = max(10, min(y - self.height() - 5, screen.height() - self.height() - 50))
            self.move(bx, by)


# ══════════════════════════════════════════════════════════════════
#  CLASE: COMIDA (PySide6)
# ══════════════════════════════════════════════════════════════════
class Comida(QWidget):
    def __init__(self, emoji, x, y):
        super().__init__()
        self.emoji = emoji
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setStyleSheet("background: transparent; border: none;")
        self.setAutoFillBackground(False)
        
        size = CONFIG["comida_size"]
        self.resize(size, size)
        self.move(x, y)
        
        self.label = QLabel(emoji, self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setFont(QFont("Arial", 22))
        self.label.setGeometry(0, 0, size, size)
        self.label.setStyleSheet("background: transparent;")
        
        self._drag_pos = None
        self.being_dragged = False
        
        self.setWindowOpacity(0)
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(400)
        self.anim.setStartValue(0)
        self.anim.setEndValue(1)
        self.anim.start()
        self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.being_dragged = True
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.being_dragged = False

    def get_center(self):
        return self.geometry().center()


# ══════════════════════════════════════════════════════════════════
#  CLASE: MASCOTA (PySide6)
# ══════════════════════════════════════════════════════════════════
class Mascota(QWidget):
    NORMAL   = "normal"
    FELIZ    = "feliz"
    HAMBRE   = "hambre"
    GRITANDO = "gritando"

    sig_mostrar_mensaje = Signal(str)

    def __init__(self):
        super().__init__()
        iniciar_db()
        self.sig_mostrar_mensaje.connect(self._on_sig_mostrar_mensaje)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setStyleSheet("background: transparent; border: none;")
        self.setAutoFillBackground(False)
        
        size = CONFIG["pet_size"]
        self.resize(size, size)
        
        self.pet_label = QLabel(self)
        self.pet_label.setAlignment(Qt.AlignCenter)
        self.pet_label.setGeometry(0, 0, size, size)
        self.pet_label.setStyleSheet("background: transparent;")
        
        self._pixmaps = {}
        self._setup_imagenes()
        
        self.globo = GloboDialogo()

        self.hambre         = 0.0
        self.estado         = self.NORMAL
        self._ultimo_estado = self.NORMAL
        self.contexto_apps  = []

        screen = QApplication.primaryScreen().geometry()
        sw, sh = screen.width(), screen.height()
        
        self.x           = float(random.randint(100, sw - 200))
        self.y           = float(random.randint(100, sh - 200))
        self.vx          = random.choice([-1.5, 1.5])
        self.dir_timer   = 0
        self.salto_phase = 0.0
        self.base_y      = self.y

        self.comidas: list[Comida] = []
        self._drag_pos = None
        
        self.timer_mov = QTimer()
        self.timer_mov.timeout.connect(self._loop_movimiento)
        self.timer_mov.start(CONFIG["move_intervalo"])
        
        self.timer_hambre = QTimer()
        self.timer_hambre.timeout.connect(self._loop_hambre)
        self.timer_hambre.start(1000)
        
        self.timer_comida = QTimer()
        self.timer_comida.timeout.connect(self._loop_comida)
        self.timer_comida.start(CONFIG["comida_intervalo"])
        
        self.timer_colision = QTimer()
        self.timer_colision.timeout.connect(self._loop_colision_comida)
        self.timer_colision.start(150)
        
        self.timer_msg = QTimer()
        self.timer_msg.timeout.connect(self._loop_mensaje_random)
        self._programar_siguiente_mensaje()
        
        self.timer_contexto = QTimer()
        self.timer_contexto.timeout.connect(self._loop_contexto_ia)
        self.timer_contexto.start(60_000)
        
        self.move(int(self.x), int(self.y))
        self.show()
        self._loop_contexto_ia()

    def _on_sig_mostrar_mensaje(self, texto):
        self.globo.mostrar(texto, int(self.x + CONFIG["pet_size"] // 2), int(self.y))

    def _setup_imagenes(self):
        img_sz = CONFIG["pet_img_size"]
        for estado, paths in IMAGENES.items():
            self._pixmaps[estado] = []
            for p in paths:
                if os.path.exists(p):
                    pix = QPixmap(p)
                    if not pix.isNull():
                        pix = pix.scaled(img_sz, img_sz, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self._pixmaps[estado].append(pix)
        
        if self._pixmaps.get(self.NORMAL):
            self.pet_label.setPixmap(self._pixmaps[self.NORMAL][0])
        else:
            log_debug("ERROR FATAL: No hay imágenes.")
            sys.exit(1)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        elif event.button() == Qt.RightButton:
            self._cerrar()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_pos:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            self.x = float(new_pos.x())
            self.y = float(new_pos.y())
            self.base_y = self.y
            self.move(new_pos)
            event.accept()

    def _cerrar(self):
        for c in self.comidas: c.close()
        self.globo.close()
        self.close()
        QApplication.quit()

    def _loop_movimiento(self):
        screen = QApplication.primaryScreen().geometry()
        sw, sh = screen.width(), screen.height()
        size = CONFIG["pet_size"]

        self.dir_timer += 1
        if self.dir_timer >= CONFIG["nueva_dir_intervalo"]:
            self.dir_timer = 0
            self.vx = random.uniform(-2.2, 2.2)
            if random.random() < 0.2: self.vx = 0.0

        if self.x <= 0 or self.x >= sw - size: self.vx *= -1
        
        self.base_y = max(30.0, min(self.base_y, float(sh - size - 60)))
        self.x += self.vx
        self.x  = max(0.0, min(self.x, float(sw - size)))

        self.salto_phase += CONFIG["salto_velocidad"]
        self.y = self.base_y - abs(math.sin(self.salto_phase)) * CONFIG["salto_altura"]

        self.move(int(self.x), int(self.y))
        
        imgs = self._pixmaps.get(self.estado, self._pixmaps.get(self.NORMAL))
        if imgs:
            idx = 1 if len(imgs) > 1 and abs(math.sin(self.salto_phase)) > 0.5 else 0
            self.pet_label.setPixmap(imgs[idx])

        self.globo.mover(int(self.x + size // 2), int(self.y))

    def _loop_hambre(self):
        self.hambre = min(CONFIG["hambre_max"], self.hambre + CONFIG["hambre_velocidad"] * 5)
        nuevo = self.NORMAL
        if self.hambre >= CONFIG["hambre_grito"]: nuevo = self.GRITANDO
        elif self.hambre >= CONFIG["hambre_grito"] * 0.7: nuevo = self.HAMBRE
        elif self.estado == self.FELIZ and self.hambre < 10: nuevo = self.FELIZ

        if nuevo != self._ultimo_estado and nuevo in (self.HAMBRE, self.GRITANDO):
            def reaccionar():
                ev = "tengo mucha hambre" if nuevo == self.GRITANDO else "quiero comer"
                self.sig_mostrar_mensaje.emit(self.ia_pensar(contexto_especial=ev))
            threading.Thread(target=reaccionar, daemon=True).start()

        self._ultimo_estado = nuevo
        self.estado = nuevo

    def _loop_comida(self):
        if len(self.comidas) < CONFIG["comida_max"]:
            screen = QApplication.primaryScreen().geometry()
            x = random.randint(100, screen.width() - 150)
            y = random.randint(100, screen.height() - 150)
            self.comidas.append(Comida(random.choice(COMIDAS), x, y))

    def _on_eaten(self, comida):
        self.hambre = max(0.0, self.hambre - 45)
        self.estado = self.FELIZ
        self._ultimo_estado = self.FELIZ
        if comida in self.comidas: self.comidas.remove(comida)
        comida.close()
        def reaccionar():
            self.sig_mostrar_mensaje.emit(self.ia_pensar(contexto_especial="comí algo rico"))
        threading.Thread(target=reaccionar, daemon=True).start()

    def _loop_colision_comida(self):
        px, py = self.x + 70, self.y + 70
        for comida in list(self.comidas):
            c = comida.get_center()
            dist = math.hypot(px - c.x(), py - c.y())
            if (comida.being_dragged and dist < 60) or (not comida.being_dragged and dist < 45):
                self._on_eaten(comida); break

    def _loop_mensaje_random(self):
        if self.estado == self.NORMAL:
            def pensar():
                txt = self.ia_pensar()
                if txt: self.sig_mostrar_mensaje.emit(txt)
            threading.Thread(target=pensar, daemon=True).start()
        self._programar_siguiente_mensaje()

    def _programar_siguiente_mensaje(self):
        self.timer_msg.start(random.randint(MENSAJE_INTERVALO_MIN, MENSAJE_INTERVALO_MAX))

    def _loop_contexto_ia(self):
        if not IA_DISPONIBLE: return
        def scan():
            try:
                apps = {p.info['name'].replace(".exe", "").capitalize() for p in psutil.process_iter(['name']) 
                        if p.info['name'].lower() not in APPS_IGNORAR and not p.info['name'].lower().startswith("service")}
                self.contexto_apps = list(apps)[:8]
                if self.contexto_apps: guardar_habito(self.contexto_apps[0], self.estado)
            except: pass
        threading.Thread(target=scan, daemon=True).start()

    def ia_pensar(self, contexto_especial=None):
        if not IA_DISPONIBLE: return "¡Hola!"
        ctx_apps = ", ".join(self.contexto_apps) if self.contexto_apps else "nada"
        try:
            res = ollama.chat(model='qwen2.5:1.5b', messages=[
                {'role': 'system', 'content': 'Eres Dewey, una mascota virtual, muy curioso, pregunton y siempre dispuesto a ayudar. Habla en ESPAÑOL. Responde con UNA frase muy corta (max 8 palabras) como una mascota curiosa. NO repitas instrucciones.'},
                {'role': 'user', 'content': f'Apps: {ctx_apps}. Estado: {self.estado}. Evento: {contexto_especial if contexto_especial else "ninguno"}'}
            ], options={"temperature": 0.8, "num_predict": 20})
            return res['message']['content'].strip().replace('"', '')
        except: return "¡Miau!"

if __name__ == "__main__":
    app = QApplication(sys.argv)
    mascota = Mascota()
    sys.exit(app.exec())
