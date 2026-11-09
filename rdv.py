"""Decoders for two urn files published by the TSE (ASN.1 BER): RDV and BU.

RDV (Registro Digital do Voto): each vote is SEQUENCE { ENUMERATED tipo, [NumericString digits] },
grouped by office; the office code is a context-tagged [1] primitive in the enclosing block.
Vote types (checked against the BU for every 2026 runoff section):
    2 = nominal (valid)   3 = blank   4 = null, with the digits typed   6 = null, no digits
Office codes: 1 = president, 3 = governor.
"""
from collections import Counter


def _tlv(b, i):
    t = b[i]; i += 1
    cls, cons, tag = t >> 6, bool(t & 0x20), t & 0x1F
    if tag == 0x1F:
        tag = 0
        while True:
            x = b[i]; i += 1
            tag = (tag << 7) | (x & 0x7F)
            if not x & 0x80:
                break
    n = b[i]; i += 1
    if n & 0x80:
        k = n & 0x7F; n = int.from_bytes(b[i:i + k], 'big'); i += k
    return cls, cons, tag, i, n          # value starts at i, length n


def _children(b, start, length):
    out, i = [], start
    while i < start + length:
        c = _tlv(b, i); out.append(c); i = c[3] + c[4]
    return out


def rdv_votes(b):
    """Count the votes in an RDV file: Counter{(office, type, digits): votes}."""
    counts = Counter()
    stack = [(0, len(b), None)]
    while stack:
        start, length, office = stack.pop()
        kids = _children(b, start, length)
        for cls, cons, tag, i, n in kids:
            if cls == 2 and tag == 1 and not cons:
                office = int.from_bytes(b[i:i + n], 'big')
        for _cls, cons, _tag, i, n in kids:
            if not cons:
                continue
            ch = _children(b, i, n)
            kinds = [(c[0], c[2]) for c in ch]
            is_vote = (0 < len(ch) <= 2 and kinds[0] == (0, 10)       # ENUMERATED
                       and all(k == (0, 18) for k in kinds[1:])        # NumericString
                       and not any(c[1] for c in ch))
            if is_vote:
                vtype = b[ch[0][3]]
                digits = b[ch[1][3]:ch[1][3] + ch[1][4]].decode() if len(ch) > 1 else ''
                counts[(office, vtype, digits)] += 1
            else:
                stack.append((i, n, office))
    return counts


def _tree(b, i, end):
    out = []
    while i < end:
        cls, cons, tag, s, n = _tlv(b, i)
        out.append((cls, cons, tag, b[s:s + n], _tree(b, s, s + n) if cons else None))
        i = s + n
    return out


def _int(node):
    return int.from_bytes(node[3], 'big')


def _ctx(nodes, tag):
    return [x for x in nodes if x[0] == 2 and x[2] == tag]


def bu_president(b):
    """President totals from a BU file: dict(votes per candidate number, blank, null, turnout)."""
    top = _tree(b, 0, len(b))[0][4]
    inner_bytes = [x for x in top if x[2] == 4 and not x[1]][0][3]
    inner = _tree(inner_bytes, 0, len(inner_bytes))[0][4]

    def elections(nodes):
        for x in nodes:
            if x[1]:
                ch = x[4]
                if ch and not ch[0][1] and ch[0][2] == 2 and len(ch) >= 5 and ch[4][1]:
                    yield x
                else:
                    yield from elections(ch)

    for el in elections(inner):
        for res in el[4][4][4]:
            r = res[4]
            turnout = _int(r[1])
            for tot in r[2][4]:
                t = tot[4]
                lists = [x for x in t if x[1] and x[2] == 16]
                if [_int(x) for x in _ctx(t, 1)] != [1] or not lists:
                    continue
                out = {'blank': 0, 'null': 0, 'turnout': turnout, 'candidates': {}}
                for item in lists[0][4]:
                    f = item[4]
                    kind, q = _int(_ctx(f, 1)[0]), _int(_ctx(f, 2)[0])
                    if kind == 1:
                        num = str(_int(_ctx(f, 3)[0][4][1]))
                        out['candidates'][num] = out['candidates'].get(num, 0) + q
                    elif kind == 2:
                        out['blank'] += q
                    elif kind == 3:
                        out['null'] += q
                return out
    raise ValueError('president not found in BU')
