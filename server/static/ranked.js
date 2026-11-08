/* Ranked public pages — client-side rendering only.
 *
 * Loaded on /ranked (and, later, on the player profile). All API-provided
 * strings are rendered via escapeHtml() or textContent; nothing is interpolated
 * raw into innerHTML. No helpers are copied into templates.
 */
(function () {
    "use strict";

    // ------------------------------------------------------------------ //
    // Helpers
    // ------------------------------------------------------------------ //

    function escapeHtml(s) {
        return String(s == null ? "" : s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function formatNum(n) {
        const v = Number(n);
        return Number.isFinite(v) ? Math.round(v).toLocaleString("ru-RU") : "0";
    }

    // Russian plural: forms = [one, few, many] (e.g. ["игра", "игры", "игр"]).
    function plural(n, forms) {
        const v = Math.abs(Math.round(Number(n) || 0));
        const n10 = v % 10;
        const n100 = v % 100;
        if (n10 === 1 && n100 !== 11) return forms[0];
        if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return forms[1];
        return forms[2];
    }

    const TIER_COLORS = {
        "Базовый": "#a3a9cf",
        "Бронза": "#cd7f32",
        "Серебро": "#cbd5e1",
        "Золото": "#fbbf24",
        "Платина": "#5eead4",
        "Алмаз": "#7dd3fc",
        "Мастер": "#c084fc",
        "Профессионал": "#f87171",
        "Легенда": "#fbcfe8",
    };

    const TIER_SHAPES = {
        "Базовый": "triangle",
        "Бронза": "triangle",
        "Серебро": "square",
        "Золото": "square",
        "Платина": "diamond",
        "Алмаз": "gem",
        "Мастер": "star",
        "Профессионал": "star",
        "Легенда": "circle",
    };

    const SHAPE_MARKUP = {
        triangle: '<path d="M8 2l7 12H1z"/>',
        square: '<rect x="2" y="2" width="12" height="12" rx="3"/>',
        diamond: '<path d="M8 1l7 7-7 7-7-7z"/>',
        gem: '<path d="M4 2h8l3 4-7 8-7-8z"/>',
        star: '<path d="M8 1.2l2.1 4.4 4.8.6-3.5 3.3.9 4.8L8 12l-4.3 2.3.9-4.8L1.1 6.2l4.8-.6z"/>',
        circle: '<circle cx="8" cy="8" r="6.5"/>',
    };

    const FALLBACK_COLOR = "#a3a9cf";
    const FALLBACK_SHAPE = "square";

    const REGION_FLAGS = {
        komi: ["Komi Republic", "Flag_of_Komi.svg"],
        tatarstan: ["Tatarstan", "Flag_of_Tatarstan.svg"],
        bashkortostan: ["Bashkortostan", "Flag_of_Bashkortostan.svg"],
        dagestan: ["Dagestan", "Flag_of_Dagestan.svg"],
        chechnya: ["Chechnya", "Flag_of_Chechnya.svg"],
        adygea: ["Adygea", "Flag_of_Adygea.svg"],
        "altai-republic": ["Altai Republic", "Flag_of_Altai_Republic.svg"],
        buryatia: ["Buryatia", "Flag_of_Buryatia.svg"],
        ingushetia: ["Ingushetia", "Flag_of_Ingushetia.svg"],
        "kabardino-balkaria": ["Kabardino-Balkaria", "Flag_of_Kabardino-Balkaria.svg"],
        kalmykia: ["Kalmykia", "Flag_of_Kalmykia.svg"],
        "karachay-cherkessia": ["Karachay-Cherkessia", "Flag_of_Karachay-Cherkessia.svg"],
        karelia: ["Karelia", "Flag_of_Karelia.svg"],
        "mari-el": ["Mari El", "Flag_of_Mari_El.svg"],
        mordovia: ["Mordovia", "Flag_of_Mordovia.svg"],
        sakha: ["Sakha (Yakutia)", "Flag_of_Sakha.svg"],
        "north-ossetia": ["North Ossetia", "Flag_of_North_Ossetia.svg"],
        tuva: ["Tuva", "Flag_of_Tuva.svg"],
        udmurtia: ["Udmurtia", "Flag_of_Udmurtia.svg"],
        khakassia: ["Khakassia", "Flag_of_Khakassia.svg"],
        chuvashia: ["Chuvashia", "Flag_of_Chuvashia.svg"],
        moscow: ["Moscow", "Flag_of_Moscow.svg"],
        "saint-petersburg": ["Saint Petersburg", "Flag_of_Saint_Petersburg.svg"],
    };

    function flagSrc(code, width) {
        code = String(code || "").toLowerCase().replace(/[^a-z0-9-]/g, "");
        if (!code) return "";
        if (REGION_FLAGS[code]) {
            return "https://commons.wikimedia.org/wiki/Special:Redirect/file/" +
                REGION_FLAGS[code][1] + "?width=" + Math.round(width);
        }
        if (code.length === 2) {
            return "https://flagcdn.com/w" + Math.round(width) + "/" + code + ".png";
        }
        return "";
    }

    function flagImg(code, width) {
        const src = flagSrc(code, width);
        if (!src) return "";
        return '<img class="flag-img" src="' + src + '" alt="" loading="lazy" onerror="this.style.display=\'none\'">';
    }

    function avatarImg(url) {
        if (!url) return "";
        return '<img class="player-avatar" src="' + escapeHtml(url) + '" alt="" loading="lazy" onerror="this.style.visibility=\'hidden\'">';
    }

    function tierColor(name) {
        return TIER_COLORS[name] || FALLBACK_COLOR;
    }

    function tierShape(name) {
        return TIER_SHAPES[name] || FALLBACK_SHAPE;
    }

    function tierShapeSvg(name, filled, size) {
        const shape = tierShape(name);
        const color = tierColor(name);
        const fill = filled ? color : "#1f2347";
        const stroke = filled ? color : "#3a4070";
        const px = Math.max(18, Math.min(22, Math.round(Number(size) || 20)));
        return '<svg class="ranked-shape" width="' + px + '" height="' + px +
            '" viewBox="0 0 16 16" fill="' + fill + '" stroke="' + stroke +
            '" stroke-width="1" stroke-linejoin="round" aria-hidden="true">' +
            SHAPE_MARKUP[shape] + "</svg>";
    }

    function tierBadge(name) {
        const color = tierColor(name);
        return '<span class="ranked-tier-badge" style="color:' + color + ';border-color:' + color + '">' +
            escapeHtml(name) + "</span>";
    }

    // Sub-rank figure states: server {filled,total}; null -> one filled marker.
    function shapeStates(sub) {
        const total = sub && sub.total != null ? Math.max(0, Math.round(Number(sub.total))) : 0;
        if (total <= 0) return [true];
        const filled = sub && sub.filled != null
            ? Math.max(0, Math.min(total, Math.round(Number(sub.filled))))
            : 0;
        const states = [];
        for (let i = 0; i < total; i++) states.push(i < filled);
        return states;
    }

    function subRankHtml(sub, tier) {
        const states = shapeStates(sub);
        if (!states.length) return "";
        return '<span class="ranked-subrank">' +
            states.map(function (filled) { return tierShapeSvg(tier, filled, 20); }).join("") +
            "</span>";
    }

    // Real star window for the current ELO, e.g. "5.35–5.65★".
    function starWindowText(win) {
        if (!win || win.min == null || win.max == null) return "";
        return Number(win.min).toFixed(2) + "–" + Number(win.max).toFixed(2) + "★";
    }

    async function fetchJson(url) {
        const res = await fetch(url);
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
    }

    function setStatus(text, isError) {
        const el = document.getElementById("rankedStatus");
        if (!el) return;
        if (!text) {
            el.style.display = "none";
            return;
        }
        el.style.display = "block";
        el.textContent = "";
        const p = document.createElement("p");
        p.className = "empty" + (isError ? " ranked-error" : "");
        p.textContent = text;
        el.appendChild(p);
    }

    // ------------------------------------------------------------------ //
    // Rules rendering (from /api/ranked/info)
    // ------------------------------------------------------------------ //

    function renderTiers(tiers) {
        const tbody = document.getElementById("rankedTiers");
        if (!tbody) return;
        tbody.innerHTML = (tiers || []).map(function (t) {
            let eloRange;
            if (t.next_min_elo == null) {
                eloRange = formatNum(t.min_elo) + "+";
            } else {
                const upper = Number(t.next_min_elo) - 1;
                eloRange = upper === Number(t.min_elo)
                    ? formatNum(t.min_elo)
                    : formatNum(t.min_elo) + " – " + formatNum(upper);
            }
            const stars = t.max_stars == null
                ? "★ " + Number(t.min_stars).toFixed(1) + "+"
                : "★ " + Number(t.min_stars).toFixed(1) + " – " + Number(t.max_stars).toFixed(1);
            const color = tierColor(t.name);
            return '<tr>' +
                '<td><span class="ranked-tier-cell">' + tierShapeSvg(t.name, true, 18) +
                '<span class="ranked-tier-badge" style="color:' + color + ';border-color:' + color + '">' + escapeHtml(t.name) + "</span></span></td>" +
                '<td class="col-num">' + eloRange + "</td>" +
                '<td class="col-num">' + stars + "</td>" +
                "</tr>";
        }).join("");
    }

    let rankedRewardChart = null;

    function renderReward(table) {
        const el = document.getElementById("rankedReward");
        if (!el) return;
        const rows = (table || []).map(function (r) {
            return { acc: Number(r[0]) * 100, reward: Number(r[1]) || 0 };
        }).filter(function (r) {
            return Number.isFinite(r.acc);
        });

        if (rankedRewardChart) {
            rankedRewardChart.destroy();
            rankedRewardChart = null;
        }
        el.innerHTML = "";
        if (!rows.length) return;

        // Fallback for a blocked CDN: show the same table as text.
        if (typeof Chart === "undefined") {
            const fallback = document.createElement("div");
            fallback.className = "ranked-sub";
            fallback.textContent = rows.map(function (r) {
                return r.acc.toFixed(0) + "% → " + fmtDelta(r.reward);
            }).join(" · ");
            el.appendChild(fallback);
            return;
        }

        const wrap = document.createElement("div");
        wrap.className = "ranked-chart-wrap";
        wrap.style.width = "100%";
        wrap.style.height = "280px";
        wrap.style.background = "rgba(255, 255, 255, 0.02)";
        wrap.style.border = "1px solid rgba(255, 255, 255, 0.06)";
        wrap.style.borderRadius = "12px";
        wrap.style.padding = "0.5rem";
        const canvas = document.createElement("canvas");
        wrap.appendChild(canvas);
        el.appendChild(wrap);

        const rewards = rows.map(function (r) { return r.reward; });
        const yMinRaw = Math.min.apply(null, rewards.concat([0]));
        const yMaxRaw = Math.max.apply(null, rewards.concat([0]));
        const yMin = yMinRaw === yMaxRaw ? yMinRaw - 1 : yMinRaw;
        const yMax = yMinRaw === yMaxRaw ? yMaxRaw + 1 : yMaxRaw;
        const xMinRaw = rows[0].acc;
        const xMaxRaw = rows[rows.length - 1].acc;
        const xMin = xMinRaw === xMaxRaw ? xMinRaw - 1 : xMinRaw;
        const xMax = xMinRaw === xMaxRaw ? xMaxRaw + 1 : xMaxRaw;
        const pointColors = rewards.map(function (v) {
            return v < 0 ? "#ff4444" : v === 0 ? "#8b9cb4" : "#00ff7f";
        });

        // Dense points along the linear segments make the scale easier to read.
        const series = [];
        for (let i = 0; i < rows.length - 1; i++) {
            const a = rows[i];
            const b = rows[i + 1];
            const steps = Math.max(1, Math.round(b.acc - a.acc));
            for (let s = 0; s < steps; s++) {
                const t = s / steps;
                series.push({
                    x: a.acc + (b.acc - a.acc) * t,
                    y: a.reward + (b.reward - a.reward) * t,
                });
            }
        }
        const last = rows[rows.length - 1];
        series.push({ x: last.acc, y: last.reward });
        const seriesColors = series.map(function (p) {
            return p.y < 0
                ? "rgba(255, 68, 68, 0.55)"
                : p.y === 0
                    ? "rgba(139, 156, 180, 0.75)"
                    : "rgba(0, 255, 127, 0.55)";
        });

        // Show the table's own points on top of the dense line.
        const controlLabelsPlugin = {
            id: "rewardPointLabels",
            afterDatasetsDraw: function (chart) {
                const meta = chart.getDatasetMeta(1);
                if (!meta || !meta.data) return;
                const ctx = chart.ctx;
                ctx.save();
                ctx.font = '600 10px "JetBrains Mono", monospace';
                ctx.textAlign = "center";
                ctx.textBaseline = "bottom";
                meta.data.forEach(function (point, i) {
                    const row = rows[i];
                    if (!row) return;
                    ctx.fillStyle = row.reward < 0
                        ? "#ff4444"
                        : row.reward === 0
                            ? "#8b9cb4"
                            : "#00ff7f";
                    ctx.fillText(fmtDelta(row.reward), point.x, point.y - 10);
                });
                ctx.restore();
            },
        };

        rankedRewardChart = new Chart(canvas, {
            type: "line",
            data: {
                datasets: [{
                    data: series,
                    borderColor: "#00ff7f",
                    borderWidth: 3,
                    tension: 0,
                    fill: false,
                    segment: {
                        borderColor: function (ctx) {
                            const mid = (ctx.p0.parsed.y + ctx.p1.parsed.y) / 2;
                            return mid < 0 ? "#ff4444" : mid > 0 ? "#00ff7f" : "#8b9cb4";
                        },
                    },
                    pointRadius: 2.5,
                    pointHoverRadius: 4,
                    pointHitRadius: 8,
                    pointBackgroundColor: seriesColors,
                    pointBorderWidth: 0,
                    clip: false,
                }, {
                    data: rows.map(function (r) {
                        return { x: r.acc, y: r.reward };
                    }),
                    showLine: false,
                    pointRadius: 6,
                    pointHoverRadius: 8,
                    pointHitRadius: 14,
                    pointBackgroundColor: pointColors,
                    pointBorderColor: "#0d1220",
                    pointBorderWidth: 2,
                    clip: false,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "nearest", intersect: true },
                animation: { duration: 500, easing: "easeOutQuart" },
                layout: { padding: { top: 26, right: 16, bottom: 8, left: 16 } },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: "rgba(13, 18, 32, 0.95)",
                        borderColor: "rgba(74, 155, 232, 0.4)",
                        borderWidth: 1,
                        titleColor: "#e6edf5",
                        bodyColor: "#c9d4e0",
                        padding: 10,
                        displayColors: false,
                        filter: function (item) {
                            return item.datasetIndex === 0;
                        },
                        callbacks: {
                            title: function (items) {
                                return "Точность: " + Math.round(items[0].parsed.x) + "%";
                            },
                            label: function (item) {
                                const v = item.parsed.y;
                                const value = fmtDelta(v) + (v === 0 ? "" : " ELO");
                                return v < 0 ? "Штраф: " + value : "Изменение ELO: " + value;
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        type: "linear",
                        min: xMin,
                        max: xMax,
                        border: { display: false },
                        grid: { display: false },
                        title: {
                            display: true,
                            text: "Точность",
                            color: "#8b9cb4",
                            font: { family: "JetBrains Mono", size: 11 },
                            padding: { top: 8 },
                        },
                        ticks: {
                            color: "#8b9cb4",
                            font: { family: "JetBrains Mono", size: 10 },
                            maxRotation: 0,
                            autoSkip: false,
                            callback: function (value) { return value + "%"; },
                        },
                        afterBuildTicks: function (axis) {
                            axis.ticks = rows.map(function (r) {
                                return { value: r.acc };
                            });
                        },
                    },
                    y: {
                        min: yMin,
                        max: yMax,
                        border: { display: false },
                        grid: {
                            color: function (context) {
                                return context.tick && context.tick.value === 0
                                    ? "rgba(230, 237, 245, 0.35)"
                                    : "rgba(255, 255, 255, 0.05)";
                            },
                        },
                        title: {
                            display: true,
                            text: "Изменение ELO",
                            color: "#8b9cb4",
                            font: { family: "JetBrains Mono", size: 11 },
                            padding: { bottom: 8 },
                        },
                        ticks: {
                            color: "#8b9cb4",
                            font: { family: "JetBrains Mono", size: 10 },
                            padding: 6,
                            callback: function (value) { return fmtDelta(value); },
                        },
                    },
                },
            },
            plugins: [controlLabelsPlugin],
        });
    }

    function renderMods(info) {
        const el = document.getElementById("rankedMods");
        if (!el) return;
        const nf = Number(info.nf_ht_penalty) || 0;
        const ez = info.ez_bonus || {};
        const reroll = info.reroll || {};
        const clamp = info.clamp || {};
        const forb = info.forbidden_mods || [];
        const forbNames = forb.map(function (m) { return escapeHtml(m.name); }).join(" · ");

        function card(icon, title, bodyHtml) {
            return '<div class="ranked-mod-card">' +
                '<div class="ranked-mod-icon">' + icon + "</div>" +
                '<div class="ranked-mod-title">' + escapeHtml(title) + "</div>" +
                '<div class="ranked-mod-body">' + bodyHtml + "</div>" +
                "</div>";
        }

        el.innerHTML =
            card("🔻", "Штраф NF / HT", "За каждый мод <strong>" + fmtDelta(nf) + "</strong> к изменению ELO за пасс (NF, HT).") +
            card(
                "💚",
                "EZ-бонус",
                fmtDelta(ez.bonus_low) + " при ★≥" + formatNum(ez.stars_low) +
                " · " + fmtDelta(ez.bonus_high) + " при ★≥" + formatNum(ez.stars_high) + "."
            ) +
            card("⛔", "Фейл / сдача / таймаут", "Штраф <strong>" + fmtDelta(info.fail_delta) + "</strong> ELO.") +
            card(
                "🔄",
                "Реролл",
                "Штраф <strong>" + fmtDelta(reroll.penalty) + "</strong> ELO, до <strong>" +
                formatNum(reroll.daily_limit) + "</strong> в сутки."
            ) +
            card(
                "📏",
                "Итог пасса",
                "Зажат в диапазон от <strong>" + fmtDelta(clamp.min) + "</strong> до <strong>" +
                fmtDelta(clamp.max) + "</strong> ELO."
            ) +
            card(
                "🎚️",
                "Старт и пол",
                "Старт — <strong>" + formatNum(info.start_elo) + "</strong> ELO, ниже <strong>" +
                formatNum(info.elo_floor) + "</strong> ELO не опуститься."
            ) +
            card("🚫", "Запрещённые моды", "Скор с этими модами не засчитывается: " + forbNames + ".");
    }

    // ------------------------------------------------------------------ //
    // Leaderboard (from /api/ranked/leaderboard)
    // ------------------------------------------------------------------ //

    const LB_PAGE = 50;
    let lbOffset = 0;
    let lbDone = false;

    function wldText(r) {
        return formatNum(r.wins) + " / " + formatNum(r.losses) + " / " + formatNum(r.draws);
    }

    function podiumCard(r, index) {
        const place = ["first", "second", "third"][index] || "";
        const wr = Number(r.win_rate || 0);
        return '<div class="ranked-podium-card ranked-podium-' + place + '">' +
            '<span class="ranked-podium-rank">#' + Number(r.rank) + "</span>" +
            avatarImg(r.avatar_url) +
            '<span class="ranked-podium-name">' + flagImg(r.flag, 20) + " " + escapeHtml(r.username) + "</span>" +
            tierBadge(r.tier) + subRankHtml(r.sub_rank, r.tier) +
            '<span class="ranked-podium-elo">' + formatNum(r.elo) + " ELO</span>" +
            '<span class="ranked-podium-meta">W / L / D ' + wldText(r) + " · " + Math.round(wr * 100) + "% побед</span>" +
            "</div>";
    }

    function rowHtml(r) {
        const wr = Number(r.win_rate || 0);
        return "<tr>" +
            '<td class="col-num">' + Number(r.rank) + "</td>" +
            '<td class="player-cell"><a class="player-link" href="/player/' + Number(r.osu_id) + '">' +
            avatarImg(r.avatar_url) +
            '<span class="player-name">' + flagImg(r.flag, 20) + " " + escapeHtml(r.username) + "</span>" +
            "</a></td>" +
            "<td>" + tierBadge(r.tier) + subRankHtml(r.sub_rank, r.tier) + "</td>" +
            '<td class="col-num">' + formatNum(r.elo) + "</td>" +
            '<td class="col-num">' + wldText(r) + "</td>" +
            '<td class="col-num">' + Math.round(wr * 100) + "%</td>" +
            "</tr>";
    }

    async function loadLeaderboard(reset) {
        const podium = document.getElementById("rankedPodium");
        const table = document.getElementById("rankedTable");
        const body = document.getElementById("rankedBody");
        const empty = document.getElementById("rankedEmpty");
        const more = document.getElementById("rankedMore");

        if (reset) {
            lbOffset = 0;
            lbDone = false;
            if (podium) podium.innerHTML = "";
            if (body) body.innerHTML = "";
            if (table) table.style.display = "none";
        }

        let rows;
        try {
            rows = await fetchJson("/api/ranked/leaderboard?limit=" + LB_PAGE + "&offset=" + lbOffset);
        } catch (e) {
            if (empty) {
                empty.textContent = "Не удалось загрузить лидерборд.";
                empty.style.display = "block";
            }
            return;
        }

        if (reset && rows.length === 0) {
            empty.textContent = "Пока никто не сыграл в Ranked.";
            empty.style.display = "block";
            return;
        }
        if (empty) empty.style.display = "none";

        const podiumRows = reset ? rows.slice(0, 3) : [];
        const tableRows = reset ? rows.slice(3) : rows;

        if (podium && podiumRows.length) {
            podium.innerHTML = podiumRows.map(function (r, i) { return podiumCard(r, i); }).join("");
        }
        if (tableRows.length) {
            table.style.display = "table";
            body.insertAdjacentHTML("beforeend", tableRows.map(rowHtml).join(""));
        }

        if (rows.length < LB_PAGE) {
            lbDone = true;
            if (more) more.style.display = "none";
        } else {
            if (more) more.style.display = "inline-block";
        }
    }

    // ------------------------------------------------------------------ //
    // Player profile card (from /api/players/{osu_id}/ranked)
    // ------------------------------------------------------------------ //

    const GRADE_COLORS = {
        XH: "#d6dae2", X: "#ffd700", SH: "#d6dae2", S: "#ffd700",
        A: "#00ff7f", B: "#1e90ff", C: "#a36cf5", D: "#ff0000",
    };
    const RANK_LABELS = { XH: "SS", SH: "S", X: "SS", S: "S" };
    const MOD_COLORS = {
        HD: "#ff69b4", HR: "#ff8c00", DT: "#4A9BE8", NC: "#a36cf5",
        HT: "#e6edf5", EZ: "#00e0a0", NF: "#8b9cb4", FL: "#ffd700",
        SO: "#8b9cb4", SD: "#8b9cb4", PF: "#ffd700", FI: "#66ff99",
        RX: "#66ff99",
    };

    function coverUrl(beatmapsetId) {
        const id = Number(beatmapsetId);
        if (!id) return null;
        return "https://assets.ppy.sh/beatmaps/" + id + "/covers/card@2x.jpg";
    }

    function fmtLength(sec) {
        sec = Number(sec) || 0;
        if (!sec) return "";
        const m = Math.floor(sec / 60);
        const s = Math.round(sec % 60);
        return m + ":" + String(s).padStart(2, "0");
    }

    function fmtDelta(delta) {
        const v = Number(delta) || 0;
        return v > 0 ? "+" + v : String(v);
    }

    function accPct(a) {
        return (Number(a) * 100).toFixed(2) + "%";
    }

    function modsBadges(mods) {
        const raw = String(mods || "").replace(/^\+/, "");
        if (!raw || raw === "NM") return '<span class="ranked-mod-muted">NM</span>';
        const letters = raw.match(/[A-Z]{2}/g) || [];
        if (!letters.length) return escapeHtml(raw);
        return letters.map(function (m) {
            const c = MOD_COLORS[m] || "#8b9cb4";
            return '<span class="ranked-mod" style="color:' + c + '">' + escapeHtml(m) + "</span>";
        }).join("");
    }

    function gradeLabel(g) {
        const up = String(g || "").toUpperCase();
        return RANK_LABELS[up] || up || "";
    }

    function gradeColor(g) {
        const up = String(g || "").toUpperCase();
        return GRADE_COLORS[up] || "#fff";
    }

    let rankedChart = null;

    const MONTHS_RU = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

    function fmtDateShort(iso) {
        const d = new Date(iso);
        if (isNaN(d.getTime())) return "";
        return String(d.getUTCDate()).padStart(2, "0") + "." + String(d.getUTCMonth() + 1).padStart(2, "0");
    }

    function fmtDateFull(iso) {
        const d = new Date(iso);
        if (isNaN(d.getTime())) return "";
        return d.getUTCDate() + " " + MONTHS_RU[d.getUTCMonth()] + " " + d.getUTCFullYear();
    }

    function last30Days(history) {
        const cutoff = Date.now() - 30 * 24 * 60 * 60 * 1000;
        const recent = history.filter(function (p) {
            const t = Date.parse(p.date);
            return !isNaN(t) && t >= cutoff;
        });
        return recent.length > 0 ? recent : history;
    }

    const tierLinesPlugin = {
        id: "tierLines",
        afterDatasetsDraw: function (chart, args, opts) {
            const tiers = (opts && opts.tiers) || [];
            if (!tiers.length) return;
            const ctx = chart.ctx;
            const chartArea = chart.chartArea;
            const yScale = chart.scales.y;
            if (!chartArea || !yScale) return;
            let lastPy = null;
            ctx.save();
            ctx.font = '10px "JetBrains Mono", monospace';
            ctx.textBaseline = "bottom";
            ctx.textAlign = "right";
            tiers.forEach(function (t) {
                const py = yScale.getPixelForValue(t.min_elo);
                if (py < chartArea.top - 1 || py > chartArea.bottom + 1) return;
                if (lastPy !== null && Math.abs(py - lastPy) < 12) return;
                lastPy = py;
                ctx.beginPath();
                ctx.setLineDash([4, 4]);
                ctx.strokeStyle = "rgba(139,156,180,0.30)";
                ctx.lineWidth = 1;
                ctx.moveTo(chartArea.left, py);
                ctx.lineTo(chartArea.right, py);
                ctx.stroke();
                ctx.setLineDash([]);
                ctx.fillStyle = "rgba(139,156,180,0.80)";
                ctx.fillText(t.name + " · " + t.min_elo, chartArea.right - 4, py - 2);
            });
            ctx.restore();
        },
    };

    function renderEloChart(history, tiers) {
        const wrap = document.getElementById("rankedEloChartWrap");
        if (!wrap || typeof Chart === "undefined") return;
        if (rankedChart) {
            rankedChart.destroy();
            rankedChart = null;
        }
        const canvas = document.createElement("canvas");
        wrap.appendChild(canvas);

        const labels = history.map(function (p) {
            return p.label === "старт" ? "старт" : fmtDateShort(p.date);
        });
        const values = history.map(function (p) { return Number(p.elo_after); });
        const single = history.length === 1;

        rankedChart = new Chart(canvas, {
            type: "line",
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    borderColor: "#4A9BE8",
                    backgroundColor: function (ctx) {
                        const chart = ctx.chart;
                        const area = chart.chartArea;
                        if (!area) return "rgba(74, 155, 232, 0.15)";
                        const g = chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
                        g.addColorStop(0, "rgba(74, 155, 232, 0.35)");
                        g.addColorStop(1, "rgba(74, 155, 232, 0.02)");
                        return g;
                    },
                    fill: true,
                    cubicInterpolationMode: "monotone",
                    pointRadius: single ? 3 : 0,
                    pointHoverRadius: 5,
                    pointHoverBackgroundColor: "#4A9BE8",
                    pointHoverBorderColor: "#ffffff",
                    pointHoverBorderWidth: 2,
                    borderWidth: 2.5,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                layout: { padding: { top: 4, right: 4 } },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: "rgba(13, 18, 32, 0.95)",
                        borderColor: "rgba(74, 155, 232, 0.4)",
                        borderWidth: 1,
                        titleColor: "#e6edf5",
                        bodyColor: "#c9d4e0",
                        padding: 10,
                        displayColors: false,
                        callbacks: {
                            title: function (items) {
                                const p = history[items[0].dataIndex];
                                return p.label === "старт" ? "старт" : fmtDateFull(p.date);
                            },
                            label: function (item) {
                                const i = item.dataIndex;
                                const cur = Number(history[i].elo_after);
                                let s = cur + " ELO";
                                if (i > 0) {
                                    const d = cur - Number(history[i - 1].elo_after);
                                    s += "  (" + fmtDelta(d) + ")";
                                }
                                return s;
                            },
                        },
                    },
                    tierLines: { tiers: tiers || [] },
                },
                scales: {
                    x: {
                        border: { display: false },
                        grid: { display: false },
                        ticks: {
                            color: "#8b9cb4",
                            font: { family: "JetBrains Mono", size: 10 },
                            maxRotation: 0,
                            autoSkip: true,
                            maxTicksLimit: 6,
                        },
                    },
                    y: {
                        border: { display: false },
                        grid: { color: "rgba(255,255,255,0.05)" },
                        grace: "8%",
                        ticks: {
                            color: "#8b9cb4",
                            font: { family: "JetBrains Mono", size: 10 },
                            padding: 6,
                        },
                    },
                },
            },
            plugins: [tierLinesPlugin],
        });
    }

    function resultRow(r) {
        const cover = coverUrl(r.beatmapset_id);
        const delta = Number(r.elo_delta) || 0;
        const baseTitle = (r.title || "").replace(/\s*\[[^\]]*\]\s*$/, "");

        const meta = [];
        if (r.version) meta.push(escapeHtml(r.version));
        if (Number(r.stars)) meta.push("★ " + Number(r.stars).toFixed(2));
        if (r.length_sec) meta.push(fmtLength(r.length_sec));

        const sub = [accPct(r.accuracy)];
        if (r.grade) {
            sub.push('<span style="color:' + gradeColor(r.grade) + '">' + escapeHtml(gradeLabel(r.grade)) + "</span>");
        }
        sub.push(modsBadges(r.mods));

        return '<div class="ranked-row">' +
            (cover ? '<div class="ranked-row-bg" style="background-image:url(' + cover + ')"></div>' : "") +
            '<div class="ranked-row-left">' +
            '<div class="ranked-row-title" title="' + escapeHtml(baseTitle) + '">' + escapeHtml(baseTitle) + "</div>" +
            '<div class="ranked-row-meta">' + meta.join(" · ") + "</div>" +
            "</div>" +
            '<div class="ranked-row-right">' +
            '<div class="ranked-row-delta ' + (delta > 0 ? "pos" : delta < 0 ? "neg" : "zero") + '">' + fmtDelta(delta) + "</div>" +
            '<div class="ranked-row-sub">' + sub.join(" · ") + "</div>" +
            "</div>" +
            "</div>";
    }

    function updateAvatarRank(data) {
        const wrap = document.getElementById("rankedRank");
        const badge = document.getElementById("rankedTierBadge");
        if (!wrap) return;
        const oldSub = document.getElementById("rankedSubRank");
        if (oldSub) oldSub.remove();
        if (!data || !data.tier) {
            wrap.style.display = "none";
            return;
        }
        const color = tierColor(data.tier);
        badge.style.color = color;
        badge.style.borderColor = color;
        badge.textContent = data.tier;
        const subHtml = subRankHtml(data.sub_rank, data.tier);
        if (subHtml) {
            const sub = document.createElement("span");
            sub.id = "rankedSubRank";
            sub.innerHTML = subHtml;
            wrap.appendChild(sub);
        }
        wrap.style.display = "flex";
    }

    window.renderRankedProfile = async function (osuId, container) {
        if (!container) return;
        let data;
        try {
            data = await fetchJson("/api/players/" + encodeURIComponent(osuId) + "/ranked");
        } catch (e) {
            container.style.display = "none";
            updateAvatarRank(null);
            return;
        }
        if (!data || !data.enabled) {
            container.style.display = "none";
            updateAvatarRank(null);
            return;
        }
        updateAvatarRank(data);

        const prog = data.progress || {};
        const pct = Math.max(0, Math.min(100, Number(prog.percent) || 0));
        const nextTier = prog.next_tier;

        const hasGames = (data.last_results && data.last_results.length > 0) ||
            (data.elo_history && data.elo_history.length > 0);

        container.style.display = "block";
        container.innerHTML = "";

        const head = document.createElement("div");
        head.className = "ranked-profile-head";
        const h3 = document.createElement("h3");
        h3.textContent = "Ranked";
        head.appendChild(h3);
        const badge = document.createElement("span");
        badge.className = "ranked-tier-badge";
        const color = tierColor(data.tier);
        badge.style.color = color;
        badge.style.borderColor = color;
        badge.textContent = data.tier;
        head.appendChild(badge);
        const subHtml = subRankHtml(data.sub_rank, data.tier);
        if (subHtml) badge.insertAdjacentHTML("afterend", subHtml);
        container.appendChild(head);

        const eloLine = document.createElement("div");
        eloLine.className = "ranked-profile-elo";
        const eloVal = document.createElement("span");
        eloVal.className = "ranked-elo-value";
        eloVal.textContent = formatNum(data.current_elo) + " ELO";
        eloLine.appendChild(eloVal);
        const track = document.createElement("div");
        track.className = "ranked-progress";
        const fill = document.createElement("div");
        fill.className = "ranked-progress-fill";
        fill.style.width = pct + "%";
        track.appendChild(fill);
        eloLine.appendChild(track);
        const progLabel = document.createElement("span");
        progLabel.className = "ranked-progress-label";
        if (nextTier) {
            progLabel.textContent = "до «" + nextTier + "»: " + formatNum(prog.points) + "/" + formatNum(prog.span) + " (" + pct + "%)";
        } else {
            progLabel.textContent = "Максимальное звание";
        }
        eloLine.appendChild(progLabel);
        container.appendChild(eloLine);

        if (!hasGames) {
            const empty = document.createElement("p");
            empty.className = "ranked-empty-note";
            empty.textContent = "Пока нет завершённых заданий Ranked.";
            container.appendChild(empty);
            return;
        }

        const stats = document.createElement("div");
        stats.className = "ranked-stats";
        const stat = function (label, value) {
            const s = document.createElement("div");
            s.className = "ranked-stat";
            const l = document.createElement("span");
            l.className = "ranked-stat-label";
            l.textContent = label;
            const v = document.createElement("span");
            v.className = "ranked-stat-value";
            v.textContent = value;
            s.appendChild(l);
            s.appendChild(v);
            return s;
        };
        stats.appendChild(stat("W / L / D", formatNum(data.wins) + " / " + formatNum(data.losses) + " / " + formatNum(data.draws)));
        stats.appendChild(stat("Win rate", Math.round(Number(data.win_rate || 0) * 100) + "%"));
        stats.appendChild(stat("Окно ★", starWindowText(data.star_window) || "—"));
        const accValue = data.best_accuracy != null
            ? accPct(data.best_accuracy) + (data.avg_accuracy != null ? " / " + accPct(data.avg_accuracy) : "")
            : "—";
        stats.appendChild(stat("Точность (лучшая / средняя)", accValue));
        stats.appendChild(stat("Сложнейшая", data.hardest_passed_stars != null ? "★" + Number(data.hardest_passed_stars).toFixed(2) : "—"));
        container.appendChild(stats);

        if (data.elo_history && data.elo_history.length > 0 && typeof Chart !== "undefined") {
            const chartHistory = last30Days(data.elo_history);
            const chartWrap = document.createElement("div");
            chartWrap.className = "ranked-chart-wrap";
            chartWrap.id = "rankedEloChartWrap";
            container.appendChild(chartWrap);
            renderEloChart(chartHistory, data.tier_thresholds || []);
        }

        if (data.last_results && data.last_results.length > 0) {
            const HISTORY_VISIBLE = 5;
            const all = data.last_results;
            const list = document.createElement("div");
            list.className = "ranked-history-list";
            const renderRows = function (count) {
                list.innerHTML = all.slice(0, count).map(resultRow).join("");
            };
            if (all.length > HISTORY_VISIBLE) {
                renderRows(HISTORY_VISIBLE);
                const more = document.createElement("div");
                more.className = "ranked-history-more";
                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = "btn btn-sm btn-ghost";
                btn.textContent = "Показать все (" + all.length + ")";
                btn.addEventListener("click", function () {
                    renderRows(all.length);
                    list.classList.add("ranked-history-expanded");
                    more.style.display = "none";
                });
                more.appendChild(btn);
                container.appendChild(list);
                container.appendChild(more);
            } else {
                renderRows(all.length);
                container.appendChild(list);
            }
        }
    };

    // ------------------------------------------------------------------ //
    // Landing page entry point
    // ------------------------------------------------------------------ //

    window.initRankedPage = async function () {
        const content = document.getElementById("rankedContent");
        const disabled = document.getElementById("rankedDisabled");

        setStatus("Загрузка…");
        let info;
        try {
            info = await fetchJson("/api/ranked/info");
        } catch (e) {
            setStatus("Не удалось загрузить правила Ranked.", true);
            return;
        }
        setStatus(null);

        if (!info.enabled) {
            if (content) content.style.display = "none";
            if (disabled) disabled.style.display = "block";
            return;
        }
        if (disabled) disabled.style.display = "none";
        if (content) content.style.display = "block";

        renderTiers(info.tiers);

        const tierNote = document.getElementById("rankedTierNote");
        if (tierNote) {
            const h = Number(info.star_window);
            tierNote.textContent = "В таблице — крайние точки диапазона звания. Фактическое окно " +
                (Number.isFinite(h) ? "шириной ±" + h.toFixed(2) + "★ " : "") +
                "сдвигается внутри диапазона вместе с ELO.";
        }

        const rewardLabel = document.getElementById("rankedRewardLabel");
        if (rewardLabel) {
            const table = info.acc_reward_table || [];
            const zeroPoint = table.find(function (r) { return Number(r[1]) === 0; });
            if (zeroPoint) {
                const zeroAcc = (Number(zeroPoint[0]) * 100).toFixed(0);
                rewardLabel.textContent =
                    "Изменение ELO за точность: ниже " + zeroAcc + "% — минус, " +
                    zeroAcc + "% — 0, выше — плюс. Точки и значения берутся из таблицы.";
            } else {
                rewardLabel.textContent =
                    "В таблице нет точки с нулевым изменением ELO: отрицательные значения уменьшают ELO, " +
                    "положительные увеличивают. Точки и значения берутся из таблицы.";
            }
        }
        renderReward(info.acc_reward_table);
        renderMods(info);

        const more = document.getElementById("rankedMore");
        if (more) {
            more.addEventListener("click", function () {
                if (lbDone) return;
                lbOffset += LB_PAGE;
                loadLeaderboard(false);
            });
        }

        await loadLeaderboard(true);
    };

    // Exposed for testability (server/tests/test_ranked_js.py runs it via node).
    window.rankedPlural = plural;
    window.rankedSubRankHtml = subRankHtml;
    window.rankedStarWindowText = starWindowText;
    window.rankedTierColors = TIER_COLORS;
    window.rankedTierShapes = TIER_SHAPES;
    window.rankedShapeStates = shapeStates;
    window.rankedTierShapeSvg = tierShapeSvg;
})();
