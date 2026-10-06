/* Pure configuration logic. Also loaded by Node contract tests; no browser APIs. */
(function (root) {
  "use strict";
  const clone = value => JSON.parse(JSON.stringify(value));
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const put = (value, key, item) => Object.defineProperty(value, key, {
    value: item, writable: true, enumerable: true, configurable: true
  });

  function create(contract) {
    const definitions = contract.schema.$defs;
    const blank = text => !text || [...text].every(char => contract.whitespace.includes(char));
    const resolve = node => node.$ref ? definitions[node.$ref.split("/").pop()] : node;
    const nonnull = node => node.anyOf ? node.anyOf.find(item => item.type !== "null") : node;
    function projectFrom(value) {
      if (value && typeof value === "object" && own(value, "config")) return value.config;
      if (value && own(value, "key") && own(value, "parameters") && own(value, "signals")) {
        throw new Error("This older analysis manifest has no config. Run analyze again or drop the original config JSON.");
      }
      return value;
    }
    function hydrate(node, value) {
      const ref = node.$ref && node.$ref.split("/").pop();
      node = resolve(node);
      if (value === undefined) {
        if (own(node, "default")) value = clone(node.default);
        else if (ref && contract.templates[ref]) value = clone(contract.templates[ref]);
        else if (node.type === "object") value = {};
        else if (node.type === "array") value = [];
        else return undefined;
      }
      if (value === null) return null;
      if (node.anyOf) return hydrate(nonnull(node), value);
      if (node.type === "object" && typeof value === "object" && !Array.isArray(value)) {
        const result = clone(value);
        for (const [key, child] of Object.entries(node.properties || {})) {
          const item = hydrate(child, own(value, key) ? value[key] : undefined);
          if (item !== undefined) put(result, key, item);
        }
        if (node.additionalProperties && typeof node.additionalProperties === "object") {
          for (const key of Object.keys(result)) put(result, key, hydrate(node.additionalProperties, result[key]));
        }
        return result;
      }
      if (node.type === "array" && Array.isArray(value)) {
        return value.map((item, index) => hydrate((node.prefixItems || [])[index] || node.items || {}, item));
      }
      return value;
    }

    function schemaErrors(node, value, path = "$", errors = []) {
      node = resolve(node);
      const fail = text => errors.push(`${path}: ${text}`);
      if (node.anyOf) {
        if (!node.anyOf.some(branch => schemaErrors(branch, value, path, []).length === 0)) fail("incompatible value");
        return errors;
      }
      if (own(node, "const") && value !== node.const) fail(`expected value: ${node.const}`);
      if (node.enum && !node.enum.includes(value)) fail("unknown choice");
      switch (node.type) {
        case "null": if (value !== null) fail("expected null"); break;
        case "boolean": if (typeof value !== "boolean") fail("expected a boolean"); break;
        case "number":
        case "integer":
          if (typeof value !== "number" || !Number.isFinite(value) || (node.type === "integer" && !Number.isInteger(value))) {
            fail("expected a valid number"); break;
          }
          if (own(node, "minimum") && value < node.minimum) fail(`minimum ${node.minimum}`);
          if (own(node, "maximum") && value > node.maximum) fail(`maximum ${node.maximum}`);
          if (own(node, "exclusiveMinimum") && value <= node.exclusiveMinimum) fail(`must be > ${node.exclusiveMinimum}`);
          if (own(node, "exclusiveMaximum") && value >= node.exclusiveMaximum) fail(`must be < ${node.exclusiveMaximum}`);
          break;
        case "string":
          if (typeof value !== "string") { fail("expected text"); break; }
          if (own(node, "minLength") && [...value].length < node.minLength) fail("text is too short");
          if (node.pattern) {
            // Pydantic's Rust regex uses a strict end anchor; JS $ accepts a final newline.
            const pattern = node.pattern.endsWith("$") ? node.pattern.slice(0, -1) + "(?![\\s\\S])" : node.pattern;
            if (!new RegExp(pattern).test(value)) fail("invalid format");
          }
          break;
        case "array":
          if (!Array.isArray(value)) { fail("expected a list"); break; }
          if (own(node, "minItems") && value.length < node.minItems) fail("list is too short");
          if (own(node, "maxItems") && value.length > node.maxItems) fail("list is too long");
          value.forEach((item, index) => schemaErrors((node.prefixItems || [])[index] || node.items || {}, item, `${path}[${index}]`, errors));
          break;
        case "object":
          if (!value || typeof value !== "object" || Array.isArray(value)) { fail("expected an object"); break; }
          for (const key of node.required || []) if (!own(value, key)) fail(`missing field: ${key}`);
          for (const [key, item] of Object.entries(value)) {
            if (own(node.properties || {}, key)) schemaErrors(node.properties[key], item, `${path}.${key}`, errors);
            else if (node.additionalProperties === false) fail(`unknown field: ${key}`);
            else if (typeof node.additionalProperties === "object") schemaErrors(node.additionalProperties, item, `${path}.${key}`, errors);
          }
          break;
      }
      return errors;
    }

    function validate(project) {
      const errors = schemaErrors(contract.schema, project);
      if (errors.length) return errors;
      const p = hydrate(contract.schema, project);
      const fail = (path, text) => errors.push(`${path}: ${text}`);
      if (!Object.keys(p.signals).length && !Object.keys(p.visualizers).length) fail("$", "add a signal or visualizer");
      const stems = contract.availableStems[p.separation.model];
      function source(item, path) {
        if (item.source !== null && item.stem !== null) fail(path, "choose a file OR a stem");
        if (item.source !== null && blank(item.source)) fail(path, "empty source path");
        if (item.stem !== null && !stems.includes(item.stem)) fail(path, "stem unavailable with this model");
      }
      for (const [name, item] of Object.entries(p.signals)) {
        const path = `signals.${name}`;
        if (blank(name)) fail(path, "empty name");
        source(item, path);
        if ((item.low ?? 0) >= (item.high ?? contract.nyquist)) fail(path, "low frequency must be below high frequency");
        const reference = item.ref_percentile ?? contract.referencePercentiles[item.feature];
        if (item.feature === "loudness" && item.floor_percentile >= reference) fail(path, "floor percentile must be below reference percentile");
      }
      p.effects.forEach((item, index) => {
        const path = `effects[${index}]`;
        if (!own(p.signals, item.signal)) fail(path, "signal not found");
        if (item.effect === "brightness" ? item.range === null || item.amount !== null : item.amount === null || item.range !== null) fail(path, "incompatible effect parameters");
      });
      for (const [name, item] of Object.entries(p.visualizers)) {
        const path = `visualizers.${name}`;
        if (blank(name)) fail(path, "empty name");
        if (item.left + item.width > 1 + 1e-12 || item.bottom + item.height > 1 + 1e-12) fail(path, "the region must fit inside the frame");
        if (item.spectrum.low >= item.spectrum.high) fail(path, "low frequency must be below high frequency");
        if (!contract.fftSizes.includes(item.spectrum.n_fft)) fail(path, "FFT size must be a power of two");
        item.tracks.forEach((track, index) => source(track, `${path}.tracks[${index}]`));
      }
      return errors;
    }

    function exportProject(project) {
      const errors = validate(project);
      if (errors.length) throw new Error(errors.join("\n"));
      return JSON.stringify(project, null, 2) + "\n";
    }

    function effectParameters(project, levels) {
      const result = { bloom: 0, exposure: 0, saturation: 0, zoom: 0, brightness: 1 };
      project.effects.forEach(item => {
        const raw = levels[item.signal] ?? 0.65;
        const value = Number.isFinite(raw) ? Math.max(0, Math.min(1, raw)) : 0;
        if (item.effect === "brightness") result.brightness *= item.range[0] + (item.range[1] - item.range[0]) * value;
        else result[item.effect] += value * item.amount;
      });
      return result;
    }
    return { hydrate: value => hydrate(contract.schema, value), validate, exportProject, effectParameters, resolve, nonnull, projectFrom };
  }
  root.BeatBloomCore = { create, clone, own, put };
  if (typeof module !== "undefined" && module.exports) module.exports = root.BeatBloomCore;
})(typeof globalThis === "undefined" ? this : globalThis);
