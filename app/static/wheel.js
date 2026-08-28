/* Wheel rendering + spin animation.
 * The server decides the outcome; this script only animates the wheel so the
 * pointer lands on the returned index. A small random jitter within the
 * winning segment keeps every spin from stopping dead-center. */

(() => {
  const code = window.WHEEL_CODE;
  const canvas = document.getElementById("wheel-canvas");
  const ctx = canvas.getContext("2d");
  const spinBtn = document.getElementById("spin-btn");
  const namesList = document.getElementById("names-list");

  const COLORS = [
    "#e6194b",
    "#3cb44b",
    "#4363d8",
    "#f58231",
    "#911eb4",
    "#42d4f4",
    "#f032e6",
    "#bfef45",
    "#469990",
    "#9a6324",
    "#800000",
    "#000075",
    "#e6beff",
    "#aaffc3",
    "#ffd8b1",
    "#808000",
  ];

  let names = [];
  let rotation = 0; // current wheel rotation in radians
  let spinning = false;

  const TAU = Math.PI * 2;
  const POINTER_ANGLE = -Math.PI / 2; // pointer sits at the top

  function normalize(a) {
    return ((a % TAU) + TAU) % TAU;
  }

  function sizeCanvas() {
    const stage = canvas.parentElement;
    const size = Math.min(stage.clientWidth, window.innerHeight * 0.7, 640);
    const dpr = window.devicePixelRatio || 1;
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }

  function draw() {
    const size = canvas.clientWidth;
    const r = size / 2;
    ctx.clearRect(0, 0, size, size);
    if (names.length === 0) return;
    const seg = TAU / names.length;

    for (let i = 0; i < names.length; i++) {
      const start = rotation + i * seg;
      ctx.beginPath();
      ctx.moveTo(r, r);
      ctx.arc(r, r, r - 4, start, start + seg);
      ctx.closePath();
      ctx.fillStyle = COLORS[i % COLORS.length];
      ctx.fill();
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.save();
      ctx.translate(r, r);
      ctx.rotate(start + seg / 2);
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ctx.fillStyle = "#ffffff";
      const fontSize = Math.max(12, Math.min(24, (r * 1.4) / names.length + 8));
      ctx.font = `bold ${fontSize}px system-ui, sans-serif`;
      ctx.shadowColor = "rgba(0,0,0,0.5)";
      ctx.shadowBlur = 3;
      let label = names[i];
      const maxWidth = r * 0.72;
      while (label.length > 2 && ctx.measureText(label).width > maxWidth) {
        label = label.slice(0, -2);
      }
      if (label !== names[i]) label += "…";
      ctx.fillText(label, r - 14, 0);
      ctx.restore();
    }

    // hub
    ctx.beginPath();
    ctx.arc(r, r, r * 0.14, 0, TAU);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
    ctx.strokeStyle = "#cccccc";
    ctx.stroke();
  }

  function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  async function spin() {
    if (spinning) return;
    spinning = true;
    spinBtn.disabled = true;

    let result;
    try {
      // Re-sync names first so the animation and the server agree on indexes
      // even if the list was edited in the admin page after this page loaded.
      const wheelRes = await fetch(`/w/${code}/api/wheel`);
      const wheelData = await wheelRes.json();
      if (JSON.stringify(wheelData.names) !== JSON.stringify(names)) {
        names = wheelData.names;
        renderNamesList();
        draw();
      }

      const res = await fetch(`/w/${code}/api/spin`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      result = await res.json();
    } catch (e) {
      alert("Spin failed — check that the wheel still exists and has names.");
      spinning = false;
      spinBtn.disabled = false;
      return;
    }

    const seg = TAU / names.length;
    const jitter = (Math.random() - 0.5) * 0.7 * seg;
    const targetMod = normalize(
      POINTER_ANGLE - (result.winner_index + 0.5) * seg + jitter,
    );
    // turns must be an integer — a fractional turn would offset the final position
    const turns = 5 + Math.floor(Math.random() * 3);
    const startRotation = rotation;
    const totalDelta = normalize(targetMod - normalize(rotation)) + turns * TAU;
    const duration = 4500 + Math.random() * 1500;
    const t0 = performance.now();

    function frame(now) {
      const t = Math.min((now - t0) / duration, 1);
      rotation = startRotation + totalDelta * easeOutCubic(t);
      draw();
      if (t < 1) {
        requestAnimationFrame(frame);
      } else {
        rotation = normalize(rotation);
        draw();
        spinning = false;
        spinBtn.disabled = false;
        showWinner(result.winner_name);
      }
    }
    requestAnimationFrame(frame);
  }

  /* ---------- winner overlay + confetti ---------- */

  const overlay = document.getElementById("winner-overlay");
  const confettiCanvas = document.getElementById("confetti-canvas");

  function showWinner(name) {
    document.getElementById("winner-name").textContent = name;
    overlay.classList.remove("hidden");
    launchConfetti();
  }

  document.getElementById("winner-close").addEventListener("click", () => {
    overlay.classList.add("hidden");
  });

  function launchConfetti() {
    const c = confettiCanvas;
    c.width = window.innerWidth;
    c.height = window.innerHeight;
    const cctx = c.getContext("2d");
    const pieces = Array.from({ length: 160 }, () => ({
      x: Math.random() * c.width,
      y: -20 - Math.random() * c.height * 0.5,
      w: 6 + Math.random() * 6,
      h: 8 + Math.random() * 8,
      vy: 2 + Math.random() * 3,
      vx: -1.5 + Math.random() * 3,
      color: COLORS[Math.floor(Math.random() * COLORS.length)],
      rot: Math.random() * TAU,
      vr: -0.1 + Math.random() * 0.2,
    }));
    const t0 = performance.now();
    (function tick(now) {
      cctx.clearRect(0, 0, c.width, c.height);
      for (const p of pieces) {
        p.x += p.vx;
        p.y += p.vy;
        p.rot += p.vr;
        cctx.save();
        cctx.translate(p.x, p.y);
        cctx.rotate(p.rot);
        cctx.fillStyle = p.color;
        cctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
        cctx.restore();
      }
      if (now - t0 < 3500 && !overlay.classList.contains("hidden")) {
        requestAnimationFrame(tick);
      } else {
        cctx.clearRect(0, 0, c.width, c.height);
      }
    })(t0);
  }

  /* ---------- init ---------- */

  function renderNamesList() {
    namesList.innerHTML = "";
    for (const name of names) {
      const li = document.createElement("li");
      li.textContent = name;
      namesList.appendChild(li);
    }
  }

  async function init() {
    const res = await fetch(`/w/${code}/api/wheel`);
    const data = await res.json();
    names = data.names;
    document.title = data.title;
    document.getElementById("wheel-title").textContent = data.title;
    renderNamesList();
    if (names.length < 2) {
      spinBtn.disabled = true;
      namesList.innerHTML =
        "<li><em>This wheel needs at least 2 names.</em></li>";
    }
    sizeCanvas();
  }

  spinBtn.addEventListener("click", spin);
  canvas.addEventListener("click", spin);
  window.addEventListener("resize", sizeCanvas);
  init();
})();
