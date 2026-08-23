const PLAYLIST_URL = "https://raw.githubusercontent.com/Mike80p/italia-tv-hub/main/output/playlist.m3u";
const EPG_GZIP_URL = "https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz";
const CACHE_SECONDS = 300;

function playlistHeader(requestUrl) {
  const base = new URL(requestUrl);
  base.pathname = "/epg.xml";
  base.search = "";
  base.hash = "";
  return `#EXTM3U url-tvg="${base.toString()}"\n`;
}

function rewriteFirstLineStream(body, requestUrl) {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  const header = playlistHeader(requestUrl);
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
      controller.enqueue(encoder.encode(header));
      const rest = pending.slice(newlineIndex + 1);
      if (rest) controller.enqueue(encoder.encode(rest));
      pending = "";
      firstLineDone = true;
    },
    flush(controller) {
      if (!firstLineDone) controller.enqueue(encoder.encode(header));
    }
  }));
}

async function proxyPlaylist(request, fetchImpl) {
  let upstream;
  try {
    upstream = await fetchImpl(PLAYLIST_URL, {
      headers: { "user-agent": "Italia-TV-Hub-EPG-Proxy/2.0" },
      cf: { cacheTtl: CACHE_SECONDS, cacheEverything: true }
    });
  } catch {
    return Response.json({ ok:false, error:"playlist_upstream_fetch_failed" }, { status:502, headers:{ "cache-control":"no-store" } });
  }
  if (!upstream.ok || !upstream.body) {
    return Response.json({ ok:false, error:"playlist_upstream_unavailable", status:upstream.status }, { status:502, headers:{ "cache-control":"no-store" } });
  }
  const headers = new Headers(upstream.headers);
  headers.set("content-type", "audio/x-mpegurl; charset=utf-8");
  headers.set("access-control-allow-origin", "*");
  headers.set("cache-control", `public, max-age=${CACHE_SECONDS}, s-maxage=${CACHE_SECONDS}`);
  headers.delete("content-length");
  return new Response(rewriteFirstLineStream(upstream.body, request.url), { status:200, headers });
}

async function proxyEpg(fetchImpl) {
  let upstream;
  try {
    upstream = await fetchImpl(EPG_GZIP_URL, {
      headers: {
        "user-agent": "Italia-TV-Hub-EPG-Proxy/2.0",
        "accept-encoding": "identity"
      },
      cf: { cacheTtl: CACHE_SECONDS, cacheEverything: true }
    });
  } catch {
    return Response.json({ ok:false, error:"epg_upstream_fetch_failed" }, { status:502, headers:{ "cache-control":"no-store" } });
  }
  if (!upstream.ok || !upstream.body) {
    return Response.json({ ok:false, error:"epg_upstream_unavailable", status:upstream.status }, { status:502, headers:{ "cache-control":"no-store" } });
  }

  let xmlStream;
  try {
    xmlStream = upstream.body.pipeThrough(new DecompressionStream("gzip"));
  } catch {
    return Response.json({ ok:false, error:"epg_decompression_failed" }, { status:502, headers:{ "cache-control":"no-store" } });
  }

  return new Response(xmlStream, {
    status:200,
    headers:{
      "access-control-allow-origin":"*",
      "cache-control":`public, max-age=${CACHE_SECONDS}, s-maxage=${CACHE_SECONDS}`,
      "content-type":"application/xml; charset=utf-8",
      "content-disposition":'inline; filename="epg.xml"'
    }
  });
}

export async function handleRequest(request, fetchImpl = fetch) {
  const url = new URL(request.url);

  if (url.pathname === "/health") {
    return Response.json({
      ok:true,
      service:"italia-tv-hub-epg-proxy",
      version:2,
      playlist_upstream:PLAYLIST_URL,
      epg_upstream:EPG_GZIP_URL,
      endpoints:["/playlist.m3u","/epg.xml","/health"]
    }, { headers:{ "cache-control":"no-store" } });
  }
  if (url.pathname === "/epg.xml") return proxyEpg(fetchImpl);
  if (url.pathname === "/" || url.pathname === "/playlist.m3u") return proxyPlaylist(request, fetchImpl);
  return new Response("Not found", { status:404 });
}

export default {
  async fetch(request) {
    return handleRequest(request);
  }
};
