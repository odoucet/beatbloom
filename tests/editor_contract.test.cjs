"use strict";
const test = require("node:test"), assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path"), { execFileSync } = require("node:child_process");
const root = path.resolve(__dirname, ".."), html = fs.readFileSync(path.join(root, "editor/beatbloom-editor.html"), "utf8");
const contract = JSON.parse(html.match(/<script id="beatbloom-contract" type="application\/json">([\s\S]*?)<\/script>/)[1]);
const { create, clone } = require("../editor/src/core.js"), core = create(contract);
const fixtures = JSON.parse(execFileSync("uv", ["run", "--locked", "python", "tools/editor_cases.py"], { cwd: root, encoding: "utf8" }));

for (const item of fixtures) test(`Python / JavaScript validity: ${item.name}`, () => {
  assert.equal(core.validate(item.project).length === 0, item.valid);
});

test("every accepted export is valid in strict Pydantic", () => {
  const values = fixtures.filter(item => item.valid).map(item => JSON.parse(core.exportProject(core.hydrate(item.project))));
  values.push(JSON.parse(core.exportProject(contract.initialProject)));
  execFileSync("uv", ["run", "--locked", "python", "-c", "import json,sys; from beatbloom.config import ProjectConfig; [ProjectConfig.model_validate_json(json.dumps(v)) for v in json.load(sys.stdin)]"], { cwd: root, input: JSON.stringify(values), encoding: "utf8" });
});

test("import keeps relative source paths and large values", () => {
  const p = core.hydrate({schema_version: 2, signals: {s: {source: "../音楽/a.wav", release_ms: 999999}}});
  const exported = JSON.parse(core.exportProject(p));
  assert.equal(exported.signals.s.source, "../音楽/a.wav");
  assert.equal(exported.signals.s.release_ms, 999999);
});

test("prototype property names survive roundtrip without pollution", () => {
  const p = core.hydrate(JSON.parse('{"schema_version":2,"signals":{"__proto__":{},"constructor":{}},"effects":[{"signal":"__proto__","effect":"zoom","amount":0.1}]}'));
  assert.equal(Object.keys(JSON.parse(core.exportProject(p)).signals).length, 2);
  assert.equal({}.stem, undefined);
});

test("synthetic effect mixing matches Python", () => {
  const p = clone(contract.initialProject), levels = Object.fromEntries(Object.keys(p.signals).map(name => [name, .37]));
  p.effects.push({signal: Object.keys(p.signals)[0], effect: "brightness", range: [.8, 1.3], amount: null});
  p.effects.push({signal: Object.keys(p.signals)[0], effect: "bloom", amount: .3, range: null});
  const expected = JSON.parse(execFileSync("uv", ["run", "--locked", "python", "-c", "import json,sys; from beatbloom.config import ProjectConfig; from beatbloom.models import Signal; from beatbloom.render.effects import parameters_at; import numpy as np; from dataclasses import asdict; p,ls=json.load(sys.stdin); s={k:Signal(k,np.array([v,v],dtype=np.float32),np.array([0.,1.]),1.) for k,v in ls.items()}; print(json.dumps(asdict(parameters_at(ProjectConfig.model_validate_json(json.dumps(p)),s,0.5))))"], {cwd: root, input: JSON.stringify([p,levels]), encoding:"utf8"}));
  const actual = core.effectParameters(p, levels);
  for (const key of Object.keys(actual)) assert.ok(Math.abs(actual[key] - expected[key]) < 1e-6, key);
});

test("one-file artifact contains no runtime network dependencies", () => {
  assert.doesNotMatch(html, /<script[^>]+\bsrc=|<link[^>]+\bhref=|\bfetch\s*\(|\bXMLHttpRequest\b|\bWebSocket\b|\bimport\s*\(/);
  assert.match(html, /connect-src 'none'/);
});

test("an empty simulated level cannot produce NaN effect parameters", () => {
  const levels = Object.fromEntries(Object.keys(contract.initialProject.signals).map(name => [name, NaN]));
  const parameters = core.effectParameters(contract.initialProject, levels);
  assert.ok(Object.values(parameters).every(Number.isFinite));
  assert.equal(parameters.zoom, 0);
});

test("analysis preparation JSON restores all project settings", () => {
  const manifest = {key: "cached-analysis", parameters: {}, config: clone(contract.initialProject), signals: {cache: "data.npz"}};
  manifest.config.effects[0].range = [.5, 1.2];
  const p = core.hydrate(core.projectFrom(manifest));
  assert.equal(core.validate(p).length, 0);
  assert.deepEqual(p, manifest.config);
  assert.equal(JSON.parse(core.exportProject(p)).key, undefined);
});

test("old analysis manifests explain how to recover their config", () => {
  assert.throws(() => core.projectFrom({key: "old", parameters: {}, signals: {}}), /Run analyze again/);
});

test("editor shell and default project use English names", () => {
  assert.match(html, /<html lang="en">/);
  assert.match(html, /href="https:\/\/github.com\/odoucet\/beatbloom"/);
  assert.deepEqual(Object.keys(contract.initialProject.signals), ["global_volume", "piano_onsets"]);
  assert.deepEqual(Object.keys(contract.initialProject.visualizers), ["waveform", "spectrum"]);
});
