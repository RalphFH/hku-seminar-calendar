#!/usr/bin/env python3
"""Fetch public HKU announcements with normal HTTPS verification; stdlib only."""
import argparse
import http.client
import json
import re
import ssl
import time
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

ORIGIN = 'https://www.cs.hku.hk'
SOURCE = ORIGIN + '/events/'
DAY = 86400000
VOID = set('area base br col embed hr img input link meta param source track wbr'.split())

def source_url(value):
    url = urllib.parse.urljoin(ORIGIN, value or '')
    parsed = urllib.parse.urlsplit(url)
    return url if parsed.scheme == 'https' and parsed.netloc == 'www.cs.hku.hk' and re.fullmatch(r'/events/[^/?#]+/', parsed.path) and not parsed.query and not parsed.fragment else ''

class Cards(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.items, self.current = [], [], None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get('class', '').split())
        if 'eventon_list_event' in classes and attrs.get('data-event_id'):
            match = re.fullmatch(r'event_(\d+)_(\d+)', attrs.get('id', ''))
            if match:
                self.current = {'id': '-'.join(match.groups()), 'time': attrs.get('data-time', ''), 'title': '', 'location': '', 'locationAttr': '', 'category': '', 'url': '', 'classes': classes, 'depth': len(self.stack)+1}
        current = self.current
        if current:
            if 'event_location_attrs' in classes:
                current['locationAttr'] = attrs.get('data-location_name', '')
            if tag == 'a' and any('evo_event_schema' in entry[1] for entry in self.stack):
                current['url'] = source_url(attrs.get('href'))
        if tag not in VOID:
            self.stack.append((tag, classes))

    def handle_endtag(self, tag):
        for index in range(len(self.stack)-1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
        if self.current and len(self.stack) < self.current['depth']:
            self.items.append(self.current)
            self.current = None

    def handle_data(self, data):
        if not self.current:
            return
        classes = set().union(*(entry[1] for entry in self.stack))
        for css, key in [('evoet_title', 'title'), ('evo_location_name', 'location'), ('evoet_tags', 'category')]:
            if css in classes:
                self.current[key] += data

def parse_cards(html):
    parser = Cards()
    parser.feed(html)
    unique = {}
    clean = lambda value: re.sub(r'\s+', ' ', value).strip()
    for card in parser.items:
        times = re.fullmatch(r'(\d{9,12})-(\d{9,12})', card['time'])
        start, end = [int(value)*1000 for value in times.groups()] if times else [0, 0]
        record = {'id': card['id'], 'title': clean(card['title']), 'location': clean(card['locationAttr'] or card['location']), 'url': card['url'], 'start': start, 'end': end, 'category': clean(card['category']), 'status': 'CANCELLED' if card['classes'] & {'cancelled', 'cancelled_event', 'canceled', 'canceled_event'} else 'CONFIRMED'}
        issue = '缺少有效标题或开始时间' if not record['title'] or not 946684800000 <= start <= 4102444800000 else '官网结束时间早于或等于开始时间，待核实' if end <= start else '官网活动时长超过七天，待核实' if end-start > 7*DAY else ''
        record['issue'] = issue
        old = unique.get(record['id'])
        if not old or (old['issue'] and not issue):
            unique[record['id']] = record
    return list(unique.values())

def download(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'HKU-Seminar-Calendar/1.0 (public event subscription)', 'Accept': 'text/html,application/rss+xml'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            final = urllib.parse.urlsplit(response.geturl())
            if final.scheme != 'https' or final.netloc != 'www.cs.hku.hk':
                raise ValueError('Unexpected upstream redirect')
            body = response.read(5_000_001)
    except urllib.error.URLError as error:
        if not isinstance(error.reason, ssl.SSLCertVerificationError):
            raise
        # The published DNS CNAME is cms12.cs.hku.hk. Its TLS hostname is
        # verified with the system CA store; the HTTP Host remains the public
        # website name. No certificate verification is disabled.
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.netloc != 'www.cs.hku.hk':
            raise
        conn = http.client.HTTPSConnection('cms12.cs.hku.hk', timeout=30, context=ssl.create_default_context())
        try:
            conn.request('GET', parsed.path+('?' + parsed.query if parsed.query else ''), headers={'Host':'www.cs.hku.hk','User-Agent':'HKU-Seminar-Calendar/1.0 (public event subscription)'})
            response = conn.getresponse()
            if response.status != 200:
                raise RuntimeError('Verified HKU backend returned HTTP '+str(response.status))
            body = response.read(5_000_001)
        finally:
            conn.close()
    if len(body) > 5_000_000:
        raise ValueError('Upstream response exceeds 5 MB')
    return body

def signature(item):
    return tuple(item.get(key, '') for key in ['title', 'start', 'end', 'location', 'url', 'status', 'note'])

def merge(old, incoming, now):
    records = {item['id']: item for item in old.get('records', [])}
    issues = {item['id']: item for item in old.get('issues', [])}
    for item in incoming:
        previous = records.get(item['id'])
        if item['issue']:
            issues[item['id']] = {key: item[key] for key in ['id', 'title', 'url', 'start']}
            issues[item['id']]['reason'] = item['issue']
            if previous:
                next_item = dict(previous, status='TENTATIVE', note=item['issue'])
                if signature(previous) != signature(next_item):
                    next_item.update(sequence=previous['sequence']+1, modified=now)
                records[item['id']] = next_item
            continue
        issues.pop(item['id'], None)
        next_item = {key: value for key, value in item.items() if key != 'issue'}
        next_item.update(note='', created=previous['created'] if previous else now, modified=previous['modified'] if previous else now, sequence=previous['sequence'] if previous else 0)
        if previous and signature(previous) != signature(next_item):
            next_item.update(sequence=previous['sequence']+1, modified=now)
        records[item['id']] = next_item
    return {'records': [item for item in records.values() if item['end'] >= now-2*366*DAY], 'issues': [item for item in issues.values() if item.get('start', now) >= now-2*366*DAY]}

def collect(output, fixture=None):
    now = int(time.time()*1000)
    old = json.loads(output.read_text()) if output.exists() else {}
    incoming = parse_cards(Path(fixture).read_text() if fixture else download(SOURCE).decode('utf8'))
    if not incoming:
        raise RuntimeError('No recognizable event cards: keep the existing published snapshot')
    checked, warning = dict(old.get('checked', {})), ''
    listed = {item['url'] for item in incoming if item['url']}
    checked.update({url: now for url in listed})
    if not fixture:
        try:
            root = ET.fromstring(download(SOURCE+'feed/'))
            links = list(dict.fromkeys(filter(None, (source_url(node.text) for node in root.findall('./channel/item/link')))))[:20]
            candidates = sorted((url for url in links if url not in listed and now-checked.get(url, 0) >= 6*3600000), key=lambda url: checked.get(url, 0))[:4]
            for url in candidates:
                detail = parse_cards(download(url).decode('utf8'))
                if detail:
                    incoming.extend(detail)
                    checked[url] = now
                else:
                    warning = '部分官网详情尚未识别，下次更新会重试'
        except Exception as error:
            warning = '部分官网详情暂时不可用：'+type(error).__name__
    snapshot = dict(merge(old, incoming, now), schema=1, source=SOURCE, checked=checked, updatedAt=now, attemptedAt=now, error='', warning=warning)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.tmp')
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2)+'\n')
    temporary.replace(output)
    print(json.dumps({'events': len(snapshot['records']), 'issues': len(snapshot['issues']), 'warning': warning}, ensure_ascii=False))

if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('--output', default='data/calendar.json', type=Path)
    cli.add_argument('--fixture')
    args = cli.parse_args()
    collect(args.output, args.fixture)
