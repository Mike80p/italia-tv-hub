const PLAYLIST_URL =
  "https://raw.githubusercontent.com/Mike80p/italia-tv-hub/main/output/playlist.m3u";

const EPG_XML_URL =
  "https://iptv-org.github.io/epg/guides/it/superguidatv.it.xml";

const CACHE_SECONDS = 300;

const TVG_ID_ALIASES = new Map([
  ["Rai 4.it", "Rai4.it"],
  ["Rai 5.it", "Rai5.it"],
  ["Rai Gulp.it", "RaiGulp.it"],
  ["Rai Movie.it", "RaiMovie.it"],
  ["Rai News 24.it", "RaiNews24.it"],
  ["Rai Premium.it", "RaiPremium.it"],
  ["Rai Scuola.it", "RaiScuola.it"],
  ["RAI Sport.it", "RaiSport.it"],
  ["Rai Sport.it", "RaiSport.it"],
  ["Rai Storia.it", "RaiStoria.it"],
  ["Rai Yoyo.it", "RaiYoyo.it"],
  ["Rai YoYo.it", "RaiYoyo.it"],
  ["Canale.5.it", "Canale5.it"],
  ["Italia.1.it", "Italia1.it"],
  ["Rete.4.it", "Rete4.it"],
]);

const NAME_ALIASES = new Map([
  ["rai 1", "Rai1.it"],
  ["rai 2", "Rai2.it"],
  ["rai 3", "Rai3.it"],
  ["rai 4", "Rai4.it"],
  ["rai 5", "Rai5.it"],
  ["rai gulp", "RaiGulp.it"],
  ["rai movie", "RaiMovie.it"],
  ["rai news 24", "RaiNews24.it"],
  ["rai premium", "RaiPremium.it"],
  ["rai scuola", "RaiScuola.it"],
  ["rai sport", "RaiSport.it"],
  ["rai storia", "RaiStoria.it"],
  ["rai yoyo", "RaiYoyo.it"],
  ["canale 5", "Canale5.it"],
  ["italia 1", "Italia1.it"],
  ["rete 4", "Rete4.it"],
  ["20 mediaset", "20.it"],
  ["boing", "Boing.it"],
  ["cartoonito", "Cartoonito.it"],
  ["cine34", "Cine34.it"],
  ["focus", "Focus.it"],
  ["iris", "Iris.it"],
  ["la5", "La5.it"],
  ["mediaset extra", "MediasetExtra.it"],
  ["italia 2", "Italia2.it"],
  ["top crime", "TopCrime.it"],
  ["tgcom24", "TGCom24.it"],
  ["la7", "La7.it"],
  ["tv8", "TV8.it"],
  ["nove", "Nove.it"],
  ["real time", "RealTime.it"],
  ["dmax", "DMAX.it"],
  ["giallo", "Giallo.it"],
  ["food network", "FoodNetwork.it"],
  ["motor trend", "MotorTrend.it"],
  ["warner tv", "WarnerTV.it"],
]);

function workerEpgUrl(requestUrl) {
  const url = new URL(requestUrl);
  url.pathname = "/epg.xml";
  url.search = "";
  url.hash = "";
  return url.toString();
}

function stripQualitySuffix(id) {
  return String(id || "").replace(/@(SD|HD|FHD|UHD|4K)$/i, "");
}

function cleanChannelName(name) {
  return String(name || "")
    .replace(/\[[^\]]*]/g, " ")
    .replace(/\([^)]*(?:p|i|hd|sd|uhd|4k)[^)]*\)/gi, " ")
    .replace(/\b(?:1080p|1080i|720p|576p|480p|4k|uhd|fhd|hd|sd)\b/gi, " ")
    .replace(/\s+G$/i, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function canonicalTvgId(rawId, displayName = "") {
  let id = stripQualitySuffix(rawId).trim();

  if (TVG_ID_ALIASES.has(id)) {
    return TVG_ID_ALIASES.get(id);
  }

  const byName = NAME_ALIASES.get(cleanChannelName(displayName));
  if (byName) {
    return byName;
  }

  return id;
}

function extinfDisplayName(line) {
  const comma = line.lastIndexOf(",");
  return comma >= 0 ? line.slice(comma + 1).trim() : "";
}

function rewriteExtinf(line) {
  if (!line.startsWith("#EXTINF:")) return line;

  const name = extinfDisplayName(line);
  const match = line.match(/\btvg-id="([^"]*)"/i);

  if (!match) {
    const id = canonicalTvgId("", name);
    if (!id) return line;
    return line.replace(
      /^#EXTINF:([^\s,]+)/,
      `#EXTINF:$1 tvg-id="${id}"`,
    );
  }

  const oldId = match[1];
  const newId = canonicalTvgId(oldId, name);
  if (!newId || newId === oldId) return line;

  return line.replace(
    /\btvg-id="[^"]*"/i,
    `tvg-id="${newId}"`,
  );
}

function playlistTransform(requestUrl) {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();

  let pending = "";
  let firstLine = true;

  return new TransformStream({
    transform(chunk, controller) {
      pending += decoder.decode(chunk, { stream: true });

      while (true) {
        const newline = pending.indexOf("\n");
        if (newline === -1) break;

        let line = pending.slice(0, newline);
        pending = pending.slice(newline + 1);

        if (line.endsWith("\r")) {
          line = line.slice(0, -1);
        }

        if (firstLine) {
          controller.enqueue(
            encoder.encode(
              `#EXTM3U url-tvg="${workerEpgUrl(requestUrl)}"\n`,
            ),
          );
          firstLine = false;
          continue;
        }

        controller.enqueue(
          encoder.encode(`${rewriteExtinf(line)}\n`),
        );
      }

      if (pending.length > 1_000_000) {
        throw new Error("M3U line buffer exceeded");
      }
    },

    flush(controller) {
      const tail = decoder.decode();
      if (tail) pending += tail;

      if (firstLine) {
        controller.enqueue(
          encoder.encode(
            `#EXTM3U url-tvg="${workerEpgUrl(requestUrl)}"\n`,
          ),
        );
        firstLine = false;
      }

      if (pending) {
        controller.enqueue(
          encoder.encode(rewriteExtinf(pending)),
        );
      }
    },
  });
}

async function playlistResponse(request, fetchImpl) {
  let upstream;
  try {
    upstream = await fetchImpl(PLAYLIST_URL, {
      headers: {
        "user-agent": "Italia-TV-Hub-EPG-Proxy/2.2",
      },
      cf: {
        cacheTtl: CACHE_SECONDS,
        cacheEverything: true,
      },
    });
  } catch {
    return Response.json(
      { ok: false, error: "playlist_fetch_failed" },
      { status: 502, headers: { "cache-control": "no-store" } },
    );
  }

  if (!upstream.ok || !upstream.body) {
    return Response.json(
      { ok: false, error: "playlist_unavailable", status: upstream.status },
      { status: 502, headers: { "cache-control": "no-store" } },
    );
  }

  return new Response(
    upstream.body.pipeThrough(playlistTransform(request.url)),
    {
      status: 200,
      headers: {
        "content-type": "audio/x-mpegurl; charset=utf-8",
        "access-control-allow-origin": "*",
        "cache-control":
          `public, max-age=${CACHE_SECONDS}, s-maxage=${CACHE_SECONDS}`,
      },
    },
  );
}

async function epgResponse(fetchImpl) {
  let upstream;
  try {
    upstream = await fetchImpl(EPG_XML_URL, {
      headers: {
        "user-agent": "Italia-TV-Hub-EPG-Proxy/2.2",
        "accept": "application/xml,text/xml,*/*",
      },
      cf: {
        cacheTtl: CACHE_SECONDS,
        cacheEverything: true,
      },
    });
  } catch {
    return Response.json(
      { ok: false, error: "epg_fetch_failed" },
      { status: 502, headers: { "cache-control": "no-store" } },
    );
  }

  if (!upstream.ok || !upstream.body) {
    return Response.json(
      { ok: false, error: "epg_unavailable", status: upstream.status },
      { status: 502, headers: { "cache-control": "no-store" } },
    );
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "content-type": "application/xml; charset=utf-8",
      "content-disposition": 'inline; filename="epg.xml"',
      "access-control-allow-origin": "*",
      "cache-control":
        `public, max-age=${CACHE_SECONDS}, s-maxage=${CACHE_SECONDS}`,
    },
  });
}

export async function handleRequest(request, fetchImpl = fetch) {
  const url = new URL(request.url);

  if (url.pathname === "/health") {
    return Response.json({
      ok: true,
      service: "italia-tv-hub-epg-proxy",
      version: "2.2",
      mapping: "canonical-tvg-id",
      endpoints: ["/playlist.m3u", "/epg.xml", "/health"],
    }, {
      headers: { "cache-control": "no-store" },
    });
  }

  if (url.pathname === "/epg.xml") {
    return epgResponse(fetchImpl);
  }

  if (url.pathname === "/" || url.pathname === "/playlist.m3u") {
    return playlistResponse(request, fetchImpl);
  }

  return new Response("Not found", { status: 404 });
}

export {
  canonicalTvgId,
  cleanChannelName,
  rewriteExtinf,
};

export default {
  async fetch(request) {
    return handleRequest(request);
  },
};
