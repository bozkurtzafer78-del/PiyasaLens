#!/usr/bin/env python3
"""
PiyasaLens - Firestore Snapshot Uploader
Local'deki data/latest_market.json ve data/latest_strategy.json verilerini
Firebase Firestore bulut veritabanına aktarır.
"""

import os
import sys
import json
import time
import base64
import tempfile
import subprocess
import requests

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
KEY_FILE = os.path.join(ROOT_DIR, 'serviceAccountKey.json')
MARKET_FILE = os.path.join(ROOT_DIR, 'data', 'latest_market.json')
STRATEGY_FILE = os.path.join(ROOT_DIR, 'data', 'latest_strategy.json')


def to_firestore_value(val):
    if val is None:
        return {'nullValue': None}
    if isinstance(val, bool):
        return {'booleanValue': val}
    if isinstance(val, int):
        return {'integerValue': str(val)}
    if isinstance(val, float):
        return {'doubleValue': val}
    if isinstance(val, str):
        return {'stringValue': val}
    if isinstance(val, list):
        return {'arrayValue': {'values': [to_firestore_value(x) for x in val]}}
    if isinstance(val, dict):
        return {'mapValue': {'fields': {k: to_firestore_value(v) for k, v in val.items()}}}
    return {'stringValue': str(val)}


def to_firestore_doc(obj):
    return {'fields': {k: to_firestore_value(v) for k, v in obj.items()}}


def get_oauth2_token(key_data):
    header = {'alg': 'RS256', 'typ': 'JWT'}
    now = int(time.time())
    claims = {
        'iss': key_data['client_email'],
        'scope': 'https://www.googleapis.com/auth/datastore',
        'aud': 'https://oauth2.googleapis.com/token',
        'iat': now,
        'exp': now + 3600
    }

    def b64url(data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')

    payload = b64url(json.dumps(header)) + '.' + b64url(json.dumps(claims))
    with tempfile.NamedTemporaryFile('w', delete=False) as tf:
        tf.write(key_data['private_key'])
        key_path = tf.name

    try:
        p = subprocess.Popen(
            ['openssl', 'dgst', '-sha256', '-sign', key_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        sig, err = p.communicate(input=payload.encode('utf-8'))
        if p.returncode != 0:
            raise RuntimeError(f"OpenSSL imzalama hatası: {err.decode('utf-8')}")
        jwt = payload + '.' + b64url(sig)

        resp = requests.post(
            'https://oauth2.googleapis.com/token',
            data={'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer', 'assertion': jwt},
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=15
        )
        resp.raise_for_status()
        return resp.json()['access_token']
    finally:
        if os.path.exists(key_path):
            os.remove(key_path)


def upload_snapshots():
    key_data = None
    env_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if env_json:
        try:
            key_data = json.loads(env_json)
        except Exception:
            pass

    if not key_data and os.path.exists(KEY_FILE):
        with open(KEY_FILE, 'r', encoding='utf-8') as f:
            key_data = json.load(f)

    if not key_data:
        print(f"[HATA] Servis hesabı anahtarı bulunamadı ({KEY_FILE} veya FIREBASE_SERVICE_ACCOUNT_JSON).")
        return False

    if not os.path.exists(MARKET_FILE):
        print(f"[HATA] Piyasa verisi bulunamadı: {MARKET_FILE}")
        return False

    with open(MARKET_FILE, 'r', encoding='utf-8') as f:
        market_payload = json.load(f)

    strategy_payload = None
    if os.path.exists(STRATEGY_FILE):
        try:
            with open(STRATEGY_FILE, 'r', encoding='utf-8') as f:
                strategy_payload = json.load(f)
        except Exception:
            pass

    project_id = key_data['project_id']
    print(f"[*] Firebase OAuth2 yetkisi alınıyor (Project: {project_id})...")
    token = get_oauth2_token(key_data)
    print("[+] Yetki alındı.")

    writes = []
    base_doc_prefix = f"projects/{project_id}/databases/(default)/documents"

    # 1. Market Sayfaları (BIST ve US)
    markets = market_payload.get('markets', {})
    for market, snapshot in markets.items():
        items = snapshot.get('items', [])
        page_size = 500
        for page_idx in range((len(items) + page_size - 1) // page_size or 1):
            page_items = items[page_idx * page_size:(page_idx + 1) * page_size]
            page_data = {
                'market': market,
                'source': snapshot.get('source', ''),
                'provider': snapshot.get('provider', ''),
                'data_quality': snapshot.get('data_quality', 'delayed'),
                'delayed': snapshot.get('delayed', True),
                'fetched_at': snapshot.get('fetched_at', ''),
                'row_count': len(items),
                'page': page_idx,
                'items': page_items
            }
            doc_name = f"{base_doc_prefix}/marketSnapshots/latest_{market}/pages/{str(page_idx).zfill(4)}"
            writes.append({
                'update': {
                    'name': doc_name,
                    **to_firestore_doc(page_data)
                }
            })
            print(f"[+] Hazırlandı: {market} Sayfa {page_idx} ({len(page_items)} hisse)")

    # 2. Meta Belgesi
    now_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    meta_data = {
        'generated_at': market_payload.get('generated_at', now_iso),
        'errors': market_payload.get('errors', []),
        'markets': list(markets.keys()),
        'provider': 'BIST Data Service + Twelve Data EOD',
        'updatedAt': now_iso
    }
    if strategy_payload and 'result' in strategy_payload:
        meta_data['gemini'] = {
            'status': 'ready',
            'generated_at': now_iso,
            'summary': strategy_payload['result'].get('market_summary', '')
        }

    writes.append({
        'update': {
            'name': f"{base_doc_prefix}/marketSnapshots/meta",
            **to_firestore_doc(meta_data)
        }
    })

    # Firestore Batch Commit
    print(f"[*] Firestore'a {len(writes)} belge aktarılıyor...")
    commit_url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents:commit"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    resp = requests.post(commit_url, json={'writes': writes}, headers=headers, timeout=30)
    if resp.status_code != 200:
        print(f"[HATA] Firestore commit başarısız ({resp.status_code}): {resp.text}")
        sys.exit(1)

    print("[BAŞARILI] Tüm piyasa verileri ve meta bilgileri Firestore'a aktarıldı!")


if __name__ == '__main__':
    upload_snapshots()
