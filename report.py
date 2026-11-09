#!/usr/bin/env python3
"""Build the PDF report (in Portuguese) from results/. Needs Chromium or Google Chrome on PATH."""
import argparse
import csv
import json
import os
import shutil
import subprocess
from collections import Counter
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', '/tmp/rdv-nulos-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter
from scipy import stats

ACCENT, BLUE, INK, INK2, MUTED, GRID = '#e34948', '#2a78d6', '#0b0b0b', '#52514e', '#a8a7a1', '#e6e5e0'
plt.rcParams.update({'font.family': ['Noto Sans', 'DejaVu Sans'], 'font.size': 8.5, 'axes.edgecolor': INK2,
                     'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2,
                     'axes.spines.top': False, 'axes.spines.right': False, 'svg.fonttype': 'none'})


def br(x, d=0):
    return f'{x:,.{d}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def q(x):
    x = float(x)
    return '1' if x >= 0.9995 else ('&lt;0,001' if x < 0.001 else br(x, 3))


def rows(path):
    with path.open(encoding='utf-8') as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--results', type=Path, default=Path('results'))
    ap.add_argument('--number', default='88')
    ap.add_argument('--state', default='SP')
    a = ap.parse_args()
    R, N, ST = a.results, a.number, a.state.upper()
    rec = json.loads((R / 'reconciliation.json').read_text())
    s = json.loads((R / f'summary_{N}.json').read_text())
    nat = rows(R / 'null_numbers_brazil.csv'); NT = sum(int(r['votes']) for r in nat)
    st_list = [r for r in rows(R / 'null_numbers_by_state.csv') if r['uf'] == ST]
    stT = sum(int(r['votes']) for r in st_list)
    zones = rows(R / f'zones_{N}.csv'); placebo = rows(R / 'placebo.csv')
    ratio = rows(R / f'state_{ST}_vs_brazil.csv')
    al = s['nb_alpha_state']

    uf_votes, uf_obs = Counter(), Counter()
    for z in zones:
        uf_votes[z['uf']] += int(z['president_votes']); uf_obs[z['uf']] += int(z['observed'])
    uf_rank = {r['uf']: r['rank'] for r in rows(R / 'null_numbers_by_state.csv') if r['digits'] == N}
    uf_rate = sorted(((1000 * uf_obs[u] / uf_votes[u], u) for u in uf_votes), reverse=True)
    nat_rate = s['rate_per_1000_brazil']

    def save(fig, name):
        fig.savefig(R / name, bbox_inches='tight'); plt.close(fig); return name

    # Figure 1: funnel plot
    E = np.array([float(z['expected_state']) for z in zones]); O = np.array([int(z['observed']) for z in zones])
    m = E >= 0.3
    fig, ax = plt.subplots(figsize=(6.6, 3.4)); ax.grid(True, color=GRID, lw=0.6); ax.set_axisbelow(True)
    ax.scatter(E[m], O[m] / E[m], s=9, color=MUTED, alpha=0.55, lw=0, label='Zona eleitoral')
    eg = np.logspace(np.log10(0.3), np.log10(E.max()), 300); r = 1 / al
    for qq, ls, lab in [(0.975, '--', 'Limite 97,5% (binomial negativa)'), (0.999, '-', 'Limite 99,9% (binomial negativa)')]:
        ax.plot(eg, stats.nbinom.ppf(qq, r, r / (r + eg)) / eg, ls, color=BLUE, lw=1.4, label=lab)
    ax.axhline(1, color=INK2, lw=0.8)
    ax.set_xscale('log'); ax.set_xlim(0.3, E.max() * 1.15); ax.set_ylim(0, 14)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: br(v, 0 if v >= 1 else 1)))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: br(v, 0) + '×'))
    ax.set_xlabel(f'Votos "{N}" esperados na zona (taxa do estado)'); ax.set_ylabel('Observado / esperado')
    for j, z in enumerate([z for z in zones if float(z['expected_state']) >= 0.3][:5]):
        x, y = float(z['expected_state']), int(z['observed']) / float(z['expected_state'])
        ax.scatter([x], [y], s=22, color=ACCENT, edgecolor='white', lw=0.8, zorder=3)
        ax.annotate(f"{z['uf']} {z['zone']}", (x, y), xytext=(5, [4, 4, -2, -10, 4][j]),
                    textcoords='offset points', fontsize=7, color=INK)
    ax.legend(frameon=False, fontsize=7, loc='upper right'); f1 = save(fig, 'fig1_funil.svg')

    # Figure 2: dispersion by number
    pl = sorted(placebo, key=lambda p: float(p['nb_alpha']))
    fig, ax = plt.subplots(figsize=(6.6, 2.7)); x = np.arange(len(pl))
    ax.bar(x, [float(p['nb_alpha']) for p in pl], width=0.72,
           color=[ACCENT if p['digits'] == N else MUTED for p in pl])
    ax.set_xticks(x, [p['digits'] for p in pl], fontsize=6.5)
    ax.set_ylabel('Dispersão entre zonas (α)'); ax.grid(axis='y', color=GRID, lw=0.6); ax.set_axisbelow(True)
    ax.set_xlabel('Número digitado (nulos com pelo menos 5.000 votos no país), do mais uniforme ao mais concentrado')
    f2 = save(fig, 'fig2_dispersao.svg')

    # Figure 3: rate by state
    ur = sorted([(v, u) for v, u in uf_rate if u != 'ZZ'])
    fig, ax = plt.subplots(figsize=(6.6, 2.6)); x = np.arange(len(ur))
    ax.bar(x, [v for v, _ in ur], width=0.72, color=[ACCENT if u == ST else BLUE for _, u in ur])
    ax.axhline(nat_rate, color=INK2, lw=0.9, ls='--')
    ax.text(len(ur) - 0.5, nat_rate, f' Brasil {br(nat_rate, 3)}', va='bottom', ha='right', fontsize=7, color=INK2)
    ax.set_xticks(x, [u for _, u in ur], fontsize=7); ax.set_ylabel(f'Votos "{N}" por mil votos')
    ax.grid(axis='y', color=GRID, lw=0.6); ax.set_axisbelow(True); f3 = save(fig, 'fig3_estados.svg')

    hl = lambda c: " class='hl'" if c else ''
    top20 = lambda lst, T: '\n'.join(f"<tr{hl(r['digits'] == N)}><td>{i}</td><td>{r['digits']}</td>"
                                     f"<td>{br(int(r['votes']))}</td><td>{br(100 * int(r['votes']) / T, 1)}%</td></tr>"
                                     for i, r in enumerate(lst[:20], 1))
    t_zones = '\n'.join(
        f"<tr><td>{z['uf']}</td><td>{z['zone']}</td><td class=l>{z['municipalities'].title()[:70]}</td>"
        f"<td>{br(int(z['president_votes']))}</td><td><b>{z['observed']}</b></td>"
        f"<td>{br(float(z['expected_state']), 1)}</td><td>{br(int(z['observed']) / float(z['expected_state']), 1)}×</td>"
        f"<td>{q(z['q_poisson_state'])}</td><td><b>{q(z['q_nb_state'])}</b></td><td>{z['max_in_one_section']}</td></tr>"
        for z in zones[:12])
    by_votes = sorted(placebo, key=lambda p: -int(p['votes_brazil']))
    t_pl = '\n'.join(f"<tr{hl(p['digits'] == N)}><td>{p['digits']}</td><td>{br(int(p['votes_brazil']))}</td>"
                     f"<td>{br(float(p['nb_alpha']), 3)}</td><td>{p['zones_flagged_poisson']}</td>"
                     f"<td>{p['zones_flagged_nb']}</td></tr>"
                     for i, p in enumerate(by_votes) if i < 16 or p['digits'] == N)
    t_uf = '\n'.join(f"<tr{hl(u == ST)}><td>{u}</td><td>{br(uf_votes[u])}</td><td>{br(uf_obs[u])}</td>"
                     f"<td>{br(v, 3)}</td><td>{uf_rank.get(u, '—')}</td></tr>" for v, u in uf_rate)
    t_ratio = '\n'.join(f"<tr{hl(r['digits'] == N)}><td>{i}</td><td>{r['digits']}</td><td>{br(float(r['rate_ratio']), 2)}×</td>"
                        f"<td>{r[f'{ST}_rank_among_states']}º</td></tr>"
                        for i, r in enumerate(ratio, 1) if i <= 10 or r['digits'] == N)
    leads = [r['digits'] for r in ratio if r[f'{ST}_rank_among_states'] == '1']
    others = [d for d in leads if d != N][:4]
    st_rank = [i for i, r in enumerate(st_list, 1) if r['digits'] == N]
    st_v = next((int(r['votes']) for r in st_list if r['digits'] == N), 0)
    n_conc = s['placebo_numbers'] - 1 - s['placebo_numbers_more_uniform']

    html = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Votos nulos {N}, 2º turno 2026</title>
<style>
@page {{ size: A4; margin: 18mm 16mm; }}
body {{ font-family: 'Noto Sans', 'DejaVu Sans', sans-serif; font-size: 9.6pt; color: {INK}; line-height: 1.42; }}
h1 {{ font-size: 17pt; margin: 0 0 4pt; line-height: 1.2; }} .sub {{ color: {INK2}; font-size: 9pt; margin-bottom: 12pt; }}
h2 {{ font-size: 11.5pt; margin: 16pt 0 5pt; border-bottom: 1px solid {GRID}; padding-bottom: 2pt; }}
p {{ margin: 0 0 6pt; }} ul {{ margin: 0 0 6pt; padding-left: 14pt; }} li {{ margin-bottom: 2pt; }}
.box {{ background: #f3f6fb; border-left: 3px solid {BLUE}; padding: 8pt 10pt; margin: 6pt 0 10pt; }} .box p:last-child {{ margin: 0; }}
table {{ border-collapse: collapse; width: 100%; font-size: 8.3pt; margin: 4pt 0 8pt; font-variant-numeric: tabular-nums; }}
th, td {{ padding: 2.4pt 5pt; border-bottom: 1px solid {GRID}; text-align: right; }}
th {{ color: {INK2}; font-weight: 600; border-bottom: 1px solid {INK2}; }} td.l, th.l {{ text-align: left; }}
tr.hl td {{ background: #fde9e8; font-weight: 700; }} .two {{ display: flex; gap: 14pt; }} .two > div {{ flex: 1; }}
figure {{ margin: 6pt 0 10pt; page-break-inside: avoid; }} figure img {{ width: 100%; }}
figcaption, .small {{ font-size: 8pt; color: {INK2}; }} code {{ font-family: monospace; font-size: 7.8pt; }}
</style></head><body>
<h1>Votos nulos digitados como “{N}” no 2º turno presidencial de 2026</h1>
<div class="sub">Teste de anomalia por zona eleitoral · Registros Digitais do Voto (RDV) de todas as seções · Análise exploratória</div>
<div class="box">
<p><b>Conclusão.</b> Nenhuma zona eleitoral registrou votos “{N}” em quantidade anormal. Comparando cada uma das {br(s['zones'])} zonas com a taxa do seu estado, o teste que considera a variação normal entre zonas (binomial negativa, com correção de Benjamini–Hochberg para falsas descobertas, q &lt; 0,05) aponta <b>{s['zones_flagged_nb_state']}</b> zonas. Contra a taxa nacional, aponta {s['zones_flagged_nb_brazil']}.</p>
<p>O “{N}” também não se concentra mais do que outros números nulos. Entre os {s['placebo_numbers']} números nulos com pelo menos 5.000 votos, {n_conc} são mais concentrados geograficamente e {s['placebo_numbers_more_uniform']} são mais uniformes. Nenhuma seção tem mais de {s['max_in_one_section']} votos “{N}”.</p>
<p>{ST} tem a maior taxa de “{N}” entre os estados: {br(s[f'rate_per_1000_{ST}'], 3)} por mil votos, contra {br(nat_rate, 3)} no Brasil. Mas o padrão não é exclusivo do “{N}”. {ST} anula mais em geral e lidera também em {', '.join('“' + d + '”' for d in others)} (seção 5.1).</p>
</div>

<h2>1. Dados</h2>
<p>O RDV é o arquivo da urna que registra cada voto como foi digitado, separado por cargo e embaralhado. Ele não traz nenhuma identificação do eleitor. No RDV, o voto nulo guarda os dígitos que o eleitor digitou. O Boletim de Urna (BU) traz apenas o total de nulos. Os dois arquivos de cada seção são públicos no portal de resultados do TSE.</p>
<ul><li><b>Cobertura:</b> {br(rec['sections'])} seções do 2º turno com RDV e BU.</li>
<li><b>Conferência com o BU:</b> os votos para presidente em 13 e em 22, os brancos e os nulos do RDV coincidem com o BU da mesma urna em <b>{br(rec['rdv_equals_bu'])}</b> de {br(rec['sections'])} seções.</li>
<li><b>Nulos para presidente:</b> {br(rec['null_with_digits'])} com dígitos registrados e {br(rec['null_without_digits'])} sem dígitos. Só os nulos com dígitos entram nesta análise.</li></ul>

<h2>2. Onde o “{N}” aparece no ranking</h2>
<p>No Brasil, o “{N}” é o <b>{s['rank_brazil']}º</b> número nulo mais digitado para presidente: {br(s['votes'])} votos, ou {br(nat_rate, 3)} por mil votos para presidente. Em {ST}, é o <b>{st_rank[0] if st_rank else '—'}º</b>: {br(st_v)} votos.</p>
<div class="two"><div><b class="small">Brasil · 20 números nulos mais digitados</b>
<table><tr><th>#</th><th>Número</th><th>Votos</th><th>% dos nulos</th></tr>{top20(nat, NT)}</table></div>
<div><b class="small">{ST} · 20 números nulos mais digitados</b>
<table><tr><th>#</th><th>Número</th><th>Votos</th><th>% dos nulos</th></tr>{top20(st_list, stT)}</table></div></div>

<h2>3. Método</h2>
<ul><li><b>Unidade:</b> zona eleitoral (UF + número da zona). No exterior, todas as zonas são “0001”, por isso a unidade lá é a cidade.</li>
<li><b>Medida:</b> votos “{N}” por voto para presidente na zona, contando todos os votos (válidos, brancos e nulos). Assim, uma zona com muitos nulos em geral não é apontada só por isso.</li>
<li><b>Esperado:</b> votos para presidente da zona × taxa de “{N}” do estado (análise principal) ou × taxa nacional.</li>
<li><b>Testes unilaterais (excesso):</b> Poisson exato, que supõe votos independentes e por isso aponta zonas demais; e binomial negativa, com variância E + αE² e α estimado por momentos com todas as zonas. A binomial negativa é o teste principal.</li>
<li><b>Correção:</b> valores q de Benjamini–Hochberg entre zonas, com limite q &lt; 0,05.</li>
<li><b>Placebo:</b> os mesmos testes para os {s['placebo_numbers']} números nulos com pelo menos 5.000 votos no país.</li></ul>

<h2>4. Resultados</h2>
<table><tr><th class=l>Teste</th><th>Zonas apontadas (q &lt; 0,05)</th></tr>
<tr><td class=l>Poisson exato, taxa do estado</td><td>{s['zones_flagged_poisson_state']}</td></tr>
<tr class=hl><td class=l>Binomial negativa, taxa do estado (principal)</td><td>{s['zones_flagged_nb_state']}</td></tr>
<tr><td class=l>Binomial negativa, taxa nacional</td><td>{s['zones_flagged_nb_brazil']}</td></tr></table>
<p>O teste de Poisson aponta centenas de zonas também para números comuns (tabela 4.2), o que mostra que ele não serve sozinho para indicar anomalia. {s['zones_with_zero']} zonas não têm nenhum voto “{N}”.</p>
<figure><img src="{f1}"><figcaption><b>Figura 1.</b> Gráfico de funil: cada ponto é uma zona. As linhas azuis são os limites superiores esperados sob a binomial negativa, sem correção para múltiplas comparações. Em vermelho, as cinco zonas com menor valor p. Zonas com menos de 0,3 voto esperado (quase todas no exterior) foram omitidas do gráfico.</figcaption></figure>
<p><b>4.1 As 12 zonas mais próximas de uma anomalia</b> (menor valor p na binomial negativa).</p>
<table><tr><th>UF</th><th>Zona</th><th class=l>Municípios</th><th>Votos pres.</th><th>“{N}” obs.</th><th>Esperado</th><th>Razão</th><th>q Poisson</th><th>q BN</th><th>Máx. numa seção</th></tr>{t_zones}</table>
<p class="small">Esperado = taxa do estado × votos para presidente da zona. BN = binomial negativa.</p>
<p><b>4.2 Placebo: o “{N}” comparado aos outros números nulos.</b></p>
<figure><img src="{f2}"><figcaption><b>Figura 2.</b> Dispersão entre zonas (α da binomial negativa) por número nulo. Quanto menor o α, mais uniforme é o número pelo país.</figcaption></figure>
<table><tr><th>Número</th><th>Votos no país</th><th>α</th><th>Zonas apontadas (Poisson)</th><th>Zonas apontadas (BN)</th></tr>{t_pl}</table>
<p class="small">Os 16 números nulos mais digitados, mais o “{N}”. A tabela completa está em <code>results/placebo.csv</code>.</p>

<h2>5. Por estado</h2>
<figure><img src="{f3}"><figcaption><b>Figura 3.</b> Votos “{N}” por mil votos para presidente, por estado. {ST} em vermelho; a linha tracejada é a média nacional.</figcaption></figure>
<table><tr><th>UF</th><th>Votos pres.</th><th>Votos “{N}”</th><th>Por mil</th><th>Posição do “{N}” entre os nulos</th></tr>{t_uf}</table>
<p><b>5.1 {ST} tem a maior taxa de “{N}”. Isso é específico do “{N}”?</b> Não. A comparação por zona usa a taxa de cada estado, então o excesso do estado como um todo fica fora dela; por isso fizemos o teste em separado. {ST} anula mais em geral: {br(s['null_rate_per_1000_' + ST], 1)} nulos com dígitos por mil votos, contra {br(s['null_rate_per_1000_brazil'], 1)} no Brasil. Além disso, {ST} lidera o país em {len(leads)} dos {s['placebo_numbers']} números nulos comuns. Na razão entre a taxa de {ST} e a nacional, o “{N}” fica em {s[f'{ST}_ratio_rank']}º lugar.</p>
<table><tr><th>#</th><th>Número</th><th>Taxa {ST} ÷ taxa Brasil</th><th>Posição de {ST} entre os 27 estados</th></tr>{t_ratio}</table>

<h2>6. Limitações</h2>
<ul><li>A zona é uma unidade administrativa. Um agrupamento que atravesse zonas vizinhas, ou que fique em poucas seções de uma zona grande, pode ser diluído.</li>
<li>O α é estimado com todas as zonas juntas, o que supõe o mesmo grau de agrupamento em todo o país.</li>
<li>O RDV mostra o que foi digitado, não a intenção do eleitor. Não dá para distinguir erro de digitação de protesto ou de qualquer outro motivo.</li>
<li>Esta é uma análise exploratória. Não foi registrada antes de ver os dados.</li></ul>
</body></html>"""
    page = R / f'relatorio_{N}.html'; page.write_text(html, encoding='utf-8')
    browser = next((b for b in ('chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable') if shutil.which(b)), None)
    if not browser:
        print(f'Chromium/Chrome not found; HTML written to {page}'); return
    subprocess.run([browser, '--headless', '--no-sandbox', '--disable-gpu', '--no-pdf-header-footer',
                    f'--print-to-pdf={R / f"relatorio_{N}.pdf"}', page.resolve().as_uri()], check=True, capture_output=True)
    print(R / f'relatorio_{N}.pdf')


if __name__ == '__main__':
    main()
