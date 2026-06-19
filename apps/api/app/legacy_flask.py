"""
过渡期 Flask 子应用

仅承载尚未迁移到 FastAPI 的蓝图（simulation / report），
由 app/main.py 通过 WSGIMiddleware 挂载。每迁移完一个蓝图，
就从这里移除；全部迁移后整个文件连同 app/api/ 一并删除。
"""

from flask import Flask
from flask_cors import CORS

from .api import simulation_bp, report_bp


def build_legacy_app() -> Flask:
    """构建仅含遗留蓝图的 Flask 应用。"""
    app = Flask(__name__)

    # 中文直接显示，不转义为 \uXXXX
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False

    CORS(app, resources={r"/api/*": {"origins": "*"}})

    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')

    return app
