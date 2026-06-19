"""
FastAPI 公共依赖项
"""

from fastapi import Header

from .utils.locale import coerce_locale, set_locale


async def use_locale(accept_language: str | None = Header(default=None)):
    """请求级依赖：从 Accept-Language 头解析语言并写入当前上下文。

    后续在该请求中调用 utils.locale.t / get_locale 即可拿到正确语言；
    若请求派生后台线程，需在线程入口处再次 set_locale(get_locale())。
    """
    set_locale(coerce_locale(accept_language))
