"""
SuperFish Backend 应用包

应用入口已迁移到 FastAPI：见 app/main.py 的 `app` 实例。
过渡期内 simulation / report 仍为 Flask 蓝图，通过 app/legacy_flask.py 经
WSGI 中间件挂载到 FastAPI 上，待逐一迁移完成后删除。
"""
