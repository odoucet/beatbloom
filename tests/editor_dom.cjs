/* Optional DOM + native Canvas check; image decoding is native, video events are mocked. */
"use strict";
const assert = require("node:assert/strict"), fs = require("node:fs"), path = require("node:path");
const {execFileSync} = require("node:child_process");
const {JSDOM, VirtualConsole, ResourceLoader} = require("jsdom");
const {createCanvas, loadImage} = require("@napi-rs/canvas");
const {File} = require("node:buffer");
const root = path.resolve(__dirname, ".."), errors = [], requests = [], surfaces = new WeakMap(), decoded = new WeakMap(), urls = new Map();
let urlSerial = 0;
let downloaded;
const console = new VirtualConsole(); console.on("jsdomError", error => errors.push(error.message));
class OfflineResources extends ResourceLoader {
  fetch(url) { requests.push(url); return Promise.reject(new Error("External resource forbidden")); }
}
const dom = new JSDOM(fs.readFileSync(path.join(root, "editor/beatbloom-editor.html"), "utf8"), {
  runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: console,
  url: "file:///beatbloom-editor.html", resources: new OfflineResources(),
  beforeParse(window) {
    function surface(item) {
      let result = surfaces.get(item);
      if (!result || result.width !== item.width || result.height !== item.height) {
        result = createCanvas(item.width, item.height); surfaces.set(item, result);
        const context = result.getContext("2d"), draw = context.drawImage.bind(context);
        context.drawImage = (source, ...args) => draw(source instanceof window.HTMLCanvasElement ? surface(source) : decoded.get(source) || source, ...args);
      }
      return result;
    }
    window.HTMLCanvasElement.prototype.getContext = function () { return surface(this).getContext("2d"); };
    window.HTMLCanvasElement.prototype.toDataURL = function () { return surface(this).toDataURL("image/png"); };
    window.Blob = Blob; window.File = File;
    window.URL.createObjectURL = blob => {
      if (blob.type === "application/json" && !blob.name) downloaded = blob;
      const url = `blob:offline-test-${++urlSerial}`; urls.set(url, blob); return url;
    };
    window.URL.revokeObjectURL = url => urls.delete(url);
    window.Image = class extends window.EventTarget {
      set src(url) {
        this.url = url;
        Promise.resolve().then(async () => {
          try {
            const bitmap = await loadImage(Buffer.from(await urls.get(url).arrayBuffer()));
            if (this.url !== url) return;
            decoded.set(this, bitmap); this.naturalWidth = bitmap.width; this.naturalHeight = bitmap.height;
            this.dispatchEvent(new window.Event("load"));
          } catch { if (this.url === url) this.dispatchEvent(new window.Event("error")); }
        });
      }
      removeAttribute() { this.url = null; }
      remove() {}
    };
    const videoPrototype = window.HTMLMediaElement.prototype;
    videoPrototype.pause = function () {};
    videoPrototype.load = function () {
      const file = urls.get(this.src); if (!file) return;
      for (const [key, value] of Object.entries({videoWidth: file.width, videoHeight: file.height, duration: file.duration})) {
        Object.defineProperty(this, key, {value, configurable: true});
      }
      decoded.set(this, createCanvas(file.width, file.height)); this.currentTime = 0;
      queueMicrotask(() => this.dispatchEvent(new window.Event("loadeddata")));
    };
    Object.defineProperty(videoPrototype, "currentTime", {
      get() { return this.testTime || 0; },
      set(value) {
        this.testTime = value;
        const bitmap = decoded.get(this);
        if (bitmap) { const ctx = bitmap.getContext("2d"); ctx.fillStyle = value < 1 ? "#147243" : "#235ce0"; ctx.fillRect(0, 0, bitmap.width, bitmap.height); }
        queueMicrotask(() => this.dispatchEvent(new window.Event("seeked")));
      }
    });
    window.HTMLAnchorElement.prototype.click = () => {};
  }
});
const {window} = dom, document = window.document, ui = window.BeatBloomEditor;
const tick = () => new Promise(resolve => setTimeout(resolve, 60));
const waitFor = async predicate => { for (let i = 0; i < 40; i++) { if (predicate()) return; await tick(); } assert.ok(predicate(), "Timed out waiting for the UI"); };
const control = (address, type) => document.querySelector(`${type || ""}[data-path="${address}"]`);
function edit(address, value, type = "input[type=number]", event = "input") {
  const item = control(address, type); assert.ok(item, address);
  item.value = value; item.dispatchEvent(new window.Event(event, {bubbles: true}));
}
function click(text) {
  const item = [...document.querySelectorAll("button")].find(item => item.textContent === text);
  assert.ok(item, text); item.click();
}
function tab(name) { document.querySelector(`[data-tab="${name}"]`).click(); }
function drop(files) {
  const event = new window.Event("drop", {bubbles: true, cancelable: true});
  Object.defineProperty(event, "dataTransfer", {value: {files, types: ["Files"]}});
  document.getElementById("preview").dispatchEvent(event); assert.equal(event.defaultPrevented, true);
}
function png(width, height) {
  const bitmap = createCanvas(width, height), ctx = bitmap.getContext("2d");
  ctx.fillStyle = "#4d827a"; ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = "#d78652"; ctx.fillRect(width / 3, height / 4, width / 3, height / 2);
  return new File([bitmap.toBuffer("image/png")], "portrait.png", {type: "image/png"});
}

(async () => {
  try {
    assert.ok(ui, errors.join("\n")); await tick();
    assert.equal(document.documentElement.lang, "en");
    assert.equal(document.querySelector("footer a").href, "https://github.com/odoucet/beatbloom");
    const before = document.getElementById("preview").toDataURL();
    edit("visualizers.waveform.opacity", ".43", "input[type=range]"); await tick();
    assert.equal(ui.getProject().visualizers.waveform.opacity, .43);
    assert.notEqual(document.getElementById("preview").toDataURL(), before);
    click("＋ Add track"); assert.equal(ui.getProject().visualizers.waveform.tracks.length, 2);
    edit("visualizers.waveform.layout", "side_by_side", "select", "change"); await tick();
    const validFrame = document.getElementById("preview").toDataURL();
    edit("visualizers.waveform.width", "1"); await tick();
    assert.equal(document.getElementById("export").disabled, true);
    assert.equal(document.getElementById("preview").toDataURL(), validFrame);
    edit("visualizers.waveform.width", ".9"); await tick();
    const beforeLevels = JSON.stringify(ui.getProject());
    edit("simulation.global_volume", ".25", "input[type=range]"); await tick();
    assert.equal(JSON.stringify(ui.getProject()), beforeLevels);
    tab("effects");
    edit("effects[0].effect", "zoom", "select", "change");
    assert.equal(ui.getProject().effects[0].range, null);
    assert.equal(ui.getProject().effects[0].amount, .02);
    assert.equal(control("effects[0].amount", "input[type=range]").max, "0.05");
    edit("effects[0].amount", ".006"); await tick();
    document.getElementById("export").click(); assert.ok(downloaded);
    const json = await downloaded.text(), exported = JSON.parse(json);
    assert.equal(exported.effects[0].amount, .006); assert.equal(exported.simulation, undefined);
    execFileSync("uv", ["run", "--locked", "python", "-c", "import sys; from beatbloom.config import ProjectConfig; ProjectConfig.model_validate_json(sys.stdin.read())"], {cwd: root, input: json});
    tab("signals");
    const name = document.querySelector('input[aria-label="Name (signals.global_volume)"]');
    name.value = "renamed_volume"; name.dispatchEvent(new window.Event("change", {bubbles: true}));
    assert.equal(ui.getProject().effects[0].signal, "renamed_volume");
    const input = document.getElementById("import-file");
    const good = fs.readFileSync(path.join(root, "examples/visualizers-demucs.json"), "utf8");
    Object.defineProperty(input, "files", {value: [{name: "stems.json", size: good.length, text: async () => good}], configurable: true});
    input.dispatchEvent(new window.Event("change")); await tick();
    assert.equal(ui.getProject().visualizers.instruments.tracks.length, 4);
    const imported = JSON.stringify(ui.getProject());
    Object.defineProperty(input, "files", {value: [{name: "old.json", size: 20, text: async () => '{"schema_version":1}'}], configurable: true});
    input.dispatchEvent(new window.Event("change")); await tick();
    assert.match(document.getElementById("message").textContent, /Import failed/);
    assert.equal(JSON.stringify(ui.getProject()), imported);
    const beforeMedia = JSON.stringify(ui.getProject());
    drop([png(360, 640)]); await waitFor(() => ui.getMediaInfo().name === "portrait.png"); await tick();
    assert.equal(document.getElementById("preview").width, 360); assert.equal(document.getElementById("preview").height, 640);
    assert.equal(JSON.stringify(ui.getProject()), beforeMedia); assert.equal(document.getElementById("video-controls").hidden, true);
    const preparation = {key: "cached-analysis", parameters: {hop: 256}, config: ui.getProject()};
    preparation.config.visualizers.instruments.opacity = .27;
    drop([new File([JSON.stringify(preparation)], "manifest.json", {type: "application/json"})]);
    await waitFor(() => ui.getProject().visualizers.instruments.opacity === .27);
    assert.equal(ui.getMediaInfo().name, "portrait.png");
    const clip = new File(["mock decoder"], "clip.webm", {type: "video/webm"});
    Object.assign(clip, {width: 640, height: 360, duration: 2});
    preparation.config.visualizers.instruments.opacity = .6;
    drop([clip, new File([JSON.stringify(preparation)], "manifest.json", {type: "application/json"})]);
    await waitFor(() => ui.getMediaInfo().name === "clip.webm" && ui.getProject().visualizers.instruments.opacity === .6); await tick();
    assert.equal(document.getElementById("preview").width, 640); assert.equal(document.getElementById("preview").height, 360);
    assert.equal(document.getElementById("video-controls").hidden, false);
    assert.equal(document.querySelector("video").paused, true);
    const firstVideoFrame = document.getElementById("preview").toDataURL(), timeline = document.getElementById("video-time");
    timeline.value = 1.2; timeline.dispatchEvent(new window.Event("input"));
    await waitFor(() => ui.getMediaInfo().time === 1.2); await tick();
    assert.notEqual(document.getElementById("preview").toDataURL(), firstVideoFrame);
    const goodSettings = JSON.stringify(ui.getProject());
    drop([png(320, 200), new File(['{"schema_version":1}'], "invalid.json", {type: "application/json"})]);
    await waitFor(() => document.getElementById("message").textContent.startsWith("Import failed"));
    assert.equal(ui.getMediaInfo().name, "clip.webm"); assert.equal(JSON.stringify(ui.getProject()), goodSettings);
    await ui.handleFiles([new File(["not an image"], "broken.png", {type: "image/png"})]);
    assert.match(document.getElementById("message").textContent, /could not decode this image/);
    assert.equal(ui.getMediaInfo().name, "clip.webm");
    document.getElementById("export").click();
    const mediaExport = await downloaded.text();
    assert.deepEqual(JSON.parse(mediaExport), JSON.parse(goodSettings));
    assert.equal(JSON.parse(mediaExport).media, undefined); assert.equal(JSON.parse(mediaExport).key, undefined);
    execFileSync("uv", ["run", "--locked", "python", "-c", "import sys; from beatbloom.config import ProjectConfig; ProjectConfig.model_validate_json(sys.stdin.read())"], {cwd: root, input: mediaExport});
    document.getElementById("reset-media").click(); await tick();
    assert.equal(ui.getMediaInfo().kind, "synthetic"); assert.equal(JSON.stringify(ui.getProject()), goodSettings);
    assert.equal(document.getElementById("preview").width, 960); assert.equal(document.getElementById("video-controls").hidden, true);
    click("Reset example"); await tick();
    if (process.env.BEATBLOOM_EDITOR_FRAME) fs.writeFileSync(process.env.BEATBLOOM_EDITOR_FRAME, surfaces.get(document.getElementById("preview")).toBuffer("image/png"));
    assert.deepEqual(errors, []); assert.deepEqual(requests, []);
    process.stdout.write("PASS: DOM + native Canvas, English UI, sliders, validation, media/config drops, native dimensions, video seeking, reset and strict Python export.\n");
  } finally { window.close(); }
})().catch(error => { process.stderr.write(String(error.stack) + "\n"); process.exitCode = 1; });
