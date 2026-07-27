const datePicker = document.getElementById('datePicker');
const scoresBody = document.getElementById('scoresBody');
const emptyMsg = document.getElementById('emptyMsg');
const dailySummary = document.getElementById('dailySummary');
const gradeCounters = document.getElementById('gradeCounters');
const gradesSection = document.getElementById('gradesSection');
const goalInput = document.getElementById('goalInput');
const goalSetBtn = document.getElementById('goalSetBtn');
const goalStatus = document.getElementById('goalStatus');
let chart = null;

const GRADE_ORDER = ['SS', 'S', 'A', 'B', 'C', 'D'];
const GRADE_LABELS = { 'XH': 'SS', 'X': 'SS', 'SH': 'S', 'S': 'S' };
const GRADE_COLORS = {
    'SS': '#ffd700', 'S': '#ff69b4', 'A': '#00ff7f',
    'B': '#1e90ff', 'C': '#ff4500', 'D': '#ff0000',
};

const PROFILE_GRADE_ORDER = ['XH', 'X', 'SH', 'S', 'A', 'B', 'C', 'D'];
const PROFILE_GRADE_COLORS = {
    'XH': '#ffd700', 'X': '#ffd700', 'SH': '#ff69b4', 'S': '#ff69b4',
    'A': '#00ff7f', 'B': '#1e90ff', 'C': '#ff4500', 'D': '#ff0000',
};

let dailyGoal = parseInt(localStorage.getItem('apGoal')) || 0;

function normalizeGrade(grade) {
    return GRADE_LABELS[grade] || grade;
}

function formatDate(ts) {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

function gradeClass(grade) {
    return 'grade-' + grade.replace('H', '');
}

function setToday() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    datePicker.value = `${y}-${m}-${day}`;
}

function truncateTitle(title, maxLen = 55) {
    return title.length > maxLen ? title.slice(0, maxLen) + '...' : title;
}

document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        document.querySelectorAll('[id^="tab-"]').forEach(t => t.style.display = 'none');
        const tab = document.getElementById('tab-' + btn.dataset.tab);
        tab.style.display = 'block';
        if (btn.dataset.tab === 'profile') loadProfile();
        if (btn.dataset.tab === 'daily') {
            setToday();
            loadDaily();
            loadScores(datePicker.value);
        }
    });
});

async function loadDaily() {
    const resp = await fetch('/api/daily');
    const days = await resp.json();
    renderChart(days);
}

async function loadScores(date) {
    try {
        const resp = await fetch(`/api/scores?date=${date}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const scores = await resp.json();
        renderScores(scores, date);
    } catch {
        goalStatus.textContent = dailyGoal > 0
            ? `🎯 Цель: ${dailyGoal} AP в день`
            : '';
    }
}

function renderGradeCounters(scores) {
    const counts = {};
    for (const g of GRADE_ORDER) counts[g] = 0;

    for (const s of scores) {
        const norm = normalizeGrade(s.grade);
        if (counts[norm] !== undefined) counts[norm]++;
    }

    const hasGrades = Object.values(counts).some(c => c > 0);
    gradesSection.style.display = hasGrades ? 'block' : 'none';

    gradeCounters.innerHTML = GRADE_ORDER.map(g => `
        <div class="grade-counter">
            <span class="grade-label" style="color:${GRADE_COLORS[g]}">${g}</span>
            <span class="grade-count">${counts[g]}</span>
        </div>
    `).join('');
}

function updateGoal(totalAp) {
    if (dailyGoal > 0) {
        const met = totalAp >= dailyGoal;
        goalStatus.textContent = met
            ? `🔥 ${Math.floor(totalAp)} / ${dailyGoal} AP — Цель выполнена!`
            : `${Math.floor(totalAp)} / ${dailyGoal} AP`;
        goalStatus.className = 'goal-status' + (met ? ' met' : '');
    } else {
        goalStatus.textContent = totalAp > 0 ? `Всего AP: ${Math.floor(totalAp)}` : '';
        goalStatus.className = 'goal-status';
    }
}

function renderChart(days) {
    const ctx = document.getElementById('apChart').getContext('2d');
    const labels = days.map(d => d.date).reverse();
    const data = days.map(d => d.total_ap).reverse();
    const counts = days.map(d => d.scores_count).reverse();

    if (chart) chart.destroy();

    if (labels.length === 0) {
        document.querySelector('.chart-section').style.display = 'none';
        return;
    }
    document.querySelector('.chart-section').style.display = 'block';

    chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'AP за день',
                data,
                backgroundColor: data.map(v => (dailyGoal > 0 && v >= dailyGoal) ? '#ffaa00' : '#4A9BE8'),
                borderRadius: 8,
                borderSkipped: false,
                hoverBackgroundColor: '#6CB4EE',
                maxBarThickness: 50,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            onHover: (e, elements) => {
                e.native.target.style.cursor = elements.length > 0 ? 'pointer' : 'default';
            },
            onClick: (e, elements) => {
                if (elements.length > 0) {
                    const idx = elements[0].index;
                    datePicker.value = labels[idx];
                    loadScores(datePicker.value);
                }
            },
            plugins: {
                legend: { labels: { color: '#aaa' } },
                tooltip: {
                    callbacks: {
                        afterLabel: function(context) {
                            return 'Карт: ' + counts[context.dataIndex];
                        }
                    }
                }
            },
            scales: {
                x: {
                    ticks: { color: '#888' },
                    grid: { display: false },
                    categoryPercentage: 0.5,
                },
                y: {
                    beginAtZero: true,
                    ticks: { color: '#888' },
                    grid: { color: '#2a2a3e' }
                }
            }
        }
    });
}

function renderScores(scores, date) {
    scoresBody.innerHTML = '';
    if (scores.length === 0) {
        emptyMsg.style.display = 'block';
        dailySummary.innerHTML = '';
        gradesSection.style.display = 'none';
        updateGoal(0);
        return;
    }
    emptyMsg.style.display = 'none';

    let totalAp = 0;
    for (const s of scores) {
        totalAp += s.ap;
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td class="title" title="${s.beatmap_title}">${truncateTitle(s.beatmap_title)}</td>
            <td>${(s.accuracy * 100).toFixed(2)}%</td>
            <td class="grade ${gradeClass(s.grade)}">${s.grade}</td>
            <td>${s.mods || 'NM'}</td>
            <td>x${s.max_combo}</td>
            <td class="pp">${s.pp ? s.pp.toFixed(1) : '-'}</td>
            <td class="ap">${Math.floor(s.ap)} AP</td>
        `;
        scoresBody.appendChild(tr);
    }

    dailySummary.innerHTML = `
        <span>Сумма AP: <strong>${Math.floor(totalAp)}</strong></span>
        <span>Карт: <strong>${scores.length}</strong></span>
    `;

    renderGradeCounters(scores);
    updateGoal(totalAp);
}

async function loadProfile() {
    const goal = dailyGoal > 0 ? dailyGoal : 0;
    try {
        const resp = await fetch(`/api/profile?goal=${goal}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        renderProfile(data);
    } catch {
        document.getElementById('profileName').textContent = 'Ошибка загрузки';
    }
}

function renderProfile(data) {
    document.getElementById('profileName').textContent = data.player_name || 'Unknown';
    document.getElementById('profTotalAp').textContent = formatNum(data.total_ap) + ' AP';
    document.getElementById('profWeightedPp').textContent = formatNum(data.weighted_pp) + ' PP';
    document.getElementById('profPlayCount').textContent = formatNum(data.play_count);
    document.getElementById('profGoalsDone').textContent = formatNum(data.goals_completed);

    const container = document.getElementById('profileGrades');
    container.innerHTML = PROFILE_GRADE_ORDER.map(g => {
        const cnt = data.grades[g] || 0;
        const color = PROFILE_GRADE_COLORS[g] || '#888';
        return `<div class="grade-badge grade-${g}">
            <span class="gl" style="color:${color}">${g}</span>
            <span class="gc">${cnt}</span>
        </div>`;
    }).join('');

    const tbody = document.getElementById('topBody');
    const empty = document.getElementById('topEmpty');
    if (!data.top_scores || data.top_scores.length === 0) {
        tbody.innerHTML = '';
        empty.style.display = 'block';
        return;
    }
    empty.style.display = 'none';

    tbody.innerHTML = data.top_scores.map(s => `
        <tr>
            <td class="title" title="${s.beatmap_title}">${truncateTitle(s.beatmap_title)}</td>
            <td>${(s.accuracy * 100).toFixed(2)}%</td>
            <td class="grade ${gradeClass(s.grade)}">${s.grade}</td>
            <td>${s.mods || 'NM'}</td>
            <td>x${s.max_combo}</td>
            <td class="pp">${s.pp ? s.pp.toFixed(1) : '-'}</td>
            <td class="ap">${Math.floor(s.ap)} AP</td>
        </tr>
    `).join('');
}

function formatNum(n) {
    if (typeof n !== 'number') return n;
    return n.toLocaleString('ru-RU');
}

datePicker.addEventListener('change', () => {
    loadScores(datePicker.value);
});

goalSetBtn.addEventListener('click', () => {
    const val = parseInt(goalInput.value);
    if (val > 0) {
        dailyGoal = val;
        localStorage.setItem('apGoal', val);
        goalStatus.textContent = `🎯 Цель: ${val} AP в день`;
        goalStatus.className = 'goal-status';
    } else {
        dailyGoal = 0;
        localStorage.removeItem('apGoal');
        goalStatus.textContent = 'Цель сброшена';
        goalStatus.className = 'goal-status';
    }
    loadScores(datePicker.value);
});

goalInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') goalSetBtn.click();
});

if (dailyGoal > 0) {
    goalInput.value = dailyGoal;
}

setToday();
loadDaily();
loadScores(datePicker.value);
