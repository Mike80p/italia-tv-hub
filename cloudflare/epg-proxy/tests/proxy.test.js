import test from "node:test";
import assert from "node:assert/strict";
import { handleRequest } from "../src/index.js";

function mockFetch(body, status = 200) {
  return async () => new Response(body, { status, headers: { "content-type": "audio/x-mpegurl", "x-upstream": "preserved" } });
}

test("rewrites only first M3U line and preserves remaining content", async () => {
  const input = '#EXTM3U url-tvg="old.xml"\n#EXTINF:-1 tvg-id="Rai1.it",Rai 1\nhttps://example/rai1.m3u8\n';
  const response = await handleRequest(new Request("https://worker.example/playlist.m3u"), mockFetch(input));
  assert.equal(response.status, 200);
  const output = await response.text();
  const lines = output.split("\n");
  assert.match(lines[0], /^#EXTM3U url-tvg="/);
  assert.match(lines[0], /superguidatv\.it\.xml/);
  assert.match(lines[0], /raiplay\.it\.xml/);
  assert.equal(lines.slice(1).join("\n"), input.split("\n").slice(1).join("\n"));
  assert.equal(response.headers.get("x-upstream"), "preserved");
  assert.equal(response.headers.get("access-control-allow-origin"), "*");
});

test("works when first line is split across stream chunks", async () => {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({ start(controller) {
    controller.enqueue(encoder.encode('#EXTM3U url-tvg="old'));
    controller.enqueue(encoder.encode('.xml"\n#EXTINF:-1,Rai 1\n'));
    controller.enqueue(encoder.encode('https://example/rai1.m3u8\n'));
    controller.close();
  }});
  const response = await handleRequest(new Request("https://worker.example/"), async () => new Response(stream, { status: 200 }));
  const output = await response.text();
  assert.ok(output.startsWith("#EXTM3U url-tvg="));
  assert.ok(output.includes("#EXTINF:-1,Rai 1\nhttps://example/rai1.m3u8\n"));
});

test("health endpoint does not fetch upstream", async () => {
  let called = false;
  const response = await handleRequest(new Request("https://worker.example/health"), async () => { called = true; throw new Error("should not run"); });
  assert.equal(response.status, 200);
  assert.equal(called, false);
  const json = await response.json();
  assert.equal(json.ok, true);
  assert.equal(json.epg_sources, 9);
});

test("returns 502 when upstream fails", async () => {
  const response = await handleRequest(new Request("https://worker.example/playlist.m3u"), async () => { throw new Error("network"); });
  assert.equal(response.status, 502);
  const json = await response.json();
  assert.equal(json.error, "upstream_fetch_failed");
});

test("returns 404 for unknown paths", async () => {
  const response = await handleRequest(new Request("https://worker.example/nope"), mockFetch("unused"));
  assert.equal(response.status, 404);
});
