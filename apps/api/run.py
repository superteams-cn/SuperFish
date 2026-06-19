"""
SuperFish Backend 启动入口（FastAPI + uvicorn）
"""

import os
import sys

# 解决 Windows 控制台中文乱码问题：在所有导入之前设置 UTF-8 编码
if sys.platform == 'win32':
    # 设置环境变量确保 Python 使用 UTF-8
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    # 重新配置标准输出流为 UTF-8
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 添加 apps/api 目录到路径，确保可导入 app 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn

from app.config import Config


def main():
    """主函数"""
    # 验证配置
    errors = Config.validate()
    if errors:
        print("配置错误:")
        for err in errors:
            print(f"  - {err}")
        print("\n请检查 .env 文件中的配置")
        sys.exit(1)

    # 获取运行配置（兼容历史 FLASK_* 环境变量名）
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 5001))
    debug = Config.DEBUG

    # 启动服务。debug 时开启热重载（需以导入字符串方式传入 app）
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=debug,
    )


if __name__ == '__main__':
    main()
