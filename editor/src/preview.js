/* Illustrative Canvas renderer. This is not an audio analyzer or the OpenCV renderer. */
(function (root) {
  "use strict";
  const clamp = (value, low = 0, high = 1) => Math.max(low, Math.min(high, value));
  const canvas = (width, height) => { const item = document.createElement("canvas"); item.width = width; item.height = height; return item; };

  function scene(width, height) {
    const image = canvas(width, height), ctx = image.getContext("2d");
    const sky = ctx.createLinearGradient(0, 0, 0, height);
    sky.addColorStop(0, "#080e22"); sky.addColorStop(.6, "#26213d"); sky.addColorStop(1, "#080e16");
    ctx.fillStyle = sky; ctx.fillRect(0, 0, width, height);
    const halo = ctx.createRadialGradient(width * .59, height * .35, 1, width * .59, height * .35, width * .49);
    halo.addColorStop(0, "#735253"); halo.addColorStop(.5, "#362e44aa"); halo.addColorStop(1, "#141c3100");
    ctx.fillStyle = halo; ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = "#080d18";
    for (let i = 0; i < 22; i++) {
      const x = i * width / 21, h = height * (.11 + ((i * 37) % 13) / 80);
      ctx.fillRect(x, height * .62 - h, width / 24, h);
      ctx.fillStyle = "#ac865a";
      for (let j = 0; j < 4; j++) ctx.fillRect(x + 7, height * .62 - h + 9 + j * 17, 3, 4);
      ctx.fillStyle = "#080d18";
    }
    const floor = ctx.createLinearGradient(0, height * .59, 0, height);
    floor.addColorStop(0, "#182b39"); floor.addColorStop(1, "#070b10");
    ctx.fillStyle = floor; ctx.fillRect(0, height * .62, width, height);
    ctx.strokeStyle = "#3e4661"; ctx.lineWidth = 1;
    for (let i = -8; i <= 8; i++) {
      ctx.beginPath(); ctx.moveTo(width * .56, height * .62); ctx.lineTo(width * .56 + i * width / 7, height); ctx.stroke();
    }
    for (let i = 0; i < 6; i++) { const y = height * (.63 + i * i * .012); ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke(); }
    ctx.fillStyle = "#0d1420"; ctx.fillRect(width * .3, height * .29, width * .49, height * .33);
    ctx.strokeStyle = "#ffa973"; ctx.lineWidth = 3;
    ctx.strokeRect(width * .33, height * .32, width * .43, height * .27);
    ctx.strokeStyle = "#6edecf"; ctx.lineWidth = 2;
    ctx.strokeRect(width * .35, height * .35, width * .39, height * .22);
    ctx.fillStyle = "#e9d9c6"; ctx.textAlign = "center"; ctx.font = `${height * .063}px sans-serif`;
    ctx.fillText("AFTER HOURS", width * .545, height * .455);
    ctx.fillStyle = "#79b0b1"; ctx.font = `${height * .018}px sans-serif`;
    ctx.fillText("S O U N D   /   L I G H T   /   M O T I O N", width * .545, height * .5);
    for (const [x, color] of [[.16, "#6ce4d4"], [.87, "#ffb277"]]) {
      ctx.strokeStyle = "#182b3b"; ctx.lineWidth = 8;
      ctx.beginPath(); ctx.moveTo(width * x, height * .2); ctx.lineTo(width * x, height * .65); ctx.stroke();
      ctx.strokeStyle = color; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(width * x, height * .25); ctx.lineTo(width * x, height * .6); ctx.stroke();
    }
    return image;
  }

  function applyEffects(base, parameters, shared) {
    const width = base.width, height = base.height, out = canvas(width, height), ctx = out.getContext("2d");
    const scale = 1 + parameters.zoom;
    ctx.drawImage(base, (1 - scale) * width / 2, (1 - scale) * height / 2, width * scale, height * scale);
    const pixels = ctx.getImageData(0, 0, width, height), glow = ctx.createImageData(width, height);
    const multiplier = parameters.brightness * (1 + parameters.exposure), luma = shared.luma;
    for (let i = 0; i < pixels.data.length; i += 4) {
      let red = pixels.data[i] / 255 * multiplier, green = pixels.data[i + 1] / 255 * multiplier, blue = pixels.data[i + 2] / 255 * multiplier;
      const gray = red * luma[0] + green * luma[1] + blue * luma[2], saturation = 1 + parameters.saturation;
      red = gray + (red - gray) * saturation; green = gray + (green - gray) * saturation; blue = gray + (blue - gray) * saturation;
      const luminance = red * luma[0] + green * luma[1] + blue * luma[2];
      const mask = clamp((luminance - shared.bloomThreshold) / (1 - shared.bloomThreshold));
      pixels.data[i] = clamp(red) * 255; pixels.data[i + 1] = clamp(green) * 255; pixels.data[i + 2] = clamp(blue) * 255;
      glow.data[i] = clamp(red * mask) * 255; glow.data[i + 1] = clamp(green * mask) * 255; glow.data[i + 2] = clamp(blue * mask) * 255;
      glow.data[i + 3] = 255;
    }
    ctx.putImageData(pixels, 0, 0);
    if (parameters.bloom > .0001) {
      const light = canvas(width, height), lightCtx = light.getContext("2d");
      lightCtx.putImageData(glow, 0, 0);
      ctx.globalCompositeOperation = "lighter";
      ctx.globalAlpha = clamp(parameters.bloom);
      ctx.filter = `blur(${shared.bloomSigma}px)`; ctx.drawImage(light, 0, 0);
      ctx.filter = "none"; ctx.globalAlpha = 1; ctx.globalCompositeOperation = "source-over";
    }
    return out;
  }

  function drawTrack(ctx, track, item, x, y, width, height, index, timestamp) {
    if (width <= 0 || height <= 0) return;
    ctx.save(); ctx.beginPath(); ctx.rect(x, y, width, height); ctx.clip(); ctx.translate(x, y);
    const identity = track.stem || track.source || "drive";
    const phase = [...identity].reduce((sum, char) => sum + char.charCodeAt(0), index * 17) / 19;
    ctx.strokeStyle = track.color; ctx.fillStyle = track.color;
    if (item.type === "waveform") {
      const count = Math.min(item.waveform.points, Math.max(2, width)), upper = [], lower = [];
      for (let i = 0; i < count; i++) {
        const t = timestamp + (i / (count - 1) - .5) * item.waveform.window_seconds;
        const amplitude = clamp((.18 + .42 * Math.abs(Math.sin(t * 3.1 + phase)) ** 7 + .17 * Math.abs(Math.cos(t * 17 + phase))) * item.gain);
        const px = i / (count - 1) * (width - 1);
        upper.push([px, (1 - amplitude) * (height - 1) / 2]);
        lower.push([px, (1 + amplitude * (.85 + .15 * Math.cos(t * 5))) * (height - 1) / 2]);
      }
      const path = points => { ctx.beginPath(); points.forEach(([px, py], i) => i ? ctx.lineTo(px, py) : ctx.moveTo(px, py)); };
      if (item.fill_opacity) {
        path([...upper, ...lower.slice().reverse()]); ctx.closePath();
        ctx.globalAlpha = item.opacity * item.fill_opacity; ctx.fill();
      }
      ctx.globalAlpha = item.opacity; ctx.lineWidth = item.line_width;
      for (const points of [upper, lower]) { path(points); ctx.stroke(); }
      if (item.waveform.show_playhead) {
        ctx.globalAlpha = item.opacity * .35; ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo((width - 1) / 2, 0); ctx.lineTo((width - 1) / 2, height); ctx.stroke();
      }
    } else {
      const count = Math.min(item.spectrum.bands, Math.max(1, width));
      ctx.globalAlpha = item.opacity;
      for (let i = 0; i < count; i++) {
        const f = i / count;
        const value = clamp((.14 + .56 * Math.exp(-f * 1.5) * Math.abs(Math.sin(f * 14 + phase)) + .15 * Math.abs(Math.sin(f * 89))) * item.gain);
        const slot = width / count, drawing = Math.max(1, slot * (1 - item.bar_gap));
        ctx.fillRect(i * slot + (slot - drawing) / 2, height * (1 - value), drawing, height * value);
      }
    }
    ctx.restore();
  }

  function drawVisualizers(ctx, definitions, shared) {
    const width = ctx.canvas.width, height = ctx.canvas.height;
    for (const item of Object.values(definitions)) {
      const x = Math.round(item.left * width), y = height - Math.round((item.bottom + item.height) * height);
      const w = Math.round((item.left + item.width) * width) - x, h = height - Math.round(item.bottom * height) - y;
      ctx.save(); ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip();
      ctx.fillStyle = item.background; ctx.globalAlpha = item.opacity * item.background_opacity; ctx.fillRect(x, y, w, h); ctx.globalAlpha = 1;
      const count = item.tracks.length, vertical = item.layout === "stacked", length = vertical ? h : w;
      const gap = Math.min(Math.round(item.gap * length), Math.max(0, Math.floor((length - count) / Math.max(1, count - 1))));
      const usable = Math.max(0, length - gap * (count - 1));
      item.tracks.forEach((track, index) => {
        const begin = Math.floor(index * usable / count) + index * gap, end = Math.floor((index + 1) * usable / count) + index * gap;
        if (item.layout === "overlay") drawTrack(ctx, track, item, x, y, w, h, index, shared.timestamp);
        else if (vertical) drawTrack(ctx, track, item, x, y + begin, w, end - begin, index, shared.timestamp);
        else drawTrack(ctx, track, item, x + begin, y, end - begin, h, index, shared.timestamp);
      });
      ctx.restore();
    }
  }

  function create(target, contract, core) {
    const shared = {...contract.preview};
    let base, scale = 1;
    function setSource(source, width, height, timestamp = contract.preview.timestamp) {
      if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1) throw new Error("Media dimensions are unavailable.");
      if (width > 16384 || height > 16384 || width * height > 32 * 1024 * 1024) throw new Error("Media exceeds the preview limit of 32 megapixels or 16,384 pixels per edge.");
      scale = Math.min(1, 1280 / Math.max(width, height));
      const next = canvas(Math.max(1, Math.round(width * scale)), Math.max(1, Math.round(height * scale)));
      next.getContext("2d").drawImage(source, 0, 0, next.width, next.height);
      base = next;
      target.width = width; target.height = height; target.style.aspectRatio = `${width} / ${height}`;
      shared.timestamp = timestamp;
    }
    const reset = () => setSource(scene(shared.width, shared.height), shared.width, shared.height);
    const render = (project, levels) => {
      const ctx = target.getContext("2d");
      ctx.clearRect(0, 0, target.width, target.height);
      ctx.drawImage(applyEffects(base, core.effectParameters(project, levels), {...shared, bloomSigma: shared.bloomSigma * scale}), 0, 0, target.width, target.height);
      drawVisualizers(ctx, project.visualizers, shared);
    };
    render.setSource = setSource; render.reset = reset; reset(); return render;
  }
  root.BeatBloomPreview = { create };
})(globalThis);
