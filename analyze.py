#!/usr/bin/env python3
"""Check RDV against BU, rank the null numbers, and test zones for an excess of one number.

Input: data/votes.csv and data/sections.csv (from download.py). Output in results/:
  reconciliation.json         RDV vs BU, president, every section
  null_numbers_brazil.csv     president null votes by digits typed
  null_numbers_by_state.csv
  zones_<N>.csv               every zone: observed, expected, Poisson and negative-binomial q-values
  placebo.csv                 the same zone test for every common null number
  state_<UF>_vs_brazil.csv    the chosen state's rate / national rate, for every common null number
  summary_<N>.json

Zone test: unit = zone (UF + zone number; abroad, UF ZZ + city, because every abroad zone is 0001).
Rate = votes typed as N / president votes cast. Expected = zone votes x state rate (or national).
One-sided tests: exact Poisson, and negative binomial NB2 (var = E + a E^2, a by moments over all
zones), which allows for ordinary clustering between zones. Benjamini-Hochberg q-values per test.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy import stats

PRES, NOMINAL, BLANK, NULL_DIGITS, NULL_NODIGITS = '1', '2', '3', '4', '6'


def bh(p):
    p = np.asarray(p, float); n = len(p); o = np.argsort(p)
    q = np.minimum.accumulate((p[o] * n / np.arange(1, n + 1))[::-1])[::-1]
    out = np.empty(n); out[o] = np.minimum(q, 1); return out


def nb_alpha(O, E):
    m = E > 0
    return max((((O[m] - E[m]) ** 2 - O[m]).sum()) / (E[m] ** 2).sum(), 1e-9)


def nb_sf(O, E, a):
    r = 1 / a
    return stats.nbinom.sf(O - 1, r, r / (r + E))


def write(path, header, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data', type=Path, default=Path('data'))
    ap.add_argument('--out', type=Path, default=Path('results'))
    ap.add_argument('--number', default='88')
    ap.add_argument('--state', default='SP')
    ap.add_argument('--min-total', type=int, default=5000, help='placebo: numbers with at least this many votes')
    ap.add_argument('--q', type=float, default=0.05)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    # ---- read ----
    secs, names = {}, {}
    with (a.data / 'sections.csv').open(encoding='utf-8') as f:
        for r in csv.DictReader(f):
            k = (r['uf'].upper(), r['mun'], r['zone'], r['section'])
            secs[k] = r; names[(k[0], k[1])] = r['municipality']
    pres = defaultdict(Counter)             # section -> totals from RDV
    nulls = defaultdict(Counter)            # section -> digits -> null votes
    with (a.data / 'votes.csv').open(encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['office'] != PRES:
                continue
            k = (r['uf'].upper(), r['mun'], r['zone'], r['section']); v = int(r['votes'])
            t = r['type']; pres[k]['votes'] += v
            if t == NOMINAL:
                pres[k][r['digits']] += v
            elif t == BLANK:
                pres[k]['blank'] += v
            elif t in (NULL_DIGITS, NULL_NODIGITS):
                pres[k]['null'] += v
                if t == NULL_DIGITS:
                    nulls[k][r['digits']] += v
                else:
                    pres[k]['null_nodigits'] += v
            else:
                pres[k][f'type{t}'] += v

    # ---- RDV vs BU ----
    bad = []
    for k, b in secs.items():
        c = pres[k]
        rdv = (c['13'], c['22'], c['blank'], c['null'])
        bu = tuple(int(b[x]) for x in ('bu_13', 'bu_22', 'bu_blank', 'bu_null'))
        if rdv != bu:
            bad.append({'section': k, 'rdv': rdv, 'bu': bu})
    nat = Counter(); by_uf = defaultdict(Counter)
    for k, c in nulls.items():
        nat.update(c); by_uf[k[0]].update(c)
    rec = {'sections': len(secs), 'rdv_equals_bu': len(secs) - len(bad), 'mismatches': bad[:50],
           'president_votes': sum(c['votes'] for c in pres.values()),
           'null_with_digits': sum(nat.values()),
           'null_without_digits': sum(c['null_nodigits'] for c in pres.values()),
           'other_vote_types': sum(v for c in pres.values() for kk, v in c.items() if kk.startswith('type'))}
    (a.out / 'reconciliation.json').write_text(json.dumps(rec, indent=1, ensure_ascii=False))

    T = sum(nat.values()); ranked = sorted(nat.items(), key=lambda x: (-x[1], x[0]))
    write(a.out / 'null_numbers_brazil.csv', ['rank', 'digits', 'votes', 'share_of_nulls'],
          [[i, d, v, f'{v / T:.6f}'] for i, (d, v) in enumerate(ranked, 1)])
    write(a.out / 'null_numbers_by_state.csv', ['uf', 'rank', 'digits', 'votes'],
          [[uf, i, d, v] for uf in sorted(by_uf)
           for i, (d, v) in enumerate(sorted(by_uf[uf].items(), key=lambda x: (-x[1], x[0])), 1)])

    # ---- zones ----
    zone_of = lambda k: (k[0], k[1]) if k[0] == 'ZZ' else (k[0], k[2])
    zones = sorted({zone_of(k) for k in secs}); zi = {z: i for i, z in enumerate(zones)}
    Z = len(zones); n_z = np.zeros(Z); uf_z = np.array([z[0] for z in zones])
    muns = defaultdict(set)
    for k in secs:
        n_z[zi[zone_of(k)]] += pres[k]['votes']; muns[zone_of(k)].add(names[(k[0], k[1])])

    def observed(d):
        O = np.zeros(Z)
        for k, c in nulls.items():
            if d in c:
                O[zi[zone_of(k)]] += c[d]
        return O

    def expected(O):
        E_st = np.zeros(Z)
        for u in set(uf_z):
            m = uf_z == u; E_st[m] = n_z[m] * O[m].sum() / n_z[m].sum()
        return E_st, n_z * O.sum() / n_z.sum()

    common = [d for d, v in ranked if v >= a.min_total]
    placebo = []
    for d in common:
        O = observed(d); E, _ = expected(O); al = nb_alpha(O, E)
        placebo.append([d, nat[d], round(al, 4), int((bh(stats.poisson.sf(O - 1, E)) < a.q).sum()),
                        int((bh(nb_sf(O, E, al)) < a.q).sum())])
    write(a.out / 'placebo.csv', ['digits', 'votes_brazil', 'nb_alpha', 'zones_flagged_poisson',
                                   'zones_flagged_nb'], placebo)

    d = a.number
    O = observed(d); E, E_nat = expected(O)
    al, al_nat = nb_alpha(O, E), nb_alpha(O, E_nat)
    p_nb = nb_sf(O, E, al)
    q_po, q_nb, q_nat = bh(stats.poisson.sf(O - 1, E)), bh(p_nb), bh(nb_sf(O, E_nat, al_nat))
    top = {}
    for k, c in nulls.items():
        i = zi[zone_of(k)]
        if c.get(d, 0) > top.get(i, ('', 0))[1]:
            top[i] = ('/'.join(k[1:]), c[d])
    write(a.out / f'zones_{d}.csv',
          ['uf', 'zone', 'municipalities', 'president_votes', 'observed', 'expected_state',
           'expected_brazil', 'p_nb_state', 'q_poisson_state', 'q_nb_state', 'q_nb_brazil',
           'max_section', 'max_in_one_section'],
          [[*zones[i], '; '.join(sorted(muns[zones[i]])), int(n_z[i]), int(O[i]), round(E[i], 3),
            round(E_nat[i], 3), f'{p_nb[i]:.3g}', f'{q_po[i]:.3g}', f'{q_nb[i]:.3g}', f'{q_nat[i]:.3g}',
            *top.get(i, ('', 0))] for i in np.argsort(p_nb, kind='stable')])

    # ---- one state vs Brazil, for every common number ----
    st = a.state.upper(); n_st = n_z[uf_z == st].sum(); N = n_z.sum()
    states = sorted(u for u in set(uf_z) if u != 'ZZ'); n_uf = {u: n_z[uf_z == u].sum() for u in states}
    rows = []
    for x in common:
        rates = sorted(((by_uf[u][x] / n_uf[u], u) for u in states), reverse=True)
        rows.append([x, round((by_uf[st][x] / n_st) / (nat[x] / N), 4), [u for _, u in rates].index(st) + 1])
    rows.sort(key=lambda r: -r[1])
    write(a.out / f'state_{st}_vs_brazil.csv', ['digits', 'rate_ratio', f'{st}_rank_among_states'], rows)

    summ = {'number': d, 'zones': Z, 'votes': int(O.sum()), 'rank_brazil': [x for x, _ in ranked].index(d) + 1,
            'rate_per_1000_brazil': round(1000 * O.sum() / N, 4),
            f'rate_per_1000_{st}': round(1000 * by_uf[st][d] / n_st, 4),
            'nb_alpha_state': round(al, 4), 'nb_alpha_brazil': round(al_nat, 4),
            'zones_flagged_poisson_state': int((q_po < a.q).sum()),
            'zones_flagged_nb_state': int((q_nb < a.q).sum()),
            'zones_flagged_nb_brazil': int((q_nat < a.q).sum()),
            'zones_with_zero': int((O == 0).sum()), 'max_in_one_section': int(max(v for _, v in top.values())),
            'placebo_numbers': len(common),
            'placebo_numbers_more_uniform': sum(1 for p in placebo if p[2] < round(al, 4)),
            f'{st}_ratio_rank': [r[0] for r in rows].index(d) + 1 if d in common else None,
            'null_rate_per_1000_' + st: round(1000 * sum(by_uf[st].values()) / n_st, 2),
            'null_rate_per_1000_brazil': round(1000 * T / N, 2)}
    (a.out / f'summary_{d}.json').write_text(json.dumps(summ, indent=1))
    print(json.dumps(rec | {'mismatches': len(bad)}, ensure_ascii=False))
    print(json.dumps(summ))


if __name__ == '__main__':
    main()
