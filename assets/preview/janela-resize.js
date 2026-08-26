// Faixas de redimensionar da janela sem moldura — compartilhadas pelo hub e
// pelo editor. O miolo da janela é do WebView2 (outro processo): o hit-test
// nativo das bordas quase nunca chega ao pai ("só apareceu uma vez na
// esquerda", caso real 25-26/08). Então as bordas moram AQUI, na página, e o
// mousedown entrega o resize ao Windows via WindowApi.begin_resize
// (WM_NCLBUTTONDOWN + HT*), que é nativo, respeita DPI e Aero Snap.
(function () {
  "use strict";
  var B = 6;    // espessura da faixa (px CSS)
  var C = 14;   // quadrado dos cantos
  var EDGES = [
    ["top",         "n-resize",  "left:" + C + "px;right:" + C + "px;top:0;height:" + B + "px"],
    ["bottom",      "s-resize",  "left:" + C + "px;right:" + C + "px;bottom:0;height:" + B + "px"],
    ["left",        "w-resize",  "top:" + C + "px;bottom:" + C + "px;left:0;width:" + B + "px"],
    ["right",       "e-resize",  "top:" + C + "px;bottom:" + C + "px;right:0;width:" + B + "px"],
    ["topleft",     "nw-resize", "top:0;left:0;width:" + C + "px;height:" + C + "px"],
    ["topright",    "ne-resize", "top:0;right:0;width:" + C + "px;height:" + C + "px"],
    ["bottomleft",  "sw-resize", "bottom:0;left:0;width:" + C + "px;height:" + C + "px"],
    ["bottomright", "se-resize", "bottom:0;right:0;width:" + C + "px;height:" + C + "px"],
  ];

  function montar() {
    if (document.getElementById("winResize")) return;
    var wrap = document.createElement("div");
    wrap.id = "winResize";
    wrap.setAttribute("aria-hidden", "true");
    EDGES.forEach(function (e) {
      var d = document.createElement("div");
      d.dataset.edge = e[0];
      d.style.cssText = "position:fixed;z-index:2147483000;cursor:" + e[1] +
        ";background:transparent;" + e[2];
      d.addEventListener("mousedown", function (ev) {
        if (ev.button !== 0) return;
        var api = window.pywebview && window.pywebview.api;
        if (!api || !api.begin_resize) return;
        ev.preventDefault();
        ev.stopPropagation();
        api.begin_resize(e[0]);
      });
      wrap.appendChild(d);
    });
    document.body.appendChild(wrap);

    // Maximizada, a janela não redimensiona — e as faixas não podem roubar
    // os 6px da beirada (barra de rolagem, botões encostados). O hub marca
    // body.maximized; o editor não marca nada, então pergunta à API.
    function sincronizar() {
      var max = document.body.classList.contains("maximized");
      var pinta = function (on) { wrap.style.display = on ? "none" : ""; };
      if (max) { pinta(true); return; }
      var api = window.pywebview && window.pywebview.api;
      if (api && api.is_maximized) {
        Promise.resolve(api.is_maximized()).then(pinta)["catch"](function () { pinta(false); });
      } else {
        pinta(false);
      }
    }
    sincronizar();
    setInterval(sincronizar, 1500);
    new MutationObserver(sincronizar).observe(document.body, {
      attributes: true, attributeFilter: ["class"],
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", montar);
  } else {
    montar();
  }
})();
