// ============================================================
// RECAP PDF -- the session recap deck as a downloadable PDF
// ============================================================
// The server builds the deck as HTML slides (GET /recap_html,
// app/services/recap_deck.py) but has no browser to print it with, so the
// PDF is made here: each 1280×720 slide is drawn to a canvas (html2canvas)
// and added as one landscape page (jsPDF). Both libraries are vendored in
// static/js/ and only load the first time someone asks for a recap.

const _RECAP_LIBS = ["/static/js/html2canvas.min.js", "/static/js/jspdf.umd.min.js"];
const _RECAP_PT = [960, 540];   // 1280×720 CSS px at 0.75 pt/px
let _recapLibs = null;          // Promise once loading has started
let _recapBusy = false;

function _loadRecapLibs() {
  if (!_recapLibs) {
    _recapLibs = Promise.all(_RECAP_LIBS.map((src) => new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = resolve;
      s.onerror = () => reject(new Error("could not load " + src));
      document.head.appendChild(s);
    }))).catch((e) => { _recapLibs = null; throw e; });   // let a later tap retry
  }
  return _recapLibs;
}

// Render the deck in an off-screen iframe at its real size, so the slides lay
// out exactly as designed whatever the phone's screen width.
function _recapFrame(html) {
  return new Promise((resolve) => {
    const frame = document.createElement("iframe");
    frame.setAttribute("aria-hidden", "true");
    frame.style.cssText = "position:fixed;left:-20000px;top:0;width:1280px;height:720px;border:0;";
    // srcdoc before attaching: otherwise "load" fires first for about:blank
    frame.srcdoc = html;
    frame.onload = () => resolve(frame);
    document.body.appendChild(frame);
  });
}

async function exportRecapPdf() {
  if (!roomCode) { alert("No active session."); return; }
  if (_recapBusy) return;
  _recapBusy = true;
  showToast("📊 Building your recap…", "info", 8000);
  let frame = null;
  try {
    const [res] = await Promise.all([
      fetch("/recap_html?room_code=" + encodeURIComponent(roomCode)),
      _loadRecapLibs(),
    ]);
    if (!res.ok) throw new Error(await res.text());
    frame = await _recapFrame(await res.text());
    const doc = frame.contentDocument;
    if (doc.fonts) await doc.fonts.ready;

    const slides = Array.from(doc.querySelectorAll(".slide"));
    if (!slides.length) throw new Error("the recap came back empty");
    const pdf = new window.jspdf.jsPDF({ orientation: "landscape", unit: "pt", format: _RECAP_PT });
    for (let i = 0; i < slides.length; i++) {
      // One slide on screen at a time, so each is captured from the top
      slides.forEach((s, j) => { s.style.display = j === i ? "" : "none"; });
      const canvas = await html2canvas(slides[i], {
        scale: 1.5, backgroundColor: "#0f1117", useCORS: true, logging: false,
        windowWidth: 1280, windowHeight: 720,
      });
      if (i) pdf.addPage(_RECAP_PT, "landscape");
      pdf.addImage(canvas.toDataURL("image/jpeg", 0.9), "JPEG", 0, 0, _RECAP_PT[0], _RECAP_PT[1]);
      // The page is a picture, so lay the slide's links (the tip link) back on top
      const box = slides[i].getBoundingClientRect();
      slides[i].querySelectorAll("a[href]").forEach((a) => {
        const r = a.getBoundingClientRect();
        pdf.link((r.left - box.left) * 0.75, (r.top - box.top) * 0.75, r.width * 0.75, r.height * 0.75, { url: a.href });
      });
    }
    const day = new Date().toISOString().slice(0, 10);
    pdf.save(`recap_${roomCode}_${day}.pdf`);
    showToast("Recap downloaded");
  } catch (e) {
    showToast("Could not build the recap: " + (e.message || "try again"), "error");
  } finally {
    if (frame) frame.remove();
    _recapBusy = false;
  }
}
