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

from PySide6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from PySide6.QtCore import Qt, QTimer, QPoint, QSize, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QPolygon, QPen, QBrush

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
    """
    Obtiene la ruta absoluta del recurso,
    compatible con PyInstaller.
    """
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

# ── Frecuencia de mensajes random ─────────────────────────────────
MENSAJE_INTERVALO_MIN = 8_000
MENSAJE_INTERVALO_MAX = 15_000
MENSAJE_DURACION      = 6_000

# ── Comidas disponibles ────────────────────────────────────────────
COMIDAS = ["🍎", "🍕", "🍩", "🐟", "🍌", "🧀", "🍗", "🍓"]

# ── CONFIGURACIÓN TÉCNICA ──────────────────────────────────────────
CONFIG = {
    "hambre_max":          100,
    "hambre_velocidad":    0.05,
    "hambre_grito":        60,
    "comida_intervalo":    13_000,
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
        
        self.texto = ""
        self.timer_ocultar = QTimer()
        self.timer_ocultar.timeout.connect(self.hide)
        
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("color: #222222; background: transparent; padding: 10px;")
        self.label.setFont(QFont("Segoe UI", 10))
        self.label.setWordWrap(True)

    def mostrar(self, texto: str, x: int, y: int):
        self.texto = texto
        self.label.setText(texto)
        
        # Calcular tamaño
        padding = 24
        max_w = 220
        metrics = self.label.fontMetrics()
        rect = metrics.boundingRect(0, 0, max_w - padding, 1000, Qt.AlignCenter | Qt.TextWordWrap, texto)
        
        tw = min(rect.width() + padding, max_w)
        th = rect.height() + padding + 15
        
        self.resize(tw, th)
        self.label.setGeometry(0, 0, tw, th - 10)
        
        bx = x - tw // 2
        by = y - th - 4
        self.move(bx, by)
        self.show()
        
        self.timer_ocultar.start(MENSAJE_DURACION)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w, h = self.width(), self.height()
        cola_w, cola_h = 12, 10
        bh = h - cola_h
        
        # Dibujar burbuja
        path = [
            QPoint(12, 0), QPoint(w - 12, 0),
            QPoint(w, 12), QPoint(w, bh - 12),
            QPoint(w, bh), QPoint(w // 2 + cola_w, bh),
            QPoint(w // 2, h),
            QPoint(w // 2 - cola_w, bh),
            QPoint(0, bh), QPoint(0, 12)
        ]
        
        poly = QPolygon(path)
        painter.setBrush(QBrush(QColor("#FFFDE7")))
        painter.setPen(QPen(QColor("#BDBDBD"), 1.5))
        painter.drawPolygon(poly)

    def mover(self, x: int, y: int):
        if self.isVisible():
            bx = x - self.width() // 2
            by = y - self.height() - 4
            self.move(bx, by)


# ══════════════════════════════════════════════════════════════════
#  CLASE: COMIDA (PySide6)
# ══════════════════════════════════════════════════════════════════
class Comida(QWidget):
    eaten = Signal(object)

    def __init__(self, emoji, x, y):
        super().__init__()
        self.emoji = emoji
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        size = CONFIG["comida_size"]
        self.resize(size, size)
        self.move(x, y)
        
        self.label = QLabel(emoji, self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setFont(QFont("Arial", 22))
        self.label.setGeometry(0, 0, size, size)
        
        self._drag_pos = None
        self.being_dragged = False
        
        # Animación aparecer
        self.setWindowOpacity(0)
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(300)
        self.anim.setStartValue(0)
        self.anim.setEndValue(1)
        self.anim.start()
        
        self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            self.being_dragged = True
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_pos:
            self.move(event.globalPos() - self._drag_pos)
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

    def __init__(self):
        super().__init__()
        iniciar_db()
        
        # ── Ventana mascota ───────────────────────
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        size = CONFIG["pet_size"]
        self.resize(size, size)
        
        self.pet_label = QLabel(self)
        self.pet_label.setAlignment(Qt.AlignCenter)
        self.pet_label.setGeometry(0, 0, size, size)
        
        self._pixmaps = {}
        self._setup_imagenes()
        
        # ── Globo de diálogo ──────────────────────
        self.globo = GloboDialogo()

        # ── Estado ───────────────────────────────
        self.hambre         = 0.0
        self.estado         = self.NORMAL
        self._ultimo_estado = self.NORMAL
        self.contexto_apps  = []

        # ── Movimiento ────────────────────────────
        screen = QApplication.primaryScreen().geometry()
        sw, sh = screen.width(), screen.height()
        
        self.x           = float(random.randint(100, sw - 200))
        self.y           = float(random.randint(100, sh - 200))
        self.vx          = random.choice([-1.5, 1.5])
        self.dir_timer   = 0
        self.salto_phase = 0.0
        self.base_y      = self.y

        # ── Comidas ───────────────────────────────
        self.comidas: list[Comida] = []

        # ── Drag mascota ──────────────────────────
        self._drag_pos = None
        
        # ── Timers ────────────────────────────────
        self.timer_mov = QTimer()
        self.timer_mov.timeout.connect(self._loop_movimiento)
        self.timer_mov.start(CONFIG["move_intervalo"])
        
        self.timer_hambre = QTimer()
        self.timer_hambre.timeout.connect(self._loop_hambre)
        self.timer_hambre.start(200)
        
        self.timer_comida = QTimer()
        self.timer_comida.timeout.connect(self._loop_comida)
        self.timer_comida.start(CONFIG["comida_intervalo"])
        
        self.timer_colision = QTimer()
        self.timer_colision.timeout.connect(self._loop_colision_comida)
        self.timer_colision.start(100)
        
        self.timer_msg = QTimer()
        self.timer_msg.timeout.connect(self._loop_mensaje_random)
        self._programar_siguiente_mensaje()
        
        self.timer_contexto = QTimer()
        self.timer_contexto.timeout.connect(self._loop_contexto_ia)
        self.timer_contexto.start(60_000)
        
        self.move(int(self.x), int(self.y))
        self.show()
        
        # Primera ejecución
        self._loop_contexto_ia()

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
            print("❌ Error: No se pudo cargar la imagen inicial.")
            sys.exit(1)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
        elif event.button() == Qt.RightButton:
            self._cerrar()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_pos:
            new_pos = event.globalPos() - self._drag_pos
            self.x = float(new_pos.x())
            self.y = float(new_pos.y())
            self.base_y = self.y
            self.move(new_pos)
            event.accept()

    def _cerrar(self):
        for c in self.comidas:
            c.close()
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
            self.vx = random.uniform(-2.5, 2.5)
            if random.random() < 0.15:
                self.vx = 0.0

        if self.x <= 0 or self.x >= sw - size:
            self.vx *= -1
        
        self.base_y = max(30.0, min(self.base_y, float(sh - size - 50)))
        self.x += self.vx
        self.x  = max(0.0, min(self.x, float(sw - size)))

        self.salto_phase += CONFIG["salto_velocidad"]
        self.y = self.base_y - abs(math.sin(self.salto_phase)) * CONFIG["salto_altura"]

        self.move(int(self.x), int(self.y))
        
        # Actualizar apariencia
        imgs = self._pixmaps.get(self.estado, self._pixmaps.get(self.NORMAL))
        if imgs:
            idx = 1 if len(imgs) > 1 and abs(math.sin(self.salto_phase)) > 0.5 else 0
            self.pet_label.setPixmap(imgs[idx])

        # Mover globo
        cx = int(self.x + size // 2)
        self.globo.mover(cx, int(self.y))

    def _loop_hambre(self):
        self.hambre = min(CONFIG["hambre_max"], self.hambre + CONFIG["hambre_velocidad"])

        if self.hambre >= CONFIG["hambre_grito"]:
            nuevo = self.GRITANDO
        elif self.hambre >= CONFIG["hambre_grito"] * 0.7:
            nuevo = self.HAMBRE
        elif self.estado != self.FELIZ:
            nuevo = self.NORMAL
        else:
            nuevo = self.estado

        if self.estado == self.FELIZ and self.hambre > 5:
            nuevo = self.NORMAL

        if nuevo != self._ultimo_estado and nuevo in (self.HAMBRE, self.GRITANDO):
            def reaccionar_hambre():
                ev = "Tengo mucha hambre" if nuevo == self.GRITANDO else "Empiezo a tener hambre"
                texto = self.ia_pensar(contexto_especial=ev)
                self._mostrar_mensaje_seguro(texto)
            threading.Thread(target=reaccionar_hambre, daemon=True).start()

        self._ultimo_estado = nuevo
        self.estado = nuevo

    def _loop_comida(self):
        if len(self.comidas) < CONFIG["comida_max"]:
            screen = QApplication.primaryScreen().geometry()
            sw, sh = screen.width(), screen.height()
            x = random.randint(50, sw - 100)
            y = random.randint(50, sh - 100)
            self.comidas.append(Comida(random.choice(COMIDAS), x, y))

    def _on_eaten(self, comida):
        self.hambre = max(0.0, self.hambre - 40)
        self.estado = self.FELIZ
        self._ultimo_estado = self.FELIZ
        if comida in self.comidas:
            self.comidas.remove(comida)
        comida.close()

        def reaccionar_comida():
            texto = self.ia_pensar(contexto_especial="Acabo de comer algo delicioso")
            self._mostrar_mensaje_seguro(texto)
        threading.Thread(target=reaccionar_comida, daemon=True).start()

    def _loop_colision_comida(self):
        px = self.x + CONFIG["pet_size"] // 2
        py = self.y + CONFIG["pet_size"] // 2
        
        for comida in list(self.comidas):
            c_center = comida.get_center()
            cx, cy = c_center.x(), c_center.y()
            dist = math.hypot(px - cx, py - cy)
            
            if comida.being_dragged and dist < 55:
                self._on_eaten(comida); break
            elif not comida.being_dragged and dist < 40:
                self._on_eaten(comida); break

    def _loop_mensaje_random(self):
        if self.estado == self.NORMAL:
            def pensar_y_mostrar():
                texto = self.ia_pensar()
                if texto:
                    self._mostrar_mensaje_seguro(texto)
            threading.Thread(target=pensar_y_mostrar, daemon=True).start()
        
        self._programar_siguiente_mensaje()

    def _programar_siguiente_mensaje(self):
        siguiente = random.randint(MENSAJE_INTERVALO_MIN, MENSAJE_INTERVALO_MAX)
        self.timer_msg.start(siguiente)

    def _mostrar_mensaje_seguro(self, texto):
        # QTimer.singleShot para ejecutar en el hilo principal
        QTimer.singleShot(0, lambda: self.globo.mostrar(texto, int(self.x + CONFIG["pet_size"] // 2), int(self.y)))

    def _loop_contexto_ia(self):
        if IA_DISPONIBLE:
            def scan():
                apps = set()
                try:
                    for proc in psutil.process_iter(['name']):
                        name = proc.info['name'].lower()
                        if name not in APPS_IGNORAR and not name.startswith("service"):
                            apps.add(name.replace(".exe", "").capitalize())
                    self.contexto_apps = list(apps)[:10]
                    if self.contexto_apps:
                        guardar_habito(self.contexto_apps[0], self.estado)
                except: pass
            threading.Thread(target=scan, daemon=True).start()

    def ia_pensar(self, contexto_especial=None):
        if not IA_DISPONIBLE:
            return "..."
        
        ctx_apps = ", ".join(self.contexto_apps) if self.contexto_apps else "nada especial"
        habitos = obtener_resumen_habitos()
        
        emocion_ia = "CURIOSO" 
        if self.estado == self.FELIZ: emocion_ia = "FELIZ"
        if self.estado in (self.HAMBRE, self.GRITANDO): emocion_ia = "HAMBRE"
        
        instrucciones_identidad = (
            "Tu nombre es Dewey. Eres una criatura digital curiosa, inteligente y juguetona. "
            "Estilo: Natural, espontáneo, ultra corto (máximo 12 palabras). "
            "NUNCA digas 'Como modelo de lenguaje'."
        )

        user_prompt = f"Humor: {emocion_ia}. Apps: {ctx_apps}."
        if contexto_especial:
            user_prompt = f"EVENTO: {contexto_especial}. " + user_prompt

        prompt = f"{instrucciones_identidad}\nContexto: {user_prompt}\nDewey dice:"
        
        try:
            res = ollama.generate(model='tinyllama', prompt=prompt, options={"num_predict": 45, "temperature": 0.9, "stop": ["\n", "Dewey:"]})
            return res['response'].strip().replace('"', '')
        except:
            return "¡Hola!"

if __name__ == "__main__":
    app = QApplication(sys.argv)
    mascota = Mascota()
    sys.exit(app.exec())
