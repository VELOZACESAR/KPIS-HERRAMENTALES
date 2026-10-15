import hashlib
import json
import re
import threading

from flask import Flask, Response, jsonify, request, send_from_directory

from . import config, db, tablero
from .ingesta import estado_fuentes

CLAVE_VALIDA = re.compile(r"^[a-z0-9_.\-]{1,80}$")


def crear_app(ingestor):
    app = Flask(__name__, static_folder=None)
    app.json.ensure_ascii = False
    actualizando = threading.Lock()

    def _json(datos):
        cuerpo = json.dumps(datos, ensure_ascii=False, default=str)
        return Response(cuerpo, mimetype="application/json", headers={"Cache-Control": "no-store"})

    @app.get("/")
    def inicio():
        return send_from_directory(config.CARPETA_WEB, "tablero.html", max_age=0)

    @app.get("/web/<path:archivo>")
    def estaticos(archivo):
        return send_from_directory(config.CARPETA_WEB, archivo, max_age=300)

    @app.get("/api/tablero")
    def api_tablero():
        datos = tablero.obtener(ingestor.version)
        sin_hora = {k: v for k, v in datos.items() if k != "generado"}
        firma = hashlib.md5(json.dumps(sin_hora, sort_keys=True, default=str).encode()).hexdigest()
        return _json({**datos, "firma": firma, "edicion_con_clave": bool(config.CLAVE_EDICION)})

    @app.put("/api/manual/<clave>")
    def api_manual(clave):
        if not CLAVE_VALIDA.match(clave):
            return jsonify(error="Clave inválida"), 400
        if config.CLAVE_EDICION and request.headers.get("X-Clave") != config.CLAVE_EDICION:
            return jsonify(error="Clave de edición incorrecta"), 403
        cuerpo = request.get_json(silent=True) or {}
        valor = cuerpo.get("valor")
        if valor is not None:
            try:
                valor = float(valor)
            except (TypeError, ValueError):
                return jsonify(error="El valor debe ser un número"), 400
            if not (0 <= valor < 1e7):
                return jsonify(error="Valor fuera de rango"), 400
        usuario = str(cuerpo.get("usuario") or "")[:80] or None
        cambio = tablero.guardar_manual(clave, valor, usuario, request.remote_addr)
        return jsonify(ok=True, cambio=cambio, manuales=tablero.manuales())

    @app.post("/api/actualizar")
    def api_actualizar():
        if not actualizando.acquire(blocking=False):
            return jsonify(ok=True, mensaje="Ya hay una actualización en curso"), 202
        try:
            cargadas = ingestor.revisar()
            tablero.invalidar()
            return jsonify(ok=True, cargadas=cargadas, fuentes=estado_fuentes())
        finally:
            actualizando.release()

    @app.get("/api/cargues")
    def api_cargues():
        filas = db.consultar("""SELECT TOP 50 id, fuente, archivo, modificado, inicio, fin, filas, estado, mensaje
                                FROM cesar.cargue ORDER BY id DESC""")
        return _json(filas)

    @app.get("/api/salud")
    def api_salud():
        try:
            db.consultar("SELECT 1 AS ok")
            bd = "ok"
        except Exception as e:
            bd = str(e)
        return jsonify(bd=bd, version=ingestor.version, fuentes={k: v["error"] for k, v in ingestor.estado.items()})

    return app
