/**
 * Contrato de fontes por marca — o campo `fontFamily` (um ID do catálogo)
 * em edit-data.json → captions/hook troca a família de TODOS os estilos.
 *
 * Os imports são estáticos (o bundler precisa deles), mas `loadFont` só é
 * CHAMADO para o id escolhido — apenas a fonte selecionada é baixada.
 * Fontes display de peso único (Anton/Bebas/Archivo Black) devolvem
 * `weight` fixo: pedir 900 numa fonte que só tem 400 renderiza negrito
 * sintético borrado, então o resolver clampa o peso.
 *
 * "auto" (ou ausência) mantém a tipografia própria de cada estilo — o
 * default continua sendo o design assinado do template, não uma fonte.
 */
import {continueRender, delayRender, staticFile} from 'remotion';
import {loadFont as loadPoppins} from '@remotion/google-fonts/Poppins';
import {loadFont as loadInter} from '@remotion/google-fonts/Inter';
import {loadFont as loadMontserrat} from '@remotion/google-fonts/Montserrat';
import {loadFont as loadPlayfair} from '@remotion/google-fonts/PlayfairDisplay';
import {loadFont as loadLora} from '@remotion/google-fonts/Lora';
import {loadFont as loadAnton} from '@remotion/google-fonts/Anton';
import {loadFont as loadBebas} from '@remotion/google-fonts/BebasNeue';
import {loadFont as loadArchivo} from '@remotion/google-fonts/ArchivoBlack';
import editData from '../public/edit-data.json';

type Resolved = {family: string; weight?: number};

const ED = editData as any;
const CAP_ID = String(ED?.captions?.fontFamily ?? '').trim().toLowerCase();
const HOOK_ID = String(ED?.hook?.fontFamily ?? '').trim().toLowerCase();

// Fonte PRÓPRIA da marca (id "arquivo"): o pipeline copia o .ttf/.otf da
// pasta ~/ATIVAVID/Fontes para public/fonts/ e aponta brandFontFile. É assim
// que fontes licenciadas que o usuário já tem (ex.: Integral do CapCut)
// entram no render sem o app precisar redistribuí-las.
const BRAND_FILE = String(ED?.brandFontFile ?? '').trim();
let brandLoaded = false;

function loadBrandFile(): Resolved | null {
  if (!BRAND_FILE) return null;
  const family = 'BrandLocal';
  if (!brandLoaded && typeof document !== 'undefined') {
    brandLoaded = true;
    const handle = delayRender('fonte da marca');
    const face = new FontFace(family, `url(${staticFile(BRAND_FILE)})`);
    face
      .load()
      .then((f) => {
        (document as any).fonts.add(f);
        continueRender(handle);
      })
      .catch(() => continueRender(handle));
  }
  // A PILHA termina em Poppins de propósito: fonte incompleta (a Integral
  // DEMO do usuário não tem NENHUM acento) caía na fonte do sistema aqui,
  // enquanto o motor próprio cobre glifo faltando com a Poppins — os dois
  // fallbacks precisam ser a MESMA fonte para os motores não divergirem.
  const reserva = loadPoppins('normal', {weights: ['400', '600', '800', '900']}).fontFamily;
  return {family: `${family}, ${reserva}`};
}

function load(id: string): Resolved | null {
  // `arquivo` ou `arquivo:<nome do arquivo>`: qual delas o pipeline já
  // decidiu ao copiar para public/fonts e apontar brandFontFile.
  if (id === 'arquivo' || id.startsWith('arquivo:')) return loadBrandFile();
  switch (id) {
    case 'poppins':
      return {family: loadPoppins('normal', {weights: ['400', '600', '800', '900']}).fontFamily};
    case 'inter':
      return {family: loadInter('normal', {weights: ['400', '600', '800', '900']}).fontFamily};
    case 'montserrat':
      return {family: loadMontserrat('normal', {weights: ['400', '600', '800', '900']}).fontFamily};
    case 'playfair':
      return {family: loadPlayfair('normal', {weights: ['400', '700', '900']}).fontFamily};
    case 'lora':
      // Lora para em 700 — clamp para não sintetizar 900
      return {family: loadLora('normal', {weights: ['400', '600', '700']}).fontFamily, weight: 700};
    case 'anton':
      return {family: loadAnton('normal', {weights: ['400']}).fontFamily, weight: 400};
    case 'bebas':
      return {family: loadBebas('normal', {weights: ['400']}).fontFamily, weight: 400};
    case 'archivo':
      return {family: loadArchivo('normal', {weights: ['400']}).fontFamily, weight: 400};
    default:
      return null;
  }
}

export const CAPTION_FONT: Resolved | null = load(CAP_ID);
export const HOOK_FONT: Resolved | null = load(HOOK_ID);

// Altura normalizada — espelho de _FATOR_ALTURA_CATALOGO no pipeline e do
// fator em _hl_linhas no motor próprio: no mesmo px a Anton tem caixa alta
// 21% maior, e um título curto (que bate no teto de px) saía mais alto só
// por causa da fonte escolhida.
const ALTURA_FATOR: Record<string, number> = {anton: 0.83};

export function hookSizeFactor(): number {
  return ALTURA_FATOR[HOOK_ID] ?? 1;
}

/** Família efetiva: a da marca quando escolhida, senão a do estilo. */
export function capFamily(styleDefault: string): string {
  return CAPTION_FONT ? CAPTION_FONT.family : styleDefault;
}

export function hookFamily(styleDefault: string): string {
  return HOOK_FONT ? HOOK_FONT.family : styleDefault;
}

/** Peso efetivo: clampa ao teto da fonte escolhida (evita negrito falso). */
export function capWeight(wanted: number): number {
  const cap = CAPTION_FONT?.weight;
  return cap != null ? Math.min(wanted, cap) : wanted;
}

export function hookWeight(wanted: number): number {
  const cap = HOOK_FONT?.weight;
  return cap != null ? Math.min(wanted, cap) : wanted;
}
