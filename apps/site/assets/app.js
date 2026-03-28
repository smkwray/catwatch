/* ============================================================
   OpenCatWatch — Frontend Application
   Loads dashboard.json + audit data, renders editorial dashboard
   with ECharts visualizations, theme-aware rendering.
   ============================================================ */

/* ── Constants ── */

const PERIL_LABELS = {
  ca_earthquake: "CA Earthquake",
  ca_wildfire: "CA Wildfire",
  cyber: "Cyber",
  earthquake: "Earthquake",
  europe_windstorm: "EU Windstorm",
  flood: "Flood",
  japan_typhoon: "JP Typhoon",
  mortgage_insurance: "Mortgage Ins.",
  other_property_cat: "Other Property",
  severe_convective_storm: "Severe Storm",
  us_wind: "US Wind",
};

const PERIL_COLORS = {
  ca_earthquake: "#ef4444",
  ca_wildfire: "#f97316",
  cyber: "#a855f7",
  earthquake: "#dc2626",
  europe_windstorm: "#06b6d4",
  flood: "#3b82f6",
  japan_typhoon: "#14b8a6",
  mortgage_insurance: "#84cc16",
  other_property_cat: "#94a3b8",
  severe_convective_storm: "#eab308",
  us_wind: "#22d3ee",
};

const HINT_LABELS = {
  strengthen_region_evidence: "Strengthen region evidence",
  replace_broad_peril_classification: "Replace broad peril",
  add_sponsor_evidence: "Add sponsor evidence",
  confirm_maturity_date: "Confirm maturity date",
};

const BLOCKER_LABELS = {
  weak_region_evidence: "Weak region",
  missing_maturity: "Missing maturity",
  broad_peril: "Broad peril",
  missing_sponsor: "Missing sponsor",
  region_unknown: "Unknown region",
};

const REASON_LABELS = {
  weak_region_evidence: "Weak region",
  broad_peril: "Broad peril",
  broad_peril_match: "Broad peril match",
  missing_sponsor: "Missing sponsor",
  region_unknown: "Unknown region",
  missing_maturity: "Missing maturity",
};

/* ── Format Helpers ── */

function fmtCapital(amount) {
  if (amount >= 1e12) return "$" + (amount / 1e12).toFixed(1) + "T";
  if (amount >= 1e9) return "$" + (amount / 1e9).toFixed(1) + "B";
  if (amount >= 1e6) return "$" + (amount / 1e6).toFixed(0) + "M";
  if (amount >= 1e3) return "$" + (amount / 1e3).toFixed(0) + "K";
  return "$" + amount.toLocaleString();
}

function fmtNum(n) {
  return typeof n === "number" ? n.toLocaleString() : String(n);
}

function escHtml(str) {
  var d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

function fmtDate(val) {
  if (!val) return "";
  return val.slice(0, 10);
}

function sourceLink(url, label) {
  if (!url) return "";
  return '<a href="' + escHtml(url) + '" target="_blank" rel="noreferrer">' + escHtml(label || "source") + "</a>";
}

/* ── Theme-Aware Chart Colors ── */

function getChartTheme() {
  var isDark = document.documentElement.getAttribute("data-theme") === "dark";
  return {
    isDark: isDark,
    bg: "transparent",
    text: isDark ? "#94a3b8" : "#64748b",
    textStrong: isDark ? "#e2e8f0" : "#1a202c",
    grid: isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)",
    axis: isDark ? "#475569" : "#cbd5e1",
    tooltipBg: isDark ? "#0f172a" : "#1e293b",
    tooltipText: isDark ? "#e2e8f0" : "#f1f5f9",
    tooltipBorder: isDark ? "#475569" : "#334155",
    accent: isDark ? "#60a5fa" : "#2563eb",
    accentLight: isDark ? "rgba(96,165,250,0.15)" : "rgba(37,99,235,0.1)",
    good: isDark ? "#4ade80" : "#16a34a",
    warn: isDark ? "#fbbf24" : "#d97706",
  };
}

function baseTooltip(t) {
  return {
    backgroundColor: t.tooltipBg,
    borderColor: t.tooltipBorder,
    textStyle: { color: t.tooltipText, fontSize: 12 },
    borderWidth: 1,
  };
}

function baseAxisLabel(t) { return { color: t.text, fontSize: 11 }; }
function baseAxisLine(t) { return { lineStyle: { color: t.axis } }; }
function baseSplitLine(t) { return { lineStyle: { color: t.grid } }; }

/* ── Data Loading ── */

async function loadJSON(url) {
  try {
    var res = await fetch(url);
    if (!res.ok) return null;
    return await res.json();
  } catch (_) {
    return null;
  }
}

/* ── ECharts Instance Registry ── */

var charts = {};
var worldMapLoaded = false;

async function loadWorldMap() {
  if (worldMapLoaded) return true;
  try {
    var res = await fetch("https://cdn.jsdelivr.net/npm/echarts@4.9.0/map/json/world.json");
    if (!res.ok) return false;
    var data = await res.json();
    echarts.registerMap("world", data);
    worldMapLoaded = true;
    return true;
  } catch (_) {
    return false;
  }
}

function initChart(id) {
  var el = document.getElementById(id);
  if (!el) return null;
  if (charts[id]) charts[id].dispose();
  var instance = echarts.init(el);
  charts[id] = instance;
  return instance;
}

function resizeAllCharts() {
  Object.values(charts).forEach(function (c) {
    if (c && !c.isDisposed()) c.resize();
  });
}

/* ============================================================
   Hero
   ============================================================ */

function renderHero(dashboard, audit) {
  var kpis = dashboard.kpis || {};
  var sb = dashboard.story_blocks || {};
  var cc = sb.capital_concentration || [];
  var runway = sb.maturity_runway || [];

  /* Total USD capital */
  var usdRow = cc.find(function (r) { return r.currency === "USD"; });
  var totalCap = usdRow ? usdRow.total_known_issue_amount : 0;
  var capEl = document.getElementById("stat-capital");
  if (capEl) capEl.textContent = fmtCapital(totalCap);

  /* Active tranches */
  var trEl = document.getElementById("stat-tranches");
  if (trEl) trEl.textContent = fmtNum(kpis.active_tranches || 0);

  /* Sponsors */
  var spEl = document.getElementById("stat-sponsors");
  if (spEl) spEl.textContent = fmtNum(kpis.identified_sponsors || 0);

  /* 12mo maturing capital */
  var mat12 = runway.find(function (r) { return r.window_months === 12 && r.currency === "USD"; });
  var matEl = document.getElementById("stat-maturing");
  if (matEl) matEl.textContent = mat12 ? fmtCapital(mat12.total_issue_amount) : "—";

  /* As-of date */
  var asOfEl = document.getElementById("as-of");
  if (asOfEl) asOfEl.textContent = "As of " + (dashboard.as_of || "unknown");

  /* Demo badge */
  var demoBadge = document.getElementById("demo-badge");
  if (demoBadge && dashboard.demo_mode) demoBadge.hidden = false;

  /* Release gate badge */
  var gateBadge = document.getElementById("gate-badge");
  if (gateBadge && audit && audit.release_gate && audit.release_gate.passed) {
    gateBadge.textContent = "Release gate passed";
    gateBadge.hidden = false;
  }
}

/* ============================================================
   Sponsor Concentration — horizontal bar by capital
   ============================================================ */

function renderSponsorChart(sb) {
  var chart = initChart("chart-sponsors");
  if (!chart) return;
  var t = getChartTheme();

  var sponsors = (sb.top_sponsors_by_capital || [])
    .filter(function (r) { return r.currency === "USD"; })
    .slice(0, 10);

  /* Editorial lead */
  var leadEl = document.getElementById("sponsors-lead");
  if (leadEl && sponsors.length >= 2) {
    var top = sponsors[0];
    leadEl.textContent =
      "The top sponsors by placed capital: " + top.sponsor_name + " leads with " +
      fmtCapital(top.total_issue_amount) + " across " + top.tranche_count +
      " tranches, followed by " + sponsors[1].sponsor_name + " at " +
      fmtCapital(sponsors[1].total_issue_amount) + ".";
  }

  var names = sponsors.map(function (s) { return s.sponsor_name; }).reverse();
  var values = sponsors.map(function (s) { return s.total_issue_amount; }).reverse();
  var counts = sponsors.map(function (s) { return s.tranche_count; }).reverse();

  chart.setOption({
    tooltip: Object.assign({ trigger: "axis", axisPointer: { type: "shadow" } }, baseTooltip(t), {
      formatter: function (params) {
        var p = params[0];
        var idx = p.dataIndex;
        return "<strong>" + escHtml(names[idx]) + "</strong><br>" +
          "Capital: " + fmtCapital(values[idx]) + "<br>" +
          "Tranches: " + counts[idx];
      },
    }),
    grid: { left: 200, right: 40, top: 12, bottom: 24 },
    xAxis: {
      type: "value",
      axisLabel: Object.assign(baseAxisLabel(t), {
        formatter: function (v) { return fmtCapital(v); },
      }),
      splitLine: baseSplitLine(t),
    },
    yAxis: {
      type: "category",
      data: names,
      axisLabel: Object.assign(baseAxisLabel(t), { width: 185, overflow: "truncate" }),
      axisLine: baseAxisLine(t),
      axisTick: { show: false },
    },
    series: [{
      type: "bar",
      data: values,
      barMaxWidth: 28,
      itemStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: t.accent },
          { offset: 1, color: t.isDark ? "#93bbfd" : "#60a5fa" },
        ]),
        borderRadius: [0, 4, 4, 0],
      },
      emphasis: { itemStyle: { color: t.accent } },
      label: {
        show: true,
        position: "right",
        color: t.text,
        fontSize: 11,
        fontFamily: "'JetBrains Mono', monospace",
        formatter: function (p) { return fmtCapital(p.value); },
      },
    }],
  });
}

/* ============================================================
   Geographic Concentration — bubble scatter by lat/lng
   ============================================================ */

function renderGeographyChart(regionMap) {
  var chart = initChart("chart-geography");
  if (!chart) return;
  var t = getChartTheme();

  /* Process region data: compute USD capital per region */
  var regions = regionMap.map(function (r) {
    var usdCap = (r.capital_by_currency || [])
      .filter(function (c) { return c.currency === "USD"; })
      .reduce(function (sum, c) { return sum + c.total_issue_amount; }, 0);
    var domPeril = (r.dominant_perils && r.dominant_perils.length)
      ? r.dominant_perils[0].peril_code
      : "other_property_cat";
    return {
      name: r.display_name,
      lng: r.longitude,
      lat: r.latitude,
      capital: usdCap,
      trancheCount: r.tranche_count,
      peril: domPeril,
    };
  }).filter(function (r) { return r.capital > 0; });

  var maxCap = Math.max.apply(null, regions.map(function (r) { return r.capital; }));

  /* Editorial lead */
  var leadEl = document.getElementById("geography-lead");
  if (leadEl && regions.length) {
    var sorted = regions.slice().sort(function (a, b) { return b.capital - a.capital; });
    leadEl.textContent =
      "Catastrophe risk transfer is overwhelmingly concentrated in the United States. " +
      sorted[0].name + " accounts for " + fmtCapital(sorted[0].capital) +
      " across " + sorted[0].trancheCount + " tranches" +
      (sorted.length > 1 ? ", with " + sorted[1].name + " at " + fmtCapital(sorted[1].capital) : "") + ".";
  }

  /* Group by dominant peril for legend */
  var perilGroups = {};
  regions.forEach(function (r) {
    if (!perilGroups[r.peril]) perilGroups[r.peril] = [];
    perilGroups[r.peril].push(r);
  });

  var series = Object.keys(perilGroups).map(function (peril) {
    var items = perilGroups[peril];
    return {
      name: PERIL_LABELS[peril] || peril,
      type: "scatter",
      coordinateSystem: worldMapLoaded ? "geo" : "cartesian2d",
      data: items.map(function (r) {
        return {
          value: [r.lng, r.lat, r.capital],
          name: r.name,
          trancheCount: r.trancheCount,
          label: {
            show: r.capital > 2e9,
            position: r.lng > 0 ? "left" : "right",
            formatter: "{b}",
            color: t.textStrong,
            fontSize: 11,
            fontWeight: 600,
            textShadowColor: t.isDark ? "rgba(15,23,42,0.8)" : "rgba(255,255,255,0.9)",
            textShadowBlur: 4,
          },
        };
      }),
      symbolSize: function (val) {
        return Math.max(18, Math.sqrt(val[2] / maxCap) * 90);
      },
      itemStyle: {
        color: PERIL_COLORS[peril] || "#94a3b8",
        opacity: 0.7,
        borderColor: t.isDark ? "rgba(255,255,255,0.25)" : "rgba(0,0,0,0.12)",
        borderWidth: 2,
      },
      emphasis: {
        scale: 1.15,
        label: { show: true },
        itemStyle: { opacity: 0.9 },
      },
    };
  });

  var option = {
    tooltip: Object.assign({ trigger: "item" }, baseTooltip(t), {
      formatter: function (p) {
        return "<strong>" + escHtml(p.name) + "</strong><br>" +
          "Capital: " + fmtCapital(p.value[2]) + "<br>" +
          "Tranches: " + p.data.trancheCount + "<br>" +
          "Dominant peril: " + (p.seriesName || "");
      },
    }),
    legend: {
      bottom: 0,
      textStyle: { color: t.text, fontSize: 11 },
      pageTextStyle: { color: t.text },
    },
    series: series,
  };

  if (worldMapLoaded) {
    option.geo = {
      map: "world",
      roam: false,
      silent: true,
      left: 0,
      right: 0,
      top: 0,
      bottom: 40,
      itemStyle: {
        areaColor: t.isDark ? "#1c2a3d" : "#f0f4f8",
        borderColor: t.isDark ? "#2d3f55" : "#d0d8e0",
        borderWidth: 0.5,
      },
      emphasis: { disabled: true },
    };
  } else {
    option.grid = { left: 30, right: 30, top: 20, bottom: 60, containLabel: false };
    option.xAxis = { show: false, min: -140, max: 160 };
    option.yAxis = { show: false, min: -45, max: 65 };
  }

  chart.setOption(option);
}

/* ============================================================
   Peril Mix — treemap by capital
   ============================================================ */

function renderPerilChart(sb) {
  var chart = initChart("chart-perils");
  if (!chart) return;
  var t = getChartTheme();

  var perils = (sb.top_perils_by_capital || [])
    .filter(function (p) { return p.currency === "USD"; })
    .sort(function (a, b) { return b.total_issue_amount - a.total_issue_amount; });

  /* Editorial lead */
  var leadEl = document.getElementById("perils-lead");
  if (leadEl && perils.length >= 3) {
    leadEl.textContent =
      (PERIL_LABELS[perils[0].peril_code] || perils[0].peril_code) +
      " dominates at " + fmtCapital(perils[0].total_issue_amount) +
      ", followed by " + (PERIL_LABELS[perils[1].peril_code] || perils[1].peril_code) +
      " at " + fmtCapital(perils[1].total_issue_amount) +
      " and " + (PERIL_LABELS[perils[2].peril_code] || perils[2].peril_code) +
      " at " + fmtCapital(perils[2].total_issue_amount) + ". USD-denominated capital only.";
  }

  chart.setOption({
    tooltip: Object.assign({}, baseTooltip(t), {
      formatter: function (p) {
        return "<strong>" + escHtml(p.name) + "</strong><br>" +
          "Capital: " + fmtCapital(p.value) + "<br>" +
          "Tranches: " + (p.data.trancheCount || "");
      },
    }),
    series: [{
      type: "treemap",
      width: "100%",
      height: "100%",
      roam: false,
      nodeClick: false,
      breadcrumb: { show: false },
      levels: [{
        itemStyle: {
          borderColor: t.isDark ? "#1e293b" : "#ffffff",
          borderWidth: 4,
          gapWidth: 4,
        },
      }],
      label: {
        show: true,
        color: "#fff",
        fontSize: 14,
        fontWeight: 700,
        formatter: function (p) {
          return p.name + "\n" + fmtCapital(p.value);
        },
        textShadowColor: "rgba(0,0,0,0.5)",
        textShadowBlur: 4,
        lineHeight: 20,
      },
      upperLabel: { show: false },
      data: perils.map(function (p) {
        return {
          name: PERIL_LABELS[p.peril_code] || p.peril_code,
          value: p.total_issue_amount,
          trancheCount: p.tranche_count,
          itemStyle: {
            color: PERIL_COLORS[p.peril_code] || "#94a3b8",
          },
        };
      }),
    }],
  });
}

/* ============================================================
   Market Timeline — bar chart by year (USD)
   ============================================================ */

function renderTimelineChart(sb) {
  var chart = initChart("chart-timeline");
  if (!chart) return;
  var t = getChartTheme();

  /* Aggregate by year, USD only */
  var yearMap = {};
  var yearCounts = {};
  (sb.market_timeline || []).forEach(function (e) {
    if (e.currency !== "USD") return;
    yearMap[e.listed_year] = (yearMap[e.listed_year] || 0) + e.total_issue_amount;
    yearCounts[e.listed_year] = (yearCounts[e.listed_year] || 0) + e.tranche_count;
  });
  var years = Object.keys(yearMap).sort();
  var values = years.map(function (y) { return yearMap[y]; });

  /* Editorial lead */
  var leadEl = document.getElementById("timeline-lead");
  if (leadEl && years.length >= 2) {
    var firstYr = years[0];
    var lastYr = years[years.length - 1];
    leadEl.textContent =
      "Public issuance visible through the BSX has grown from " +
      fmtCapital(yearMap[firstYr]) + " in " + firstYr + " to " +
      fmtCapital(yearMap[lastYr]) + " in " + lastYr +
      ", reflecting both market growth and improving registry coverage. USD only.";
  }

  chart.setOption({
    tooltip: Object.assign({ trigger: "axis", axisPointer: { type: "shadow" } }, baseTooltip(t), {
      formatter: function (params) {
        var p = params[0];
        return "<strong>" + p.name + "</strong><br>" +
          "Capital: " + fmtCapital(p.value) + "<br>" +
          "Tranches: " + (yearCounts[p.name] || 0);
      },
    }),
    grid: { left: 72, right: 24, top: 24, bottom: 40 },
    xAxis: {
      type: "category",
      data: years,
      axisLabel: baseAxisLabel(t),
      axisLine: baseAxisLine(t),
      axisTick: { lineStyle: { color: t.axis } },
    },
    yAxis: {
      type: "value",
      axisLabel: Object.assign(baseAxisLabel(t), {
        formatter: function (v) { return fmtCapital(v); },
      }),
      splitLine: baseSplitLine(t),
    },
    series: [{
      type: "bar",
      data: values,
      barMaxWidth: 52,
      itemStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: t.accent },
          { offset: 1, color: t.accentLight },
        ]),
        borderRadius: [4, 4, 0, 0],
      },
      emphasis: { itemStyle: { color: t.accent } },
    }],
  });
}

/* ============================================================
   Maturity Runway — 3 stat cards
   ============================================================ */

function renderRunwayCards(sb) {
  var el = document.getElementById("runway-grid");
  if (!el) return;

  var runway = sb.maturity_runway || [];
  var windows = [12, 24, 36];
  var max36 = 0;

  var cards = windows.map(function (w) {
    var usd = runway.find(function (r) { return r.window_months === w && r.currency === "USD"; });
    var trancheCount = 0;
    var capital = 0;
    if (usd) {
      trancheCount = usd.tranche_count;
      capital = usd.total_issue_amount;
    }
    if (w === 36) max36 = capital;
    return { window: w, trancheCount: trancheCount, capital: capital };
  });

  el.innerHTML = cards.map(function (c) {
    var pct = max36 > 0 ? ((c.capital / max36) * 100).toFixed(1) : 0;
    return '<div class="runway-card">' +
      '<div class="runway-window">' + c.window + '-month window</div>' +
      '<div class="runway-count">' + fmtNum(c.trancheCount) + '</div>' +
      '<div class="runway-count-label">tranches</div>' +
      '<div class="runway-capital">' + fmtCapital(c.capital) + '</div>' +
      '<div class="runway-bar"><div class="runway-bar-fill" style="width:' + pct + '%"></div></div>' +
      '</div>';
  }).join("");
}

/* ============================================================
   Maturity Wall — stacked bar by quarter
   ============================================================ */

function aggregateMaturityByQuarter(rows) {
  var buckets = {};
  var perilSet = new Set();
  rows.forEach(function (row) {
    if (!row.maturity_date) return;
    var d = new Date(row.maturity_date);
    var q = Math.floor(d.getMonth() / 3) + 1;
    var key = d.getFullYear() + " Q" + q;
    if (!buckets[key]) buckets[key] = {};
    var perils = row.peril_codes || [];
    if (!perils.length) perils = ["unknown"];
    perils.forEach(function (p) {
      perilSet.add(p);
      buckets[key][p] = (buckets[key][p] || 0) + 1;
    });
  });
  var quarters = Object.keys(buckets).sort();
  var perils = Array.from(perilSet).sort();
  return { quarters: quarters, perils: perils, buckets: buckets };
}

function renderMaturityWallChart(rows) {
  var chart = initChart("chart-maturity");
  if (!chart) return;
  var t = getChartTheme();
  var agg = aggregateMaturityByQuarter(rows);

  var series = agg.perils.map(function (peril) {
    return {
      name: PERIL_LABELS[peril] || peril,
      type: "bar",
      stack: "maturity",
      barMaxWidth: 36,
      emphasis: { focus: "series" },
      itemStyle: { color: PERIL_COLORS[peril] || "#64748b" },
      data: agg.quarters.map(function (q) {
        return (agg.buckets[q] || {})[peril] || 0;
      }),
    };
  });

  chart.setOption({
    tooltip: Object.assign({ trigger: "axis", axisPointer: { type: "shadow" } }, baseTooltip(t)),
    legend: {
      type: "scroll",
      bottom: 0,
      textStyle: { color: t.text, fontSize: 11 },
      pageTextStyle: { color: t.text },
      pageIconColor: t.text,
      pageIconInactiveColor: t.grid,
    },
    grid: { left: 48, right: 16, top: 12, bottom: 84 },
    xAxis: {
      type: "category",
      data: agg.quarters,
      axisLabel: Object.assign(baseAxisLabel(t), { rotate: 45 }),
      axisLine: baseAxisLine(t),
      axisTick: { lineStyle: { color: t.axis } },
    },
    yAxis: {
      type: "value",
      name: "Tranches",
      nameTextStyle: { color: t.text, fontSize: 11 },
      axisLabel: baseAxisLabel(t),
      splitLine: baseSplitLine(t),
    },
    series: series,
  });
}

/* ============================================================
   Watchlist Pressure
   ============================================================ */

function renderWatchlistPressure(sb) {
  var wp = sb.watchlist_pressure || {};
  var pub = wp.public_match_count || 0;
  var cand = wp.candidate_match_count || 0;

  /* Editorial lead */
  var leadEl = document.getElementById("watchlist-lead");
  if (leadEl) {
    leadEl.textContent =
      "The watchlist tracks " + fmtNum(pub) + " public hazard\u2013tranche matches and " +
      fmtNum(cand) + " candidates still below the public evidence threshold. " +
      (wp.candidate_ratio_pct ? wp.candidate_ratio_pct.toFixed(0) + "% of all matches are still candidates." : "");
  }

  /* Split blocks */
  var splitEl = document.getElementById("wl-split");
  if (splitEl) {
    splitEl.innerHTML =
      '<div class="wl-block">' +
        '<div class="wl-count wl-count-public">' + fmtNum(pub) + '</div>' +
        '<div class="wl-label">Public matches</div>' +
        '<div class="wl-desc">Cleared evidence thresholds for region, peril, and sponsor.</div>' +
      '</div>' +
      '<div class="wl-block">' +
        '<div class="wl-count wl-count-candidate">' + fmtNum(cand) + '</div>' +
        '<div class="wl-label">Review candidates</div>' +
        '<div class="wl-desc">Awaiting stronger region, peril, or sponsor evidence to reach public status.</div>' +
      '</div>';
  }
}

function renderBlockersChart(sb) {
  var chart = initChart("chart-blockers");
  if (!chart) return;
  var t = getChartTheme();

  var hints = ((sb.watchlist_pressure || {}).top_promotion_hints || []);
  var names = hints.map(function (h) { return HINT_LABELS[h.hint_code] || h.hint_code.replace(/_/g, " "); }).reverse();
  var values = hints.map(function (h) { return h.count; }).reverse();

  chart.setOption({
    tooltip: Object.assign({ trigger: "axis", axisPointer: { type: "shadow" } }, baseTooltip(t)),
    grid: { left: 200, right: 32, top: 8, bottom: 8 },
    xAxis: {
      type: "value",
      axisLabel: baseAxisLabel(t),
      splitLine: baseSplitLine(t),
    },
    yAxis: {
      type: "category",
      data: names,
      axisLabel: Object.assign(baseAxisLabel(t), { width: 190, overflow: "truncate" }),
      axisLine: baseAxisLine(t),
      axisTick: { show: false },
    },
    series: [{
      type: "bar",
      data: values,
      barMaxWidth: 24,
      itemStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: t.warn },
          { offset: 1, color: t.accent },
        ]),
        borderRadius: [0, 4, 4, 0],
      },
      emphasis: { itemStyle: { color: t.accent } },
      label: {
        show: true,
        position: "right",
        color: t.text,
        fontSize: 11,
        fontFamily: "'JetBrains Mono', monospace",
        formatter: function (p) { return fmtNum(p.value); },
      },
    }],
  });
}

function renderBlockedFamiliesChart(sb) {
  var chart = initChart("chart-blocked-families");
  if (!chart) return;
  var t = getChartTheme();

  var families = ((sb.watchlist_pressure || {}).top_candidate_blockers_by_family || []).slice(0, 5);
  var names = families.map(function (f) { return f.family_name; }).reverse();
  var values = families.map(function (f) { return f.count; }).reverse();

  chart.setOption({
    tooltip: Object.assign({ trigger: "axis", axisPointer: { type: "shadow" } }, baseTooltip(t)),
    grid: { left: 180, right: 32, top: 8, bottom: 8 },
    xAxis: {
      type: "value",
      name: "Candidates",
      nameTextStyle: { color: t.text, fontSize: 11 },
      axisLabel: baseAxisLabel(t),
      splitLine: baseSplitLine(t),
    },
    yAxis: {
      type: "category",
      data: names,
      axisLabel: Object.assign(baseAxisLabel(t), { width: 170, overflow: "truncate" }),
      axisLine: baseAxisLine(t),
      axisTick: { show: false },
    },
    series: [{
      type: "bar",
      data: values,
      barMaxWidth: 24,
      itemStyle: {
        color: t.warn,
        borderRadius: [0, 4, 4, 0],
      },
      emphasis: { itemStyle: { color: t.accent } },
      label: {
        show: true,
        position: "right",
        color: t.text,
        fontSize: 11,
        fontFamily: "'JetBrains Mono', monospace",
        formatter: function (p) { return fmtNum(p.value); },
      },
    }],
  });
}

/* ============================================================
   Evidence Quality
   ============================================================ */

function renderEvidenceQuality(sb, coverageGaps, triggerSummary) {
  var scorecard = sb.coverage_scorecard || {};

  /* Scorecard */
  var scorecardEl = document.getElementById("scorecard-content");
  if (scorecardEl) {
    var metrics = [
      { label: "Sponsor", value: scorecard.sponsor_coverage_pct || 0 },
      { label: "Region", value: scorecard.region_coverage_pct || 0 },
      { label: "Amount", value: scorecard.amount_coverage_pct || 0 },
      { label: "Trigger", value: scorecard.trigger_coverage_pct || 0 },
    ];
    scorecardEl.innerHTML = metrics.map(function (m) {
      var pct = m.value.toFixed(1);
      var cls = m.value >= 80 ? "good" : m.value >= 40 ? "warn" : "bad";
      return '<div class="score-row">' +
        '<span class="score-label">' + m.label + '</span>' +
        '<div class="score-bar"><div class="score-bar-fill score-bar-' + cls + '" style="width:' + Math.min(pct, 100) + '%"></div></div>' +
        '<span class="score-value">' + pct + '%</span>' +
        '</div>';
    }).join("");
  }

  /* Coverage gaps */
  var gapsEl = document.getElementById("gaps-content");
  if (gapsEl && coverageGaps) {
    var gaps = [
      { label: "Missing issue amount", count: coverageGaps.missing_issue_amount || 0 },
      { label: "Missing region", count: coverageGaps.missing_region || 0 },
      { label: "Missing maturity", count: coverageGaps.missing_maturity || 0 },
      { label: "Missing trigger type", count: coverageGaps.missing_trigger_type || 0 },
      { label: "Missing sponsor", count: coverageGaps.missing_sponsor || 0 },
    ];
    gapsEl.innerHTML = gaps.map(function (g) {
      var cls = g.count > 50 ? "gap-high" : g.count > 0 ? "gap-mid" : "gap-zero";
      return '<div class="gap-row">' +
        '<span class="gap-label">' + g.label + '</span>' +
        '<span class="gap-count ' + cls + '">' + fmtNum(g.count) + '</span>' +
        '</div>';
    }).join("");
  }

  /* Trigger coverage */
  var triggerEl = document.getElementById("trigger-content");
  if (triggerEl && triggerSummary) {
    var total = (triggerSummary.known_trigger_rows || 0) + (triggerSummary.missing_trigger_rows || 0);
    var pctKnown = total > 0 ? ((triggerSummary.known_trigger_rows / total) * 100).toFixed(1) : "0.0";
    var html = '<div class="trigger-headline">' +
      '<span class="trigger-value">' + (triggerSummary.known_trigger_rows || 0) + '</span>' +
      '<span class="trigger-of"> of ' + total + ' tranches (' + pctKnown + '%)</span>' +
      '</div>';
    (triggerSummary.by_trigger_type || []).forEach(function (tt) {
      html += '<div class="trigger-type-row">' +
        '<span class="trigger-type-label">' + tt.trigger_type.replace(/_/g, " ") + '</span>' +
        '<span class="trigger-type-count">' + tt.count + '</span>' +
        '</div>';
    });
    triggerEl.innerHTML = html;
  }
}

/* ============================================================
   Unresolved Families
   ============================================================ */

function renderUnresolvedFamilies(sb) {
  var el = document.getElementById("unresolved-list");
  if (!el) return;

  var families = sb.unresolved_families || [];
  if (!families.length) {
    el.innerHTML = '<p class="empty-msg">No unresolved families.</p>';
    return;
  }

  el.innerHTML = families.map(function (f) {
    var blockers = (f.top_blockers || []).map(function (b) {
      return '<span class="blocker-tag">' + escHtml(BLOCKER_LABELS[b.blocker_code] || b.blocker_code) + '</span>';
    }).join("");
    return '<div class="unresolved-item">' +
      '<span class="unresolved-name">' + escHtml(f.family_name) + '</span>' +
      '<span class="unresolved-count">' + fmtNum(f.candidate_rows) + ' candidates</span>' +
      '<span class="unresolved-blockers">' + blockers + '</span>' +
      '</div>';
  }).join("");
}

/* ============================================================
   Methodology Notes
   ============================================================ */

function renderNotes(notes) {
  var root = document.getElementById("notes-list");
  if (!root) return;
  root.innerHTML = "";
  if (!notes || !notes.length) return;
  notes.forEach(function (text) {
    var li = document.createElement("li");
    li.textContent = text;
    root.appendChild(li);
  });
}

/* ============================================================
   Tables — sortable, searchable, paginated
   ============================================================ */

var PAGE_SIZE = 25;
var tableState = {};

function initTableState(key, rows) {
  tableState[key] = {
    allRows: rows,
    filteredRows: rows.slice(),
    sortCol: null,
    sortAsc: true,
    expanded: false,
  };
}

function watchlistColumns() {
  return [
    { key: "event_name", label: "Event", fmt: function (r) { return escHtml(r.event_name || ""); } },
    { key: "peril_code", label: "Peril", fmt: function (r) { return escHtml(PERIL_LABELS[r.peril_code] || r.peril_code || ""); } },
    { key: "region_codes", label: "Region", fmt: function (r) { return escHtml((r.region_codes || []).join(", ")); } },
    { key: "matched_tranche_count", label: "Matches", cls: "text-right mono", fmt: function (r) {
      return String(r.matched_tranche_count || (r.matched_tranches || []).length);
    }},
    { key: "exact_match_count", label: "Exact", cls: "text-right mono", fmt: function (r) { return String(r.exact_match_count || 0); } },
    { key: "broad_match_count", label: "Broad", cls: "text-right mono", fmt: function (r) { return String(r.broad_match_count || 0); } },
    { key: "source_url", label: "Source", fmt: function (r) { return sourceLink(r.source_url, r.source_name || "source"); } },
  ];
}

function candidatesColumns() {
  return [
    { key: "event_name", label: "Event", fmt: function (r) { return escHtml(r.event_name || ""); } },
    { key: "peril_code", label: "Peril", fmt: function (r) { return escHtml(PERIL_LABELS[r.peril_code] || r.peril_code || ""); } },
    { key: "region_codes", label: "Region", fmt: function (r) { return escHtml((r.region_codes || []).join(", ")); } },
    { key: "candidate_match_count", label: "Candidates", cls: "text-right mono", fmt: function (r) { return String(r.candidate_match_count || 0); } },
    { key: "confidence_band", label: "Confidence", fmt: function (r) {
      var b = r.confidence_band || "low";
      var cls = b === "high" ? "badge-high" : "badge-low";
      return '<span class="badge ' + cls + '">' + escHtml(b) + '</span>';
    }},
    { key: "source_url", label: "Source", fmt: function (r) { return sourceLink(r.source_url, r.source_name || "source"); } },
  ];
}

function maturityColumns() {
  return [
    { key: "tranche_name", label: "Tranche", fmt: function (r) { return escHtml(r.tranche_name || ""); } },
    { key: "sponsor_name", label: "Sponsor", fmt: function (r) { return escHtml(r.sponsor_name || ""); } },
    { key: "peril_codes", label: "Perils", fmt: function (r) {
      return escHtml((r.peril_codes || []).map(function (p) { return PERIL_LABELS[p] || p; }).join(", "));
    }},
    { key: "listed_date", label: "Listed", cls: "nowrap mono", fmt: function (r) { return escHtml(fmtDate(r.listed_date)); } },
    { key: "maturity_date", label: "Maturity", cls: "nowrap mono", fmt: function (r) { return escHtml(fmtDate(r.maturity_date)); } },
    { key: "source_url", label: "Source", fmt: function (r) { return sourceLink(r.source_url, "BSX"); } },
  ];
}

function renderTable(tableId, stateKey, columns) {
  var state = tableState[stateKey];
  if (!state) return;
  var table = document.getElementById(tableId);
  if (!table) return;

  var rows = state.filteredRows;
  var limit = state.expanded ? rows.length : Math.min(PAGE_SIZE, rows.length);
  var showing = rows.slice(0, limit);

  var thead = "<thead><tr>";
  columns.forEach(function (col, idx) {
    var arrow = "";
    if (state.sortCol === idx) {
      arrow = '<span class="sort-arrow active">' + (state.sortAsc ? "\u25B2" : "\u25BC") + "</span>";
    } else {
      arrow = '<span class="sort-arrow">\u25B2</span>';
    }
    thead += '<th data-col="' + idx + '">' + escHtml(col.label) + arrow + "</th>";
  });
  thead += "</tr></thead>";

  var tbody = "<tbody>";
  if (!showing.length) {
    tbody += '<tr><td colspan="' + columns.length + '" class="table-empty">No matching rows.</td></tr>';
  } else {
    showing.forEach(function (row) {
      tbody += "<tr>";
      columns.forEach(function (col) {
        var cls = col.cls ? ' class="' + col.cls + '"' : "";
        tbody += "<td" + cls + ">" + col.fmt(row) + "</td>";
      });
      tbody += "</tr>";
    });
  }
  tbody += "</tbody>";

  table.innerHTML = thead + tbody;

  table.querySelectorAll("th").forEach(function (th) {
    th.addEventListener("click", function () {
      var colIdx = parseInt(th.getAttribute("data-col"), 10);
      if (state.sortCol === colIdx) {
        state.sortAsc = !state.sortAsc;
      } else {
        state.sortCol = colIdx;
        state.sortAsc = true;
      }
      sortTableRows(stateKey, columns, colIdx, state.sortAsc);
      renderTable(tableId, stateKey, columns);
    });
  });

  var countEl = document.getElementById(stateKey + "-count");
  if (countEl) countEl.textContent = rows.length + " rows";
  var showingEl = document.getElementById(stateKey + "-showing");
  if (showingEl) showingEl.textContent = "Showing " + limit + " of " + rows.length;
  var moreBtn = document.getElementById(stateKey + "-more");
  if (moreBtn) {
    if (rows.length > PAGE_SIZE) {
      moreBtn.hidden = false;
      moreBtn.textContent = state.expanded ? "Show less" : "Show all " + rows.length;
    } else {
      moreBtn.hidden = true;
    }
  }
}

function sortTableRows(stateKey, columns, colIdx, asc) {
  var state = tableState[stateKey];
  var col = columns[colIdx];
  state.filteredRows.sort(function (a, b) {
    var va = col.fmt(a).replace(/<[^>]+>/g, "").toLowerCase();
    var vb = col.fmt(b).replace(/<[^>]+>/g, "").toLowerCase();
    var na = parseFloat(va);
    var nb = parseFloat(vb);
    if (!isNaN(na) && !isNaN(nb)) return asc ? na - nb : nb - na;
    if (va < vb) return asc ? -1 : 1;
    if (va > vb) return asc ? 1 : -1;
    return 0;
  });
}

function filterTable(stateKey, columns, tableId, query) {
  var state = tableState[stateKey];
  if (!state) return;
  var q = query.toLowerCase().trim();
  if (!q) {
    state.filteredRows = state.allRows.slice();
  } else {
    state.filteredRows = state.allRows.filter(function (row) {
      return columns.some(function (col) {
        return col.fmt(row).replace(/<[^>]+>/g, "").toLowerCase().indexOf(q) >= 0;
      });
    });
  }
  state.expanded = false;
  renderTable(tableId, stateKey, columns);
}

function setupTable(tableId, stateKey, columns, searchId, moreId, rows) {
  initTableState(stateKey, rows);
  renderTable(tableId, stateKey, columns);

  var searchEl = document.getElementById(searchId);
  if (searchEl) {
    searchEl.addEventListener("input", function () {
      filterTable(stateKey, columns, tableId, searchEl.value);
    });
  }

  var moreBtn = document.getElementById(moreId);
  if (moreBtn) {
    moreBtn.addEventListener("click", function () {
      tableState[stateKey].expanded = !tableState[stateKey].expanded;
      renderTable(tableId, stateKey, columns);
    });
  }
}

/* ============================================================
   Tabs
   ============================================================ */

function setupTabs() {
  var buttons = document.querySelectorAll(".tab-btn[data-tab]");
  buttons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var tab = btn.getAttribute("data-tab");
      buttons.forEach(function (b) {
        b.classList.toggle("active", b === btn);
        b.setAttribute("aria-selected", b === btn ? "true" : "false");
      });
      document.querySelectorAll(".tab-content").forEach(function (panel) {
        panel.hidden = panel.id !== "tab-" + tab;
      });
      resizeAllCharts();
    });
  });
}

/* ============================================================
   Sticky Nav Active State
   ============================================================ */

function setupNavHighlight() {
  var links = document.querySelectorAll("#main-nav a[href^='#']");
  if (!links.length) return;
  var sections = [];
  links.forEach(function (link) {
    var id = link.getAttribute("href").slice(1);
    var el = document.getElementById(id);
    if (el) sections.push({ el: el, link: link });
  });

  function update() {
    var scrollY = window.scrollY + 80;
    var active = sections[0];
    sections.forEach(function (s) {
      if (s.el.offsetTop <= scrollY) active = s;
    });
    links.forEach(function (l) { l.classList.remove("active"); });
    if (active) active.link.classList.add("active");
  }

  window.addEventListener("scroll", update, { passive: true });
  update();
}

/* ============================================================
   Chart Update — re-renders all charts on theme change
   ============================================================ */

function updateAllCharts(dashboard) {
  var sb = dashboard.story_blocks || {};
  renderSponsorChart(sb);
  renderGeographyChart(dashboard.region_map || []);
  renderPerilChart(sb);
  renderTimelineChart(sb);
  renderMaturityWallChart(dashboard.maturity_wall || []);
  renderBlockersChart(sb);
  renderBlockedFamiliesChart(sb);
}

/* ============================================================
   Main
   ============================================================ */

async function main() {
  var data = await Promise.all([
    loadJSON("./data/dashboard.json"),
    loadJSON("./data/audit.json"),
  ]);
  var dashboard = data[0];
  var audit = data[1];

  if (!dashboard) {
    document.getElementById("hero-stats").innerHTML =
      '<div class="loading-msg" style="grid-column:1/-1">Failed to load dashboard data.</div>';
    return;
  }

  var sb = dashboard.story_blocks || {};

  /* Hero */
  renderHero(dashboard, audit);

  /* Load world map for geographic visualization */
  await loadWorldMap();

  /* Charts */
  updateAllCharts(dashboard);

  /* Runway cards (HTML, not chart) */
  renderRunwayCards(sb);

  /* Watchlist pressure (HTML) */
  renderWatchlistPressure(sb);

  /* Evidence quality (HTML) */
  renderEvidenceQuality(sb, dashboard.coverage_gaps, dashboard.trigger_summary);

  /* Unresolved families */
  renderUnresolvedFamilies(sb);

  /* Methodology */
  renderNotes(dashboard.notes || []);

  /* Tables */
  setupTable("watchlist-table", "watchlist", watchlistColumns(), "watchlist-search", "watchlist-more", dashboard.watchlist || []);
  setupTable("candidates-table", "candidates", candidatesColumns(), "candidates-search", "candidates-more", dashboard.watchlist_review_candidates || []);
  setupTable("maturity-table", "maturity", maturityColumns(), "maturity-search", "maturity-more", dashboard.maturity_wall || []);

  setupTabs();
  setupNavHighlight();

  /* Theme change observer */
  new MutationObserver(function (mutations) {
    mutations.forEach(function (m) {
      if (m.attributeName === "data-theme") {
        updateAllCharts(dashboard);
      }
    });
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  /* Resize handler */
  window.addEventListener("resize", resizeAllCharts);
}

main().catch(function (err) {
  console.error("OpenCatWatch init error:", err);
  var el = document.getElementById("hero-stats");
  if (el) el.innerHTML = '<div class="loading-msg" style="grid-column:1/-1">Error: ' + String(err.message || err) + "</div>";
});
