"""Envío del resumen del tablero a un chat de Teams (botón "Enviar a Teams").

El servidor fotografía cada sección con Edge sin ventana (página en modo ?reporte=...), arma el cuerpo del mensaje
de Microsoft Graph con las imágenes adentro y lo manda a un flujo de Power Automate, que solo lo reenvía al chat.
El PC envía y no al revés porque la nube de Microsoft no puede entrar a la red interna.

.env:  TEAMS_FLUJO_URL=https://...   (URL del disparador HTTP del flujo; sin ella el botón avisa y no envía)
"""
import base64
import io
import json
import logging
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html import escape

from . import config, db

log = logging.getLogger("tablero.teams")

SECCIONES = [("aceros", "Aceros retrofit"), ("mantenimiento", "Mantenimiento de moldes"), ("oem", "Aceros OEM · BMW X5"),
             ("moldes", "Fabricación de moldes"), ("serigrafia", "Serigrafía")]
EDGE = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
ESPERAS = (0, 20, 60)

_enviando = threading.Lock()


def url_flujo():
    return (os.environ.get("TEAMS_FLUJO_URL") or "").strip()


def _edge():
    return next((r for r in EDGE if os.path.exists(r)), None)


def _recortar(png):
    """Edge fotografía una ventana alta fija: se corta el fondo vacío de abajo y se pasa a JPG (pesa mucho menos)."""
    from PIL import Image, ImageChops
    img = Image.open(io.BytesIO(png)).convert("RGB")
    m = 60
    zona = img.crop((m, 0, img.width - m, img.height))
    fondo = Image.new("RGB", zona.size, img.getpixel((img.width // 2, img.height - 2)))
    caja = ImageChops.difference(zona, fondo).convert("L").point(lambda v: 255 if v > 18 else 0).getbbox()
    if caja:
        img = img.crop((0, 0, img.width, min(img.height, caja[3] + 30)))
    salida = io.BytesIO()
    img.save(salida, "JPEG", quality=88, optimize=True)
    return salida.getvalue()


def capturar(seccion):
    edge = _edge()
    if not edge:
        raise RuntimeError("No encontré Microsoft Edge en este PC")
    perfil = tempfile.mkdtemp(prefix="tablero_teams_")
    destino = os.path.join(perfil, "captura.png")
    url = f"http://127.0.0.1:{config.PUERTO}/?reporte={seccion}"
    try:
        subprocess.run([edge, "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
                        f"--user-data-dir={perfil}", "--virtual-time-budget=25000",
                        f"--window-size=1400,{1500}", "--force-device-scale-factor=1.5",
                        f"--screenshot={destino}", url],
                       timeout=120, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(20):
            if os.path.exists(destino) and os.path.getsize(destino) > 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(f"Edge no generó la imagen de {seccion}")
        with open(destino, "rb") as f:
            return _recortar(f.read())
    finally:
        shutil.rmtree(perfil, ignore_errors=True)


def _cuerpo_graph(imagenes, generado):
    """Cuerpo listo para POST /chats/{id}/messages: el flujo no tiene que armar nada."""
    partes = [f"<p><b>Indicadores del área · Herramentales</b><br>Actualizado {escape(generado)}</p>"]
    hosted = []
    for i, (titulo, jpg) in enumerate(imagenes, start=1):
        partes.append(f'<p><b>{escape(titulo)}</b><br><img src="../hostedContents/{i}/$value" style="width:900px"></p>')
        hosted.append({"@microsoft.graph.temporaryId": str(i), "contentBytes": base64.b64encode(jpg).decode("ascii"),
                       "contentType": "image/jpeg"})
    return {"body": {"contentType": "html", "content": "".join(partes)}, "hostedContents": hosted}


def _registrar(estado, bytes_, detalle, usuario, ip):
    try:
        db.ejecutar("""INSERT INTO cesar.reporte_envio (fecha, estado, bytes, detalle, usuario, ip, pc)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""", db.ahora(), estado, bytes_, (detalle or "")[:1000], usuario, ip,
                    socket.gethostname()[:60])
    except Exception:
        log.exception("No se pudo registrar el envío a Teams")


def enviar(usuario=None, ip=None):
    """Devuelve (ok, mensaje). Nunca lanza excepción."""
    url = url_flujo()
    if not url:
        return False, "Falta TEAMS_FLUJO_URL en el .env del servidor"
    if not _enviando.acquire(blocking=False):
        return False, "Ya hay un envío en curso"
    try:
        try:
            with ThreadPoolExecutor(max_workers=3) as ex:
                fotos = list(ex.map(lambda s: (s[1], capturar(s[0])), SECCIONES))
        except Exception as e:
            _registrar("ERROR", None, f"No se pudieron generar las imágenes: {e}", usuario, ip)
            return False, f"No se pudieron generar las imágenes: {e}"
        generado = db.ahora().strftime("%d/%m/%Y %I:%M %p")
        cuerpo = json.dumps({"titulo": "Indicadores Herramentales", "fecha": generado,
                             "graph": _cuerpo_graph(fotos, generado)}).encode("utf-8")
        peso = sum(len(j) for _, j in fotos)
        error = ""
        for intento, espera in enumerate(ESPERAS, start=1):
            time.sleep(espera)
            try:
                req = urllib.request.Request(url, data=cuerpo, method="POST", headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=90) as r:
                    if 200 <= r.status < 300:
                        msg = f"Enviado a Teams ({len(fotos)} imágenes, {peso // 1024} KB)"
                        _registrar("OK", peso, msg, usuario, ip)
                        return True, msg
                    error = f"El flujo respondió {r.status}"
            except urllib.error.HTTPError as e:
                error = f"El flujo respondió {e.code}: {e.read()[:300].decode('utf-8', 'replace')}"
            except Exception as e:
                error = f"Sin conexión con Power Automate: {e}"
            log.warning("Envío a Teams, intento %s falló: %s", intento, error)
        _registrar("ERROR", peso, error, usuario, ip)
        return False, error
    finally:
        _enviando.release()
