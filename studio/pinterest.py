"""Authenticated Pinterest Board discovery, never an anonymous scraper."""
from urllib.parse import urlencode, urlsplit
import requests
from .assets import ingest_image, MAX_BYTES

BASE = 'https://api.pinterest.com/v5'


def api_get(settings, route, params=None):
    settings.require('pinterest')
    response = requests.get(BASE + route, params=params,
        headers={'Authorization': 'Bearer ' + settings.secret('pinterest_access_token')}, timeout=(10, 30))
    if not response.ok:
        raise ValueError(f'Pinterest 返回 HTTP {response.status_code}；请核对 Token、Board 授权和 scopes。')
    return response.json()


def image_url(pin):
    images = (pin.get('media') or {}).get('images') or {}
    for size in ['1200x', '600x', '400x300', '150x150']:
        value = images.get(size) or {}
        url = value.get('url', '')
        if safe_pin_image(url):
            return url
    return ''


def safe_pin_image(url):
    parsed = urlsplit(url)
    return parsed.scheme == 'https' and parsed.hostname == 'i.pinimg.com' and not parsed.username and parsed.port in (None, 443)


def search_board(settings, query, bookmark=None, language="pt-BR"):
    settings.require('pinterest')
    from .director import scene_query
    query = scene_query(query, settings, language)
    board_id = settings.get()['pinterest_board_id']
    if not board_id.isdigit():
        settings.require('pinterest')
        raise ValueError('Board ID 无效。')
    params = {'page_size': 100}
    if bookmark:
        params['bookmark'] = bookmark
    data = api_get(settings, f'/boards/{board_id}/pins', params)
    terms = query.casefold().split()
    items = []
    for pin in data.get('items', []):
        title = pin.get('title') or pin.get('description') or 'Pinterest 场景'
        searchable = (title + ' ' + (pin.get('description') or '')).casefold()
        if terms and not any(term in searchable for term in terms):
            continue
        url = image_url(pin)
        if url:
            items.append({'id': pin['id'], 'title': title[:250], 'url': f"https://www.pinterest.com/pin/{pin['id']}/", 'image_url': url})
    return {'items': items, 'bookmark': data.get('bookmark'), 'recommended_query': query,
            'search_url': 'https://www.pinterest.com/search/pins/?' + urlencode({'q': query or {'pt-BR': 'interior casa Brasil luz natural sem pessoas', 'es-MX': 'interior casa México luz natural sin personas', 'en-US': 'home interior natural light no people', 'fil-PH': 'bahay interior natural na ilaw walang tao'}[language]})}


def import_pin(settings, store, pin_id):
    pin = api_get(settings, f'/pins/{pin_id}')
    if str(pin.get('board_id', '')) != settings.get()['pinterest_board_id']:
        raise ValueError('该 Pin 不属于当前已授权 Board。')
    url = image_url(pin)
    if not url:
        raise ValueError('该 Pin 没有可用的图片。')
    # No redirect following; remote input cannot turn this into arbitrary URL fetching.
    with requests.get(url, stream=True, timeout=(10, 40), allow_redirects=False) as response:
        if response.status_code != 200:
            raise ValueError('场景图片下载失败，请选择其他 Pin 或上传自己的场景图。')
        content = bytearray()
        for chunk in response.iter_content(64 * 1024):
            content.extend(chunk)
            if len(content) > MAX_BYTES:
                raise ValueError('场景图片超过 10 MB。')
    return ingest_image(store, bytes(content), 'scene', pin.get('title') or f'pinterest-{pin_id}',
                        f'https://www.pinterest.com/pin/{pin_id}/')
