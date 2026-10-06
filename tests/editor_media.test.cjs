/* Media lifecycle tests with decoder events supplied by an in-memory DOM. */
"use strict";
const assert = require("node:assert/strict"), fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
const {test} = require("node:test");
const source = fs.readFileSync(path.join(__dirname, "../editor/src/media.js"), "utf8");

function harness(onFrame) {
  const elements = [], urls = new Map(), revoked = [], frames = [], errors = [], timers = new Map();
  let serial = 0;
  class Decoder extends EventTarget {
    constructor(kind) {
      super(); this.kind = kind; this.removed = false; this.paused = true; this.currentTime = 0;
      this.naturalWidth = this.naturalHeight = this.videoWidth = this.videoHeight = 0;
      this.duration = NaN; elements.push(this);
    }
    set src(value) { this.url = value; }
    removeAttribute(name) { if (name === "src") this.url = null; }
    setAttribute() {}
    pause() { this.paused = true; this.pauseCount = (this.pauseCount || 0) + 1; }
    load() { this.loadCount = (this.loadCount || 0) + 1; }
    remove() { this.removed = true; }
    decode(width = 1080, height = 1920, duration = 4) {
      this.naturalWidth = this.videoWidth = width; this.naturalHeight = this.videoHeight = height; this.duration = duration;
      this.dispatchEvent(new Event(this.kind === "video" ? "loadeddata" : "load"));
    }
  }
  const context = vm.createContext({
    document: {createElement: kind => new Decoder(kind), body: {append() {}}},
    Image: class extends Decoder { constructor() { super("image"); } },
    URL: {
      createObjectURL(file) { const url = `blob:test-${++serial}`; urls.set(url, file); return url; },
      revokeObjectURL(url) { revoked.push(url); urls.delete(url); }
    },
    setTimeout(callback) { const id = ++serial; timers.set(id, callback); return id; },
    clearTimeout(id) { timers.delete(id); }
  });
  vm.runInContext(source, context);
  const api = context.BeatBloomMedia, media = api.create({
    onFrame(element, info) { if (onFrame) onFrame(element, info); frames.push({...info}); },
    onError(error) { errors.push(error.message); }
  });
  return {api, media, elements, urls, revoked, frames, errors, timers};
}
const image = (name = "portrait.PNG") => ({name, type: ""});
const video = (name = "clip.webm") => ({name, type: "video/webm"});
const plain = value => JSON.parse(JSON.stringify(value));

test("file classification handles MIME types and extension fallback", () => {
  const {api} = harness();
  for (const file of [image(), {name: "unknown", type: "image/avif"}]) assert.equal(api.kindOf(file), "image");
  for (const file of [video(), {name: "CLIP.MOV", type: ""}]) assert.equal(api.kindOf(file), "video");
  assert.equal(api.kindOf({name: "manifest.JSON", type: ""}), "config");
  assert.equal(api.kindOf({name: "settings", type: "application/json"}), "config");
  assert.equal(api.kindOf({name: "song.wav", type: "audio/wav"}), null);
});

test("an image reports native portrait dimensions and releases its URL on reset", async () => {
  const h = harness(), loading = h.media.load(image());
  h.elements[0].decode();
  assert.deepEqual(plain(await loading), {kind: "image", name: "portrait.PNG", width: 1080, height: 1920, duration: null, time: 0});
  assert.equal(h.frames.length, 1); assert.equal(h.urls.size, 1); assert.equal(h.timers.size, 0);
  h.media.reset(); h.media.reset();
  assert.equal(h.media.info(), null); assert.equal(h.urls.size, 0); assert.equal(h.revoked.length, 1);
});

test("a video stays paused, redraws on seek, and clamps time below its endpoint", async () => {
  const h = harness(), loading = h.media.load(video()), decoder = h.elements[0];
  assert.equal(decoder.muted, true); assert.equal(decoder.playsInline, true); assert.equal(decoder.loadCount, 1);
  decoder.decode(640, 360, 2); await loading;
  assert.equal(decoder.paused, true);
  h.media.seek(1.2); decoder.dispatchEvent(new Event("seeked"));
  assert.equal(h.frames.at(-1).time, 1.2);
  h.media.seek(99); assert.equal(decoder.currentTime, 1.999);
  h.media.seek(-2); assert.equal(decoder.currentTime, 0);
  h.media.seek(NaN); assert.equal(decoder.currentTime, 0);
  const count = h.frames.length; h.media.seek(0); assert.equal(h.frames.length, count + 1);
  h.media.reset(); decoder.dispatchEvent(new Event("seeked"));
  assert.equal(h.frames.length, count + 1); assert.equal(decoder.removed, true); assert.equal(decoder.pauseCount, 1);
  assert.equal(h.urls.size, 0);
});

test("a duration becoming available updates the frame metadata", async () => {
  const h = harness(), loading = h.media.load(video()), decoder = h.elements[0];
  decoder.decode(160, 90, Infinity); await loading;
  assert.equal(h.frames[0].duration, null); h.media.seek(1); assert.equal(decoder.currentTime, 0);
  decoder.duration = 3; decoder.dispatchEvent(new Event("durationchange"));
  assert.equal(h.frames.at(-1).duration, 3); h.media.seek(1); assert.equal(decoder.currentTime, 1);
  h.media.reset();
});

test("failed decoding retains the previous media and releases the failed candidate", async () => {
  const h = harness(), first = h.media.load(image()); h.elements[0].decode(); await first;
  const second = h.media.load(video()); h.elements[1].dispatchEvent(new Event("error"));
  await assert.rejects(second, /could not decode this video/);
  assert.equal(h.media.info().name, "portrait.PNG"); assert.equal(h.frames.length, 1);
  assert.equal(h.urls.size, 1); assert.equal(h.elements[0].removed, false); assert.equal(h.elements[1].removed, true);
  h.media.reset();
});

test("replacing a pending import cannot overwrite the newer media", async () => {
  const h = harness(), first = h.media.load(image("first.png")), second = h.media.load(image("second.png"));
  h.elements[1].decode(320, 180); await second;
  assert.equal(await first, null); h.elements[0].decode();
  assert.equal(h.media.info().name, "second.png"); assert.equal(h.frames.length, 1);
  assert.equal(h.urls.size, 1); assert.equal(h.timers.size, 0); h.media.reset();
});

test("cancelling a pending import keeps the active frame", async () => {
  const h = harness(), first = h.media.load(image()); h.elements[0].decode(); await first;
  const pending = h.media.load(video()); h.media.cancelPending();
  assert.equal(await pending, null); h.elements[1].decode();
  assert.equal(h.media.info().kind, "image"); assert.equal(h.frames.length, 1); assert.equal(h.urls.size, 1);
  h.media.reset();
});

test("reset while decoding cancels cleanly and releases the decoder", async () => {
  const h = harness(), loading = h.media.load(video()); h.media.reset();
  assert.equal(await loading, null); assert.equal(h.timers.size, 0); assert.equal(h.urls.size, 0);
  h.elements[0].decode(); assert.equal(h.frames.length, 0);
});

test("a loading timeout releases resources and remains an actionable error", async () => {
  const h = harness(), loading = h.media.load(image());
  [...h.timers.values()][0](); await assert.rejects(loading, /timed out/);
  assert.equal(h.urls.size, 0); assert.equal(h.timers.size, 0); assert.equal(h.media.info(), null);
});

test("an unsupported file allocates no decoder or object URL", async () => {
  const h = harness(); await assert.rejects(h.media.load({name: "audio.wav", type: "audio/wav"}), /Choose an image or video/);
  assert.equal(h.elements.length, 0); assert.equal(h.urls.size, 0);
});

test("a rejected frame preserves the previous active media", async () => {
  const h = harness((element, info) => { if (info.width > 16384) throw new Error("Media exceeds the preview limit."); });
  const first = h.media.load(image()); h.elements[0].decode(); await first;
  const oversized = h.media.load(image("large.png")); h.elements[1].decode(20000, 100);
  await assert.rejects(oversized, /preview limit/); assert.equal(h.media.info().name, "portrait.PNG");
  assert.equal(h.frames.length, 1); assert.equal(h.urls.size, 1); h.media.reset();
});

test("runtime video decoder errors reach the UI callback", async () => {
  const h = harness(), loading = h.media.load(video()); h.elements[0].decode(); await loading;
  h.elements[0].dispatchEvent(new Event("error")); assert.match(h.errors[0], /could not decode this video frame/);
  h.media.reset();
});
