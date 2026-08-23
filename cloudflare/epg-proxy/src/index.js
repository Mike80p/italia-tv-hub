const PLAYLIST_URL = "https://raw.githubusercontent.com/Mike80p/italia-tv-hub/main/output/playlist.m3u";

const EPG_URLS = [
  "https://iptv-org.github.io/epg/guides/it/superguidatv.it.xml",
  "https://iptv-org.github.io/epg/guides/it/raiplay.it.xml",
  "https://iptv-org.github.io/epg/guides/it/mediaset.it.xml",
  "https://iptv-org.github.io/epg/guides/it/tivu.tv.xml",
  "https://iptv-org.github.io/epg/guides/it/guidatv.sky.it.xml",
  "https://iptv-org.github.io/epg/guides/it/tv.blue.ch.xml",
  "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/PlutoTV/it.xml.gz",
  "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/SamsungTVPlus/it.xml.gz",
  "https://raw.githubusercontent.com/Mike80p/italia-tv-hub/main/output/epg.xml"
];

const HEADER = `#EXTM3U url-tvg="${EPG_URLS.join(",")}"\n`;

function contentHeaders(source) {
  const headers = new Headers(source.headers);
  headers.set("content-type", "audio/x-mpegurl; charset=utf-8");
  headers.set("cache-control", "public, max-age=300, s-maxage=300");
  headers.set("access-control-allow-origin", "*");
  headers.delete("content-length");
  return headers;
}

function rewriteFirstLineStream(body) {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  let firstLineDone = false;
  let pending = "";

  return body.pipeThrough(new TransformStream({
    transform(chunk, controller) {
      if (firstLineDone) {
        controller.enqueue(chunk);
        return;
      }
      pending += decoder.decode(chunk, { stream: true });
      const newlineIndex = pending.indexOf("\n");
      if (newlineIndex === -1) {
        if (pending.length > 16384) throw new Error("Invalid M3U: first line too long");
        return;
      }
      controller.enqueue(encoder.encode(HEADER));
      const rest = pending.slice(newlineIndex + 1);
      if (rest) controller.enqueue(encoder.encode(rest));
      pending = "";
      firstLineDone = true;
    },
    flush(controller) {
      if (!firstLineDone) controller.enqueue(encoder.encode(HEADER));
    }
  }));
}

export async function handleRequest(request, fetchImpl = fetch) {
  const url = new URL(request.url);
  if (url.pathname === "/health") {
    return Response.json({ ok: true, service: "italia-tv-hub-epg-proxy", epg_sources: EPG_URLS.length, upstream: PLAYLIST_URL }, { headers: { "cache-control": "no-store" } });
  }
  if (url.pathname !== "/" && url.pathname !== "/playlist.m3u") return new Response("Not found", { status: 404 });

  let upstream;
  try {
    upstream = await fetchImpl(PLAYLIST_URL, {
      headers: { "user-agent": "Italia-TV-Hub-EPG-Proxy/1.0" },
      cf: { cacheTtl: 300, cacheEverything: true }
    });
  } catch {
    return Response.json({ ok: false, error: "upstream_fetch_failed" }, { status: 502, headers: { "cache-control": "no-store" } });
  }

  if (!upstream.ok || !upstream.body) {
    return Response.json({ ok: false, error: "upstream_unavailable", status: upstream.status }, { status: 502, headers: { "cache-control": "no-store" } });
  }

  return new Response(rewriteFirstLineStream(upstream.body), { status: 200, headers: contentHeaders(upstream) });
}

export default { async fetch(request) { return handleRequest(request); } };
