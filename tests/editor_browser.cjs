/* Optional real-browser integration check. Opens file://, never starts a server. */
"use strict";
const assert = require("node:assert/strict"), fs = require("node:fs"), os = require("node:os"), path = require("node:path");
const { pathToFileURL } = require("node:url"), { execFileSync } = require("node:child_process");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "..");

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "beatbloom-editor-"));
  const browser = await chromium.launch({ headless: true, ...(process.env.BEATBLOOM_BROWSER_EXECUTABLE ? { executablePath: process.env.BEATBLOOM_BROWSER_EXECUTABLE } : {}) });
  try {
    const page = await browser.newPage({ viewport: { width: 1360, height: 960 }, acceptDownloads: true });
    const errors = [], network = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("request", request => { if (/^https?:/.test(request.url())) network.push(request.url()); });
    await page.goto(pathToFileURL(path.join(root, "editor/beatbloom-editor.html")).href);
    await page.waitForFunction(() => globalThis.BeatBloomEditor && document.getElementById("status").textContent.includes("Configuration valid"));
    const screenshot = () => page.locator("#preview").evaluate(item => item.toDataURL());
    const dropFiles = async files => page.evaluate(items => {
      const transfer = new DataTransfer();
      for (const item of items) transfer.items.add(new File([Uint8Array.from(atob(item.base64), c => c.charCodeAt(0))], item.name, {type: item.type}));
      const event = new DragEvent("drop", {bubbles: true, cancelable: true, dataTransfer: transfer});
      document.getElementById("preview").dispatchEvent(event);
      if (!event.defaultPrevented) throw new Error("File drop did not prevent browser navigation");
    }, files);
    assert.equal(await page.locator("html").getAttribute("lang"), "en");
    assert.equal(await page.locator("footer a").getAttribute("href"), "https://github.com/odoucet/beatbloom");
    let before = await screenshot();
    const setSlider = async (address, value) => page.locator(`input[type=range][data-path="${address}"]`).evaluate((item, next) => { item.value = next; item.dispatchEvent(new Event("input", {bubbles: true})); }, value);
    await setSlider("visualizers.waveform.opacity", .43);
    assert.equal(await page.evaluate(() => BeatBloomEditor.getProject().visualizers.waveform.opacity), .43);
    await page.waitForFunction(previous => document.getElementById("preview").toDataURL() !== previous, before);
    await page.getByRole("button", {name: "＋ Add track", exact: true}).first().click();
    await page.locator('select[data-path="visualizers.waveform.layout"]').selectOption("side_by_side");
    assert.equal(await page.evaluate(() => BeatBloomEditor.getProject().visualizers.waveform.tracks.length), 2);
    before = await screenshot();
    await page.locator('input[type=number][data-path="visualizers.waveform.width"]').fill("1");
    assert.equal(await page.locator("#export").isDisabled(), true);
    assert.equal(await screenshot(), before);
    await page.locator('input[type=number][data-path="visualizers.waveform.width"]').fill("0.9");
    assert.equal(await page.locator("#export").isDisabled(), false);
    const projectBeforeSimulation = await page.evaluate(() => JSON.stringify(BeatBloomEditor.getProject()));
    await setSlider("simulation.global_volume", .25);
    assert.equal(await page.evaluate(() => JSON.stringify(BeatBloomEditor.getProject())), projectBeforeSimulation);
    const downloadPromise = page.waitForEvent("download"); await page.locator("#export").click();
    const download = await downloadPromise, output = path.join(tmp, "beatbloom.json"); await download.saveAs(output);
    const exported = JSON.parse(fs.readFileSync(output, "utf8"));
    assert.equal(exported.visualizers.waveform.opacity, .43);
    assert.equal(exported.simulation, undefined);
    execFileSync("uv", ["run", "--locked", "beatbloom", "validate", output], {cwd: root, encoding: "utf8"});
    await page.locator("#import-file").setInputFiles(path.join(root, "examples/visualizers-demucs.json"));
    await page.waitForFunction(() => Object.keys(BeatBloomEditor.getProject().visualizers).includes("instruments"));
    assert.equal(await page.evaluate(() => BeatBloomEditor.getProject().visualizers.instruments.tracks.length), 4);
    const imported = await page.evaluate(() => JSON.stringify(BeatBloomEditor.getProject()));
    const invalid = path.join(tmp, "invalid.json"); fs.writeFileSync(invalid, '{"schema_version":1,"bands":[]}');
    await page.locator("#import-file").setInputFiles(invalid);
    await page.waitForFunction(() => document.getElementById("message").textContent.startsWith("Import failed"));
    assert.equal(await page.evaluate(() => JSON.stringify(BeatBloomEditor.getProject())), imported);
    const imageData = await page.evaluate(() => {
      const bitmap = document.createElement("canvas"); bitmap.width = 120; bitmap.height = 200;
      const ctx = bitmap.getContext("2d"); ctx.fillStyle = "#40817c"; ctx.fillRect(0, 0, 120, 200);
      ctx.fillStyle = "#e0824b"; ctx.fillRect(30, 40, 60, 100); return bitmap.toDataURL().split(",")[1];
    });
    await dropFiles([{name: "portrait.png", type: "image/png", base64: imageData}]);
    await page.waitForFunction(() => BeatBloomEditor.getMediaInfo().name === "portrait.png");
    assert.deepEqual(await page.locator("#preview").evaluate(item => [item.width, item.height]), [120, 200]);
    assert.equal(await page.evaluate(() => JSON.stringify(BeatBloomEditor.getProject())), imported);
    const video = path.join(tmp, "clip.webm");
    execFileSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=4", "-t", "2", "-an", "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", video]);
    const preparation = {key: "test-analysis", parameters: {hop: 256}, config: JSON.parse(imported)};
    preparation.config.visualizers.instruments.opacity = .31;
    await dropFiles([
      {name: "clip.webm", type: "video/webm", base64: fs.readFileSync(video).toString("base64")},
      {name: "manifest.json", type: "application/json", base64: Buffer.from(JSON.stringify(preparation)).toString("base64")}
    ]);
    await page.waitForFunction(() => BeatBloomEditor.getMediaInfo().name === "clip.webm" && BeatBloomEditor.getProject().visualizers.instruments.opacity === .31);
    assert.deepEqual(await page.locator("#preview").evaluate(item => [item.width, item.height]), [160, 90]);
    assert.equal(await page.locator("video").evaluate(item => item.paused), true);
    before = await screenshot();
    await page.locator("#video-time").evaluate(item => { item.value = 1.2; item.dispatchEvent(new Event("input")); });
    await page.waitForFunction(() => Math.abs(BeatBloomEditor.getMediaInfo().time - 1.2) < .001);
    await page.waitForFunction(previous => document.getElementById("preview").toDataURL() !== previous, before);
    const restored = await page.evaluate(() => JSON.stringify(BeatBloomEditor.getProject()));
    await dropFiles([{name: "broken.png", type: "image/png", base64: Buffer.from("invalid image").toString("base64")}]);
    await page.waitForFunction(() => document.getElementById("message").textContent.startsWith("Import failed"));
    assert.equal(await page.evaluate(() => BeatBloomEditor.getMediaInfo().name), "clip.webm");
    const mediaDownloadPromise = page.waitForEvent("download"); await page.locator("#export").click();
    const mediaDownload = await mediaDownloadPromise, mediaOutput = path.join(tmp, "media-config.json"); await mediaDownload.saveAs(mediaOutput);
    assert.deepEqual(JSON.parse(fs.readFileSync(mediaOutput, "utf8")), JSON.parse(restored));
    execFileSync("uv", ["run", "--locked", "beatbloom", "validate", mediaOutput], {cwd: root, encoding: "utf8"});
    await page.locator("#reset-media").click();
    assert.equal(await page.evaluate(() => BeatBloomEditor.getMediaInfo().kind), "synthetic");
    assert.equal(await page.evaluate(() => JSON.stringify(BeatBloomEditor.getProject())), restored);
    await page.locator("#reset").click();
    await page.waitForFunction(() => Object.keys(BeatBloomEditor.getProject().visualizers).includes("waveform"));
    if (process.env.BEATBLOOM_EDITOR_SCREENSHOT) await page.screenshot({path: process.env.BEATBLOOM_EDITOR_SCREENSHOT});
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    assert.deepEqual(errors, []); assert.deepEqual(network, []);
    console.log("PASS: file://, English UI, sliders, native image/video drops, paused seeking, preparation JSON, export and mobile layout; zero HTTP requests.");
  } finally {
    await browser.close(); fs.rmSync(tmp, {recursive: true, force: true});
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
