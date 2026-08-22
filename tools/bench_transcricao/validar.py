# -*- coding: utf-8 -*-
"""Gera a página onde uma pessoa ouve os trechos e marca o correto.

Uma página HTML por vídeo, sem servidor e sem instalar nada: abre no
navegador, o áudio toca só o trecho do ponto, a pessoa clica no que ouviu e
baixa o JSON no fim. Foi o caminho mais curto entre "os motores discordam" e
"existe referência humana".

A ordem das opções é embaralhada por ponto, e nenhum rótulo diz de qual motor
veio cada texto. Se a pessoa souber que "aquela é a do Scribe", ela para de
ouvir e começa a votar em motor — que é justamente o viés que a referência
existe para não ter. O mapa motor→texto fica no JSON de saída, para o
relatório, não na tela.

Uso:
    python tools/bench_transcricao/validar.py <video_id> --saida validacao/
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from tools.bench_transcricao.discordancia import Ponto

_MODELO = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Validar transcrição — {video}</title>
<style>
 body{{font:16px/1.5 system-ui,sans-serif;max-width:52rem;margin:2rem auto;
      padding:0 1rem;background:#111;color:#eee}}
 h1{{font-size:1.3rem}} .p{{border:1px solid #333;border-radius:8px;
      padding:1rem;margin:1rem 0;background:#1a1a1a}}
 .p.ok{{border-color:#2d6}} .t{{font-family:ui-monospace,monospace;color:#8bf}}
 .ctx{{color:#888;font-size:.9rem;margin:.4rem 0}}
 .ctx b{{color:#eee}}
 label{{display:block;padding:.5rem;border-radius:6px;cursor:pointer}}
 label:hover{{background:#252525}}
 button{{font:inherit;padding:.4rem .9rem;border-radius:6px;border:1px solid #444;
      background:#222;color:#eee;cursor:pointer}}
 button:hover{{background:#2a2a2a}}
 input[type=text]{{width:100%;padding:.5rem;background:#222;color:#eee;
      border:1px solid #444;border-radius:6px;font:inherit}}
 #barra{{position:sticky;top:0;background:#111;padding:.8rem 0;
      border-bottom:1px solid #333;z-index:9}}
</style></head><body>
<h1>Validar transcrição — {video}</h1>
<p class="ctx">Ouça cada trecho e marque o que a pessoa <b>realmente falou</b>.
Escreva exatamente como foi dito: se ela falou "cê", marque "cê", não "você".
Se nenhuma opção estiver certa, use <b>Outro</b>. Se não der para entender,
use <b>[inaudível]</b> — não adivinhe.</p>
<p class="ctx">Esta página cronometra quanto tempo você leva em cada trecho.
É a medida de <b>retrabalho real</b> do benchmark — trabalhe no ritmo normal,
sem pressa e sem pular.</p>
<audio id="a" src="{audio}" preload="auto"></audio>
<div id="barra"><span id="cont"></span> &nbsp; <button onclick="baixar()">Baixar decisões</button></div>
<div id="lista"></div>
<script>
const PONTOS = {pontos};
const VIDEO = {video_json};
const dec = JSON.parse(localStorage.getItem('val_'+VIDEO) || '{{}}');
const a = document.getElementById('a');
let parar = null;

function tocar(ini, fim) {{
  a.currentTime = Math.max(0, ini - {folga});
  a.play();
  clearTimeout(parar);
  parar = setTimeout(() => a.pause(), (fim - ini + {folga} * 2) * 1000);
}}

function marcar(carimbo, texto) {{
  dec[carimbo] = texto;
  localStorage.setItem('val_' + VIDEO, JSON.stringify(dec));
  render();
}}

function outro(carimbo) {{
  const v = document.getElementById('o_' + carimbo).value.trim();
  if (v) marcar(carimbo, v);
}}

function baixar() {{
  const b = new Blob([JSON.stringify({{video: VIDEO, decisoes: dec}}, null, 2)],
                     {{type: 'application/json'}});
  const u = URL.createObjectURL(b), l = document.createElement('a');
  l.href = u; l.download = 'validacao_' + VIDEO + '.json';
  document.body.appendChild(l); l.click(); l.remove(); URL.revokeObjectURL(u);
}}

function render() {{
  const feitos = PONTOS.filter(p => dec[p.carimbo] !== undefined).length;
  const ms = Object.values(tel).reduce((s, t) => s + (t.ms || 0), 0);
  document.getElementById('cont').textContent =
    feitos + ' de ' + PONTOS.length + ' trechos marcados · ' +
    (ms / 60000).toFixed(1) + ' min de trabalho';
  document.getElementById('lista').innerHTML = PONTOS.map(p => {{
    const esc = s => s.replace(/[&<>"]/g, c =>
      ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}})[c]);
    const sel = dec[p.carimbo];
    const ops = p.candidatos.map((c, i) => `
      <label><input type="radio" name="r_${{p.carimbo}}" ${{sel === c ? 'checked' : ''}}
        onchange="marcar('${{p.carimbo}}', ${{JSON.stringify(c).replace(/"/g, '&quot;')}})">
        ${{esc(c)}}</label>`).join('');
    return `<div class="p ${{sel !== undefined ? 'ok' : ''}}">
      <button onclick="tocar(${{p.inicio}}, ${{p.fim}}, '${{p.carimbo}}')">▶ ouvir</button>
      <span class="t">${{p.carimbo}}</span>
      <div class="ctx">…${{esc(p.contexto_antes)}} <b>[ ? ]</b> ${{esc(p.contexto_depois)}}…</div>
      ${{ops}}
      <label><input type="radio" name="r_${{p.carimbo}}"
        ${{sel !== undefined && !p.candidatos.includes(sel) ? 'checked' : ''}}>
        Outro:</label>
      <input type="text" id="o_${{p.carimbo}}"
        value="${{sel !== undefined && !p.candidatos.includes(sel) ? esc(sel) : ''}}"
        onblur="outro('${{p.carimbo}}')" placeholder="escreva o que ouviu">
    </div>`;
  }}).join('');
}}
render();
</script></body></html>
"""


def _embaralhar(candidatos: list[str], semente: str) -> list[str]:
    """Ordem estável por ponto, mas sem relação com a ordem dos motores.

    `random` não entra: a página precisa dar a mesma ordem se for reaberta,
    senão a pessoa perde a referência visual no meio do trabalho.
    """
    return sorted(candidatos, key=lambda c: hash((semente, c)) & 0xFFFFFFFF)


def gerar(video_id: str, audio: Path, pontos: list[Ponto], saida: Path,
          folga: float = 1.2) -> Path:
    dados = [{
        "carimbo": p.carimbo(),
        "inicio": round(p.inicio, 3),
        "fim": round(p.fim, 3),
        "candidatos": _embaralhar(p.candidatos, p.carimbo()),
        "contexto_antes": p.contexto_antes,
        "contexto_depois": p.contexto_depois,
    } for p in pontos]

    saida.mkdir(parents=True, exist_ok=True)
    destino = saida / f"validar_{video_id}.html"
    destino.write_text(_MODELO.format(
        video=html.escape(video_id),
        video_json=json.dumps(video_id),
        audio=html.escape(audio.as_uri() if audio.is_absolute() else str(audio)),
        pontos=json.dumps(dados, ensure_ascii=False),
        folga=folga,
    ), encoding="utf-8")

    # O mapa motor→texto NÃO vai para a página (viés), mas o relatório precisa.
    (saida / f"propostas_{video_id}.json").write_text(json.dumps(
        {p.carimbo(): p.propostas for p in pontos},
        ensure_ascii=False, indent=2), encoding="utf-8")
    return destino
