// ============================================================
// RECAP PDF -- the session recap deck as a downloadable PDF
// ============================================================
// The server builds the deck as HTML slides (GET /recap_html,
// app/services/recap_deck.py) but has no browser to print it with, so the
// PDF is made here: each 1280×720 slide is drawn to a canvas (html2canvas)
// and added as one landscape page (jsPDF). Both libraries are vendored in
// static/js/ and only load the first time someone asks for a recap.
//
// Saving: desktops download the file. Phones get the share sheet (Save to
// Files, AirDrop, WhatsApp...) instead: iOS can't download a blob, and
// jsPDF's fallback of opening the blob URL would navigate the home-screen
// app away from the game. iOS only opens the share sheet from a tap, and the
// build takes a while, so a "Recap ready" bar offers the tap.

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

// Phones and tablets: a coarse pointer and the Web Share API with files
function _recapUseShareSheet(file) {
  return window.matchMedia("(pointer: coarse)").matches
    && !!navigator.canShare && navigator.canShare({ files: [file] });
}

function _downloadRecap(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

function _deliverRecap(blob, name) {
  const file = new File([blob], name, { type: "application/pdf" });
  if (!_recapUseShareSheet(file)) {
    _downloadRecap(blob, name);
    showToast("Recap downloaded");
    return;
  }
  _showRecapReady(file);
}

function _closeRecapReady() {
  const bar = document.getElementById("recap-ready");
  if (bar) bar.remove();
}

function _showRecapReady(file) {
  _closeRecapReady();
  const bar = document.createElement("div");
  bar.id = "recap-ready";
  bar.className = "recap-ready";
  bar.innerHTML = `<span class="recap-ready-text">📊 Recap ready</span>
    <button type="button" class="btn green" id="recap-ready-share">Save / share PDF</button>
    <button type="button" class="recap-ready-close" title="Close">✕</button>`;
  document.body.appendChild(bar);
  bar.querySelector(".recap-ready-close").onclick = _closeRecapReady;
  bar.querySelector("#recap-ready-share").onclick = async () => {
    try {
      await navigator.share({ files: [file], title: "Session recap" });
      _closeRecapReady();
    } catch (e) {
      if (e.name === "AbortError") return;           // closed the sheet: keep the bar for another go
      _downloadRecap(file, file.name);                 // share refused: try a plain download instead
      _closeRecapReady();
    }
  };
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
    _deliverRecap(pdf.output("blob"), `recap_${roomCode}_${day}.pdf`);
  } catch (e) {
    showToast("Could not build the recap: " + (e.message || "try again"), "error");
  } finally {
    if (frame) frame.remove();
    _recapBusy = false;
  }
}
