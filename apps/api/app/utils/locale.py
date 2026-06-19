import json
import os
import contextvars

# 当前请求/线程的语言。使用 contextvars 以同时兼容：
# 1) FastAPI 异步请求（由依赖项在请求开始时 set_locale）
# 2) 后台线程（线程入口处显式 set_locale 传入捕获的语言）
_current_locale: "contextvars.ContextVar[str | None]" = contextvars.ContextVar(
    'current_locale', default=None
)

_locales_dir = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..', 'packages', 'shared', 'locales'
)

# Load language registry
with open(os.path.join(_locales_dir, 'languages.json'), 'r', encoding='utf-8') as f:
    _languages = json.load(f)

# Load translation files
_translations = {}
for filename in os.listdir(_locales_dir):
    if filename.endswith('.json') and filename != 'languages.json':
        locale_name = filename[:-5]
        with open(os.path.join(_locales_dir, filename), 'r', encoding='utf-8') as f:
            _translations[locale_name] = json.load(f)


def coerce_locale(raw: str | None) -> str:
    """把任意输入归一化为受支持的语言，缺省回退中文。"""
    return raw if raw in _translations else 'zh'


def set_locale(locale: str):
    """设置当前上下文的语言。在后台线程入口处调用以继承请求语言。"""
    _current_locale.set(locale)


def get_locale() -> str:
    # 使用 contextvar：FastAPI 请求由 deps.use_locale 设置，后台线程入口处再次设置
    return _current_locale.get() or 'zh'


def t(key: str, **kwargs) -> str:
    locale = get_locale()
    messages = _translations.get(locale, _translations.get('zh', {}))

    value = messages
    for part in key.split('.'):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            value = None
            break

    if value is None:
        value = _translations.get('zh', {})
        for part in key.split('.'):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = None
                break

    if value is None:
        return key

    if kwargs:
        for k, v in kwargs.items():
            value = value.replace(f'{{{k}}}', str(v))

    return value


def get_language_instruction() -> str:
    locale = get_locale()
    lang_config = _languages.get(locale, _languages.get('zh', {}))
    return lang_config.get('llmInstruction', '请使用中文回答。')
