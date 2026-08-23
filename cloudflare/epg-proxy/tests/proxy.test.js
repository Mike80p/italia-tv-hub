import test from "node:test";
import assert from "node:assert/strict";
import { gzipSync } from "node:zlib";
import { handleRequest } from "../src/index.js";

function playlistFetch(body) {
  return async (url) => {
    if (String(url).includes("playlist.m3u")) {
      return new Response(body, { status:200, headers:{ "x-source":"playlist" } });
    }
    throw new Error("unexpected URL");
  };
}

function epgFetch(xml) {
  const gz = gzipSync(Buffer.from(xml, "utf8"));
  return async (url) => {
    if (String(url).includes("epg_ripper_IT1.xml.gz")) {
      return new Response(gz, { status:200, headers:{ "content-type":"application/gzip" } });
    }
    throw new Error("unexpected URL");
  };
}

test("playlist header points to worker /epg.xml", async () => {
  const input = '#EXTM3U url-tvg="old.xml"\n#EXTINF:-1 tvg-id="Rai1.it",Rai 1\nhttps://example/rai1.m3u8\n';
  const response = await handleRequest(
    new Request("https://italia-tv-hub-epg-proxy.example.workers.dev/playlist.m3u"),
    playlistFetch(input)
  );
  const output = await response.text();
  assert.match(output.split("\n")[0], /\/epg\.xml"/);
  assert.equal(output.split("\n").slice(1).join("\n"), input.split("\n").slice(1).join("\n"));
});

test("/epg.xml returns decompressed valid XML", async () => {
  const xml = '<?xml version="1.0" encoding="UTF-8"?><tv><channel id="Rai1.it"><display-name>Rai 1</display-name></channel><programme channel="Rai1.it" start="20260823120000 +0200" stop="20260823130000 +0200"><title>Test</title></programme></tv>';
  const response = await handleRequest(
    new Request("https://italia-tv-hub-epg-proxy.example.workers.dev/epg.xml"),
    epgFetch(xml)
  );
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("content-type"), "application/xml; charset=utf-8");
  assert.equal(await response.text(), xml);
});

test("/health advertises v2 endpoints", async () => {
  const response = await handleRequest(
    new Request("https://italia-tv-hub-epg-proxy.example.workers.dev/health"),
    async () => { throw new Error("health must not fetch"); }
  );
  const json = await response.json();
  assert.equal(json.ok, true);
  assert.equal(json.version, 2);
  assert.ok(json.endpoints.includes("/epg.xml"));
});

test("EPG upstream failure returns 502", async () => {
  const response = await handleRequest(
    new Request("https://italia-tv-hub-epg-proxy.example.workers.dev/epg.xml"),
    async () => { throw new Error("network"); }
  );
  assert.equal(response.status, 502);
  const json = await response.json();
  assert.equal(json.error, "epg_upstream_fetch_failed");
});

test("unknown path returns 404", async () => {
  const response = await handleRequest(
    new Request("https://italia-tv-hub-epg-proxy.example.workers.dev/nope"),
    async () => new Response("unused")
  );
  assert.equal(response.status, 404);
});
