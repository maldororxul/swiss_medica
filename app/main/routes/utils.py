from typing import Optional, Dict
from flask import request
from urllib.parse import urlparse, parse_qs


def get_data_from_post_request(_request) -> Optional[Dict]:
    if request.content_type == 'application/json':
        return _request.json
    elif request.content_type == 'application/x-www-form-urlencoded':
        return _request.form.to_dict()
    else:
        return None


def get_args_from_url(url: str) -> Dict:
    """ Получает словарь аргументов из URL, подходит для разбора utm

    Args:
        url: адрес

    Returns:
        {'utm_source': ..., 'utm_medium': ..., ...}
    """
    parse_result = urlparse(url)
    return {key: value[0] for key, value in parse_qs(parse_result.query).items()}
