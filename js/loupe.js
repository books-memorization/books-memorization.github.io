// Magnifier loupe for heatmap figures. Desktop / fine-pointer only (no touch).
(function () {
  if (!window.matchMedia || !window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;

  var ZOOM = 2;        // magnification (stays crisp: images are ~2x their displayed size)
  var LW = 90, LH = 90;   // lens size: a compact square
  var HW = LW / 2, HH = LH / 2;

  window.addEventListener("DOMContentLoaded", function () {
    var imgs = document.querySelectorAll(".figcard.zoom img");
    if (!imgs.length) return;

    var loupe = document.createElement("div");
    loupe.className = "loupe";
    loupe.style.width = LW + "px";
    loupe.style.height = LH + "px";
    document.body.appendChild(loupe);

    function hide() { loupe.style.display = "none"; }
    hide();

    function move(e, img) {
      var rect = img.getBoundingClientRect();
      var x = e.clientX - rect.left, y = e.clientY - rect.top;
      if (x < 0 || y < 0 || x > rect.width || y > rect.height) { hide(); return; }
      var fx = x / rect.width, fy = y / rect.height;

      var strips = img.getAttribute("data-loupe-strips");

      // data-plot="L,T,R,B" restricts the loupe to the data rectangle (no titles, tick
      // labels, colorbars, or padding). With per-strip bands the vertical arming is
      // governed by the strips instead, so data-plot only gates left/right there.
      var pa = img.getAttribute("data-plot");
      if (pa) {
        var b = pa.split(",");
        var outH = fx < +b[0] || fx > +b[2], outV = fy < +b[1] || fy > +b[3];
        if (outH || (!strips && outV)) { img.style.cursor = "default"; hide(); return; }
      }

      // Pick an optional vertical "fit" band:
      //  - data-loupe-strips="t1,b1;t2,b2;..." : one band per heatmap strip; use the strip
      //    under the cursor and hide in the gaps/labels between strips.
      //  - data-loupe-fit="Ttop,Tbottom"       : a single fixed band.
      // In fit mode the lens grows to that band's full magnified height and locks to it
      // vertically, sliding horizontally like a magnifier bar.
      var band = null;
      if (strips) {
        var arr = strips.split(";");
        for (var i = 0; i < arr.length; i++) {
          var s = arr[i].split(",");
          if (fy >= +s[0] && fy <= +s[1]) { band = [+s[0], +s[1]]; break; }
        }
        if (!band) { img.style.cursor = "default"; hide(); return; }
      } else {
        var fit = img.getAttribute("data-loupe-fit");
        if (fit) { var f = fit.split(","); band = [+f[0], +f[1]]; }
      }

      if (pa || strips) img.style.cursor = "zoom-in";
      loupe.style.display = "block";
      loupe.style.backgroundImage = "url('" + (img.currentSrc || img.src) + "')";
      loupe.style.backgroundSize = (rect.width * ZOOM) + "px " + (rect.height * ZOOM) + "px";
      loupe.style.width = LW + "px";

      if (band) {
        var ta = band[0], tb = band[1];
        var lh = (tb - ta) * rect.height * ZOOM;
        loupe.style.height = lh + "px";
        loupe.style.backgroundPosition = (HW - x * ZOOM) + "px " + (-ta * rect.height * ZOOM) + "px";
        loupe.style.left = (e.clientX - HW) + "px";
        loupe.style.top = (rect.top + (ta + tb) / 2 * rect.height - lh / 2) + "px";
        return;
      }

      loupe.style.height = LH + "px";
      // center the magnified point under the cursor within the lens
      loupe.style.backgroundPosition = (HW - x * ZOOM) + "px " + (HH - y * ZOOM) + "px";
      loupe.style.left = (e.clientX - HW) + "px";
      loupe.style.top = (e.clientY - HH) + "px";
    }

    imgs.forEach(function (img) {
      img.addEventListener("mousemove", function (e) { move(e, img); });
      img.addEventListener("mouseleave", hide);
    });
  });
})();
