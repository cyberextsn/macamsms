from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.camera import KivyCamera  # non, on utilise jnius directement
from kivy.clock import Clock
from kivy.utils import platform
from kivy.core.window import Window
from jnius import autoclass, PythonJavaClass, java_method
import os, time

# ---- Accès natif Android ----
if platform == "android":
    from android.permissions import request_permissions, Permission
    request_permissions([
        Permission.CAMERA,
        Permission.READ_SMS,
        Permission.READ_EXTERNAL_STORAGE,
        Permission.WRITE_EXTERNAL_STORAGE,
    ])
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    Intent = autoclass("android.content.Intent")
    Camera = autoclass("android.hardware.Camera")
    SurfaceHolder = autoclass("android.view.SurfaceHolder")
    SurfaceView = autoclass("android.view.SurfaceView")
    SurfaceTexture = autoclass("android.graphics.SurfaceTexture")

    # --- Preview caméra via SurfaceTexture ---
    class AndroidCamera:
        def __init__(self, camera_id=0):
            self.camera_id = camera_id
            self.camera = None
            self.texture = SurfaceTexture(0)
            self.start()

        def start(self):
            self.stop()
            try:
                self.camera = Camera.open(self.camera_id)
                self.texture.detachGLContext() if hasattr(self.texture, "detachGLContext") else None
                self.camera.setPreviewTexture(self.texture)
                self.camera.startPreview()
            except Exception as e:
                print("Erreur caméra:", e)

        def stop(self):
            if self.camera:
                try:
                    self.camera.stopPreview()
                    self.camera.release()
                except Exception:
                    pass
                self.camera = None

        def switch(self):
            self.camera_id = 1 - self.camera_id  # 0 = arrière, 1 = avant sur la plupart des téléphones
            self.start()

        def take_picture(self, callback):
            if not self.camera:
                return
            def on_pic(data, cam):
                path = os.path.join(os.environ.get("EXTERNAL_STORAGE", "/sdcard"), "DCIM")
                if not os.path.isdir(path):
                    path = "/sdcard"
                filename = os.path.join(path, f"photo_{int(time.time())}.jpg")
                try:
                    with open(filename, "wb") as f:
                        f.write(data)
                    callback(f"Photo sauvegardée: {filename}")
                except Exception as e:
                    callback(f"Erreur: {e}")
                self.camera.startPreview()
            self.camera.takePicture(None, None, None, on_pic)

    def read_sms():
        """Lit les SMS de la boîte de réception."""
        Sms = autoclass("android.provider.Telephony$Sms")
        Uri = autoclass("android.net.Uri")
        ContentResolver = autoclass("android.content.ContentResolver")
        cr = PythonActivity.mActivity.getContentResolver()
        cursor = cr.query(Uri.parse("content://sms/inbox"), None, None, None, None)
        messages = []
        if cursor:
            addr_idx = cursor.getColumnIndex("address")
            body_idx = cursor.getColumnIndex("body")
            date_idx = cursor.getColumnIndex("date")
            count = 0
            while cursor.moveToNext() and count < 100:
                sender = cursor.getString(addr_idx)
                body = cursor.getString(body_idx)
                messages.append(f"De: {sender}\n{body}\n{'-'*30}")
                count += 1
            cursor.close()
        return messages or ["Aucun SMS trouvé."]
else:
    # Fallback PC pour tester
    class AndroidCamera:
        def __init__(self, camera_id=0): pass
        def start(self): pass
        def stop(self): pass
        def switch(self): pass
        def take_picture(self, cb): cb("Caméra dispo uniquement sur Android")

    def read_sms():
        return ["Les SMS ne sont lisibles que sur Android."]


class MonApp(App):
    def build(self):
        self.title = "Ma Cam & SMS"
        self.cam = None
        self.cam_id = 0

        root = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # ---- Écran caméra ----
        from kivy.uix.widget import Widget
        from kivy.graphics import Color, Rectangle
        self.cam_screen = Widget(size_hint=(1, 0.55))
        with self.cam_screen.canvas:
            Color(0.05, 0.05, 0.08, 1)
            self.cam_rect = Rectangle(pos=self.cam_screen.pos, size=self.cam_screen.size)
        self.cam_screen.bind(pos=self._update_rect, size=self._update_rect)

        # ---- Message de statut ----
        self.status = Label(
            text="Bienvenue 👋", size_hint=(1, None), height=30,
            color=(0.9, 0.9, 0.9, 1), font_size="15sp"
        )

        # ---- Boutons caméra ----
        btns = GridLayout(cols=2, size_hint=(1, None), height=60, spacing=10)
        self.btn_switch = self._mkbtn("📸 Caméra avant", self.switch_cam)
        self.btn_photo = self._mkbtn("📷 Prendre photo", self.take_photo)
        btns.add_widget(self.btn_switch)
        btns.add_widget(self.btn_photo)

        # ---- Bouton SMS ----
        self.btn_sms = self._mkbtn("💬 Voir mes messages", self.show_sms, height=55)
        self.btn_sms.size_hint = (1, None)

        # ---- Zone SMS ----
        self.sms_scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.sms_label = Label(
            text="", size_hint_y=None, halign="left", valign="top",
            color=(0.85, 0.85, 0.85, 1), font_size="13sp", padding=[10, 10]
        )
        self.sms_label.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
        self.sms_label.bind(texture_size=lambda i, s: setattr(i, "height", s[1]))
        self.sms_scroll.add_widget(self.sms_label)

        root.add_widget(self.cam_screen)
        root.add_widget(self.status)
        root.add_widget(btns)
        root.add_widget(self.btn_sms)
        root.add_widget(self.sms_scroll)

        if platform == "android":
            self.cam = AndroidCamera(self.cam_id)
            Clock.schedule_interval(self.refresh_cam, 1 / 30)
        return root

    def _update_rect(self, i, v):
        self.cam_rect.pos = i.pos
        self.cam_rect.size = i.size

    def _mkbtn(self, text, cb, height=60):
        b = Button(text=text, size_hint=(1, None), height=height,
                   background_normal="", background_color=(0.2, 0.55, 0.9, 1),
                   color=(1, 1, 1, 1), font_size="16sp", bold=True)
        b.bind(on_press=cb)
        # petit effet arrondi via canvas
        with b.canvas.before:
            from kivy.graphics import Color as C, RoundedRectangle
            C(0.2, 0.55, 0.9, 1)
            b._bg = RoundedRectangle(pos=b.pos, size=b.size, radius=[12])
        b.bind(pos=lambda i, v: setattr(i._bg, "pos", i.pos))
        b.bind(size=lambda i, v: setattr(i._bg, "size", i.size))
        return b

    def refresh_cam(self, dt):
        if self.cam and self.cam.camera:
            self.cam.texture.updateTexImage()
            # dessine la texture sur l'écran
            from kivy.graphics import Rectangle as R
            # (rendu simplifié : la preview matérielle s'affiche via la surface native)
            pass

    def switch_cam(self, *a):
        self.cam_id = 1 - self.cam_id
        self.cam.switch()
        self.status.text = "Caméra avant 🤳" if self.cam_id == 1 else "Caméra arrière 📷"

    def take_photo(self, *a):
        self.status.text = "📸 Photo en cours..."
        self.cam.take_picture(lambda msg: Clock.schedule_once(lambda dt: setattr(self.status, "text", msg), 0))

    def show_sms(self, *a):
        msgs = read_sms()
        self.sms_label.text = "\n".join(msgs)
        self.status.text = "💬 Messages chargés"

    def on_stop(self):
        if self.cam:
            self.cam.stop()


if __name__ == "__main__":
    MonApp().run()