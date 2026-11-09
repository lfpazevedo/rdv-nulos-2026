#!/usr/bin/env python3
"""Download the RDV and BU of every 2026 runoff section from the TSE and count the votes.

For each state: the section list (config/<uf>-p003221-cs.json). For each section that is not
aggregated into another: aux.json -> file hash -> <id>-rdv.dat and <id>-bu.dat.
Raw files go to data/raw/<uf>/ (skipped if already there). Output:
  data/votes.csv     one row per (section, office, vote type, digits) with the RDV count
  data/sections.csv  one row per finished section, with the BU president totals
  data/errors.jsonl  sections that could not be processed
Safe to interrupt and run again: it resumes where it stopped.
"""
import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

from rdv import bu_president, rdv_votes

BASE = 'https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3221'
UFS = 'ac al ap am ba ce df es go ma mt ms mg pa pb pr pe pi rj rn rs ro rr sc sp se to zz'.split()
UA = 'rdv-nulos-2026/1.0 (pesquisa academica)'


def get(url, tries=3):
    for k in range(tries):
        try:
            with urlopen(Request(url, headers={'User-Agent': UA}), timeout=60) as r:
                return r.read()
        except Exception:
            if k == tries - 1:
                raise


def cached(url, path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.part'); tmp.write_bytes(get(url)); tmp.replace(path)
    return path.read_bytes()


def section_list(uf, data):
    tree = json.loads(cached(f'{BASE}/config/{uf}/{uf}-p003221-cs.json', data / 'config' / f'{uf}.json'))
    for ab in tree['abr']:
        for mu in ab['mu']:
            for z in mu['zon']:
                for s in z['sec']:
                    if 'nsp' not in s:            # aggregated sections have no files of their own
                        yield uf, mu['cd'], mu['nm'], z['cd'], s['ns']


def process(sec, data):
    uf, mun, _name, zone, num = sec
    base = f'{BASE}/dados/{uf}/{mun}/{zone}/{num}'
    aux = json.loads(get(f'{base}/p003221-{uf}-m{mun}-z{zone}-s{num}-aux.json'))
    hashes = sorted(aux.get('hashes', []), key=lambda h: h.get('st') != 'Totalizado')
    for h in hashes:
        files = {a['tp']: a['nm'] for a in h.get('arq', [])}
        if 'rdv' in files and 'bu' in files:
            rdv = cached(f"{base}/{h['hash']}/{files['rdv']}", data / 'raw' / uf / files['rdv'])
            bu = cached(f"{base}/{h['hash']}/{files['bu']}", data / 'raw' / uf / files['bu'])
            return rdv_votes(rdv), bu_president(bu)
    raise ValueError('no RDV/BU listed in aux.json')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--uf', action='append', choices=UFS, help='repeatable; default: all')
    ap.add_argument('--data', type=Path, default=Path('data'))
    ap.add_argument('--threads', type=int, default=32)
    a = ap.parse_args()
    a.data.mkdir(parents=True, exist_ok=True)
    votes_p, secs_p = a.data / 'votes.csv', a.data / 'sections.csv'
    key = lambda r: tuple(r[:4])

    done = set()
    if secs_p.exists():
        with secs_p.open(encoding='utf-8') as f:
            done = {key(r) for r in list(csv.reader(f))[1:]}
    if votes_p.exists():   # drop vote rows of sections that never reached sections.csv
        with votes_p.open(encoding='utf-8') as f:
            rows = list(csv.reader(f))
        keep = [rows[0]] + [r for r in rows[1:] if key(r) in done]
        if len(keep) < len(rows):
            with votes_p.open('w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerows(keep)

    todo = [s for uf in (a.uf or UFS) for s in section_list(uf, a.data)
            if (s[0], s[1], s[3], s[4]) not in done]
    print(f'{len(todo)} sections to process ({len(done)} done)', flush=True)

    new_v, new_s = not votes_p.exists(), not secs_p.exists()
    errors = 0
    with votes_p.open('a', newline='', encoding='utf-8') as fv, \
            secs_p.open('a', newline='', encoding='utf-8') as fs, \
            (a.data / 'errors.jsonl').open('a', encoding='utf-8') as fe, \
            ThreadPoolExecutor(a.threads) as ex:
        wv, ws = csv.writer(fv), csv.writer(fs)
        if new_v:
            wv.writerow(['uf', 'mun', 'zone', 'section', 'office', 'type', 'digits', 'votes'])
        if new_s:
            ws.writerow(['uf', 'mun', 'zone', 'section', 'municipality',
                         'bu_13', 'bu_22', 'bu_blank', 'bu_null', 'bu_turnout'])

        def job(sec):
            try:
                return sec, process(sec, a.data), None
            except Exception as e:  # noqa: BLE001
                return sec, None, repr(e)[:200]

        for n, (sec, res, err) in enumerate(ex.map(job, todo), 1):
            uf, mun, name, zone, num = sec
            if err:
                errors += 1
                fe.write(json.dumps({'section': [uf, mun, zone, num], 'error': err}) + '\n')
            else:
                votes, bu = res
                for (office, vtype, digits), v in sorted(votes.items(), key=lambda x: str(x[0])):
                    wv.writerow([uf, mun, zone, num, office, vtype, digits, v])
                fv.flush()   # vote rows first, then the "done" row
                c = bu['candidates']
                ws.writerow([uf, mun, zone, num, name, c.get('13', 0), c.get('22', 0),
                             bu['blank'], bu['null'], bu['turnout']])
                fs.flush()
            if n % 1000 == 0:
                print(f'{n}/{len(todo)} (errors: {errors})', flush=True)
    print(f'finished: {len(todo) - errors} sections, {errors} errors (see data/errors.jsonl)', file=sys.stderr)


if __name__ == '__main__':
    main()
