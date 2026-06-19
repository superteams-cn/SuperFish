"""
旧版 Flask API 路由模块（过渡期）

graph 已迁移到 FastAPI（见 app/routers/graph.py）；
simulation 与 report 仍为 Flask 蓝图，经 WSGI 中间件挂载到 FastAPI 上，
待逐一迁移完成后整体删除本模块。
"""

from flask import Blueprint

simulation_bp = Blueprint('simulation', __name__)
report_bp = Blueprint('report', __name__)

from . import simulation  # noqa: E402, F401
from . import report  # noqa: E402, F401
