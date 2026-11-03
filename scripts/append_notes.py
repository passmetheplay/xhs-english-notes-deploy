#!/usr/bin/env python3
"""Append a selected batch using the shared exporter, preserving archived notes.

The original Markdown library is unavailable on this machine. Existing note
records, HTML sections and image bytes therefore come from a verified baseline.
No old source content or provenance is reconstructed or overwritten.
"""
import argparse
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exporter', required=True, type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--note', action='append', required=True)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('xhs_exporter', args.exporter)
    exporter = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = exporter
    spec.loader.exec_module(exporter)
    root = args.root.resolve()
    baseline = json.loads((args.baseline / 'publish-manifest.json').read_text())
    html = (args.baseline / 'index.html').read_text()
    # Verify archived image bytes before using their metadata.
    for record in baseline['notes']:
        for image in record['images']:
            for kind in ('original', 'web'):
                entry = image[kind]
                exporter.verify_hash(root / entry['path'], entry['sha256'], entry['path'])
    sections = dict(re.findall(r'<section class="note" id="([^"]+)">(.*?)</section>', html, re.S))
    notes = []
    for record in baseline['notes']:
        section = sections[record['id']]
        match = re.search(r'<div class="body-text">(.*?)</div>\s*<div class="images">', section, re.S)
        if not match:
            raise RuntimeError('Cannot preserve body for ' + record['id'])
        notes.append(SimpleNamespace(order=record['order'], note_id=record['id'],
                     title=record['title'], account=record['account'],
                     body_html=match.group(1), images=record['images']))
    new_notes = []
    for order, relative in enumerate(args.note, len(notes) + 1):
        path = exporter.path_within(root / relative, root)
        new_notes.append(exporter.parse_note(path, root, order, 5, 1086, 1448, False))
    ids = [n.note_id for n in notes + new_notes]
    if len(ids) != len(set(ids)):
        raise RuntimeError('Duplicate note IDs')
    if args.dry_run:
        print(json.dumps({'preserved': len(notes), 'added': [n.note_id for n in new_notes],
                          'new_images': sum(len(n.images) for n in new_notes)}, ensure_ascii=False))
        return
    records = copy.deepcopy(baseline['notes'])
    files = set(baseline['generated_files'])
    for note in new_notes:
        images = []
        for image in note.images:
            original = f'notes/{note.note_id}/original/{image.filename}'
            web = f'notes/{note.note_id}/web/{Path(image.filename).stem}.webp'
            exporter.copy_exact(image.path, root / original)
            exporter.create_webp(image.path, root / web, 82)
            files.update((original, web))
            images.append({'filename': image.filename, 'alt': image.alt,
                'source': image.source_relative, 'width': image.width, 'height': image.height,
                'source_sha256': image.sha256,
                'original': {'path': original, 'size': image.size, 'sha256': image.sha256},
                'web': {'path': web, 'size': (root / web).stat().st_size,
                        'sha256': exporter.sha256_file(root / web), 'format': 'webp', 'quality': 82}})
        records.append({'order': note.order, 'id': note.note_id, 'source_note': note.source_relative,
            'source_note_sha256': note.source_sha256, 'title': note.title, 'account': note.account,
            'style': note.style, 'status': note.status, 'fingerprint': exporter.fingerprint_note(note),
            'images': images})
    notes += new_notes
    site = copy.deepcopy(baseline['site'])
    generated_at = exporter.utc_now()
    local_date = datetime.fromisoformat(generated_at.replace('Z', '+00:00')).astimezone(
        timezone(timedelta(hours=8))
    ).date()
    site.update(title=f'小红书英语口语｜{len(notes)}篇',
                subtitle=f'小黑人场景英语 · 新增{len(new_notes)}篇 · {local_date}')
    new_html = exporter.render_site(site, notes, records, generated_at)
    rendered = dict(re.findall(r'<section class="note" id="([^"]+)">(.*?)</section>', new_html, re.S))
    for key, section in sections.items():
        if rendered[key] != section:
            raise RuntimeError('Archived note HTML changed: ' + key)
    stable = {'schema_version': exporter.SCHEMA_VERSION, 'generator_version': exporter.GENERATOR_VERSION,
              'site': site, 'notes': records}
    original_bytes = sum(i['original']['size'] for n in records for i in n['images'])
    webp_bytes = sum(i['web']['size'] for n in records for i in n['images'])
    manifest = {**stable, 'generated_at': generated_at,
        'output_digest': exporter.sha256_bytes(exporter.canonical_json(stable)),
        'source_root_hint': 'sources', 'changes': exporter.change_summary(baseline, records),
        'totals': {'notes': len(records), 'images': sum(len(n['images']) for n in records),
                   'original_bytes': original_bytes, 'webp_bytes': webp_bytes,
                   'savings_percent': 100 * (1 - webp_bytes / original_bytes)}}
    exporter.atomic_write_text(root / 'index.html', new_html)
    exporter.atomic_write_text(root / exporter.REPORT_NAME, exporter.build_report(manifest))
    if args.record:
        manifest['history_record_appended'] = exporter.append_history(root / exporter.HISTORY_NAME, manifest)
        files.add(exporter.HISTORY_NAME)
    manifest['generated_files'] = sorted(files)
    manifest['artifacts'] = {name: exporter.sha256_file(root / name) for name in
        ('index.html', 'assets/site.css', 'assets/site.js', exporter.REPORT_NAME, exporter.HISTORY_NAME)}
    exporter.atomic_write_text(root / exporter.MANIFEST_NAME,
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'totals': manifest['totals'], 'changes': manifest['changes'],
                      'archived_html_preserved': len(sections)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
