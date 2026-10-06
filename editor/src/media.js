/* Local-file decoding only. Object URLs are released when replaced or reset. */
(function (root) {
  "use strict";
  function kindOf(file) {
    const type = (file.type || "").toLowerCase(), name = (file.name || "").toLowerCase();
    if (type === "application/json" || name.endsWith(".json")) return "config";
    if (type.startsWith("image/") || /\.(png|jpe?g|webp|gif|bmp|svg|avif|ico)$/.test(name)) return "image";
    if (type.startsWith("video/") || /\.(mp4|m4v|mov|webm|ogv|ogg|mkv|avi)$/.test(name)) return "video";
    return null;
  }

  function create(options) {
    let current = null, candidate = null, generation = 0;
    const cancelled = () => Object.assign(new Error("Media import cancelled."), {name: "AbortError"});
    function dispose(entry) {
      if (!entry || entry.disposed) return;
      entry.disposed = true;
      if (entry.cancel) entry.cancel();
      for (const remove of entry.listeners) remove();
      if (entry.kind === "video") { entry.element.pause(); entry.element.removeAttribute("src"); entry.element.load(); }
      else entry.element.removeAttribute("src");
      entry.element.remove(); URL.revokeObjectURL(entry.url);
    }
    function info(entry) {
      const element = entry.element, video = entry.kind === "video";
      return {
        kind: entry.kind, name: entry.name,
        width: video ? element.videoWidth : element.naturalWidth,
        height: video ? element.videoHeight : element.naturalHeight,
        duration: video && Number.isFinite(element.duration) ? element.duration : null,
        time: video && Number.isFinite(element.currentTime) ? element.currentTime : 0
      };
    }
    function ready(entry) {
      return new Promise((resolve, reject) => {
        const event = entry.kind === "video" ? "loadeddata" : "load";
        const settle = error => {
          clearTimeout(timer); entry.element.removeEventListener(event, loaded); entry.element.removeEventListener("error", failed);
          entry.cancel = null; error ? reject(error) : resolve();
        };
        const loaded = () => settle();
        const failed = () => settle(new Error(entry.kind === "video" ? "The browser could not decode this video. Try an H.264 MP4 or WebM file." : "The browser could not decode this image."));
        const timer = setTimeout(() => settle(new Error("Media loading timed out. Try another file.")), 30000);
        entry.cancel = () => settle(cancelled());
        entry.element.addEventListener(event, loaded); entry.element.addEventListener("error", failed);
        entry.element.src = entry.url;
        if (entry.kind === "video") entry.element.load();
      });
    }
    async function load(file) {
      const kind = kindOf(file);
      if (!["image", "video"].includes(kind)) throw new Error("Choose an image or video file.");
      const token = ++generation;
      dispose(candidate); candidate = null;
      const element = kind === "video" ? document.createElement("video") : new Image();
      const entry = {kind, name: file.name, element, url: URL.createObjectURL(file), listeners: [], disposed: false, cancel: null};
      candidate = entry;
      if (kind === "video") {
        element.preload = "auto"; element.muted = true; element.playsInline = true; element.className = "media-decoder";
        element.setAttribute("aria-hidden", "true"); document.body.append(element);
      }
      try {
        await ready(entry);
        if (token !== generation) { dispose(entry); return null; }
        const metadata = info(entry);
        if (!metadata.width || !metadata.height) throw new Error("Media dimensions are unavailable.");
        options.onFrame(element, metadata);
        dispose(current); current = entry; candidate = null;
        if (kind === "video") {
          const frame = () => {
            if (current !== entry || entry.disposed) return;
            try { options.onFrame(element, info(entry)); } catch (error) { if (options.onError) options.onError(error); }
          };
          const failed = () => { if (options.onError) options.onError(new Error("The browser could not decode this video frame.")); };
          for (const event of ["seeked", "resize", "durationchange"]) { element.addEventListener(event, frame); entry.listeners.push(() => element.removeEventListener(event, frame)); }
          element.addEventListener("error", failed); entry.listeners.push(() => element.removeEventListener("error", failed));
        }
        return metadata;
      } catch (error) {
        dispose(entry);
        if (candidate === entry) candidate = null;
        if (error.name === "AbortError" || token !== generation) return null;
        throw error;
      }
    }
    function seek(value) {
      if (!current || current.kind !== "video") return;
      const duration = current.element.duration;
      if (!Number.isFinite(value) || !Number.isFinite(duration) || duration <= 0) return;
      const time = Math.max(0, Math.min(Math.max(0, duration - .001), value));
      if (Math.abs(current.element.currentTime - time) < 1e-8) options.onFrame(current.element, info(current));
      else current.element.currentTime = time;
    }
    function cancelPending() { generation++; dispose(candidate); candidate = null; }
    function reset() { cancelPending(); dispose(current); current = null; }
    return {load, seek, cancelPending, reset, info: () => current ? info(current) : null};
  }
  root.BeatBloomMedia = {create, kindOf};
})(globalThis);
