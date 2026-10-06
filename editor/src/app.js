(function () {
  "use strict";
  const contract = JSON.parse(document.getElementById("beatbloom-contract").textContent);
  const core = BeatBloomCore.create(contract), { clone, own, put } = BeatBloomCore;
  const $ = id => document.getElementById(id);
  const element = (tag, text, className) => {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (className) item.className = className;
    return item;
  };
  const button = (text, action, className = "secondary") => {
    const item = element("button", text, className); item.type = "button"; item.addEventListener("click", action); return item;
  };
  const names = {
    stem: "Stem", source: "Audio file", feature: "Feature", low: "Low frequency", high: "High frequency",
    attack_ms: "Attack", release_ms: "Release", gate: "Gate", gamma: "Gamma curve",
    ref_percentile: "Reference percentile", floor_percentile: "Floor percentile",
    signal: "Signal", effect: "Effect", amount: "Amount", range: "Brightness range",
    type: "Type", layout: "Layout", left: "Left margin", width: "Width", height: "Height", bottom: "Bottom margin",
    gap: "Track gap", opacity: "Opacity", gain: "Gain", background: "Background", background_opacity: "Background opacity",
    color: "Color", line_width: "Line width", fill_opacity: "Fill opacity", bar_gap: "Bar gap",
    window_seconds: "Visible window", points: "Points", show_playhead: "Center playhead", n_fft: "FFT size",
    bands: "Bands", floor_db: "Floor", model: "Model", device: "Device", backend: "Backend",
    shifts: "Shifts", overlap: "Overlap", segment: "Segment", jobs: "CPU workers", seed: "Seed"
  };
  const choices = {
    waveform: "Waveform", spectrum: "Spectrum", overlay: "Overlay", stacked: "Stacked", side_by_side: "Side by side",
    onset: "Onsets", rms: "RMS energy", loudness: "Loudness", mix: "Full mix", drums: "Drums", bass: "Bass",
    vocals: "Vocals", other: "Other", guitar: "Guitar", piano: "Piano", bloom: "Bloom", exposure: "Exposure",
    saturation: "Saturation", zoom: "Zoom", brightness: "Brightness"
  };
  const percent = new Set(["left", "width", "height", "bottom", "gap", "opacity", "background_opacity", "fill_opacity", "bar_gap", "gate", "overlap"]);
  const analysis = new Set(["low", "high", "attack_ms", "release_ms", "gate", "gamma", "ref_percentile", "floor_percentile", "floor_db", "n_fft"]);
  const recommended = { amount: 2, gain: 3, gamma: 4, attack_ms: 2000, release_ms: 5000, shifts: 10, jobs: 16, seed: 1000 };
  const initialNumber = { low: 30, high: 16000, ref_percentile: 99.5, segment: 7 };
  let project = core.hydrate(contract.initialProject), lastValidProject = clone(project), tab = "visualizers", pending = false, importGeneration = 0, dragDepth = 0;
  const levels = Object.create(null);
  const draw = BeatBloomPreview.create($("preview"), contract, core);
  const syntheticInfo = () => ({kind: "synthetic", name: "01 / NIGHT SCENE", width: contract.preview.width, height: contract.preview.height, time: 0, duration: null});
  let mediaInfo = syntheticInfo();
  const media = BeatBloomMedia.create({
    onFrame(source, info) {
      draw.setSource(source, info.width, info.height, info.kind === "video" ? info.time : contract.preview.timestamp);
      mediaInfo = info; renderMediaInfo(); refreshPreview();
    },
    onError(error) { $("message").textContent = error.message; }
  });

  function refreshPreview() {
    if (!pending) {
      pending = true;
      requestAnimationFrame(() => { pending = false; draw(core.validate(project).length ? lastValidProject : project, levels); });
    }
  }

  function formatTime(value) {
    if (!Number.isFinite(value)) return "—";
    const minutes = Math.floor(value / 60), seconds = (value % 60).toFixed(2).padStart(5, "0");
    return `${minutes}:${seconds}`;
  }

  function renderMediaInfo() {
    $("media-kind").textContent = mediaInfo.kind === "synthetic" ? "Synthetic image" : mediaInfo.kind === "video" ? "Video still" : "Your image";
    $("media-name").textContent = mediaInfo.name; $("media-name").title = mediaInfo.name;
    $("media-size").textContent = `${mediaInfo.width} × ${mediaInfo.height} · STILL FRAME`;
    $("reset-media").hidden = mediaInfo.kind === "synthetic";
    $("video-controls").hidden = mediaInfo.kind !== "video";
    const duration = mediaInfo.duration;
    $("video-time").max = Number.isFinite(duration) ? Math.max(0, duration - .001) : 0;
    $("video-time").value = mediaInfo.time; $("video-time").disabled = !Number.isFinite(duration) || duration <= 0;
    $("video-position").textContent = `${formatTime(mediaInfo.time)} / ${formatTime(duration)}`;
  }

  function display(key, value) {
    if (!Number.isFinite(value)) return "—";
    if (percent.has(key)) return `${Number((value * 100).toFixed(1))} %`;
    const unit = key.endsWith("_ms") ? " ms" : key === "window_seconds" ? " s" : ["low", "high"].includes(key) ? " Hz" : key === "floor_db" ? " dB" : "";
    return `${Number(value.toFixed(4))}${unit}`;
  }

  function update() {
    const errors = core.validate(project);
    $("export").disabled = errors.length > 0;
    $("status").textContent = errors.length ? "Fix the settings before exporting." : "Configuration valid · schema v2";
    $("status").classList.toggle("invalid", errors.length > 0);
    $("errors").replaceChildren(...errors.slice(0, 8).map(text => element("li", text)));
    $("errors").hidden = errors.length === 0;
    $("json").value = JSON.stringify(project, null, 2);
    if (!errors.length) { lastValidProject = clone(project); refreshPreview(); }
  }

  function numeric(label, key, node, value, path, set) {
    const field = element("div", undefined, "field");
    const title = element("div", undefined, "field-title"), output = element("output", display(key, value));
    title.append(element("span", label), output); field.append(title);
    const row = element("div", undefined, "number-row"), slider = element("input"), input = element("input");
    slider.type = "range"; input.type = "number";
    const step = node.sliderStep ?? (node.type === "integer" ? 1 : percent.has(key) ? .005 : ["low", "high"].includes(key) || key.endsWith("_ms") ? 1 : .01);
    const minimum = node.minimum ?? (node.exclusiveMinimum !== undefined ? node.exclusiveMinimum + (node.type === "integer" ? 1 : step) : 0);
    const maximum = node.maximum ?? (node.exclusiveMaximum !== undefined ? node.exclusiveMaximum - step : node.sliderMax ?? recommended[key] ?? Math.max(5, value * 2));
    slider.min = Math.min(minimum, value); slider.max = Math.max(maximum, value); slider.step = step; slider.value = value;
    input.step = "any"; input.value = value;
    if (node.minimum !== undefined) input.min = node.minimum;
    if (node.maximum !== undefined) input.max = node.maximum;
    for (const control of [slider, input]) {
      control.setAttribute("aria-label", `${label} (${path})`); control.dataset.path = path;
      control.addEventListener("input", () => {
        const current = control.valueAsNumber;
        set(current); output.textContent = display(key, current);
        if (control === slider) input.value = current;
        else { slider.min = Math.min(minimum, current); slider.max = Math.max(maximum, current); slider.value = current; }
        update();
      });
    }
    row.append(slider, input); field.append(row); return field;
  }

  function field(model, key, object, path) {
    const original = contract.schema.$defs[model].properties[key];
    const nullable = original.anyOf && original.anyOf.some(node => node.type === "null");
    const node = core.resolve(core.nonnull(original)), value = object[key];
    const label = names[key] || key, address = `${path}.${key}`;
    const set = next => {
      put(object, key, next);
      if (key === "stem" && next !== null) object.source = null;
      if (key === "source" && next !== null) object.stem = null;
    };
    let wrapper, control;
    if (["number", "integer"].includes(node.type) && key !== "n_fft") {
      const tuning = key === "amount" ? object.effect === "zoom" ? {sliderMax: .05, sliderStep: .0005} : ["exposure", "saturation"].includes(object.effect) ? {sliderMax: .5, sliderStep: .005} : {} : {};
      wrapper = numeric(label, key, {...node, ...tuning}, value ?? initialNumber[key] ?? 0, address, set);
    } else {
      wrapper = element("label", undefined, "field");
      wrapper.append(element("span", label, "field-title"));
      if (node.enum || key === "signal" || key === "n_fft") {
        control = element("select");
        let options = key === "signal" ? Object.keys(project.signals) : key === "n_fft" ? contract.fftSizes : key === "stem" ? contract.availableStems[project.separation.model] : node.enum;
        if (nullable) {
          const automatic = element("option", "Automatic (drive / mix)"); automatic.value = ""; control.append(automatic);
        }
        if (value !== null && !options.includes(value)) options = [value, ...options];
        for (const option of options) { const item = element("option", choices[option] || String(option)); item.value = option; control.append(item); }
        control.value = value ?? "";
        control.addEventListener("change", () => {
          const next = control.value === "" && nullable ? null : key === "n_fft" ? Number(control.value) : control.value;
          if (key === "effect") {
            const signal = object.signal, amount = object.amount;
            Object.assign(object, clone(contract.effects[next]), { signal });
            if (next !== "brightness" && amount !== null) object.amount = amount;
          } else set(next);
          renderControls(); update();
        });
      } else if (node.type === "boolean") {
        control = element("input"); control.type = "checkbox"; control.checked = value;
        control.addEventListener("change", () => { set(control.checked); update(); });
      } else if (node.type === "array" && node.prefixItems) {
        wrapper = element("div", undefined, "field"); wrapper.append(element("span", label, "field-title"));
        node.prefixItems.forEach((item, index) => wrapper.append(numeric(index ? "Loud" : "Quiet", "range", item, value[index], `${address}[${index}]`, next => { object[key][index] = next; })));
      } else {
        control = element("input"); control.type = node.pattern === "^#[0-9a-fA-F]{6}$" ? "color" : "text";
        control.value = value ?? "";
        if (key === "source") control.placeholder = "../stems/piano.wav";
        control.addEventListener("change", () => { set(key === "source" && !control.value ? null : control.value); renderControls(); update(); });
        if (control.type === "color") control.addEventListener("input", () => { set(control.value); update(); });
      }
      if (control) { control.dataset.path = address; control.setAttribute("aria-label", `${label} (${address})`); wrapper.append(control); }
    }
    if (nullable && !["stem", "source", "amount", "range"].includes(key)) {
      const automatic = element("label", undefined, "nullable"), check = element("input");
      check.type = "checkbox"; check.checked = value === null;
      check.setAttribute("aria-label", `${label} automatic (${address})`);
      for (const child of wrapper.querySelectorAll("input,select")) child.disabled = check.checked;
      check.addEventListener("change", () => { set(check.checked ? null : initialNumber[key] ?? 0); renderControls(); update(); });
      automatic.append(check, element("span", "Automatic")); wrapper.append(automatic);
    }
    if ((["SignalConfig", "SpectrumConfig"].includes(model) && analysis.has(key)) || (model === "WaveformConfig" && key === "ref_percentile")) wrapper.append(element("p", "Audio analysis setting; preview audio remains simulated.", "hint"));
    return wrapper;
  }

  function fields(model, object, path, primary) {
    const container = element("div");
    const properties = contract.schema.$defs[model].properties;
    const advanced = element("details", undefined, "advanced"); advanced.append(element("summary", "Advanced settings"));
    const append = (key, parent) => {
      if (key === "tracks") { parent.append(tracks(object, path)); return; }
      if (["waveform", "spectrum"].includes(key)) {
        if (object.type !== key) return;
        const section = element("details", undefined, "advanced"); section.open = true;
        section.append(element("summary", choices[key]));
        section.append(fields(key === "waveform" ? "WaveformConfig" : "SpectrumConfig", object[key], `${path}.${key}`, key === "waveform" ? ["window_seconds", "points", "show_playhead"] : ["bands"]));
        parent.append(section); return;
      }
      if (model === "EffectConfig" && (key === "amount" && object.effect === "brightness" || key === "range" && object.effect !== "brightness")) return;
      parent.append(field(model, key, object, path));
    };
    for (const key of primary) if (own(properties, key)) append(key, container);
    for (const key of Object.keys(properties)) if (!primary.includes(key)) append(key, advanced);
    if (advanced.children.length > 1) container.append(advanced);
    return container;
  }

  function tracks(object, path) {
    const list = element("div", undefined, "advanced"); list.append(element("strong", "Audio tracks"));
    object.tracks.forEach((track, index) => {
      const section = element("div", undefined, "track"); section.append(element("strong", `TRACK ${index + 1}`));
      section.append(fields("VisualizerTrackConfig", track, `${path}.tracks[${index}]`, ["stem", "source", "color"]));
      const remove = button("Remove track", () => { object.tracks.splice(index, 1); renderControls(); update(); }, "secondary danger");
      remove.disabled = object.tracks.length <= 1; section.append(remove); list.append(section);
    });
    const add = button("＋ Add track", () => {
      const track = clone(contract.templates.VisualizerTrackConfig);
      track.color = ["#65d4ff", "#ffa76a", "#bf9af2", "#71d8ba"][object.tracks.length % 4];
      object.tracks.push(track); renderControls(); update();
    });
    add.disabled = object.tracks.length >= contract.schema.$defs.VisualizerConfig.properties.tracks.maxItems;
    list.append(add); return list;
  }

  function unique(collection, stem) {
    let name = stem, index = 2;
    while (own(collection, name)) name = `${stem}_${index++}`;
    return name;
  }

  function rename(collection, oldName, next) {
    if (next === oldName) return;
    if (!next.trim() || (next !== oldName && own(collection, next))) { $("message").textContent = "Choose a unique, non-empty name."; renderControls(); return; }
    const replacement = {};
    for (const [name, value] of Object.entries(project[collection])) put(replacement, name === oldName ? next : name, value);
    project[collection] = replacement;
    if (collection === "signals") {
      project.effects.forEach(item => { if (item.signal === oldName) item.signal = next; });
      levels[next] = levels[oldName]; delete levels[oldName]; renderLevels();
    }
    renderControls(); update();
  }

  function renderControls() {
    const target = $("controls"); target.replaceChildren();
    if (tab === "separation") {
      target.append(element("p", "Python runs separation when instrument stems are used.", "hint"));
      target.append(fields("SeparationConfig", project.separation, "separation", ["model", "device", "shifts", "overlap"])); return;
    }
    const entries = tab === "effects" ? project.effects.map((item, index) => [index, item]) : Object.entries(project[tab]);
    if (!entries.length) target.append(element("p", "No items yet. Add one below.", "empty"));
    for (const [name, object] of entries) {
      const group = element("details", undefined, "group"); group.open = entries.length <= 2;
      const summary = element("summary", tab === "effects" ? choices[object.effect] : name);
      summary.append(element("span", tab === "visualizers" ? choices[object.type] : tab === "signals" ? choices[object.feature] : object.signal, "kind"));
      group.append(summary); const body = element("div", undefined, "fields");
      if (tab !== "effects") {
        const nameField = element("label", undefined, "field"); nameField.append(element("span", "Name", "field-title"));
        const input = element("input"); input.value = name; input.setAttribute("aria-label", `Name (${tab}.${name})`);
        input.addEventListener("change", () => rename(tab, name, input.value)); nameField.append(input); body.append(nameField);
      }
      const model = tab === "effects" ? "EffectConfig" : tab === "signals" ? "SignalConfig" : "VisualizerConfig";
      const path = tab === "effects" ? `effects[${name}]` : `${tab}.${name}`;
      const primary = tab === "effects" ? ["signal", "effect", "amount", "range"] : tab === "signals" ? ["stem", "source", "feature", "low", "high", "attack_ms", "release_ms", "gate", "gamma"] : ["type", "layout", "left", "width", "height", "bottom", "opacity", "gain", "tracks", object.type];
      body.append(fields(model, object, path, primary));
      const actions = element("div", undefined, "row-actions");
      actions.append(button("Remove", () => {
        if (tab === "effects") project.effects.splice(name, 1);
        else {
          delete project[tab][name];
          if (tab === "signals") { project.effects = project.effects.filter(item => item.signal !== name); delete levels[name]; renderLevels(); }
        }
        renderControls(); update();
      }, "secondary danger"));
      body.append(actions); group.append(body); target.append(group);
    }
    const additions = element("div", undefined, "row-actions");
    function add(kind) {
      if (tab === "visualizers") {
        const item = clone(contract.templates.VisualizerConfig); item.type = kind;
        put(project.visualizers, unique(project.visualizers, kind), item);
      } else if (tab === "signals") {
        put(project.signals, unique(project.signals, "energy"), clone(contract.templates.SignalConfig)); renderLevels();
      } else {
        if (!Object.keys(project.signals).length) { put(project.signals, "energy", clone(contract.templates.SignalConfig)); renderLevels(); }
        const item = clone(contract.effects.bloom); item.signal = Object.keys(project.signals)[0]; project.effects.push(item);
      }
      renderControls(); update();
    }
    if (tab === "visualizers") additions.append(button("＋ Waveform", () => add("waveform")), button("＋ Spectrum", () => add("spectrum")));
    else additions.append(button(tab === "signals" ? "＋ Signal" : "＋ Effect", add));
    target.append(additions);
  }

  function renderLevels() {
    const target = $("levels"); target.replaceChildren();
    for (const name of Object.keys(project.signals)) {
      if (!own(levels, name)) levels[name] = project.signals[name].feature === "loudness" ? .65 : .55;
      target.append(numeric(name, "opacity", { type: "number", minimum: 0, maximum: 1 }, levels[name], `simulation.${name}`, next => { levels[name] = next; }));
    }
    if (!Object.keys(project.signals).length) target.append(element("p", "Visualizers use a fixed, synthetic audio shape.", "hint"));
  }

  function importProject(value) {
    value = core.projectFrom(value);
    const errors = core.validate(value);
    if (errors.length) throw new Error(errors.join("\n"));
    project = core.hydrate(value);
    for (const name of Object.keys(levels)) delete levels[name];
    renderControls(); renderLevels(); update();
  }

  document.querySelectorAll("[data-tab]").forEach(item => item.addEventListener("click", () => {
    tab = item.dataset.tab;
    document.querySelectorAll("[data-tab]").forEach(other => other.setAttribute("aria-pressed", other === item ? "true" : "false"));
    renderControls();
  }));
  async function handleFiles(files) {
    const request = ++importGeneration;
    try {
      files = Array.from(files);
      if (!files.length) return;
      media.cancelPending();
      const configs = files.filter(file => BeatBloomMedia.kindOf(file) === "config"), pictures = files.filter(file => ["image", "video"].includes(BeatBloomMedia.kindOf(file)));
      if (configs.length + pictures.length !== files.length) throw new Error("Drop an image, video, or JSON configuration file.");
      if (configs.length > 1 || pictures.length > 1) throw new Error("Drop one media file and one configuration JSON at a time.");
      let settings;
      if (configs.length) {
        const file = configs[0];
        if (file.size > 1024 * 1024) throw new Error("Configuration JSON exceeds 1 MiB.");
        settings = core.projectFrom(JSON.parse(await file.text()));
        const errors = core.validate(settings); if (errors.length) throw new Error(errors.join("\n"));
      }
      if (request !== importGeneration) return;
      if (pictures.length) {
        $("message").textContent = `Loading ${pictures[0].name}…`;
        const info = await media.load(pictures[0]);
        if (!info || request !== importGeneration) return;
      }
      if (settings) importProject(settings);
      $("message").textContent = `${files.map(file => file.name).join(" + ")} imported. Files stay on this device.`;
    } catch (error) { if (request === importGeneration && error.name !== "AbortError") $("message").textContent = `Import failed: ${error.message}`; }
  }

  function resetMedia() {
    importGeneration++; media.reset(); draw.reset(); mediaInfo = syntheticInfo(); renderMediaInfo(); refreshPreview();
  }

  for (const id of ["import-file", "media-file"]) $(id).addEventListener("change", async event => {
    await handleFiles(event.target.files); event.target.value = "";
  });
  const hasFiles = event => Array.from(event.dataTransfer?.types || []).includes("Files") || event.dataTransfer?.files?.length;
  document.addEventListener("dragenter", event => { if (hasFiles(event)) { event.preventDefault(); dragDepth++; document.body.classList.add("is-dragging"); } });
  document.addEventListener("dragover", event => { if (hasFiles(event)) { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; } });
  document.addEventListener("dragleave", event => { if (hasFiles(event) && --dragDepth <= 0) { dragDepth = 0; document.body.classList.remove("is-dragging"); } });
  document.addEventListener("drop", event => {
    if (!hasFiles(event)) return;
    event.preventDefault(); dragDepth = 0; document.body.classList.remove("is-dragging"); void handleFiles(event.dataTransfer.files);
  });
  $("reset-media").addEventListener("click", resetMedia);
  $("video-time").addEventListener("input", event => media.seek(event.target.valueAsNumber));
  window.addEventListener("pagehide", () => media.reset());
  $("export").addEventListener("click", () => {
    try {
      const text = core.exportProject(project), blob = new Blob([text], { type: "application/json" });
      const url = URL.createObjectURL(blob), link = element("a");
      link.href = url; link.download = "beatbloom.json"; document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000); $("message").textContent = "beatbloom.json exported.";
    } catch (error) { $("message").textContent = error.message; }
  });
  $("reset").addEventListener("click", () => { resetMedia(); importProject(contract.initialProject); $("message").textContent = "Example restored."; });
  $("version").textContent = `Python ${contract.beatbloomVersion} · editor ${contract.editorVersion}`;
  globalThis.BeatBloomEditor = { importProject, handleFiles, getProject: () => clone(project), getMediaInfo: () => clone(mediaInfo) };
  renderControls(); renderLevels(); renderMediaInfo(); update();
})();
