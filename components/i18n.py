"""
DiscoverLatest 洞察運算 - 多語系支援
"""
import json
from pathlib import Path
from typing import Dict, Optional

# 預設語言
DEFAULT_LANG = 'zh-TW'

# 支援的語言
SUPPORTED_LANGS = ['zh-TW', 'en']

# 語言顯示名稱
LANG_NAMES = {
    'zh-TW': '繁體中文',
    'en': 'English'
}

# 快取
_translations: Dict[str, Dict] = {}


def load_translations(lang: str) -> Dict:
    """載入指定語言的翻譯字典"""
    if lang in _translations:
        return _translations[lang]
    
    locale_path = Path(__file__).parent.parent / 'locales' / f'{lang}.json'
    
    try:
        with open(locale_path, 'r', encoding='utf-8') as f:
            _translations[lang] = json.load(f)
    except FileNotFoundError:
        # 若找不到，使用預設語言
        if lang != DEFAULT_LANG:
            return load_translations(DEFAULT_LANG)
        _translations[lang] = {}
    
    return _translations[lang]


def t(key: str, lang: str = DEFAULT_LANG, **kwargs) -> str:
    """
    翻譯函式
    
    Args:
        key: 翻譯鍵值（支援點號分隔，如 'nav.home'）
        lang: 語言代碼
        **kwargs: 替換參數
        
    Returns:
        翻譯後的字串
    """
    translations = load_translations(lang)
    
    # 支援點號分隔的鍵值
    keys = key.split('.')
    value = translations
    
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            value = None
            break
    
    if value is None:
        # 找不到翻譯，回傳 key 本身
        return key
    
    # 替換參數
    if kwargs:
        try:
            value = value.format(**kwargs)
        except KeyError:
            pass
    
    return value


def get_all_translations(lang: str = DEFAULT_LANG) -> Dict:
    """取得完整翻譯字典"""
    return load_translations(lang)


def get_supported_langs() -> list:
    """取得支援的語言清單"""
    return [(code, LANG_NAMES.get(code, code)) for code in SUPPORTED_LANGS]
