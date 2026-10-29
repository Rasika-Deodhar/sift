(function () {
  const feed = document.getElementById("feed");
  const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  // Simple word-wrap for SVG text.
  function wrap(text, max) {
    const out = [];
    for (const para of text.split("\n")) {
      let line = "";
      for (const w of para.split(" ")) {
        if ((line + " " + w).trim().length > max) { out.push(line.trim()); line = w; }
        else line += " " + w;
      }
      out.push(line.trim());
    }
    return out;
  }

  function art(p) {
    const [a, b] = p.palette;
    const title = wrap(p.title, 22).map((l, i) =>
      `<text x="40" y="${110 + i * 46}" font-size="38" font-weight="800" fill="#fff">${esc(l)}</text>`).join("");
    const body = wrap(p.body, 40).map((l, i) =>
      `<text x="40" y="${300 + i * 30}" font-size="21" fill="#ffffffdd">${esc(l)}</text>`).join("");
    // Decorative shapes vary by post id so every post hashes differently.
    const seed = [...p.id].reduce((s, c) => s + c.charCodeAt(0), 0);
    const cx = 380 + (seed % 60), cy = 60 + (seed % 90), r = 50 + (seed % 40);
    return `<svg class="media" viewBox="0 0 480 480" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${esc(p.title)}">
      <defs><linearGradient id="g${p.id}" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient></defs>
      <rect width="480" height="480" fill="url(#g${p.id})"/>
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="#ffffff22"/>
      <rect x="${20 + (seed % 30)}" y="420" width="${120 + (seed % 200)}" height="14" rx="7" fill="#ffffff33"/>
      ${title}${body}</svg>`;
  }

  function avatar(user) {
    const h = [...user].reduce((s, c) => (s * 31 + c.charCodeAt(0)) % 360, 7);
    return `<span class="avatar" style="background:hsl(${h} 60% 50%)"></span>`;
  }

  for (const p of window.SIFT_DEMO_POSTS) {
    const media = p.kind === "reel"
      ? `<video class="media reel" loop playsinline preload="auto">
         <source src="${p.src.replace(/\.mp4$/, ".webm")}" type="video/webm" />
         <source src="${p.src}" type="video/mp4" /></video>`
      : art(p);
    const el = document.createElement("section");
    el.className = "post";
    el.innerHTML = `<article class="card">
      <div class="head">${avatar(p.user)}<span>${esc(p.user)}</span>
        <span class="badge">${p.kind === "reel" ? "Reel" : "Post"}</span></div>
      ${media}
      <div class="meta"><div class="likes">${p.likes.toLocaleString()} likes</div>
        <b>${esc(p.user)}</b> ${esc(p.caption)}</div></article>`;
    feed.appendChild(el);
  }

  // Autoplay reels only while on screen (with sound once the user has interacted).
  let interacted = false;
  addEventListener("pointerdown", () => { interacted = true; }, { once: true });
  addEventListener("keydown", () => { interacted = true; }, { once: true });
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      const v = e.target.querySelector("video");
      if (!v) continue;
      if (e.intersectionRatio > 0.6) { v.muted = !interacted; v.currentTime = 0; v.play().catch(() => {}); }
      else v.pause();
    }
  }, { threshold: [0, 0.6, 1] });
  document.querySelectorAll(".post").forEach((el) => io.observe(el));
})();
