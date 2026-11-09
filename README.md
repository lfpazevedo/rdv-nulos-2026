# Votos nulos no 2º turno de 2026: quais números foram digitados?

Na urna eletrônica, quem digita um número que não pertence a nenhum candidato vota nulo. O Boletim de
Urna (BU) só informa o total de nulos. Já o **Registro Digital do Voto (RDV)**, arquivo público de cada
urna, guarda cada voto exatamente como foi digitado, sem identificação do eleitor e em ordem embaralhada.
Por isso o RDV mostra **qual número** foi digitado em cada voto nulo.

Este repositório baixa o RDV e o BU de todas as seções do 2º turno presidencial de 2026, confere um
contra o outro e testa se alguma zona eleitoral digitou um número (por padrão, o **88**) com frequência
anormal.

**Relatório (PDF):** [`results/relatorio_88.pdf`](results/relatorio_88.pdf)

## Reproduzir

Requer Python 3.10+ e cerca de 3 GB de disco. O relatório em PDF também precisa de Chromium ou Google Chrome.

```bash
pip install -r requirements.txt
python -m unittest discover tests   # decodificadores, com uma seção real (segundos)
python download.py                  # todas as seções do TSE (algumas horas; pode interromper e retomar)
python analyze.py                   # conferência e testes (segundos)
python report.py                    # gera results/relatorio_88.pdf
```

* `download.py --uf sp` baixa um estado só (a opção pode ser repetida).
* `analyze.py --number 99 --state RJ` testa outro número e outro estado.
* `report.py --number 99 --state RJ` gera o relatório correspondente.

## Arquivos

| Arquivo | O que faz |
|---|---|
| `rdv.py` | Decodifica o RDV (votos por cargo, tipo e dígitos) e o BU (totais para presidente). |
| `download.py` | Lê a lista oficial de seções de cada estado e baixa o RDV e o BU de cada seção. Os arquivos brutos ficam em `data/raw/`; as contagens, em `data/votes.csv` e `data/sections.csv`. |
| `analyze.py` | Confere o RDV contra o BU, ranqueia os números nulos e faz os testes por zona. Grava em `results/`. |
| `report.py` | Monta o relatório em PDF a partir de `results/`. |
| `tests/` | Teste dos decodificadores, com o RDV e o BU de uma seção (BA 30007/0205/0177). |

## Método, em resumo

* **Unidade:** zona eleitoral (UF + zona). No exterior, a unidade é a cidade, porque todas as zonas lá são “0001”.
* **Medida:** votos no número testado por voto para presidente na zona.
* **Esperado:** votos da zona × taxa do estado (análise principal) ou × taxa nacional.
* **Testes unilaterais:** Poisson exato e binomial negativa (variância E + αE², com α estimado por momentos). A binomial negativa é o teste principal, porque leva em conta a variação normal entre zonas. Os valores q são de Benjamini–Hochberg.
* **Placebo:** o mesmo teste para todos os números nulos com pelo menos 5.000 votos no país.
* **Estado:** a razão entre a taxa do estado escolhido e a nacional, para cada número nulo comum.

Tipos de voto no RDV, conferidos contra o BU: 2 = nominal, 3 = branco, 4 = nulo com dígitos, 6 = nulo sem dígitos.

## Fonte e limites

* **Fonte:** portal de resultados do TSE (`resultados.tse.jus.br`), arquivos de urna do 2º turno (código `3221` nas URLs). Os dados são públicos e não identificam eleitores.
* **Intenção:** o RDV mostra o que foi digitado, não a intenção do eleitor. Não dá para distinguir erro de digitação de protesto.
* **Escopo:** esta é uma análise exploratória, não registrada antes de ver os dados.

---

*English summary:* the RDV file published for every Brazilian voting machine stores each vote as typed, including the digits of null votes. This repo downloads the RDV and BU for every 2026 presidential runoff section, checks them against each other, ranks the numbers typed in null votes, and tests whether any electoral zone typed a given number (default 88) unusually often, using Poisson and negative-binomial tests with a placebo across other numbers.
