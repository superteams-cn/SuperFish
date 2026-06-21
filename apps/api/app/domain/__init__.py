"""领域模型层：纯数据类与枚举，不依赖 repositories/services/db。

位于分层最底部，供 repositories（行<->领域映射）与 services（业务编排）共同依赖，
从而打破「Manager ↔ Repository」的循环导入。
"""
