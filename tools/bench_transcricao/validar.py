# -*- coding: utf-8 -*-
"""Gera a página onde uma pessoa ouve os trechos e marca o correto.

Uma página HTML por vídeo, sem servidor e sem instalar nada: abre no
navegador, o áudio toca só o trecho do ponto, a pessoa clica no que ouviu e
baixa o JSON no fim.

A ordem das opções é embaralhada por ponto, e nenhum rótulo diz de qual motor
veio cada texto. Se a pessoa souber que "aquela é a do Scribe", ela para de
ouvir e começa a votar em motor — o viés que a referência existe para não ter.
O mapa motor→texto fica no JSON de saída, para o relatório, não na tela.

A página CRONOMETRA cada trecho e conta escutas, trocas de opção e digitação.
É a única medida de retrabalho REAL do benchmark: WER e corridas de erro são
proxies, isto é relógio.

SOBRE O TEMPLATE: a montagem é por substituição de marcadores `__ASSIM__`, e
não por `str.format`. Com `format`, cada `{` do JavaScript precisa virar `{{`,
e um escape errado no meio de uma edição gera uma página que ABRE mas quebra
no primeiro erro de JavaScript — foi exatamente o que aconteceu uma vez: o
`render()` referenciava uma variável cuja declaração não fora aplicada, a
lista de trechos saía vazia e nada na tela dizia por quê. Marcador não tem
escape, então não tem como errar assim de novo.

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
<title>Validar transcrição — __VIDEO__</title>
<style>
 body{font:16px/1.5 system-ui,sans-serif;max-width:52rem;margin:2rem auto;
      padding:0 1rem;background:#111;color:#eee}
 h1{font-size:1.3rem} .p{border:1px solid #333;border-radius:8px;
      padding:1rem;margin:1rem 0;background:#1a1a1a}
 .p.ok{border-color:#2d6} .t{font-family:ui-monospace,monospace;color:#8bf}
 .ctx{color:#888;font-size:.9rem;margin:.4rem 0}
 .ctx b{color:#eee}
 label{display:block;padding:.5rem;border-radius:6px;cursor:pointer}
 label:hover{background:#252525}
 button{font:inherit;padding:.4rem .9rem;border-radius:6px;border:1px solid #444;
      background:#222;color:#eee;cursor:pointer}
 button:hover{background:#2a2a2a}
 input[type=text]{width:100%;padding:.5rem;background:#222;color:#eee;
      border:1px solid #444;border-radius:6px;font:inherit}
 #barra{position:sticky;top:0;background:#111;padding:.8rem 0;
      border-bottom:1px solid #333;z-index:9}
 #erro{background:#511;border:1px solid #944;padding:1rem;border-radius:8px;
      display:none;white-space:pre-wrap;font-family:ui-monospace,monospace}
</style></head><body>
<h1>Validar transcrição — __VIDEO__</h1>
<p class="ctx">Ouça cada trecho e marque o que a pessoa <b>realmente falou</b>.
Escreva exatamente como foi dito: se ela falou "cê", marque "cê", não "você".
Se nenhuma opção estiver certa, use <b>Outro</b>. Se não der para entender,
use <b>[inaudível]</b> — não adivinhe.</p>
<p class="ctx">Esta página cronometra quanto tempo você leva em cada trecho.
É a medida de <b>retrabalho real</b> do benchmark — trabalhe no ritmo normal,
sem pressa e sem pular.</p>
<div id="erro"></div>
<audio id="a" src="__AUDIO__" preload="auto"></audio>
<div id="barra"><span id="cont"></span> &nbsp;
  <button onclick="baixar()">Baixar decisões</button></div>
<div id="lista"></div>
<script>
const PONTOS = __PONTOS__;
const VIDEO = __VIDEO_JSON__;
const FOLGA = __FOLGA__;

// Se qualquer coisa quebrar, a pessoa PRECISA ver. Uma página que abre sem a
// lista e sem explicação custou uma rodada inteira do benchmark.
window.onerror = function (msg, src, lin, col) {
  const e = document.getElementById('erro');
  e.style.display = 'block';
  e.textContent = 'A pagina quebrou: ' + msg + ' (linha ' + lin + ')\\n' +
    'Mande esta mensagem para quem montou o benchmark.';
  return false;
};

function ler(chave, padrao) {
  try { return JSON.parse(localStorage.getItem(chave) || padrao); }
  catch (e) { return JSON.parse(padrao); }
}
function grava(chave, valor) {
  try { localStorage.setItem(chave, JSON.stringify(valor)); } catch (e) {}
}

const dec = ler('val_' + VIDEO, '{}');
const tel = ler('tel_' + VIDEO, '{}');
const a = document.getElementById('a');
let parar = null, aberto = null, desde = 0;

function reg(carimbo) {
  if (!tel[carimbo]) tel[carimbo] = {ms: 0, escutas: 0, trocas: 0, digitou: false};
  return tel[carimbo];
}
function focar(carimbo) {
  if (aberto === carimbo) return;
  fechar();
  aberto = carimbo;
  desde = Date.now();
}
function fechar() {
  if (aberto === null) return;
  reg(aberto).ms += Date.now() - desde;
  grava('tel_' + VIDEO, tel);
  aberto = null;
}
window.addEventListener('beforeunload', fechar);

function tocar(ini, fim, carimbo) {
  focar(carimbo);
  reg(carimbo).escutas += 1;
  grava('tel_' + VIDEO, tel);
  a.currentTime = Math.max(0, ini - FOLGA);
  a.play();
  clearTimeout(parar);
  parar = setTimeout(function () { a.pause(); }, (fim - ini + FOLGA * 2) * 1000);
}

function marcar(carimbo, texto) {
  focar(carimbo);
  if (dec[carimbo] !== undefined && dec[carimbo] !== texto) reg(carimbo).trocas += 1;
  fechar();
  dec[carimbo] = texto;
  grava('val_' + VIDEO, dec);
  render();
}

function outro(carimbo) {
  const v = document.getElementById('o_' + carimbo).value.trim();
  if (!v) return;
  reg(carimbo).digitou = true;
  marcar(carimbo, v);
}

function baixar() {
  fechar();
  const dados = {video: VIDEO, decisoes: dec, telemetria: tel};
  const b = new Blob([JSON.stringify(dados, null, 2)], {type: 'application/json'});
  const u = URL.createObjectURL(b), l = document.createElement('a');
  l.href = u; l.download = 'validacao_' + VIDEO + '.json';
  document.body.appendChild(l); l.click(); l.remove(); URL.revokeObjectURL(u);
}

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                  .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function render() {
  const feitos = PONTOS.filter(function (p) {
    return dec[p.carimbo] !== undefined;
  }).length;
  let ms = 0;
  for (const k in tel) ms += (tel[k].ms || 0);
  document.getElementById('cont').textContent =
    feitos + ' de ' + PONTOS.length + ' trechos marcados · ' +
    (ms / 60000).toFixed(1) + ' min de trabalho';

  document.getElementById('lista').innerHTML = PONTOS.map(function (p) {
    const sel = dec[p.carimbo];
    const nome = 'r_' + p.carimbo.replace(/[^0-9a-z]/gi, '');
    const ops = p.candidatos.map(function (c) {
      const marcado = (sel === c) ? ' checked' : '';
      return '<label><input type="radio" name="' + nome + '"' + marcado +
        ' onchange="marcar(' + esc(JSON.stringify(p.carimbo)) + ',' +
        esc(JSON.stringify(c)) + ')"> ' + esc(c) + '</label>';
    }).join('');
    const digitado = (sel !== undefined && p.candidatos.indexOf(sel) < 0);
    return '<div class="p' + (sel !== undefined ? ' ok' : '') + '">' +
      '<button onclick="tocar(' + p.inicio + ',' + p.fim + ',' +
        esc(JSON.stringify(p.carimbo)) + ')">▶ ouvir</button> ' +
      '<span class="t">' + esc(p.carimbo) + '</span>' +
      '<div class="ctx">…' + esc(p.contexto_antes) + ' <b>[ ? ]</b> ' +
        esc(p.contexto_depois) + '…</div>' + ops +
      '<label><input type="radio" name="' + nome + '"' +
        (digitado ? ' checked' : '') + '> Outro:</label>' +
      '<input type="text" id="o_' + p.carimbo + '" value="' +
        (digitado ? esc(sel) : '') + '" onblur="outro(' +
        esc(JSON.stringify(p.carimbo)) + ')" ' +
        'placeholder="escreva o que ouviu">' +
    '</div>';
  }).join('');
}

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

    corpo = (_MODELO
             .replace("__VIDEO_JSON__", json.dumps(video_id))
             .replace("__VIDEO__", html.escape(video_id))
             .replace("__AUDIO__", html.escape(
                 audio.as_uri() if audio.is_absolute() else str(audio)))
             .replace("__PONTOS__", json.dumps(dados, ensure_ascii=False))
             .replace("__FOLGA__", repr(float(folga))))

    saida.mkdir(parents=True, exist_ok=True)
    destino = saida / f"validar_{video_id}.html"
    destino.write_text(corpo, encoding="utf-8")

    # O mapa motor→texto NÃO vai para a página (viés), mas o relatório precisa.
    (saida / f"propostas_{video_id}.json").write_text(json.dumps(
        {p.carimbo(): p.propostas for p in pontos},
        ensure_ascii=False, indent=2), encoding="utf-8")
    return destino
