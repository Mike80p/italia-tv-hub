const PLAYLIST_URL =
  "https://raw.githubusercontent.com/Mike80p/italia-tv-hub/main/output/playlist.m3u";

const EPG_GZ_URL =
  "https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz";

const CACHE_SECONDS = 300;

const TVG_ID_ALIASES = new Map([
  ["Rai1.it@SD", "Rai1.it"],
  ["Rai2.it@SD", "Rai2.it"],
  ["Rai3.it@HD", "Rai3.it"],
  ["20.it@SD", "20.it"],
  ["Canale5.it@SD", "Canale.5.it"],
  ["Canale5.it", "Canale.5.it"],
  ["Italia1.it@SD", "Italia.1.it"],
  ["Italia1.it", "Italia.1.it"],
  ["Rete4.it@SD", "Rete.4.it"],
  ["Rete4.it", "Rete.4.it"],
  ["Iris.it@SD", "Iris.it"],
]);

const PREFER_G_IDS = new Set([
  "Rai1.it",
  "Rai2.it",
  "Rai3.it",
  "20.it",
  "Canale.5.it",
  "Iris.it",
  "Italia.1.it",
  "Rete.4.it",
]);

function workerEpgUrl(requestUrl) {
  const url = new URL(requestUrl);
  url.pathname = "/epg.xml";
  url.search = "";
  url.hash = "";
  return url.toString();
}

function canonicalTvgId(rawId) {
  const value = String(rawId || "").trim();

  if (TVG_ID_ALIASES.has(value)) {
    return TVG_ID_ALIASES.get(value);
  }

  return value.replace(/@(SD|HD|FHD|UHD|4K)$/i, "");
}

function displayName(line) {
  const comma = line.lastIndexOf(",");
  return comma >= 0 ? line.slice(comma + 1).trim() : "";
}

function cleanDisplayName(name) {
  return String(name || "")
    .replace(/\s*\[Geo-blocked\]\s*/gi, " ")
    .replace(
      /\s*\((?:1080p|1080i|720p|576p|480p|4K|UHD|FHD|HD|SD)\)\s*/gi,
      " ",
    )
    .replace(/\s+G$/i, "")
    .replace(/\s+/g, " ")
    .trim();
}

function rewriteExtinf(line) {
  if (!line.startsWith("#EXTINF:")) return line;

  let output = line;
  const idMatch = output.match(/\btvg-id="([^"]*)"/i);

  if (idMatch) {
    const oldId = idMatch[1];
    const newId = canonicalTvgId(oldId);

    if (newId && newId !== oldId) {
      output = output.replace(
        /\btvg-id="[^"]*"/i,
        `tvg-id="${newId}"`,
      );
    }
  }

  const comma = output.lastIndexOf(",");
  if (comma >= 0) {
    output =
      output.slice(0, comma + 1) +
      cleanDisplayName(output.slice(comma + 1));
  }

  return output;
}

function parseRecords(text) {
  const lines = text.replace(/\r/g, "").split("\n");
  lines.shift();

  const records = [];
  let current = [];

  for (const line of lines) {
    if (line.startsWith("#EXTINF:")) {
      if (current.length) records.push(current);
      current = [line];
    } else if (current.length) {
      current.push(line);
    }
  }

  if (current.length) records.push(current);
  return records;
}

function recordInfo(record) {
  const extinf = record[0] || "";
  const idMatch = extinf.match(/\btvg-id="([^"]*)"/i);
  const rawId = idMatch ? idMatch[1] : "";
  const channelId = canonicalTvgId(rawId);
  const name = displayName(extinf);

  return {
    channelId,
    name,
    isG: /\sG$/i.test(name),
    isGeoBlocked: /\[Geo-blocked\]/i.test(name),
  };
}

function dedupeRecords(records) {
  const groups = new Map();

  for (const record of records) {
    const info = recordInfo(record);
    const key = info.channelId || info.name.toLowerCase();

    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push({ record, info });
  }

  const result = [];

  for (const variants of groups.values()) {
    if (variants.length === 1) {
      result.push(variants[0].record);
      continue;
    }

    let selected = null;

    if (PREFER_G_IDS.has(variants[0].info.channelId)) {
      selected = variants.find(
        (variant) => variant.info.isG && !variant.info.isGeoBlocked,
      );
    }

    if (!selected) {
      selected = variants.find(
        (variant) => !variant.info.isGeoBlocked,
      );
    }

    if (!selected) selected = variants[0];
    result.push(selected.record);
  }

  return result;
}

function buildPlaylist(text, requestUrl) {
  const records = dedupeRecords(parseRecords(text));
  const lines = [
    `#EXTM3U url-tvg="${workerEpgUrl(requestUrl)}"`,
  ];

  for (const record of records) {
    lines.push(rewriteExtinf(record[0]), ...record.slice(1));
  }

  return lines.join("\n").replace(/\n+$/, "") + "\n";
}

async function playlistResponse(request, fetchImpl = fetch) {
  let upstream;

  try {
    upstream = await fetchImpl(PLAYLIST_URL, {
      headers: {
        "user-agent": "Italia-TV-Hub-EPG-Proxy/2.5",
      },
      cf: {
        cacheTtl: CACHE_SECONDS,
        cacheEverything: true,
      },
    });
  } catch {
    return Response.json(
      { ok: false, error: "playlist_fetch_failed" },
      { status: 502 },
    );
  }

  if (!upstream.ok) {
    return Response.json(
      {
        ok: false,
        error: "playlist_unavailable",
        status: upstream.status,
      },
      { status: 502 },
    );
  }

  const sourceText = await upstream.text();
  const cleanPlaylist = buildPlaylist(sourceText, request.url);

  return new Response(cleanPlaylist, {
    status: 200,
    headers: {
      "content-type": "audio/x-mpegurl; charset=utf-8",
      "access-control-allow-origin": "*",
      "cache-control":
        `public, max-age=${CACHE_SECONDS}, s-maxage=${CACHE_SECONDS}`,
    },
  });
}

async function epgResponse(fetchImpl = fetch) {
  let upstream;

  try {
    upstream = await fetchImpl(EPG_GZ_URL, {
      headers: {
        "user-agent": "Italia-TV-Hub-EPG-Proxy/2.5",
        accept: "application/gzip,application/octet-stream,*/*",
      },
      cf: {
        cacheTtl: CACHE_SECONDS,
        cacheEverything: true,
      },
    });
  } catch {
    return Response.json(
      { ok: false, error: "epg_fetch_failed" },
      { status: 502 },
    );
  }

  if (!upstream.ok || !upstream.body) {
    return Response.json(
      {
        ok: false,
        error: "epg_unavailable",
        status: upstream.status,
      },
      { status: 502 },
    );
  }

  let xmlStream;

  try {
    xmlStream = upstream.body.pipeThrough(
      new DecompressionStream("gzip"),
    );
  } catch {
    return Response.json(
      { ok: false, error: "epg_decompression_failed" },
      { status: 502 },
    );
  }

  return new Response(xmlStream, {
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
      version: "2.5",
      epg_source: "EPGShare IT1",
      mapping: "epgshare-compatible",
      dedupe: "conservative-primary-view",
      endpoints: ["/playlist.m3u", "/epg.xml", "/health"],
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
  cleanDisplayName,
  rewriteExtinf,
  parseRecords,
  dedupeRecords,
  buildPlaylist,
};

export default {
  async fetch(request) {
    return handleRequest(request);
  },
};
