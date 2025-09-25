/*
  Minimal EAN-13 SVG renderer for Hango (no dependencies).
  Renders all <svg class="ean13" data-token="..."> elements.
  Author: ChatGPT (MIT-licensed snippet)
*/
(function() {
  "use strict";

  var L = ["0001101","0011001","0010011","0111101","0100011","0110001","0101111","0111011","0110111","0001011"];
  var G = ["0100111","0110011","0011011","0100001","0011101","0111001","0000101","0010001","0001001","0010111"];
  var R = ["1110010","1100110","1101100","1000010","1011100","1001110","1010000","1000100","1001000","1110100"];
  var PARITY = {
    "0": "LLLLLL",
    "1": "LLGLGG",
    "2": "LLGGLG",
    "3": "LLGGGL",
    "4": "LGLLGG",
    "5": "LGGLLG",
    "6": "LGGGLL",
    "7": "LGLGLG",
    "8": "LGLGGL",
    "9": "LGGLGL"
  };

  function computeCheck(n12) {
    var s = 0;
    for (var i = 0; i < 12; i++) {
      var d = n12.charCodeAt(i) - 48;
      s += (i % 2 === 0) ? d : d * 3;
    }
    return (10 - (s % 10)) % 10;
  }

  function encodeEAN13(n13) {
    if (!/^\d{13}$/.test(n13)) throw new Error("EAN13 needs 13 digits");
    // Optional: verify check digit, but do not reject to avoid UX friction
    try {
      var cd = computeCheck(n13.slice(0,12));
      // if (cd !== (n13.charCodeAt(12) - 48)) console.warn("EAN-13 check digit mismatch");
    } catch (e) {}

    var first = n13[0];
    var pattern = "101"; // start guard
    var parity = PARITY[first];
    // left 6 digits (1..6 mapped from n13[1..6])
    for (var i=1; i<=6; i++) {
      var d = n13.charCodeAt(i) - 48;
      var enc = parity[i-1] === "L" ? L[d] : G[d];
      pattern += enc;
    }
    pattern += "01010"; // middle guard
    // right 6 digits (7..12 mapped from n13[7..12])
    for (var j=7; j<=12; j++) {
      var d2 = n13.charCodeAt(j) - 48;
      pattern += R[d2];
    }
    pattern += "101"; // end guard
    return pattern;
  }

  function renderToSvg(svg, n13, opts) {
    opts = opts || {};
    var module = +opts.module || 2; // px per module
    var height = +opts.height || 60; // bar height px
    var margin = +opts.margin || 10 * module; // quiet zone

    // clear svg
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var pattern = encodeEAN13(n13);
    var width = margin*2 + pattern.length * module;
    svg.setAttribute("width", width);
    svg.setAttribute("height", height + 18);
    svg.setAttribute("viewBox", "0 0 " + width + " " + (height + 18));
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "EAN-13 " + n13);
    // Background (white) so barcode stays readable on dark themes
    var bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    bg.setAttribute("x", 0);
    bg.setAttribute("y", 0);
    bg.setAttribute("width", width);
    bg.setAttribute("height", height + 18);
    bg.setAttribute("fill", "#ffffff");
    svg.appendChild(bg);

    var x = margin;
    for (var i=0; i<pattern.length; i++) {
      if (pattern[i] === "1") {
        var rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rect.setAttribute("x", x);
        rect.setAttribute("y", 0);
        rect.setAttribute("width", module);
        rect.setAttribute("height", height);
        rect.setAttribute("fill", "#000000");
        rect.setAttribute("shape-rendering", "crispEdges");
        svg.appendChild(rect);
      }
      x += module;
    }
    // Text under
    var txt = document.createElementNS("http://www.w3.org/2000/svg", "text");
    txt.setAttribute("x", width / 2);
    txt.setAttribute("y", height + 14);
    txt.setAttribute("font-family", "monospace");
    txt.setAttribute("font-size", "12");
    txt.setAttribute("text-anchor", "middle");
    txt.setAttribute("fill", "#000000");
    txt.textContent = n13;
    svg.appendChild(txt);
  }

  function renderAll() {
    var nodes = document.querySelectorAll("svg.ean13[data-token]");
    nodes.forEach(function(svg){
      var token = svg.getAttribute("data-token") || "";
      if (/^\d{12}$/.test(token)) {
        // auto-append check digit if omitted
        var cd = computeCheck(token);
        token = token + String(cd);
        svg.setAttribute("data-token", token);
      }
      if (!/^\d{13}$/.test(token)) return;
      renderToSvg(svg, token, {});
    });
  }

  // Public APIs
  window.renderEAN13 = renderToSvg;
  window.renderAllEAN13 = renderAll;

  if (document.readyState === "complete" || document.readyState === "interactive") {
    setTimeout(renderAll, 0);
  } else {
    document.addEventListener("DOMContentLoaded", renderAll);
  }
})();