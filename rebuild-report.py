import re
import json
from datetime import datetime, timedelta
from collections import deque
import os
import sys

# Configuration (matching ping-tuckz.py)
GAP_SECONDS = 20  # Gap to start new chunk (for timeout handling)
WINDOW_SECONDS = 6  # 6 seconds for pre/post normal buffers (legacy, may not be used)
SPIKE_THRESHOLD = 50
CONSISTENT_SPIKE_THRESHOLD = 3
BUFFER_MAX = 1000
NORMAL_PING_THRESHOLD = 10  # Consecutive normal pings to end chunk
NORMAL_PING_KEEP_AT_END = 2  # Normal pings to keep at end of chunk
NORMAL_PING_KEEP_AT_START = 2  # Normal pings before first abnormality

# Input and output files (configurable via command line args)
if len(sys.argv) >= 3:
    TXT_LOG_FILE = sys.argv[1]
    HTML_OUTPUT_FILE = sys.argv[2]
else:
    TXT_LOG_FILE = os.path.join("Results", "2025.12.05-Dec.Fri.5.txt")
    HTML_OUTPUT_FILE = os.path.join("Results", "2025.12.05-Dec.Fri.5-rebuilt.htm")

def parse_latency(ping_line):
    if is_timeout(ping_line):
        return None
    # Match raw ping output and Ping Tuckz's normalized record format.
    time_match = re.search(r'(?:time|latency)[=<](\d+\.?\d*)\s*ms', ping_line, re.IGNORECASE)
    return int(float(time_match.group(1))) if time_match else None

def is_timeout(line):
    line_lower = line.lower()
    return 'request timed out' in line_lower or 'request timeout' in line_lower or 'status=timeout' in line_lower

def is_ping_record(line):
    return (
        'Reply from' in line or
        'bytes from' in line or
        'Request timed out' in line or
        'Request timeout' in line or
        'latency=' in line or
        'status=timeout' in line
    )

def parse_timestamp(line):
    # Extract timestamp from line like: (2025-12-05) @ 09:02:29 pm - Reply from...
    timestamp_match = re.search(r'\((\d{4}-\d{2}-\d{2})\) @ (\d{1,2}):(\d{2}):(\d{2})\s+(am|pm)', line, re.IGNORECASE)
    if not timestamp_match:
        return None
    date_str, hour_str, minute_str, second_str, ampm = timestamp_match.groups()
    hour = int(hour_str)
    minute = int(minute_str)
    second = int(second_str)
    if ampm.lower() == 'pm' and hour != 12:
        hour += 12
    elif ampm.lower() == 'am' and hour == 12:
        hour = 0
    year, month, day = map(int, date_str.split('-'))
    return datetime(year, month, day, hour, minute, second)

def normalize_ping_record(line):
    """Return a privacy-preserving ping record with no target host or reply IP."""
    timestamp = parse_timestamp(line)
    if timestamp is None:
        return line
    timestamp_str = timestamp.strftime("(%Y-%m-%d) @ %I:%M:%S %p").lower()
    if is_timeout(line):
        return f"{timestamp_str} - status=timeout"
    latency = parse_latency(line)
    if latency is None:
        return line
    return f"{timestamp_str} - latency={latency}ms"

def get_html_class(latency):
    if latency is None:
        return 'timeout'
    elif latency < 50:
        return 'normal'
    elif 50 <= latency <= 100:
        return 'medium'
    else:
        return 'high'

def get_time_buffer_start(idx, seconds_back):
    """Get index approx seconds_back before buffer[idx][0]"""
    target_time = buffer[idx][0] - timedelta(seconds=seconds_back)
    for i in range(idx - 1, -1, -1):
        if buffer[i][0] >= target_time:
            continue
        return max(0, i + 1)
    return 0

def get_time_buffer_end(idx, seconds_forward):
    """Get index approx seconds_forward after buffer[idx][0]"""
    target_time = buffer[idx][0] + timedelta(seconds=seconds_forward)
    for i in range(idx + 1, len(buffer)):
        if buffer[i][0] > target_time:
            return i - 1
    return len(buffer) - 1

def has_consistent_spike(start_idx, end_idx):
    """Check for 3+ consecutive >=50ms in range (skip timeouts)"""
    consec = 0
    for i in range(start_idx, end_idx + 1):
        lat = buffer[i][1]
        if lat is not None and lat >= SPIKE_THRESHOLD:
            consec += 1
            if consec >= CONSISTENT_SPIKE_THRESHOLD:
                return True
        elif lat is not None:
            consec = 0
    return False

def finalize_current_chunk(end_due_to_normal_gap=False, last_normal_indices_at_end=None):
    global current_chunk_start, last_abnormal_time, pending_finalization, current_chunk_abnormalities, last_chunk_end_idx
    if current_chunk_start is None or not current_chunk_abnormalities:
        return
    first_abnormal_idx = current_chunk_start
    last_abnormal_idx = current_chunk_abnormalities[-1]

    # Collect pre normals: exactly NORMAL_PING_KEEP_AT_START normals before first abnormality
    pre_indices = []
    normal_count = 0
    for i in range(first_abnormal_idx - 1, -1, -1):
        if buffer[i][1] is not None and buffer[i][1] < SPIKE_THRESHOLD:
            pre_indices.append(i)
            normal_count += 1
            if normal_count == NORMAL_PING_KEEP_AT_START:
                break
        else:
            break
    pre_indices.reverse()

    # Collect post normals: exactly NORMAL_PING_KEEP_AT_END normals after last abnormality
    post_indices = []
    normal_count = 0
    for i in range(last_abnormal_idx + 1, len(buffer)):
        if buffer[i][1] is not None and buffer[i][1] < SPIKE_THRESHOLD:
            post_indices.append(i)
            normal_count += 1
            if normal_count == NORMAL_PING_KEEP_AT_END:
                break
        else:
            break

    # All indices for the chunk: pre normals + abnormalities + post normals
    all_indices = pre_indices + current_chunk_abnormalities + post_indices
    if not all_indices:
        return

    # Sort to ensure order (though should already be sorted)
    all_indices.sort()

    # Count for title
    abnormal_count = len(current_chunk_abnormalities)
    timeout_count = sum(1 for i in current_chunk_abnormalities if buffer[i][1] is None)
    high_count = sum(1 for i in current_chunk_abnormalities if buffer[i][1] is not None and buffer[i][1] >= SPIKE_THRESHOLD)
    consistent_note = " (includes consistent spike)" if has_consistent_spike(first_abnormal_idx, last_abnormal_idx) else ""
    timeout_note = f", {timeout_count} timeout(s)" if timeout_count > 0 else ""
    title = f"Abnormality: {abnormal_count} issue(s) ({high_count} high(s) >= {SPIKE_THRESHOLD} ms{timeout_note}){consistent_note}"

    output_chunk(title, all_indices)
    # Track where this chunk ended to prevent overlap with next chunk
    last_chunk_end_idx = max(all_indices)
    current_chunk_start = None
    current_chunk_abnormalities = []
    pending_finalization = False

def output_chunk(title, all_indices):
    if not all_indices:
        return
    min_idx = min(all_indices)
    max_idx = max(all_indices)
    event_lines = [buffer[i][2] for i in all_indices]

    # HTML output (buffered) - only add if there are abnormalities (>=50ms or timeouts, no upper limit)
    has_abnormalities = any(
        buffer[i][1] is None or (buffer[i][1] is not None and buffer[i][1] >= SPIKE_THRESHOLD)
        for i in all_indices
    )

    if has_abnormalities:
        global event_html_list, last_date_header, chunk_metadata_list

        # Collect latency classes for nav widget
        chunk_classes = []
        for i in all_indices:
            lat = buffer[i][1]
            chunk_classes.append('timeout' if lat is None else get_html_class(lat))

        chunk_index = len(event_html_list)

        # Add date header if this is a new day
        chunk_date = buffer[min_idx][0].date()
        date_header_html = ''
        if last_date_header != chunk_date:
            date_str = buffer[min_idx][0].strftime("%A, %B %d, %Y")  # e.g., "Friday, January 31, 2026"
            date_header_html = f'<div class="date-header">{date_str}</div>\n'
            last_date_header = chunk_date

        separator = '<div class="chunk-separator"></div>\n' if len(event_html_list) > 0 and date_header_html == '' else ''

        # Format time range prominently
        start_time = buffer[min_idx][0].strftime("%I:%M:%S %p").lstrip('0')
        end_time = buffer[max_idx][0].strftime("%I:%M:%S %p").lstrip('0')
        time_range_html = f'<span class="time-range">{start_time} - {end_time}</span>'

        # Use global ping numbers (1-indexed)
        chunk_date_str = buffer[min_idx][0].strftime("%A, %B %d, %Y")
        # Seconds-of-day range + peak latency so the graph can focus this chunk on zoom
        _start_dt, _end_dt = buffer[min_idx][0], buffer[max_idx][0]
        start_sec = _start_dt.hour * 3600 + _start_dt.minute * 60 + _start_dt.second
        end_sec = _end_dt.hour * 3600 + _end_dt.minute * 60 + _end_dt.second
        chunk_peak, chunk_has_timeout = 0, False
        for i in all_indices:
            lat = buffer[i][1]
            if lat is None:
                chunk_has_timeout = True
            elif lat > chunk_peak:
                chunk_peak = lat
        peak_score = 100000 if chunk_has_timeout else chunk_peak
        html_header = f'{separator}{date_header_html}<div class="event" id="chunk-{chunk_index}" data-start-sec="{start_sec}" data-end-sec="{end_sec}" data-peak="{peak_score}"><div class="header">{title} | Pings {min_idx + 1}–{max_idx + 1} | {chunk_date_str} | {time_range_html}</div>\n'
        html_body = ''
        for line in event_lines:
            line = normalize_ping_record(line)
            ping_line = line.split(' - ', 1)[1] if ' - ' in line else line
            latency = parse_latency(ping_line)
            css_class = 'timeout' if latency is None else get_html_class(latency)
            line_without_ttl = re.sub(r'\s+TTL=\d+', '', line)
            # Simplify timestamp to show only time (remove date)
            line_simplified = re.sub(r'\(\d{4}-\d{2}-\d{2}\) @ ', '', line_without_ttl)
            html_body += f'<span class="{css_class}">{line_simplified}</span><br>\n'
        html_output = html_header + html_body + '</div>\n'
        event_html_list.append(html_output)
        chunk_metadata_list.append(chunk_classes)

def _compute_widget_marks(class_sequence, num_marks=10):
    """Downsample a sequence of CSS classes into num_marks representative marks."""
    n = len(class_sequence)
    if n <= num_marks:
        pad_total = num_marks - n
        pad_left = pad_total // 2
        pad_right = pad_total - pad_left
        return ['normal'] * pad_left + list(class_sequence) + ['normal'] * pad_right
    marks = []
    for i in range(num_marks):
        start = int(i * n / num_marks)
        end = int((i + 1) * n / num_marks)
        segment = class_sequence[start:end]
        if 'timeout' in segment:
            marks.append('timeout')
        elif 'high' in segment:
            marks.append('high')
        elif 'medium' in segment:
            marks.append('medium')
        else:
            marks.append('normal')
    return marks

def _build_chunk_nav_html(metadata_list, has_graph=False):
    """Build the sticky tabbed panel: Abnormality Navigator + Daily Latency Graph."""
    if not metadata_list and not has_graph:
        return ''
    nav_html = '<div id="chunk-nav">\n<div class="chunk-nav-tabs">'
    if has_graph:
        nav_html += '<button class="chunk-nav-tab active" data-tab="graph-pane">Latency Graph</button>'
    nav_tab_cls = 'chunk-nav-tab' if has_graph else 'chunk-nav-tab active'
    nav_html += f'<button class="{nav_tab_cls}" data-tab="nav-pane">Latency Chunks</button></div>\n'
    # Latency graph pane (default tab when available)
    if has_graph:
        nav_html += '<div id="graph-pane" class="chunk-nav-pane active">\n<div class="graph-hint"><span>drag to zoom · double-click to reset</span><span class="graph-reset" id="latency-graph-reset">reset zoom</span></div>\n<canvas id="latency-graph"></canvas>\n<div id="latency-tooltip"></div>\n</div>\n'
    # Latency chunks pane
    pane_cls = 'chunk-nav-pane' if has_graph else 'chunk-nav-pane active'
    nav_html += f'<div id="nav-pane" class="{pane_cls}">\n'
    if metadata_list:
        nav_html += '<div class="chunk-nav-section-label">Daily Abnormalities</div>\n'
        nav_html += '<div class="chunk-nav-scroll">\n<div class="chunk-nav-grid">\n'
        for idx, class_sequence in enumerate(metadata_list):
            marks = _compute_widget_marks(class_sequence)
            nav_html += f'<a href="#chunk-{idx}" class="chunk-widget" title="Abnormality {idx + 1} ({len(class_sequence)} pings)">'
            for mark_class in marks:
                nav_html += f'<span class="chunk-mark-{mark_class}"></span>'
            nav_html += '</a>\n'
        nav_html += '</div>\n</div>\n<div class="chunk-nav-fade"></div>\n'
    else:
        nav_html += '<div class="chunk-nav-empty">No abnormalities recorded.</div>\n'
    nav_html += '</div>\n'
    # Footer: Home button, bottom-left of the panel
    nav_html += '<div class="chunk-nav-footer"><span class="chunk-nav-home" id="chunk-nav-home" title="Scroll to top"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12l9-9 9 9"/><path d="M5 10v10a1 1 0 001 1h3v-6h6v6h3a1 1 0 001-1V10"/></svg><span class="chunk-nav-home-label">Home</span></span></div>\n'
    nav_html += '</div>\n<div id="chunk-nav-spacer"></div>\n'
    return nav_html

def _build_latency_graph_payload(txt_path):
    """Read the day's TXT log and build a JSON payload of every ping for the latency graph.
    Returns a compact JSON string {"points": [[secondsOfDay, latencyMs|null], ...]} (null = timeout),
    or None if the file is missing or contains no ping lines.
    """
    if not txt_path or not os.path.exists(txt_path):
        return None
    points = []
    with open(txt_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Skip non-ping lines (summaries, headers, separators, abnormality listings)
            if line.startswith('Session Summary') or line.startswith('All Individual') or \
               line.startswith('===') or line.startswith('---') or line.startswith('['):
                continue
            if not is_ping_record(line):
                continue
            ts = parse_timestamp(line)
            if ts is None:
                continue
            sec = ts.hour * 3600 + ts.minute * 60 + ts.second
            if is_timeout(line):
                points.append([sec, None])
            else:
                latency = parse_latency(line)
                if latency is not None:
                    points.append([sec, latency])
    if not points:
        return None
    points.sort(key=lambda p: p[0])
    return json.dumps({"points": points}, separators=(',', ':'))

CHUNK_NAV_SCRIPT = """<script>
(function() {
    var nav = document.getElementById('chunk-nav');
    var spacer = document.getElementById('chunk-nav-spacer');
    var banner = document.getElementById('day-banner');
    if (!nav) return;
    // Sticky behavior — nav sits just below the sticky day-banner
    var navTop = nav.offsetTop;
    var navHeight = nav.offsetHeight;
    function bannerH() { return banner ? banner.offsetHeight : 0; }
    window.addEventListener('scroll', function() {
        if (window.scrollY >= navTop - bannerH()) {
            nav.classList.add('sticky');
            nav.style.top = (bannerH() + 4) + 'px';
            spacer.style.height = navHeight + 'px';
            spacer.classList.add('active');
        } else {
            nav.classList.remove('sticky');
            nav.style.top = '';
            spacer.style.height = '0';
            spacer.classList.remove('active');
        }
    });
    // Grid sizing + fade indicator (deferred until the chunks pane is visible)
    var scrollBox = nav.querySelector('.chunk-nav-scroll');
    var fade = nav.querySelector('.chunk-nav-fade');
    var grid = nav.querySelector('.chunk-nav-grid');
    var gridSized = false;
    function updateFade() {
        if (!fade || !scrollBox) return;
        var canScroll = scrollBox.scrollHeight > scrollBox.clientHeight + 2;
        var atBottom = scrollBox.scrollTop + scrollBox.clientHeight >= scrollBox.scrollHeight - 2;
        if (canScroll && !atBottom) { fade.classList.add('visible'); }
        else { fade.classList.remove('visible'); }
    }
    function sizeGrid() {
        if (gridSized || !scrollBox || !grid) return;
        var firstWidget = grid.querySelector('.chunk-widget');
        if (!firstWidget || !firstWidget.offsetHeight) return; // pane not visible yet
        var rowH = firstWidget.offsetHeight + 4; // 4px gap
        var rows = Math.round(grid.scrollHeight / rowH);
        var maxRows = Math.min(rows, 2); // show exactly 1 or 2 full rows
        scrollBox.style.maxHeight = (maxRows * rowH) + 'px';
        gridSized = true;
        updateFade();
    }
    if (scrollBox) scrollBox.addEventListener('scroll', updateFade);

    // Tab switching between the latency graph and latency chunks panes
    var tabs = nav.querySelectorAll('.chunk-nav-tab');
    tabs.forEach(function(tab) {
        tab.addEventListener('click', function() {
            tabs.forEach(function(t) { t.classList.remove('active'); });
            nav.querySelectorAll('.chunk-nav-pane').forEach(function(p) { p.classList.remove('active'); });
            tab.classList.add('active');
            var pane = document.getElementById(tab.getAttribute('data-tab'));
            if (pane) pane.classList.add('active');
            if (tab.getAttribute('data-tab') === 'graph-pane' && window.__drawLatencyGraph) {
                window.__drawLatencyGraph();
            }
            if (tab.getAttribute('data-tab') === 'nav-pane') sizeGrid();
            // Pane heights differ; keep the sticky spacer and top offset in sync
            navHeight = nav.offsetHeight;
            if (nav.classList.contains('sticky')) {
                nav.style.top = (bannerH() + 4) + 'px';
                spacer.style.height = navHeight + 'px';
            }
        });
    });
    // Size now if the chunks pane is the default-visible pane
    var navPane = document.getElementById('nav-pane');
    if (navPane && navPane.classList.contains('active')) sizeGrid();

    // Home button scrolls to top
    var homeBtn = document.getElementById('chunk-nav-home');
    if (homeBtn) {
        homeBtn.addEventListener('click', function() {
            animateScrollTo(0);
        });
    }

    // Temporary highlight on the chunk a nav widget (or graph zoom) points to
    var highlighted = null, clearOnScroll = null, settleScroll = null, settleTimer = null;
    function clearHighlight() {
        if (highlighted) { highlighted.classList.remove('chunk-highlight'); highlighted = null; }
        if (clearOnScroll) { window.removeEventListener('scroll', clearOnScroll); clearOnScroll = null; }
        if (settleScroll) { window.removeEventListener('scroll', settleScroll); settleScroll = null; }
        if (settleTimer) { clearTimeout(settleTimer); settleTimer = null; }
    }
    function armClearOnScroll() {
        // The programmatic scroll has settled; clear on the next genuine user scroll
        if (settleScroll) { window.removeEventListener('scroll', settleScroll); settleScroll = null; }
        settleTimer = null;
        clearOnScroll = clearHighlight;
        window.addEventListener('scroll', clearOnScroll);
    }
    // Custom rAF smooth scroll — native 'smooth' silently no-ops over very large
    // distances (these reports can be 100k+ px tall), so animate it ourselves.
    function animateScrollTo(to) {
        var start = window.scrollY;
        var max = document.documentElement.scrollHeight - window.innerHeight;
        to = Math.max(0, Math.min(to, max));
        var dist = to - start;
        if (Math.abs(dist) < 2) { window.scrollTo(0, to); return; }
        var duration = 500, t0 = null;
        function ease(p) { return p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2; }
        function step(ts) {
            if (t0 === null) t0 = ts;
            var p = Math.min(1, (ts - t0) / duration);
            window.scrollTo(0, start + dist * ease(p));
            if (p < 1) requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
    }
    // Center a chunk in the viewport below the sticky sections and highlight it
    function focusChunk(target) {
        if (!target) return;
        clearHighlight();
        var stickyH = bannerH() + nav.offsetHeight;
        var rect = target.getBoundingClientRect();
        var targetAbs = rect.top + window.scrollY;
        var gap = Math.max(12, (window.innerHeight - stickyH - rect.height) / 2);
        var targetPos = Math.max(0, targetAbs - stickyH - gap);
        animateScrollTo(targetPos);
        target.classList.add('chunk-highlight');
        highlighted = target;
        // Wait for the smooth scroll to settle (debounced), not a fixed delay —
        // a long scroll keeps firing events well past any fixed timeout.
        settleScroll = function() {
            if (settleTimer) clearTimeout(settleTimer);
            settleTimer = setTimeout(armClearOnScroll, 150);
        };
        window.addEventListener('scroll', settleScroll);
        // Fallback in case the target is already in view and no scroll fires
        settleTimer = setTimeout(armClearOnScroll, 200);
    }
    window.__focusChunk = focusChunk; // let the latency graph reuse this on zoom
    // Smooth scroll to chunks when clicking widgets
    var widgets = document.querySelectorAll('.chunk-widget');
    widgets.forEach(function(w) {
        w.addEventListener('click', function(e) {
            e.preventDefault();
            focusChunk(document.querySelector(this.getAttribute('href')));
        });
    });
})();
</script>
"""

LATENCY_GRAPH_SCRIPT = """<script>
(function() {
    var dataEl = document.getElementById('latency-data');
    var canvas = document.getElementById('latency-graph');
    if (!dataEl || !canvas) return;
    var points;
    try { points = JSON.parse(dataEl.textContent).points; } catch (e) { return; }
    if (!points || !points.length) return;
    var ctx = canvas.getContext('2d');
    var pane = document.getElementById('graph-pane');
    var tooltip = document.getElementById('latency-tooltip');
    var PAD_L = 52, PAD_R = 14, PAD_T = 14, PAD_B = 26, CSS_H = 260;
    var DAY = 86400;
    var viewStart = 0, viewEnd = DAY;
    var dragStart = null, dragCur = null;
    var cols = [], plotW = 0;

    function lowerBound(t) {
        var lo = 0, hi = points.length;
        while (lo < hi) { var mid = (lo + hi) >> 1; if (points[mid][0] < t) lo = mid + 1; else hi = mid; }
        return lo;
    }
    function fmtTime(sec, withSec) {
        sec = Math.max(0, Math.min(DAY - 1, Math.round(sec)));
        var h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
        var ap = h >= 12 ? 'pm' : 'am';
        var h12 = h % 12 || 12;
        var out = h12 + ':' + (m < 10 ? '0' : '') + m;
        if (withSec) out += ':' + (s < 10 ? '0' : '') + s;
        return out + ' ' + ap;
    }
    function draw() {
        var cssW = canvas.clientWidth;
        if (!cssW) return;
        var dpr = window.devicePixelRatio || 1;
        canvas.width = Math.round(cssW * dpr);
        canvas.height = Math.round(CSS_H * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, cssW, CSS_H);
        plotW = Math.max(10, Math.floor(cssW - PAD_L - PAD_R));
        var plotH = CSS_H - PAD_T - PAD_B;
        var span = viewEnd - viewStart;

        // Aggregate visible points into per-pixel columns (min/max/avg per column)
        cols = new Array(plotW);
        var i0 = lowerBound(viewStart), i1 = lowerBound(viewEnd + 1);
        var yMax = 0;
        for (var i = i0; i < i1; i++) {
            var t = points[i][0], lat = points[i][1];
            var c = Math.min(plotW - 1, Math.floor((t - viewStart) / span * plotW));
            var col = cols[c] || (cols[c] = { t: t, min: Infinity, max: -Infinity, sum: 0, n: 0, to: 0 });
            if (lat === null) { col.to++; }
            else {
                if (lat < col.min) col.min = lat;
                if (lat > col.max) col.max = lat;
                col.sum += lat; col.n++;
                if (lat > yMax) yMax = lat;
            }
        }
        yMax = Math.max(150, Math.ceil(yMax * 1.05 / 50) * 50);
        function xPos(t) { return PAD_L + (t - viewStart) / span * plotW; }
        function yPos(v) { return PAD_T + plotH - (v / yMax) * plotH; }

        // Plot background
        ctx.fillStyle = '#222';
        ctx.fillRect(PAD_L, PAD_T, plotW, plotH);
        ctx.lineWidth = 1;

        // Y grid + labels
        var ySteps = [10, 20, 25, 50, 100, 200, 250, 500, 1000];
        var yStep = ySteps[ySteps.length - 1];
        for (var k = 0; k < ySteps.length; k++) { if (yMax / ySteps[k] <= 6) { yStep = ySteps[k]; break; } }
        ctx.font = '10px monospace';
        ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
        for (var v = 0; v <= yMax; v += yStep) {
            var gy = yPos(v);
            ctx.strokeStyle = '#2e2e2e';
            ctx.beginPath(); ctx.moveTo(PAD_L, gy); ctx.lineTo(PAD_L + plotW, gy); ctx.stroke();
            ctx.fillStyle = '#888'; ctx.fillText(v + ' ms', PAD_L - 6, gy);
        }
        // Threshold reference lines (50 ms medium, 100 ms high)
        [[50, '#ff8c00'], [100, '#ff4444']].forEach(function(ref) {
            if (ref[0] > yMax) return;
            var ry = yPos(ref[0]);
            ctx.strokeStyle = ref[1]; ctx.globalAlpha = 0.45; ctx.setLineDash([4, 4]);
            ctx.beginPath(); ctx.moveTo(PAD_L, ry); ctx.lineTo(PAD_L + plotW, ry); ctx.stroke();
            ctx.setLineDash([]); ctx.globalAlpha = 1;
        });
        // X grid + time-of-day labels
        var xSteps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600];
        var xStep = xSteps[xSteps.length - 1];
        for (var k2 = 0; k2 < xSteps.length; k2++) { if (span / xSteps[k2] <= 12) { xStep = xSteps[k2]; break; } }
        ctx.textAlign = 'center'; ctx.textBaseline = 'top';
        for (var tx = Math.ceil(viewStart / xStep) * xStep; tx <= viewEnd; tx += xStep) {
            var gx = xPos(tx);
            ctx.strokeStyle = '#2e2e2e';
            ctx.beginPath(); ctx.moveTo(gx, PAD_T); ctx.lineTo(gx, PAD_T + plotH); ctx.stroke();
            ctx.fillStyle = '#888'; ctx.fillText(fmtTime(tx, xStep < 60), gx, PAD_T + plotH + 5);
        }
        // Min-max band (vertical line per column) + timeout ticks along the top
        var gapThreshold = Math.max(10, 3 * span / plotW);
        for (var c2 = 0; c2 < plotW; c2++) {
            var col2 = cols[c2];
            if (!col2) continue;
            var bx = PAD_L + c2 + 0.5;
            if (col2.n) {
                ctx.strokeStyle = 'rgba(74,158,255,0.35)';
                ctx.beginPath(); ctx.moveTo(bx, yPos(col2.min) + 1); ctx.lineTo(bx, yPos(col2.max) - 1); ctx.stroke();
            }
            if (col2.to) {
                ctx.strokeStyle = '#ff6666';
                ctx.beginPath(); ctx.moveTo(bx, PAD_T); ctx.lineTo(bx, PAD_T + 8); ctx.stroke();
            }
        }
        // Average line, broken across gaps (e.g. between sessions)
        ctx.strokeStyle = '#4a9eff';
        ctx.beginPath();
        var prevT = null;
        for (var c3 = 0; c3 < plotW; c3++) {
            var col3 = cols[c3];
            if (!col3 || !col3.n) continue;
            var lx = PAD_L + c3 + 0.5, ly = yPos(col3.sum / col3.n);
            if (prevT !== null && col3.t - prevT <= gapThreshold) ctx.lineTo(lx, ly);
            else ctx.moveTo(lx, ly);
            prevT = col3.t;
        }
        ctx.stroke();
        // Drag-selection overlay
        if (dragStart !== null && dragCur !== null) {
            var sx = Math.min(dragStart, dragCur), ex = Math.max(dragStart, dragCur);
            ctx.fillStyle = 'rgba(74,158,255,0.15)';
            ctx.fillRect(sx, PAD_T, ex - sx, plotH);
            ctx.strokeStyle = 'rgba(74,158,255,0.6)';
            ctx.strokeRect(sx + 0.5, PAD_T + 0.5, ex - sx - 1, plotH - 1);
        }
    }
    function eventX(e) {
        return e.clientX - canvas.getBoundingClientRect().left;
    }
    canvas.addEventListener('mousedown', function(e) {
        e.preventDefault();
        dragStart = eventX(e);
        dragCur = null;
    });
    canvas.addEventListener('mousemove', function(e) {
        var x = eventX(e);
        if (dragStart !== null) { dragCur = x; draw(); }
        if (!tooltip) return;
        var c = Math.floor(x - PAD_L);
        var col = (c >= 0 && c < plotW) ? cols[c] : null;
        if (col) {
            var html = fmtTime(col.t, true);
            if (col.n) {
                html += col.n === 1 ? ' \\u2014 ' + col.max + ' ms'
                    : ' \\u2014 min ' + col.min + ' / avg ' + Math.round(col.sum / col.n) + ' / max ' + col.max + ' ms (' + col.n + ' pings)';
            }
            if (col.to) html += ' \\u2014 ' + col.to + ' timeout(s)';
            tooltip.textContent = html;
            tooltip.style.display = 'block';
            var px = x + 14;
            if (px + tooltip.offsetWidth > pane.clientWidth - 10) px = x - tooltip.offsetWidth - 10;
            tooltip.style.left = px + 'px';
            tooltip.style.top = (canvas.offsetTop + 8) + 'px';
        } else {
            tooltip.style.display = 'none';
        }
    });
    canvas.addEventListener('mouseleave', function() {
        if (tooltip) tooltip.style.display = 'none';
        if (dragStart !== null) { dragStart = dragCur = null; draw(); }
    });
    // After a zoom, scroll to + highlight the most prominent chunk now in view
    function focusVisibleChunk() {
        if (!window.__focusChunk) return;
        var events = document.querySelectorAll('.event[data-start-sec]');
        var best = null, bestPeak = -1;
        for (var i = 0; i < events.length; i++) {
            var ev = events[i];
            var s = +ev.getAttribute('data-start-sec'), e = +ev.getAttribute('data-end-sec');
            if (e < viewStart || s > viewEnd) continue; // no overlap with the zoom window
            var peak = +ev.getAttribute('data-peak');
            if (peak > bestPeak) { bestPeak = peak; best = ev; }
        }
        if (best) window.__focusChunk(best);
    }
    canvas.addEventListener('mouseup', function(e) {
        if (dragStart === null) return;
        var endX = eventX(e);
        var sx = Math.min(dragStart, endX), ex = Math.max(dragStart, endX);
        dragStart = dragCur = null;
        if (ex - sx >= 5) {
            var span = viewEnd - viewStart;
            var newStart = viewStart + Math.max(0, sx - PAD_L) / plotW * span;
            var newEnd = viewStart + Math.min(plotW, ex - PAD_L) / plotW * span;
            if (newEnd - newStart < 10) {
                var mid = (newStart + newEnd) / 2;
                newStart = mid - 5; newEnd = mid + 5;
            }
            viewStart = Math.max(0, newStart);
            viewEnd = Math.min(DAY, newEnd);
            draw();
            focusVisibleChunk();
            return;
        }
        draw();
    });
    function resetZoom() { viewStart = 0; viewEnd = DAY; draw(); }
    canvas.addEventListener('dblclick', resetZoom);
    var resetBtn = document.getElementById('latency-graph-reset');
    if (resetBtn) resetBtn.addEventListener('click', resetZoom);
    window.addEventListener('resize', function() {
        if (pane && pane.classList.contains('active')) draw();
    });
    window.__drawLatencyGraph = draw;
    if (pane && pane.classList.contains('active')) draw();
})();
</script>
"""

def finalize_html():
    global total_pings, total_abnormals, total_normals, total_mediums, total_highs
    global sum_normal_latency, sum_medium_latency, sum_high_latency, sum_abnormal_latency
    global timeout_lines
    avg_normal = sum_normal_latency / total_normals if total_normals > 0 else 0
    avg_medium = sum_medium_latency / total_mediums if total_mediums > 0 else 0
    avg_high = sum_high_latency / total_highs if total_highs > 0 else 0
    avg_abnormal = sum_abnormal_latency / total_abnormals if total_abnormals > 0 else 0
    timeout_count = len(timeout_lines)
    abnormality_percentage = (total_abnormals / total_pings * 100) if total_pings > 0 else 0

    # Sticky day-banner (date + stats) at top of page
    primary_date_str = buffer[0][0].strftime("%A, %B %d, %Y") if buffer else 'Ping Log'
    banner_html = (
        f'<div id="day-banner">'
        f'<div class="day-title">{primary_date_str}</div>'
        f'<div class="day-stats">Total Pings: {total_pings} | Abnormalities (&gt;50 ms): {total_abnormals} ({abnormality_percentage:.1f}%) | Timeouts: {timeout_count} | Avg Normal: {avg_normal:.1f} ms | Avg Medium: {avg_medium:.1f} ms | Avg High: {avg_high:.1f} ms | Avg Abnormal: {avg_abnormal:.1f} ms</div>'
        f'</div>\n'
    )
    summary_html = f'<div class="summary"><h3>Session Summary</h3>Total Pings: {total_pings} | Abnormalities (&gt;50 ms): {total_abnormals} ({abnormality_percentage:.1f}%) | Timeouts: {timeout_count} | Average Normal Latency: {avg_normal:.1f} ms | Average Medium Latency: {avg_medium:.1f} ms | Average High Latency: {avg_high:.1f} ms | Average Abnormal Latency: {avg_abnormal:.1f} ms</div>\n'

    html_header = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Ping Monitoring Log</title>
    <style>
        body { font-family: monospace; white-space: pre-wrap; background-color: #1a1a1a; color: #e0e0e0; margin: 0; }
        .summary h3 { margin: 0 0 4px 0; }
        .normal { color: #b0b0b0; }
        .medium { color: #ff8c00; font-weight: bold; }
        .high { color: #ff4444; font-weight: bold; }
        .timeout { color: #ff6666; font-weight: bold; }
        .date-header { font-size: 1.5em; font-weight: bold; color: #4a9eff; margin: 8px 12px 6px 12px; padding: 10px; background-color: #1e2a3a; border-left: 5px solid #4a9eff; }
        .event { border: 1px solid #444; margin: 3px 12px; padding: 10px; background-color: #2a2a2a; transition: border-color 0.2s, box-shadow 0.2s; }
        .event.chunk-highlight { border-color: #4a9eff; box-shadow: 0 0 0 2px #4a9eff; }
        .header { font-weight: bold; background-color: #333; color: #e0e0e0; padding: 5px; }
        .time-range { font-size: 1.2em; color: #ffcc00; font-weight: bold; }
        .summary { margin: 4px 12px; padding: 10px; background-color: #2d3a4a; border: 2px solid #5a7ba7; color: #e0e0e0; }
        .timeout-section { border: 1px solid #664444; margin: 6px 12px; padding: 10px; background-color: #3a2a2a; }
        .timeout-line { color: #ff6666; }
        .chunk-separator { page-break-before: always; }
        .abnormalities-section { border: 2px solid #ff6b6b; margin: 6px 12px; padding: 10px; background-color: #fff5f5; }
        .abnormality-item { margin: 5px 0; padding: 3px; }
        .abnormality-medium { background-color: #fff4e6; padding: 2px 5px; }
        .abnormality-high { background-color: #ffe6e6; padding: 2px 5px; }
        #day-banner { position: sticky; top: 0; z-index: 200; padding: 8px 14px 10px 14px; background-color: #1e2a3a; border-left: 5px solid #4a9eff; white-space: normal; }
        .day-title { font-size: 1.5em; font-weight: bold; color: #4a9eff; }
        .day-stats { font-size: 0.85em; color: #c0c8d0; margin-top: 3px; }
        #chunk-nav { margin: 4px 12px; padding: 0; background-color: #1a1a1a; border: 1px solid #444; z-index: 100; white-space: normal; position: relative; }
        #chunk-nav.sticky { position: fixed; top: 0; left: 12px; right: 12px; margin: 0; box-shadow: 0 2px 8px rgba(0,0,0,0.5); }
        .chunk-nav-sep { width: 1px; height: 1em; background-color: #444; }
        .chunk-nav-footer { padding: 7px 10px; border-top: 1px solid #444; }
        .chunk-nav-home { display: inline-flex; align-items: center; gap: 5px; cursor: pointer; color: #4a9eff; font-size: 0.9em; line-height: 1; transition: color 0.15s; }
        .chunk-nav-home:hover { color: #7ab4ff; }
        .chunk-nav-home-label { font-weight: bold; letter-spacing: 0.03em; }
        .chunk-nav-scroll { overflow-y: auto; scrollbar-width: none; -ms-overflow-style: none; padding: 0 10px 10px 10px; }
        .chunk-nav-scroll::-webkit-scrollbar { display: none; }
        .chunk-nav-grid { display: flex; flex-wrap: wrap; gap: 3px; align-items: flex-end; }
        .chunk-widget { display: flex; flex-direction: column; gap: 1px; padding: 3px 2px; background-color: #2a2a2a; border: 1px solid #444; border-radius: 3px; cursor: pointer; text-decoration: none; transition: border-color 0.15s, background-color 0.15s; width: 14px; align-items: center; }
        .chunk-widget:hover { border-color: #4a9eff; background-color: #333; }
        .chunk-mark-normal { display: block; width: 10px; height: 6px; background-color: #555; border-radius: 1px; }
        .chunk-mark-medium { display: block; width: 10px; height: 6px; background-color: #ff8c00; border-radius: 1px; }
        .chunk-mark-high { display: block; width: 10px; height: 6px; background-color: #ff4444; border-radius: 1px; }
        .chunk-mark-timeout { display: block; width: 10px; height: 6px; background-color: #ff6666; border-radius: 1px; }
        .chunk-nav-fade { position: absolute; bottom: 0; left: 0; right: 0; height: 20px; background: linear-gradient(transparent, #1a1a1a); pointer-events: none; opacity: 0; transition: opacity 0.2s; }
        .chunk-nav-fade.visible { opacity: 1; }
        #chunk-nav-spacer { display: none; }
        #chunk-nav-spacer.active { display: block; }
        .chunk-nav-tabs { display: flex; align-items: flex-end; gap: 0; padding: 8px 10px 0 10px; background-color: #1a1a1a; border-bottom: 1px solid #444; }
        .chunk-nav-tab { background: #242424; border: 1px solid #444; border-bottom: none; color: #888; font-family: monospace; font-size: 0.95em; font-weight: bold; letter-spacing: 0.04em; padding: 5px 16px 4px 16px; cursor: pointer; border-radius: 4px 4px 0 0; margin-right: 4px; position: relative; bottom: -1px; transition: color 0.15s, background 0.15s, border-color 0.15s; }
        .chunk-nav-tab:hover:not(.active) { color: #b0b0b0; background: #2e2e2e; }
        .chunk-nav-tab.active { background: #1a1a1a; border-color: #4a9eff; color: #4a9eff; border-bottom-color: #1a1a1a; }
        .chunk-nav-pane { display: none; }
        .chunk-nav-pane.active { display: block; }
        .chunk-nav-section-label { color: #666; font-size: 0.78em; font-weight: bold; letter-spacing: 0.1em; text-transform: uppercase; padding: 6px 10px 2px 10px; }
        .chunk-nav-empty { color: #666; padding: 0 10px 10px 10px; }
        #graph-pane { padding: 0 10px 10px 10px; position: relative; }
        #latency-graph { width: 100%; height: 260px; display: block; cursor: crosshair; }
        .graph-hint { color: #666; font-size: 0.85em; padding: 2px 0 6px 0; display: flex; align-items: center; gap: 12px; }
        .graph-reset { color: #5a7ba7; cursor: pointer; }
        .graph-reset:hover { color: #7a9bc7; }
        #latency-tooltip { position: absolute; display: none; background-color: #111; border: 1px solid #4a9eff; color: #e0e0e0; padding: 4px 8px; font-size: 0.85em; pointer-events: none; z-index: 10; white-space: nowrap; }
    </style>
</head>
<body>
"""

    # Build the full-day latency graph payload from the input TXT
    try:
        graph_json = _build_latency_graph_payload(TXT_LOG_FILE)
    except Exception as e:
        print(f"Error building latency graph data: {e}")
        graph_json = None

    with open(HTML_OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html_header)
        f.write(banner_html)
        chunk_nav = _build_chunk_nav_html(chunk_metadata_list, graph_json is not None)
        f.write(chunk_nav)
        for eh in event_html_list:
            f.write(eh)
        f.write(summary_html)
        if chunk_nav:
            f.write(CHUNK_NAV_SCRIPT)
        if graph_json:
            f.write('<script id="latency-data" type="application/json">' + graph_json + '</script>\n')
            f.write(LATENCY_GRAPH_SCRIPT)
        f.write('</body>\n</html>')

# Read the TXT file and extract all ping lines
print(f"Reading TXT file: {TXT_LOG_FILE}")
all_ping_lines = []
with open(TXT_LOG_FILE, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        # Skip empty lines and chunk headers
        if not line or line.startswith('=') or line.startswith('---') or line.startswith('Session Summary') or line.startswith('All Individual') or line.startswith('[') or 'Abnormality Chunk:' in line or 'Abnormality:' in line or 'Pings ' in line or 'Timestamp:' in line:
            continue
        # Only process lines that look like ping responses or normalized records.
        if is_ping_record(line):
            all_ping_lines.append(normalize_ping_record(line))

print(f"Found {len(all_ping_lines)} ping lines")

# Initialize globals
# For reprocessing, we don't need maxlen since we have the full file
# Use a list instead of deque to avoid index invalidation issues
buffer = []
abnormalities = []
current_chunk_abnormalities = []
current_chunk_start = None
last_abnormal_time = None
consecutive_normal_count = 0  # Track consecutive normal pings
last_normal_indices = []  # Track recent normal ping indices (for trimming)
last_chunk_end_idx = -1  # Track where the last finalized chunk ended (to prevent overlap)
total_pings = 0
total_abnormals = 0
total_normals = 0
total_mediums = 0
total_highs = 0
sum_normal_latency = 0.0
sum_medium_latency = 0.0
sum_high_latency = 0.0
sum_abnormal_latency = 0.0
timeout_lines = []
event_html_list = []
chunk_metadata_list = []
pending_finalization = False
_first_ts = parse_timestamp(all_ping_lines[0]) if all_ping_lines else None
last_date_header = _first_ts.date() if _first_ts else None  # Pre-set to file's day; header only needed for day crossings

# Process each ping line
print("Processing ping lines...")

for line in all_ping_lines:
    # Parse timestamp
    timestamp = parse_timestamp(line)
    if timestamp is None:
        continue
    
    total_pings += 1
    
    # Check for timeout
    if is_timeout(line):
        timeout_lines.append(line)
        buffer.append((timestamp, None, line))
        current_idx = len(buffer) - 1
        # Reset consecutive normal count (timeout is abnormality)
        consecutive_normal_count = 0
        last_normal_indices = []
        # Check for new chunk - start new chunk if no current chunk exists
        # (Time-based logic removed - chunks are now only split by 10+ consecutive normal pings)
        if current_chunk_start is None:
            current_chunk_start = current_idx
        pending_finalization = True
        last_abnormal_time = timestamp
        continue
    
    # Parse latency
    latency = parse_latency(line)
    if latency is None:
        continue
    
    # Update stats
    if latency < 50:
        total_normals += 1
        sum_normal_latency += latency
    elif 50 <= latency <= 100:
        total_mediums += 1
        sum_medium_latency += latency
        total_abnormals += 1
        sum_abnormal_latency += latency
    else:  # >100
        total_highs += 1
        sum_high_latency += latency
        total_abnormals += 1
        sum_abnormal_latency += latency
    
    # Buffer append
    buffer.append((timestamp, latency, line))
    current_idx = len(buffer) - 1
    
    # Handle normal vs abnormal pings
    if latency < SPIKE_THRESHOLD:  # Normal ping
        # Track consecutive normal pings
        consecutive_normal_count += 1
        last_normal_indices.append(current_idx)
        # Keep only last NORMAL_PING_THRESHOLD indices
        if len(last_normal_indices) > NORMAL_PING_THRESHOLD:
            last_normal_indices.pop(0)
        
        # Check if we should finalize chunk due to normal ping gap
        if pending_finalization and consecutive_normal_count >= NORMAL_PING_THRESHOLD:
            # Pass the current last_normal_indices so we can keep the last 5
            # Make a copy BEFORE adding current_idx (which we just added)
            finalize_current_chunk(end_due_to_normal_gap=True, last_normal_indices_at_end=last_normal_indices.copy())
            consecutive_normal_count = 0
            last_normal_indices = []
    else:  # Abnormal ping (>=50ms)
        # Reset consecutive normal count
        consecutive_normal_count = 0
        last_normal_indices = []
        
        # Treat ALL latencies >=50ms as abnormalities that trigger chunks (no upper limit)
        abnormalities.append(current_idx)
        current_chunk_abnormalities.append(current_idx)

        # Check for new chunk - start new chunk if no current chunk exists
        # (Time-based logic removed - chunks are now only split by 10+ consecutive normal pings)
        if current_chunk_start is None:
            current_chunk_start = current_idx
        pending_finalization = True
        last_abnormal_time = timestamp

# Finalize any pending chunk
if pending_finalization or current_chunk_start is not None:
    finalize_current_chunk()
# Reset tracking variables
consecutive_normal_count = 0
last_normal_indices = []

# Generate HTML
print("Generating HTML...")
finalize_html()

print(f"Done! Output written to: {HTML_OUTPUT_FILE}")
print(f"Total abnormalities created: {len(event_html_list)}")
print(f"Total pings processed: {total_pings}")
print(f"Total abnormalities (>=50ms): {total_abnormals}")

