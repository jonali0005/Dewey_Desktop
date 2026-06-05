"""
🐾 Dewey_vr2.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Una mascota virtual que vive en tu escritorio.
Soporta imágenes PNG personalizadas y mensajes aleatorios.

Requisitos:
  pip install pillow

Ejecutar:
  python Dewey_vr2.0.py
"""

import tkinter as tk
import random
import math
import os

import sys
import threading
import sqlite3

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
        #base_path = os.path.abspath(".")
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)


# Pillow es obligatorio para usar imágenes PNG
try:
    from PIL import Image, ImageTk
except ImportError:
    print("❌ Error: Pillow no encontrado. Es obligatorio para esta versión.")
    print("   Instálalo con: pip install pillow\n")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════
#  🎨  PERSONALIZACIÓN  ← Edita aquí todo lo que quieras cambiar
# ══════════════════════════════════════════════════════════════════

# ── Imágenes de la mascota por estado ─────────────────────────────
# Pon la ruta a tus PNG sin fondo.
# Formato: [Imagen_Normal, Imagen_Salto]
IMAGENES = {
    "normal":   [resource_path("imagenes/Dewey-Base.png"), resource_path("imagenes/Dewey-Jump.png")],
    "feliz":    [resource_path("imagenes/Dewey-Happy.png"), resource_path("imagenes/Dewey-Happy-Jump.png")],
    "hambre":   [resource_path("imagenes/Dewey-Hungry.png"), resource_path("imagenes/Dewey-Hungry.png")],
    "gritando": [resource_path("imagenes/Dewey-Angry.png"), resource_path("imagenes/Dewey-Angry-Jump.png")],
}

# ── Frecuencia de mensajes random ─────────────────────────────────
MENSAJE_INTERVALO_MIN = 8_000    # ms mínimo entre mensajes (8 seg)
MENSAJE_INTERVALO_MAX = 15_000   # ms máximo entre mensajes (15 seg)
MENSAJE_DURACION      = 6_000    # ms que permanece visible el mensaje

# ── Comidas disponibles ────────────────────────────────────────────
COMIDAS = ["🍎", "🍕", "🍩", "🐟", "🍌", "🧀", "🍗", "🍓"]

# ══════════════════════════════════════════════════════════════════
#  ⚙️  CONFIGURACIÓN TÉCNICA
# ══════════════════════════════════════════════════════════════════
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
#  UTILIDADES
# ══════════════════════════════════════════════════════════════════
def cargar_imagen(path: str, size: int):
    """
    Carga un PNG con transparencia y lo convierte a PhotoImage.
    """
    if not path:
        return None
    ruta = os.path.abspath(path)
    if not os.path.isfile(ruta):
        print(f"⚠  Imagen no encontrada: {ruta}")
        return None
    try:
        img = Image.open(ruta).convert("RGBA")
        img = img.resize((size, size), Image.NEAREST)
        return ImageTk.PhotoImage(img)
    except Exception as e:
        print(f"⚠  Error cargando imagen '{ruta}': {e}")
        return None


# ══════════════════════════════════════════════════════════════════
#  GLOBO DE DIÁLOGO
# ══════════════════════════════════════════════════════════════════
class GloboDialogo:
    """Ventana flotante que muestra un mensaje encima de la mascota."""

    def __init__(self, root):
        self.root = root
        self.win = None
        self._ocultar_id = None

    def mostrar(self, texto: str, x: int, y: int):
        self._cancelar_ocultar()
        if self.win:
            try:
                self.win.destroy()
            except Exception:
                pass

        self.win = tk.Toplevel(self.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.config(bg="white")
        try:
            self.win.attributes("-transparentcolor", "white")
        except Exception:
            pass

        c = tk.Canvas(self.win, bg="white", highlightthickness=0)
        c.pack()

        PADDING = 12
        MAX_W   = 220
        # Medir texto
        lbl = tk.Label(self.root, text=texto, font=("Segoe UI", 10),
                       wraplength=MAX_W - PADDING * 2)
        lbl.update_idletasks()
        tw = min(lbl.winfo_reqwidth() + PADDING * 2, MAX_W)
        th = lbl.winfo_reqheight() + PADDING * 2 + 10
        lbl.destroy()

        self._dibujar_burbuja(c, tw, th)
        c.config(width=tw, height=th)
        c.create_text(tw // 2, (th - 10) // 2, text=texto,
                      font=("Segoe UI", 10), fill="#222222",
                      width=tw - PADDING * 2, justify="center")

        bx = x - tw // 2
        by = y - th - 4
        self.win.geometry(f"+{bx}+{by}")
        self._ocultar_id = self.root.after(MENSAJE_DURACION, self.ocultar)

    def _dibujar_burbuja(self, c, w, h):
        cola_w, cola_h = 12, 10
        bh = h - cola_h
        puntos = [
            12, 0,  w - 12, 0,
            w,  12, w, bh - 12,
            w,  bh, w // 2 + cola_w, bh,
            w // 2, h,
            w // 2 - cola_w, bh,
            0, bh,  0, 12,
        ]
        c.create_polygon(puntos, fill="#FFFDE7", outline="#BDBDBD",
                         smooth=False, width=1.5)

    def ocultar(self):
        self._cancelar_ocultar()
        if self.win:
            try:
                self.win.destroy()
            except Exception:
                pass
            self.win = None

    def _cancelar_ocultar(self):
        if self._ocultar_id:
            try:
                self.root.after_cancel(self._ocultar_id)
            except Exception:
                pass
            self._ocultar_id = None

    def mover(self, x: int, y: int):
        if self.win:
            try:
                tw = self.win.winfo_width()
                th = self.win.winfo_height()
                self.win.geometry(f"+{x - tw // 2}+{y - th - 4}")
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════
#  CLASE: COMIDA
# ══════════════════════════════════════════════════════════════════
class Comida:
    def __init__(self, root, emoji, x, y, on_eaten):
        self.root = root
        self.emoji = emoji
        self.on_eaten = on_eaten
        self._drag_offset = (0, 0)
        self._being_dragged = False

        size = CONFIG["comida_size"]
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.config(bg="white")
        try:
            self.win.attributes("-transparentcolor", "white")
        except Exception:
            pass

        self.canvas = tk.Canvas(self.win, width=size, height=size,
                                bg="white", highlightthickness=0)
        self.canvas.pack()
        self.label = self.canvas.create_text(size // 2, size // 2,
                                             text=emoji, font=("Arial", 22))
        self.win.geometry(f"{size}x{size}+{x}+{y}")

        self.canvas.bind("<ButtonPress-1>",   self._drag_start)
        self.canvas.bind("<B1-Motion>",       self._drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._drag_end)

        self._appear_scale = 0.3
        self._animate_appear()

    def _animate_appear(self):
        if self._appear_scale < 1.0:
            self._appear_scale = min(1.0, self._appear_scale + 0.1)
            s = max(1, int(CONFIG["comida_size"] * self._appear_scale))
            try:
                self.canvas.config(width=s, height=s)
                self.canvas.coords(self.label, s // 2, s // 2)
                self.root.after(20, self._animate_appear)
            except (tk.TclError, AttributeError):
                pass

    def _drag_start(self, e):
        self._drag_offset = (e.x, e.y)
        self._being_dragged = True

    def _drag_motion(self, e):
        nx = self.win.winfo_x() + e.x - self._drag_offset[0]
        ny = self.win.winfo_y() + e.y - self._drag_offset[1]
        self.win.geometry(f"+{nx}+{ny}")

    def _drag_end(self, e):
        self._being_dragged = False

    def get_center(self):
        return (self.win.winfo_x() + CONFIG["comida_size"] // 2,
                self.win.winfo_y() + CONFIG["comida_size"] // 2)

    def destroy(self):
        try:
            self.win.destroy()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════
#  CLASE: MASCOTA
# ══════════════════════════════════════════════════════════════════
class Mascota:
    NORMAL   = "normal"
    FELIZ    = "feliz"
    HAMBRE   = "hambre"
    GRITANDO = "gritando"

    def __init__(self):
        iniciar_db()
        self.root = tk.Tk()
        self.root.withdraw()

        # ── Ventana mascota ───────────────────────
        self.win = tk.Toplevel(self.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.config(bg="white")
        try:
            self.win.attributes("-transparentcolor", "white")
        except Exception:
            pass

        size = CONFIG["pet_size"]
        self.canvas = tk.Canvas(self.win, width=size, height=size,
                                bg="white", highlightthickness=0)
        self.canvas.pack()

        self.pet_img_item  = None
        self.pet_text_item = None
        self._tk_images    = {}
        self._setup_imagenes()

        # ── Globo de diálogo ──────────────────────
        self.globo = GloboDialogo(self.root)

        # ── Estado ───────────────────────────────
        self.hambre         = 0.0
        self.estado         = self.NORMAL
        self._ultimo_estado = self.NORMAL
        self.contexto_apps  = []

        # ── Movimiento ────────────────────────────
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.x           = float(random.randint(100, sw - 200))
        self.y           = float(random.randint(100, sh - 200))
        self.vx          = random.choice([-1.5, 1.5])
        self.dir_timer   = 0
        self.salto_phase = 0.0
        self.base_y      = self.y

        # ── Comidas ───────────────────────────────
        self.comidas: list[Comida] = []

        # ── Drag mascota ──────────────────────────
        self._drag_offset = (0, 0)
        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>",     self._drag_motion)
        #self.canvas.bind("<Button-3>", self._cerrar)
        self.canvas.bind("<Button-3>", self._cerrar)
        self.win.bind("<Button-3>", self._cerrar)

        # ── Arrancar loops ────────────────────────
        self._posicionar()
        self._loop_movimiento()
        self._loop_hambre()
        self._loop_comida()
        self._loop_colision_comida()
        self._loop_mensaje_random()
        self._loop_contexto_ia()

        self.root.mainloop()

    # ─────────────────────────────────────────
    def _loop_contexto_ia(self):
        """Actualiza la lista de programas y guarda en la base de datos."""
        if IA_DISPONIBLE:
            def scan():
                apps = set()
                try:
                    for proc in psutil.process_iter(['name']):
                        name = proc.info['name'].lower()
                        if name not in APPS_IGNORAR and not name.startswith("service"):
                            apps.add(name.replace(".exe", "").capitalize())
                    self.contexto_apps = list(apps)[:10]
                    
                    # Guardar hábito (la app principal)
                    if self.contexto_apps:
                        guardar_habito(self.contexto_apps[0], self.estado)
                except: pass
            
            threading.Thread(target=scan, daemon=True).start()
        
        self.root.after(60_000, self._loop_contexto_ia) # Escanear cada minuto

    def ia_pensar(self, contexto_especial=None):
        """Genera un pensamiento con la personalidad definitiva de Dewey."""
        if not IA_DISPONIBLE:
            return "..."
        
        ctx_apps = ", ".join(self.contexto_apps) if self.contexto_apps else "nada especial"
        habitos = obtener_resumen_habitos()
        
        # Mapeo extendido de emociones solicitado por el usuario
        DESC_EMOCIONES = {
            "FELIZ":       "Alegre y optimista, celebra logros.",
            "EMOCIONADO":  "Mucha energía y exclamaciones.",
            "CURIOSO":     "Hace preguntas sobre lo que ve.",
            "SORPRENDIDO": "Reacciona de forma expresiva.",
            "ORGULLOSO":   "Felicita al usuario.",
            "JUGUETON":    "Hace bromas y comentarios divertidos.",
            "CONCENTRADO": "Habla poco, observa con atención.",
            "PREOCUPADO":  "Quiere ayudar con los errores.",
            "ABURRIDO":    "Busca interacción interesante.",
            "SOMNOLIENTO": "Tranquilo y calmado.",
            "CONFUNDIDO":  "Busca aclaraciones, se perdió.",
            "HAMBRE":      "Dramático y sarcástico por comida.",
        }

        # Determinar emoción actual para la IA (puedes ampliar la lógica de estados luego)
        emocion_ia = "CURIOSO" 
        if self.estado == self.FELIZ: emocion_ia = "FELIZ"
        if self.estado in (self.HAMBRE, self.GRITANDO): emocion_ia = "HAMBRE"
        
        instrucciones_identidad = (
            "Tu nombre es Dewey. Eres una criatura digital curiosa, inteligente y juguetona. "
            "No eres una IA corporativa. Eres una MASCOTA VIVA que acompaña al usuario. "
            "Tu estilo: Natural, espontáneo, ultra corto (máximo 12 palabras), expresivo. "
            "Usa ocasionalmente: ¡Oh!, Jeje, Hmm..., ¡Qué interesante! "
            "REGLAS: Español, habla sobre lo que ocurre en pantalla, da consejos útiles pero divertidos. "
            "NUNCA digas 'Como modelo de lenguaje'."
        )

        if contexto_especial:
            user_prompt = f"EVENTO: {contexto_especial}. Humor: {emocion_ia}. Apps: {ctx_apps}."
        else:
            user_prompt = f"Humor: {emocion_ia} ({DESC_EMOCIONES.get(emocion_ia)}). Apps ahora: {ctx_apps}. Memoria: {habitos}."

        prompt = (
            f"{instrucciones_identidad}\n"
            f"Contexto actual: {user_prompt}\n"
            "Dewey dice:"
        )
        
        try:
            res = ollama.generate(
                model='tinyllama', 
                prompt=prompt, 
                options={
                    "num_predict": 45, 
                    "temperature": 0.9,
                    "stop": ["\n", "Dewey:", "Usuario:", "Contexto:", "Evento:"]
                }
            )
            pensamiento = res['response'].strip().replace('"', '')
            if ":" in pensamiento: pensamiento = pensamiento.split(":")[-1].strip()
            
            print(f"🧠 Dewey [{emocion_ia}] dice: {pensamiento}")
            return pensamiento if pensamiento else "¡Hola!"
        except:
            return "¡Oh! ¿Qué estamos haciendo?"

    # ─────────────────────────────────────────
    def _setup_imagenes(self):
        size   = CONFIG["pet_size"]
        img_sz = CONFIG["pet_img_size"]
        cx, cy = size // 2, size // 2

        for estado, paths in IMAGENES.items():
            self._tk_images[estado] = []
            for p in paths:
                img = cargar_imagen(p, img_sz)
                if img:
                    self._tk_images[estado].append(img)

        if self._tk_images.get(self.NORMAL):
            img_inicial = self._tk_images[self.NORMAL][0]
            self.pet_img_item = self.canvas.create_image(
                cx, cy, image=img_inicial, anchor="center")
        else:
            print("❌ Error: No se pudo cargar la imagen inicial (normal).")
            sys.exit(1)

    def _usar_imagenes(self):
        return any(len(imgs) > 0 for imgs in self._tk_images.values())

    # ─────────────────────────────────────────
    def _drag_start(self, e):
        self._drag_offset = (e.x, e.y)

    def _drag_motion(self, e):
        nx = self.win.winfo_x() + e.x - self._drag_offset[0]
        ny = self.win.winfo_y() + e.y - self._drag_offset[1]
        self.x = float(nx)
        self.y = float(ny)
        self.base_y = self.y
        self._posicionar()

    def _cerrar(self, event=None):
   
        try:
        # Destruir comidas
            for comida in self.comidas:
                comida.destroy()

        # Destruir globo de diálogo
            self.globo.ocultar()

        # Destruir ventana mascota
            self.win.destroy()

        # Cerrar aplicación
            self.root.quit()
            self.root.destroy()

        except Exception as e:
            print("Error al cerrar:", e)

    def _posicionar(self):
        self.win.geometry(f"+{int(self.x)}+{int(self.y)}")

    def _centro_pantalla(self):
        s = CONFIG["pet_size"]
        return int(self.x + s // 2), int(self.y + s // 2)

    # ─────────────────────────────────────────
    def _loop_movimiento(self):
        sw   = self.root.winfo_screenwidth()
        sh   = self.root.winfo_screenheight()
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

        self._posicionar()
        self._actualizar_apariencia()

        cx, cy = self._centro_pantalla()
        self.globo.mover(cx, int(self.y))

        self.root.after(CONFIG["move_intervalo"], self._loop_movimiento)

    def _actualizar_apariencia(self):
        imgs = self._tk_images.get(self.estado, self._tk_images.get(self.NORMAL))
        if imgs and self.pet_img_item:
            # Si está saltando (fase alta del seno), usar imagen de salto si existe
            idx = 1 if len(imgs) > 1 and abs(math.sin(self.salto_phase)) > 0.5 else 0
            self.canvas.itemconfig(self.pet_img_item, image=imgs[idx])

    # ─────────────────────────────────────────
    def _loop_hambre(self):
        self.hambre = min(CONFIG["hambre_max"],
                          self.hambre + CONFIG["hambre_velocidad"])

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

        # Reacción IA al cambiar a estado de hambre
        if nuevo != self._ultimo_estado and nuevo in (self.HAMBRE, self.GRITANDO):
            def reaccionar_hambre():
                ev = "Tengo mucha hambre" if nuevo == self.GRITANDO else "Empiezo a tener hambre"
                texto = self.ia_pensar(contexto_especial=ev)
                cx, cy = self._centro_pantalla()
                self.root.after(0, lambda: self.globo.mostrar(texto, cx, int(self.y)))
            
            threading.Thread(target=reaccionar_hambre, daemon=True).start()

        self._ultimo_estado = nuevo
        self.estado = nuevo
        self.root.after(200, self._loop_hambre)

    # ─────────────────────────────────────────
    def _loop_comida(self):
        if len(self.comidas) < CONFIG["comida_max"]:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            x = random.randint(50, sw - 100)
            y = random.randint(50, sh - 100)
            self.comidas.append(
                Comida(self.root, random.choice(COMIDAS), x, y, self._on_eaten))
        self.root.after(CONFIG["comida_intervalo"], self._loop_comida)

    def _on_eaten(self, comida):
        self.hambre = max(0.0, self.hambre - 40)
        self.estado = self.FELIZ
        self._ultimo_estado = self.FELIZ
        if comida in self.comidas:
            self.comidas.remove(comida)
        comida.destroy()

        def reaccionar_comida():
            texto = self.ia_pensar(contexto_especial="Acabo de comer algo delicioso")
            cx, cy = self._centro_pantalla()
            self.root.after(0, lambda: self.globo.mostrar(texto, cx, int(self.y)))
        
        threading.Thread(target=reaccionar_comida, daemon=True).start()

    # ─────────────────────────────────────────
    def _loop_colision_comida(self):
        px, py = self._centro_pantalla()
        for comida in list(self.comidas):
            try:
                cx, cy = comida.get_center()
                dist = math.hypot(px - cx, py - cy)
                if comida._being_dragged and dist < 55:
                    self._on_eaten(comida); break
                elif not comida._being_dragged and dist < 40:
                    self._on_eaten(comida); break
            except Exception:
                if comida in self.comidas:
                    self.comidas.remove(comida)
        self.root.after(100, self._loop_colision_comida)

    # ─────────────────────────────────────────
    def _loop_mensaje_random(self):
        if self.estado == self.NORMAL:
            def pensar_y_mostrar():
                texto = self.ia_pensar()
                if texto:
                    cx, cy = self._centro_pantalla()
                    self.root.after(0, lambda: self.globo.mostrar(texto, cx, int(self.y)))
            
            threading.Thread(target=pensar_y_mostrar, daemon=True).start()

        siguiente = random.randint(MENSAJE_INTERVALO_MIN, MENSAJE_INTERVALO_MAX)
        self.root.after(siguiente, self._loop_mensaje_random)


# ══════════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("🐾 Dewey_vr2.0 — Edición IA Autónoma")
    print("━" * 40)
    print("  • Se mueve y salta por tu pantalla")
    print("  • Aparece comida cada ~13 seg → arrástrala a la mascota")
    print("  • Sin comida → empieza a gritar")
    print("  • 🧠 IA AUTÓNOMA: Dewey observa tus apps y piensa por sí solo")
    print()
    if IA_DISPONIBLE:
        print("  ✓ Ollama & psutil detectados — Cerebro activado")
    else:
        print("  ✗ IA no disponible — Usando frases predefinidas")
        print("    Instala: pip install ollama psutil")
    print()
    print("  ✓ Imágenes PNG habilitadas")
    print("━" * 40 + "\n")
    Mascota()
