#!/usr/bin/env python3
"""
BIOMAS Sync Script — Atualiza os dados de tarefas no index.html
a partir do Google Sheets.

Uso:
  python3 sync-sheets.py

Requisitos:
  pip install requests (geralmente já está disponível)

A planilha precisa estar com compartilhamento público ("Qualquer pessoa com o link").
"""

import csv
import io
import json
import re
import sys
import os

try:
    import requests
except ImportError:
    import urllib.request
    import ssl

    # Fallback sem requests
    class SimpleRequests:
        @staticmethod
        def get(url):
            ctx = ssl.create_default_context()
            resp = urllib.request.urlopen(url, context=ctx)
            raw = resp.read()
            # Google Sheets CSV is always UTF-8
            text = raw.decode('utf-8')
            return type('Response', (), {'text': text, 'status_code': resp.getcode()})()

    requests = SimpleRequests()

SHEET_ID = '1bSrKJ54O7bsil2ooBXE3KWZDaiM5fanTWk_z6lOX-3g'
CSV_URL = f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid=0'

# Path to index.html (same folder as this script)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(SCRIPT_DIR, 'index.html')

# Column mapping (CSV header -> JS field name)
COL_MAP = {
    'TASK': 'task',
    'PROJECT': 'project',
    'LIVING LAB': 'lab',
    'WHO': 'who',
    'SPRINT #': 'sprint',
    'Status': 'status',
}

# Additional detail columns
DETAIL_MAP = {
    'Perguntas que estamos tentando responder': 'pergunta',
    'Contexto': 'contexto',
    'Aprendizados': 'aprendizados',
    'Próximos passos': 'proximos',
}


def fetch_csv():
    """Fetch CSV from Google Sheets."""
    print(f"Buscando dados de: {CSV_URL[:80]}...")
    resp = requests.get(CSV_URL)
    if resp.status_code != 200:
        raise Exception(f"Erro HTTP {resp.status_code}")
    if '<!DOCTYPE' in resp.text[:200]:
        raise Exception("Planilha não está pública ou URL incorreta")
    return resp.text


def parse_tasks(csv_text):
    """Parse CSV into list of task dicts."""
    reader = csv.DictReader(io.StringIO(csv_text))
    tasks = []
    for i, row in enumerate(reader, start=1):
        task_name = (row.get('TASK') or '').strip()
        if not task_name:
            continue

        t = {'id': i}

        for csv_col, js_field in COL_MAP.items():
            val = (row.get(csv_col) or '').strip()
            if js_field == 'sprint':
                try:
                    val = int(float(val))
                except (ValueError, TypeError):
                    val = 1
            t[js_field] = val

        for csv_col, js_field in DETAIL_MAP.items():
            # Try exact match first, then fuzzy
            val = row.get(csv_col, '')
            if not val:
                for key in row:
                    if csv_col.lower()[:10] in key.lower():
                        val = row[key]
                        break
            t[js_field] = (val or '').strip()

        # Normalize status
        status_upper = t.get('status', '').upper().strip()
        valid = ['COMPLETED', 'IN PROGRESS', 'SCHEDULED', 'ON HOLD']
        if status_upper not in valid:
            t['status'] = 'IN PROGRESS'
        else:
            t['status'] = status_upper

        tasks.append(t)

    return tasks


def escape_js_string(s):
    """Escape a string for inclusion in JS source."""
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\r\n', ' ')
    s = s.replace('\r', ' ')
    s = s.replace('\n', ' ')
    s = s.replace('\t', ' ')
    # Remove any other control characters
    s = ''.join(c if ord(c) >= 32 or c in '' else ' ' for c in s)
    # Collapse multiple spaces
    while '  ' in s:
        s = s.replace('  ', ' ')
    return s.strip()


def tasks_to_js(tasks):
    """Convert task list to JS array literal."""
    lines = []
    for t in tasks:
        fields = []
        fields.append(f'id:{t["id"]}')
        for key in ['task', 'project', 'lab', 'who']:
            fields.append(f'{key}:"{escape_js_string(t.get(key, ""))}"')
        fields.append(f'sprint:{t.get("sprint", 1)}')
        fields.append(f'status:"{escape_js_string(t.get("status", "IN PROGRESS"))}"')
        for key in ['pergunta', 'contexto', 'aprendizados', 'proximos']:
            fields.append(f'{key}:"{escape_js_string(t.get(key, ""))}"')
        lines.append('    {' + ', '.join(fields) + '}')
    return '[\n' + ',\n'.join(lines) + '\n  ]'


def update_html(tasks):
    """Replace BASELINE_TASKS in index.html."""
    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    js_array = tasks_to_js(tasks)

    # Replace the BASELINE_TASKS array
    pattern = r'(const BASELINE_TASKS = )\[[\s\S]*?\];'
    replacement = f'\\1{js_array};'

    new_html, count = re.subn(pattern, replacement, html, count=1)

    if count == 0:
        raise Exception("Não encontrei BASELINE_TASKS no index.html")

    # Write as raw UTF-8 bytes to avoid any locale/encoding issues
    raw_bytes = new_html.encode('utf-8')
    # Safety check: detect double-encoding before writing
    if b'\xc3\x83\xc2' in raw_bytes:
        raise Exception("Double-encoded UTF-8 detected! Aborting to protect file.")
    with open(INDEX_PATH, 'wb') as f:
        f.write(raw_bytes)

    return count


def main():
    print("=" * 50)
    print("BIOMAS · Sync Google Sheets → index.html")
    print("=" * 50)

    try:
        csv_text = fetch_csv()
        tasks = parse_tasks(csv_text)
        print(f"Encontradas {len(tasks)} tarefas na planilha.")

        if not tasks:
            print("Nenhuma tarefa encontrada. Abortando.")
            sys.exit(1)

        update_html(tasks)
        print(f"index.html atualizado com sucesso!")
        print(f"Arquivo: {INDEX_PATH}")
        print("=" * 50)

    except Exception as e:
        print(f"ERRO: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
