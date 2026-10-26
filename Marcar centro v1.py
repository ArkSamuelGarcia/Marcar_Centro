"""
Extensión para IngeTrazo: Marca de Centro Proporcional en Cruz (+)
Genera dos líneas perpendiculares en forma de cruz (+) en el centro exacto
del arco o círculo seleccionado, con una longitud igual al 5% de su diámetro.
Por: Ark Samuel Garcia.
"""

import math
import traceback
from PySide6.QtGui import QVector3D
from tools.base import Tool
from core.history import SnapshotImport

# Proporción respecto al diámetro: 0.05 = 5% del diámetro (o 10% del radio)
MARK_DIAMETER_RATIO = 0.05


def _get_mark_length(radius):
    """Calcula la longitud total de cada línea de la cruz como el 5% del diámetro."""
    return 2.0 * abs(float(radius)) * MARK_DIAMETER_RATIO


def _to_vec3(pt):
    """Convierte cualquier representación de punto de IngeTrazo a QVector3D."""
    if pt is None:
        return None
    if isinstance(pt, QVector3D):
        return pt
    if hasattr(pt, "x") and hasattr(pt, "y") and hasattr(pt, "z"):
        try:
            return QVector3D(float(pt.x()), float(pt.y()), float(pt.z()))
        except TypeError:
            return QVector3D(float(pt.x), float(pt.y), float(pt.z))
    if isinstance(pt, (tuple, list)) and len(pt) >= 3:
        return QVector3D(float(pt[0]), float(pt[1]), float(pt[2]))
    if hasattr(pt, "pos"):
        return _to_vec3(pt.pos)
    return None


def _circumcenter_3d(p1, p2, p3):
    """Calcula analíticamente el centro 3D y la normal del plano a partir de 3 puntos."""
    v1 = QVector3D(p2.x() - p1.x(), p2.y() - p1.y(), p2.z() - p1.z())
    v2 = QVector3D(p3.x() - p1.x(), p3.y() - p1.y(), p3.z() - p1.z())

    normal = QVector3D.crossProduct(v1, v2)
    n_len_sq = normal.lengthSquared()

    if n_len_sq < 1e-12:
        return None, QVector3D(0, 0, 1)

    d1 = v1.lengthSquared()
    d2 = v2.lengthSquared()

    c1 = QVector3D.crossProduct(v2, normal)
    c2 = QVector3D.crossProduct(normal, v1)

    rx = (d1 * c1.x() + d2 * c2.x()) / (2.0 * n_len_sq)
    ry = (d1 * c1.y() + d2 * c2.y()) / (2.0 * n_len_sq)
    rz = (d1 * c1.z() + d2 * c2.z()) / (2.0 * n_len_sq)

    center = QVector3D(p1.x() + rx, p1.y() + ry, p1.z() + rz)
    normal.normalize()

    return center, normal


def extract_points_from_selection(selection, scene):
    """Extrae los vértices necesarios de la selección (aristas, curvas o caras)."""
    pts = []
    mesh = getattr(scene, "mesh", None) or getattr(scene, "loose_mesh", None)

    items = []
    for container_attr in ("edges", "curves", "faces", "items"):
        val = getattr(selection, container_attr, None)
        if val:
            if callable(val):
                val = val()
            items.extend(val)

    if not items and hasattr(selection, "__iter__"):
        try:
            items.extend(list(selection))
        except TypeError:
            pass

    if not items:
        items = [selection]

    for item in items:
        # 1. Curva nativa que ya conozca su centro
        curve = getattr(item, "curve", None) or item
        if hasattr(curve, "center") and curve.center is not None:
            c = _to_vec3(curve.center)
            n = _to_vec3(getattr(curve, "normal", None)) or QVector3D(0, 0, 1)
            r = getattr(curve, "radius", None)
            if c:
                return [c], n, r

        # 2. Secuencia de vértices (arista, cara o polilínea)
        for attr in ("vertices", "points", "pts", "loop", "outer_loop", "polygon"):
            seq = getattr(item, attr, None)
            if seq and hasattr(seq, "__iter__"):
                for v in seq:
                    if isinstance(v, int) and mesh and hasattr(mesh, "vertices"):
                        pt = _to_vec3(mesh.vertices[v])
                    else:
                        pt = _to_vec3(v)
                    if pt and pt not in pts:
                        pts.append(pt)
                if pts:
                    break

        # 3. Aristas con extremos definidos
        for pair in (("v1", "v2"), ("start", "end"), ("p1", "p2"), ("a", "b")):
            if hasattr(item, pair[0]) and hasattr(item, pair[1]):
                pA = _to_vec3(getattr(item, pair[0]))
                pB = _to_vec3(getattr(item, pair[1]))
                if pA and pA not in pts:
                    pts.append(pA)
                if pB and pB not in pts:
                    pts.append(pB)

    return pts, None, None


def find_arc_center_and_plane(selection, scene):
    """Obtiene el centro, radio y vector normal del arco o círculo."""
    pts, direct_normal, direct_radius = extract_points_from_selection(selection, scene)

    if direct_normal is not None and len(pts) == 1:
        return pts[0], direct_normal, (direct_radius or 1.0)

    if len(pts) >= 3:
        n = len(pts)
        p1 = pts[0]
        p2 = pts[n // 3]
        p3 = pts[(2 * n) // 3]
        center, normal = _circumcenter_3d(p1, p2, p3)
        if center:
            radius = (p1 - center).length()
            return center, normal, radius

    return None, None, None


def execute_mark_center(viewport, selection=None):
    scene = viewport.scene
    sel = selection or getattr(viewport, "selection", None) or getattr(scene, "selection", None)

    center, normal, radius = find_arc_center_and_plane(sel, scene)

    if not center or radius is None:
        viewport.flash_status("Selecciona un arco o círculo para marcar su centro.", 3500)
        return

    # Longitud de cada línea: 5% del diámetro
    mark_length = _get_mark_length(radius)
    half_len = mark_length / 2.0  # Mitad hacia cada lado desde el centro

    # Definir vectores perpendiculares contenidos en el plano del arco
    if abs(normal.z()) > 0.95:  # Plano horizontal
        u = QVector3D(1.0, 0.0, 0.0)
        v = QVector3D(0.0, 1.0, 0.0)
    else:  # Plano vertical o inclinado
        u = QVector3D.crossProduct(normal, QVector3D(0.0, 0.0, 1.0))
        if u.lengthSquared() < 1e-6:
            u = QVector3D.crossProduct(normal, QVector3D(0.0, 1.0, 0.0))
        u.normalize()
        v = QVector3D.crossProduct(normal, u)
        v.normalize()

    # Coordenadas de los extremos de la cruz (+)
    p1_a = center - (u * half_len)
    p1_b = center + (u * half_len)

    p2_a = center - (v * half_len)
    p2_b = center + (v * half_len)

    def mutate(target_scene):
        target_mesh = getattr(target_scene, "mesh", None)
        loose_mesh = getattr(target_scene, "loose_mesh", None)

        for m in (target_mesh, loose_mesh):
            if m is not None and hasattr(m, "add_edge"):
                try:
                    m.add_edge(p1_a, p1_b)
                    m.add_edge(p2_a, p2_b)
                except Exception as err:
                    print(f"[center_mark] Error al añadir arista: {err}")
                    traceback.print_exc()

    try:
        # Registrar en el historial para permitir Ctrl+Z
        viewport.history.execute(SnapshotImport(mutate))
        viewport.notify_scene_changed()

        # Forzar refresco visual inmediato
        if hasattr(viewport, "update"):
            viewport.update()
        if hasattr(viewport, "repaint"):
            viewport.repaint()

        viewport.flash_status(
            f"Cruz (+) al centro creada (longitud: {mark_length:.3f})", 3000
        )

    except Exception as e:
        print(f"[center_mark] Error en transacción: {e}")
        traceback.print_exc()
        viewport.flash_status(f"Error al dibujar la marca: {e}", 4000)


# ---------------------------------------------------------------------------
# Entrada en el menú Extensiones
# ---------------------------------------------------------------------------
class CenterMarkTool(Tool):
    name = "Marcar Centro (+)"
    shortcut = None
    description = "Dibuja una cruz (+) proporcional al 5% del diámetro en el centro del arco o círculo"

    def on_activate(self, viewport):
        execute_mark_center(viewport)

    def on_deactivate(self, viewport):
        pass


# ---------------------------------------------------------------------------
# Menú contextual de clic derecho
# ---------------------------------------------------------------------------
def setup(app):
    def context_handler(menu, selection):
        if selection:
            menu.addAction("Marcar centro (+)", lambda: execute_mark_center(app.viewport, selection))

    app.add_context_menu(context_handler)