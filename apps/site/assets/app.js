const dashboardUrl = "./data/dashboard.json";

function fmtDate(value) {
  if (!value) return "unknown";
  return value.slice(0, 10);
}

function monthDiff(start, end) {
  const s = new Date(start);
  const e = new Date(end);
  const months = (e.getFullYear() - s.getFullYear()) * 12 + (e.getMonth() - s.getMonth());
  return Math.max(1, months);
}

function clearNode(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

function divWithClass(className, text) {
  const div = document.createElement("div");
  if (className) div.className = className;
  if (text !== undefined) div.textContent = text;
  return div;
}

function linkNode(href, label) {
  if (!href) return null;
  const link = document.createElement("a");
  link.href = href;
  link.target = "_blank";
  link.rel = "noreferrer";
  link.textContent = label;
  return link;
}

function appendMetaLine(parent, text, link) {
  const meta = divWithClass("meta");
  meta.appendChild(document.createTextNode(text));
  if (link) {
    meta.appendChild(document.createTextNode(" "));
    meta.appendChild(link);
  }
  parent.appendChild(meta);
}

function renderKpis(kpis) {
  const root = document.getElementById("kpis");
  clearNode(root);
  Object.entries(kpis).forEach(([key, value]) => {
    const card = divWithClass("kpi");
    card.appendChild(divWithClass("label", key.replaceAll("_", " ")));
    card.appendChild(divWithClass("value", String(value)));
    root.appendChild(card);
  });
}

function renderMaturityWall(rows) {
  const root = document.getElementById("maturity-wall");
  clearNode(root);
  const now = new Date();
  rows.forEach((row) => {
    const start = row.listed_date || "2025-01-01";
    const end = row.maturity_date || "2026-01-01";
    const totalMonths = Math.max(1, monthDiff(start, end));
    const elapsedMonths = Math.max(0, monthDiff(start, now.toISOString()));
    const width = Math.max(8, Math.min(100, Math.round((elapsedMonths / totalMonths) * 100)));

    const bar = divWithClass("bar");
    const top = divWithClass("bar-top");
    const left = document.createElement("div");
    left.appendChild(divWithClass("bar-title", row.tranche_name || "Unknown tranche"));
    left.appendChild(
      divWithClass(
        "bar-meta",
        `${row.sponsor_name || "Unknown sponsor"} · ${(row.peril_codes || []).join(", ")}`
      )
    );
    if (row.review_status) {
      left.appendChild(divWithClass("bar-meta", `Review status: ${row.review_status}`));
    }
    top.appendChild(left);
    top.appendChild(divWithClass("bar-meta", `${fmtDate(start)} → ${fmtDate(end)}`));

    const track = divWithClass("track");
    const fill = divWithClass("fill");
    fill.style.width = `${width}%`;
    track.appendChild(fill);

    bar.appendChild(top);
    bar.appendChild(track);
    appendMetaLine(bar, "Listing evidence:", linkNode(row.source_url, "source"));
    appendMetaLine(
      bar,
      `Sponsor evidence (${row.sponsor_source_type || "unknown"}):`,
      linkNode(row.sponsor_source_url, "source")
    );
    root.appendChild(bar);
  });
}

function renderWatchlist(rows) {
  const root = document.getElementById("watchlist");
  clearNode(root);
  rows.forEach((row) => {
    const card = divWithClass("watch");
    card.appendChild(divWithClass("name", row.event_name || "Unknown event"));
    card.appendChild(
      divWithClass("meta", `${row.peril_code || "unknown"} · ${(row.region_codes || []).join(", ")}`)
    );
    appendMetaLine(
      card,
      `Event evidence (${row.source_name || "unknown source"}):`,
      linkNode(row.source_url, "source")
    );
    if (row.reason_text) {
      card.appendChild(divWithClass("meta", row.reason_text));
    }
    const trancheCount = row.matched_tranche_count || (row.matched_tranches || []).length;
    card.appendChild(
      divWithClass(
        "meta",
        `Matched tranches (${trancheCount}): ${(row.matched_tranches || []).join(", ")}`
      )
    );
    (row.matched_tranche_rows || []).forEach((match) => {
      const matchRow = divWithClass("match-row");
      matchRow.appendChild(
        divWithClass(
          "meta",
          `${match.tranche_name || "Unknown tranche"} · ${match.sponsor_name || "Unknown sponsor"} · score ${match.score ?? "0"}`
        )
      );
      if (match.reason_text) {
        matchRow.appendChild(divWithClass("meta", match.reason_text));
      }
      appendMetaLine(matchRow, "Tranche evidence:", linkNode(match.source_url, "listing"));
      appendMetaLine(
        matchRow,
        `Sponsor evidence (${match.sponsor_source_type || "unknown"}):`,
        linkNode(match.sponsor_source_url, "source")
      );
      if (match.review_status) {
        matchRow.appendChild(divWithClass("meta", `Review status: ${match.review_status}`));
      }
      card.appendChild(matchRow);
    });
    const exactCount = row.exact_match_count || 0;
    const broadCount = row.broad_match_count || 0;
    card.appendChild(divWithClass("meta", `Exact: ${exactCount} · Broad: ${broadCount}`));
    card.appendChild(divWithClass("pill", "possible overlap"));
    root.appendChild(card);
  });
}

function renderMatrix(rows) {
  const root = document.getElementById("matrix");
  clearNode(root);
  if (!rows.length) {
    root.textContent = "No matrix rows yet.";
    return;
  }

  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["Sponsor", "Peril", "Count"].forEach((label) => {
    const th = document.createElement("th");
    th.textContent = label;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    [row.sponsor_name, row.peril_code, row.count].forEach((value) => {
      const td = document.createElement("td");
      td.textContent = String(value ?? "");
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  table.appendChild(thead);
  table.appendChild(tbody);
  root.appendChild(table);
}

function renderNotes(notes) {
  const root = document.getElementById("notes");
  clearNode(root);
  notes.forEach((note) => {
    const li = document.createElement("li");
    li.textContent = note;
    root.appendChild(li);
  });
}

async function main() {
  const res = await fetch(dashboardUrl);
  const data = await res.json();
  document.getElementById("as-of").textContent = `As of ${data.as_of}${data.demo_mode ? " · demo" : ""}`;
  renderKpis(data.kpis || {});
  renderMaturityWall(data.maturity_wall || []);
  renderWatchlist(data.watchlist || []);
  renderMatrix(data.sponsor_peril_matrix || []);
  renderNotes(data.notes || []);
}

main().catch((err) => {
  console.error(err);
  const pre = document.createElement("pre");
  pre.textContent = String(err);
  document.body.appendChild(pre);
});
