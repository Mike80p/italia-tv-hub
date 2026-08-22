(() => {
  "use strict";

  const PLAYLIST_URL = "https://raw.githubusercontent.com/Mike80p/italia-tv-hub/main/output/playlist.m3u";
  const EPG_URL = "https://raw.githubusercontent.com/Mike80p/italia-tv-hub/main/output/epg.xml";

  const state = {
    channels: [],
    programmesByChannel: new Map(),
    selectedChannel: null,
    selectedDateKey: null,
  };

  const normalize = (value) => String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/\b(?:4k|uhd|fhd|full\s*hd|hd|sd|1080p|1080i|720p|576p|480p)\b/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

  function parseAttributes(line) {
    const result = {};
    const payload = line.includes(":") ? line.slice(line.indexOf(":") + 1) : line;
    const beforeName = payload.includes(",") ? payload.slice(0, payload.lastIndexOf(",")) : payload;
    const pattern = /([\w-]+)="([^"]*)"/g;
    let match;
    while ((match = pattern.exec(beforeName)) !== null) result[match[1]] = match[2];
    return result;
  }

  function parseM3U(text) {
    const lines = String(text || "").replace(/\r/g, "").split("\n");
    const channels = [];
    for (let i = 0; i < lines.length; i += 1) {
      const line = lines[i].trim();
      if (!line.startsWith("#EXTINF:")) continue;
      const attrs = parseAttributes(line);
      const comma = line.lastIndexOf(",");
      const name = (comma >= 0 ? line.slice(comma + 1) : attrs["tvg-name"] || "Canale").trim();
      let url = "";
      for (let j = i + 1; j < lines.length; j += 1) {
        const candidate = lines[j].trim();
        if (!candidate || candidate.startsWith("#")) continue;
        url = candidate;
        break;
      }
      channels.push({
        name,
        url,
        tvgId: attrs["tvg-id"] || "",
        tvgName: attrs["tvg-name"] || "",
        logo: attrs["tvg-logo"] || "",
        group: attrs["group-title"] || "Altro",
      });
    }
    return channels;
  }

  function parseXmltvDate(raw) {
    const match = String(raw || "").match(/^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?:\s*([+-])(\d{2})(\d{2}))?/);
    if (!match) return null;
    const [, y, m, d, hh, mm, ss, sign, oh, om] = match;
    let utcMs = Date.UTC(+y, +m - 1, +d, +hh, +mm, +ss);
    if (sign) {
      const offset = ((+oh * 60) + +om) * 60_000;
      utcMs += sign === "+" ? -offset : offset;
    }
    return new Date(utcMs);
  }

  function dateKey(date) {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "Europe/Rome",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(date);
  }

  function timeLabel(date) {
    return new Intl.DateTimeFormat("it-IT", {
      timeZone: "Europe/Rome",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date);
  }

  function dayLabel(key, todayKey) {
    const date = new Date(`${key}T12:00:00+02:00`);
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowKey = dateKey(tomorrow);
    if (key === todayKey) return "Oggi";
    if (key === tomorrowKey) return "Domani";
    return new Intl.DateTimeFormat("it-IT", {
      weekday: "short",
      day: "numeric",
      month: "short",
      timeZone: "Europe/Rome",
    }).format(date);
  }

  function matchProgrammeKeys(channel, knownEpgIds, displayNameMap) {
    const keys = [];
    if (channel.tvgId && knownEpgIds.has(channel.tvgId)) keys.push(channel.tvgId);
    const candidates = [channel.tvgName, channel.name].filter(Boolean).map(normalize).filter(Boolean);
    for (const candidate of candidates) {
      const exact = displayNameMap.get(candidate);
      if (exact && !keys.includes(exact)) keys.push(exact);
    }
    return keys;
  }

  function buildEpg(xmlText, channels) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(xmlText, "application/xml");
    if (doc.querySelector("parsererror")) throw new Error("EPG XML non valido");

    const displayNameMap = new Map();
    const knownEpgIds = new Set();
    for (const node of doc.querySelectorAll("channel")) {
      const id = node.getAttribute("id") || "";
      if (!id) continue;
      knownEpgIds.add(id);
      for (const display of node.querySelectorAll("display-name")) {
        const key = normalize(display.textContent);
        if (key && !displayNameMap.has(key)) displayNameMap.set(key, id);
      }
    }

    const rawById = new Map();
    for (const node of doc.querySelectorAll("programme")) {
      const channelId = node.getAttribute("channel") || "";
      const start = parseXmltvDate(node.getAttribute("start"));
      const stop = parseXmltvDate(node.getAttribute("stop"));
      if (!channelId || !start || !stop) continue;
      const item = {
        channelId,
        start,
        stop,
        title: node.querySelector("title")?.textContent?.trim() || "Programma",
        description: node.querySelector("desc")?.textContent?.trim() || "",
        category: node.querySelector("category")?.textContent?.trim() || "",
      };
      if (!rawById.has(channelId)) rawById.set(channelId, []);
      rawById.get(channelId).push(item);
    }

    const byChannel = new Map();
    channels.forEach((channel, index) => {
      const keys = matchProgrammeKeys(channel, knownEpgIds, displayNameMap);
      const programmes = keys.flatMap((key) => rawById.get(key) || []);
      const unique = new Map();
      programmes.forEach((item) => unique.set(`${item.start.getTime()}|${item.stop.getTime()}|${item.title}`, item));
      byChannel.set(index, [...unique.values()].sort((a, b) => a.start - b.start));
    });
    return byChannel;
  }

  function programmeClass(programme, now) {
    if (programme.start <= now && programme.stop > now) return "current";
    if (programme.stop <= now) return "past";
    return "future";
  }

  function progressPercent(programme, now) {
    const duration = programme.stop - programme.start;
    if (duration <= 0) return 0;
    return Math.max(0, Math.min(100, ((now - programme.start) / duration) * 100));
  }

  globalThis.ItaliaTVHubTest = {
    normalize,
    parseAttributes,
    parseM3U,
    parseXmltvDate,
    dateKey,
    programmeClass,
    progressPercent,
  };
  if (typeof document === "undefined") return;

  const el = {
    status: document.querySelector("#status"),
    search: document.querySelector("#channel-search"),
    channelList: document.querySelector("#channel-list"),
    empty: document.querySelector("#empty-state"),
    guide: document.querySelector("#guide-content"),
    logo: document.querySelector("#selected-channel-logo"),
    group: document.querySelector("#selected-channel-group"),
    name: document.querySelector("#selected-channel-name"),
    nowCard: document.querySelector("#now-card"),
    nowTime: document.querySelector("#now-time"),
    nowTitle: document.querySelector("#now-title"),
    nowDescription: document.querySelector("#now-description"),
    nowProgress: document.querySelector("#now-progress"),
    dateTabs: document.querySelector("#date-tabs"),
    schedule: document.querySelector("#schedule"),
    noSchedule: document.querySelector("#no-schedule"),
    scheduleCount: document.querySelector("#schedule-count"),
  };

  function makeFallback(name) {
    const box = document.createElement("span");
    box.className = "channel-thumb-fallback";
    box.textContent = (name || "TV").slice(0, 2).toUpperCase();
    return box;
  }

  function renderChannels(filter = "") {
    const query = normalize(filter);
    el.channelList.replaceChildren();
    state.channels.forEach((channel, index) => {
      if (query && !normalize(`${channel.name} ${channel.group}`).includes(query)) return;
      const button = document.createElement("button");
      button.className = "channel-button";
      button.type = "button";
      button.setAttribute("role", "listitem");
      button.setAttribute("aria-selected", String(state.selectedChannel === index));
      button.dataset.index = String(index);

      if (channel.logo) {
        const img = document.createElement("img");
        img.className = "channel-thumb";
        img.src = channel.logo;
        img.alt = "";
        img.loading = "lazy";
        img.addEventListener("error", () => img.replaceWith(makeFallback(channel.name)));
        button.append(img);
      } else button.append(makeFallback(channel.name));

      const copy = document.createElement("span");
      const name = document.createElement("span");
      name.className = "channel-name";
      name.textContent = channel.name;
      const meta = document.createElement("span");
      meta.className = "channel-meta";
      const count = state.programmesByChannel.get(index)?.length || 0;
      meta.textContent = `${channel.group}${count ? ` · ${count} programmi EPG` : ""}`;
      copy.append(name, meta);
      button.append(copy);
      button.addEventListener("click", () => selectChannel(index));
      el.channelList.append(button);
    });
  }

  function selectChannel(index) {
    if (index < 0 || !state.channels[index]) return;
    state.selectedChannel = index;
    const channel = state.channels[index];
    const programmes = state.programmesByChannel.get(index) || [];
    const today = dateKey(new Date());
    const dates = [...new Set(programmes.map((item) => dateKey(item.start)))].sort();
    state.selectedDateKey = dates.includes(today) ? today : (dates[0] || today);

    el.empty.hidden = true;
    el.guide.hidden = false;
    el.name.textContent = channel.name;
    el.group.textContent = channel.group;
    el.logo.src = channel.logo || "";
    el.logo.alt = channel.logo ? `Logo ${channel.name}` : "";
    el.logo.closest(".logo-shell").hidden = !channel.logo;
    renderChannels(el.search.value);
    renderGuide();
    document.querySelector(".guide-panel")?.scrollIntoView({ block: "start", behavior: "smooth" });
  }

  function renderGuide() {
    const programmes = state.programmesByChannel.get(state.selectedChannel) || [];
    const now = new Date();
    const today = dateKey(now);
    const availableDates = [...new Set(programmes.map((item) => dateKey(item.start)))].sort();

    el.dateTabs.replaceChildren();
    availableDates.forEach((key) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "date-tab";
      button.textContent = dayLabel(key, today);
      if (key === state.selectedDateKey) button.setAttribute("aria-current", "date");
      button.addEventListener("click", () => {
        state.selectedDateKey = key;
        renderGuide();
      });
      el.dateTabs.append(button);
    });

    const current = programmes.find((item) => item.start <= now && item.stop > now);
    if (current) {
      el.nowCard.hidden = false;
      el.nowTime.textContent = `${timeLabel(current.start)} – ${timeLabel(current.stop)}`;
      el.nowTitle.textContent = current.title;
      el.nowDescription.textContent = current.description || current.category || "";
      el.nowProgress.style.width = `${progressPercent(current, now).toFixed(1)}%`;
    } else el.nowCard.hidden = true;

    const dayItems = programmes.filter((item) => dateKey(item.start) === state.selectedDateKey);
    el.schedule.replaceChildren();
    el.scheduleCount.textContent = dayItems.length ? `${dayItems.length} programmi` : "";
    el.noSchedule.hidden = dayItems.length > 0;

    dayItems.forEach((programme) => {
      const status = programmeClass(programme, now);
      const item = document.createElement("article");
      item.className = `programme ${status}`;
      item.setAttribute("role", "listitem");
      if (status === "current") item.id = "current-programme";
      const time = document.createElement("div");
      time.className = "programme-time-slot";
      time.textContent = `${timeLabel(programme.start)}\n${timeLabel(programme.stop)}`;
      const content = document.createElement("div");
      const title = document.createElement("p");
      title.className = "programme-title";
      title.textContent = programme.title;
      content.append(title);
      if (programme.description || programme.category) {
        const desc = document.createElement("p");
        desc.className = "programme-desc";
        desc.textContent = programme.description || programme.category;
        content.append(desc);
      }
      item.append(time, content);
      el.schedule.append(item);
    });

    requestAnimationFrame(() => document.querySelector("#current-programme")?.scrollIntoView({ block: "center" }));
  }

  async function load() {
    try {
      const [playlistResponse, epgResponse] = await Promise.all([
        fetch(PLAYLIST_URL, { cache: "no-store" }),
        fetch(EPG_URL, { cache: "no-store" }),
      ]);
      if (!playlistResponse.ok) throw new Error(`Playlist HTTP ${playlistResponse.status}`);
      if (!epgResponse.ok) throw new Error(`EPG HTTP ${epgResponse.status}`);
      const [playlistText, epgText] = await Promise.all([playlistResponse.text(), epgResponse.text()]);
      state.channels = parseM3U(playlistText);
      state.programmesByChannel = buildEpg(epgText, state.channels);
      const withEpg = state.channels.filter((_, i) => (state.programmesByChannel.get(i) || []).length > 0).length;
      el.status.textContent = `${state.channels.length} canali · EPG su ${withEpg}`;
      renderChannels();
      const firstWithEpg = state.channels.findIndex((_, i) => (state.programmesByChannel.get(i) || []).length > 0);
      selectChannel(firstWithEpg >= 0 ? firstWithEpg : 0);
    } catch (error) {
      console.error(error);
      el.status.textContent = "Errore caricamento guida TV";
      el.empty.innerHTML = "<p>Impossibile caricare playlist o programmazione. Riprova più tardi.</p>";
    }
  }

  el.search.addEventListener("input", () => renderChannels(el.search.value));
  load();
})();
