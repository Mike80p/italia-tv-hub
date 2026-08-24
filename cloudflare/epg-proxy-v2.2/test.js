import test from "node:test";
import assert from "node:assert/strict";
import {
  canonicalTvgId,
  rewriteExtinf,
  handleRequest,
} from "./index.js";

test("quality suffixes normalize to canonical IDs", () => {
  assert.equal(canonicalTvgId("Rai1.it@SD", "Rai 1 (720p)"), "Rai1.it");
  assert.equal(canonicalTvgId("Rai3.it@HD", "Rai 3 (720p)"), "Rai3.it");
  assert.equal(canonicalTvgId("20.it@SD", "20 Mediaset"), "20.it");
});

test("space and punctuation aliases normalize", () => {
  assert.equal(canonicalTvgId("Rai 4.it", "Rai 4 G"), "Rai4.it");
  assert.equal(canonicalTvgId("Rai News 24.it", "Rai News 24 G"), "RaiNews24.it");
  assert.equal(canonicalTvgId("Canale.5.it", "Canale 5 G"), "Canale5.it");
  assert.equal(canonicalTvgId("Rete.4.it", "Rete 4 G"), "Rete4.it");
});

test("display name repairs known bad IDs", () => {
  assert.equal(canonicalTvgId("wrong.id", "Italia 1 G"), "Italia1.it");
  assert.equal(canonicalTvgId("", "Rai Movie G"), "RaiMovie.it");
});

test("EXTINF is rewritten without changing other metadata", () => {
  const line = '#EXTINF:-1 tvg-id="Rai2.it@SD" tvg-logo="logo.png" group-title="RAI",Rai 2 (1080p)';
  const out = rewriteExtinf(line);
  assert.equal(out, '#EXTINF:-1 tvg-id="Rai2.it" tvg-logo="logo.png" group-title="RAI",Rai 2 (1080p)');
});

test("missing tvg-id is inserted for known name", () => {
  const out = rewriteExtinf('#EXTINF:-1 group-title="RAI",Rai 5 G');
  assert.match(out, /tvg-id="Rai5\.it"/);
});

test("health reports V2.2", async () => {
  const response = await handleRequest(
    new Request("https://example.workers.dev/health"),
    async () => { throw new Error("must not fetch"); },
  );
  const data = await response.json();
  assert.equal(data.version, "2.2");
  assert.equal(data.mapping, "canonical-tvg-id");
});
