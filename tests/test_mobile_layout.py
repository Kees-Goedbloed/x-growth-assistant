#!/usr/bin/env python3
"""375px layout checks against fixture builds (never repo data/)."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import repo_guard  # noqa: E402,F401

PROBE = r"""
<script>
(function(){
  function overlap(a,b){
    return a && b && a.bottom > b.top + 1 && a.top < b.bottom - 1
      && a.right > b.left + 1 && a.left < b.right - 1;
  }
  function txt(n){ return (n.textContent || '').replace(/\s+/g, ' ').trim(); }
  function openNamedFold(root, re){
    const folds=Array.from((root||document).querySelectorAll('details.fold'));
    const fold=folds.find(d=>re.test((d.querySelector('summary')||{}).textContent||''));
    if(fold) fold.open=true;
    return fold;
  }
  function chartHost(root){
    return Array.from((root||document).querySelectorAll('.echart')).filter(el=>el.clientHeight>20);
  }
  function yTickGap(host){
    if(!host) return null;
    const ticks=Array.from(host.querySelectorAll('text')).filter(t=>{
      const b=t.getBoundingClientRect();
      const hb=host.getBoundingClientRect();
      return b.width>1 && b.height>1 && b.left < hb.left + 80;
    });
    const boxes=ticks.map(t=>t.getBoundingClientRect()).sort((a,b)=>a.top-b.top);
    if(boxes.length<2) return {n:boxes.length, minGap:null, h:host.getBoundingClientRect().height};
    let min=Infinity;
    for(let i=1;i<boxes.length;i++) min=Math.min(min, boxes[i].top-boxes[i-1].bottom);
    return {n:boxes.length, minGap:min, h:host.getBoundingClientRect().height};
  }
  function minYGap(hosts){
    let min=Infinity, n=0;
    hosts.forEach(host=>{
      const g=yTickGap(host);
      if(g && g.minGap!=null){ min=Math.min(min, g.minGap); n++; }
    });
    return {minGap:isFinite(min)?min:null, n};
  }
  function plotSvgs(root){
    return chartHost(root).filter(el=>!el.classList.contains('echart-spark') && !el.classList.contains('echart-heat') && !el.classList.contains('echart-hbar'));
  }
  function miniLabelClip(){
    const root=document.querySelector('#s8');
    if(!root) return {clipped:[]};
    const hosts=Array.from(root.querySelectorAll('.echart-hbar'));
    const clipped=[];
    hosts.forEach(host=>{
      const sb=host.getBoundingClientRect();
      Array.from(host.querySelectorAll('text')).forEach(t=>{
        const label=txt(t);
        if(/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)$/.test(label)) return;
        const b=t.getBoundingClientRect();
        if(b.width<1 || b.height<1) return;
        if(b.left < sb.left - 2) clipped.push('L:'+label);
        if(b.top < sb.top - 2) clipped.push('T:'+label);
      });
    });
    return {clipped, svgCount:hosts.length};
  }
  function overlapBox(a,b){
    return a && b && a.bottom > b.top + 1 && a.top < b.bottom - 1
      && a.right > b.left + 1 && a.left < b.right - 1;
  }
  function heatFit(){
    const hosts=Array.from(document.querySelectorAll('.hmwrap .echart'));
    const clipped=[];
    let captionOverlap=false;
    hosts.forEach(host=>{
      const sb=host.getBoundingClientRect();
      const texts=Array.from(host.querySelectorAll('text')).filter(t=>{
        const b=t.getBoundingClientRect();
        return b.width>1 && b.height>1;
      });
      texts.forEach(t=>{
        const b=t.getBoundingClientRect();
        const label=txt(t);
        if(b.left < sb.left - 2) clipped.push('L:'+label);
        if(b.top < sb.top - 2) clipped.push('T:'+label);
        if(b.right > sb.right + 2) clipped.push('R:'+label);
      });
      const cap=texts.find(t=>/^hour →$/.test(txt(t)));
      if(cap){
        const cb=cap.getBoundingClientRect();
        texts.forEach(t=>{
          if(t===cap) return;
          if(overlapBox(cb, t.getBoundingClientRect())) captionOverlap=true;
        });
      }
    });
    return {clipped, captionOverlap, svgCount:hosts.length};
  }
  function write(report){
    let el = document.getElementById('layout-report');
    if (!el) {
      el = document.createElement('pre');
      el.id = 'layout-report';
      document.body.appendChild(el);
    }
    el.textContent = JSON.stringify(report);
  }
  function measure(){
    const doc = document.documentElement;
    const sticky = document.querySelector('#filterbar');
    const kpi = document.querySelector('.kpi');
    const title = document.querySelector('main h3');
    const notes = Array.from(document.querySelectorAll('#s6 .txt .note, #s6 .top-meta'));
    const truncated = notes.filter(n => n.scrollWidth > n.clientWidth + 1).map(txt);
    const nums = Array.from(document.querySelectorAll('#s6 .mini-top td.num, #s6 .mini-top td.r'))
      .filter(n => n.offsetParent !== null);
    const truncatedNums = nums.filter(n => n.scrollWidth > n.clientWidth + 1).map(txt);
    const metrics = Array.from(document.querySelectorAll('#s6 .top-metrics'))
      .filter(n => n.getClientRects().length);
    const wrappedMetrics = metrics.filter(n => n.getClientRects().length > 1).map(txt);
    const unknownMeta = notes.filter(n => /\bunknown\b/i.test(n.textContent || '')).map(txt);
    window.scrollTo(0, 0);
    const restBar = sticky.getBoundingClientRect();
    const restKpi = kpi ? kpi.getBoundingClientRect() : null;
    const restTitle = title ? title.getBoundingClientRect() : null;
    openNamedFold(document.querySelector('#s4'), /conversion/i);
    openNamedFold(document.querySelector('#s8'), /analysis/i);
    openNamedFold(document.querySelector('#s6'), /best time to post/i);
    openNamedFold(document.querySelector('#s8'), /best reply time/i);
    const y = Math.min(500, Math.max(0, doc.scrollHeight - doc.clientHeight));
    window.scrollTo(0, y);
    setTimeout(function(){
      if (typeof fitAxisFonts === 'function') fitAxisFonts();
      const scrolled = sticky.getBoundingClientRect();
      const mains = plotSvgs().filter(s=>!s.closest('details.fold'));
      const folds = plotSvgs().filter(s=>s.closest('#s4 details.fold'));
      const mainY = minYGap(mains);
      const foldY = minYGap(folds);
      const mini = miniLabelClip();
      const heat = heatFit();
      write({
        clientWidth: doc.clientWidth,
        innerWidth: window.innerWidth,
        scrollWidth: Math.max(doc.scrollWidth, document.body.scrollWidth),
        stickyHeight: Math.round(restBar.height),
        stickyPosition: getComputedStyle(sticky).position,
        stickyTopAfterScroll: Math.round(scrolled.top),
        stickyHeightAfterScroll: Math.round(scrolled.height),
        scrolledY: window.scrollY,
        kpiCoveredAtRest: overlap(restBar, restKpi),
        titleCoveredAtRest: overlap(restBar, restTitle),
        hasCustomToggle: !!document.querySelector('#filterbar details.bar-custom'),
        customSummaryVisible: (function(){
          const s=document.querySelector('#filterbar details.bar-custom > summary');
          if(!s) return false;
          const cs=getComputedStyle(s);
          return cs.display!=='none' && s.getClientRects().length>0;
        })(),
        dateInputsPresent: !!document.getElementById('fs') && !!document.getElementById('fe'),
        presetOverflow: (function(){
          const p=document.querySelector('.bar-presets');
          return p ? Math.max(0, p.scrollWidth - p.clientWidth) : 99;
        })(),
        allCoveredByCustom: (function(){
          const all=document.querySelector('#filterbar button[data-p="all"]');
          const custom=document.querySelector('#filterbar details.bar-custom > summary')
            || document.querySelector('#filterbar details.bar-custom');
          if(!all||!custom) return true;
          return overlap(all.getBoundingClientRect(), custom.getBoundingClientRect());
        })(),
        allFullyInBar: (function(){
          const all=document.querySelector('#filterbar button[data-p="all"]');
          const bar=document.querySelector('#filterbar');
          if(!all||!bar) return false;
          const a=all.getBoundingClientRect(), b=bar.getBoundingClientRect();
          return a.left >= b.left - 1 && a.right <= b.right + 1;
        })(),
        chipsInBar: (function(){
          const bar=document.querySelector('#filterbar');
          if(!bar) return false;
          const b=bar.getBoundingClientRect();
          const els=Array.from(document.querySelectorAll('#filterbar button[data-p], #filterbar details.bar-custom > summary'));
          return els.every(el=>{
            const a=el.getBoundingClientRect();
            return a.width>2 && a.left >= b.left - 1 && a.right <= b.right + 1;
          });
        })(),
        titleVisible: (function(){
          const h=document.querySelector('#dash-title');
          const bar=document.querySelector('#filterbar');
          if(!h||!bar) return false;
          const a=h.getBoundingClientRect(), b=bar.getBoundingClientRect();
          const cs=getComputedStyle(h);
          return a.width>2 && a.height>2 && a.right <= b.right + 1 && a.left >= b.left - 1
            && cs.textOverflow!=='ellipsis' && h.scrollWidth <= h.clientWidth + 2;
        })(),
        chipLabels: Array.from(document.querySelectorAll('#filterbar button[data-p], #filterbar details.bar-custom > summary')).map(el=>((el.innerText||el.textContent||'').replace(/\s+/g,' ').trim())),
        metColVisible: Array.from(document.querySelectorAll('#s6 .mini-top td.met')).filter(n=>n.getClientRects().length>0).length,
        topMetricDupes: (function(){
          const rows=Array.from(document.querySelectorAll('#s6 .mini-top tr'));
          return rows.filter(tr=>{
            const col=tr.querySelector('td.met');
            const sub=tr.querySelector('.top-metrics');
            const colOn=col&&col.getClientRects().length>0;
            const subOn=sub&&sub.getClientRects().length>0;
            return colOn && subOn;
          }).length;
        })(),
        noteCount: notes.length,
        truncatedNotes: truncated,
        truncatedNums: truncatedNums,
        wrappedMetrics: wrappedMetrics,
        unknownMeta: unknownMeta,
        ariaPressed: Array.from(document.querySelectorAll('#filterbar button[data-p]')).map(b => ({
          p: b.getAttribute('data-p'),
          pressed: b.getAttribute('aria-pressed'),
          on: b.classList.contains('on')
        })),
        axTickH: (function(){
          const t=document.querySelector('.echart text');
          if(!t) return 0;
          const b=t.getBoundingClientRect();
          return b.height;
        })(),
        outLabH: (function(){
          const t=document.querySelector('.echart text');
          if(!t) return null;
          return t.getBoundingClientRect().height;
        })(),
        minMainYGap: mainY.minGap,
        mainYCharts: mainY.n,
        minFoldYGap: foldY.minGap,
        foldYCharts: foldY.n,
        miniLabelClipped: mini.clipped,
        miniBarCount: mini.svgCount,
        heatLabelClipped: heat.clipped,
        heatCaptionOverlap: heat.captionOverlap,
        heatCount: heat.svgCount,
      });
    }, 220);
  }
  function go(){ setTimeout(measure, 80); }
  if (document.readyState === 'complete') go();
  else window.addEventListener('load', go);
})();
</script>
"""


def _chrome_args(chrome, url, window="375,812"):
    return [
        chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
        "--disable-dev-shm-usage", "--hide-scrollbars",
        "--force-device-scale-factor=1", f"--window-size={window}",
        "--virtual-time-budget=12000", "--dump-dom", url,
    ]


def _chrome_bin():
    for name in ("google-chrome-stable", "google-chrome", "chromium-browser", "chromium"):
        p = shutil.which(name)
        if p:
            return p
    return None


def _ensure_fixtures():
    script = ROOT / "test-fixtures" / "make_fixtures.py"
    subprocess.run([sys.executable, str(script)], cwd=ROOT, check=True, capture_output=True, text=True)
    return ROOT / "test-fixtures" / "data"


def _build(data: Path, dest: Path, mode: str):
    r = subprocess.run(
        [sys.executable, str(ROOT / "build.py"),
         "--data", str(data), "--mode", mode, "--out", str(dest),
         "--today", "2026-09-25"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise AssertionError(f"build {mode} failed\n{r.stdout}\n{r.stderr}")


def _inject_probe(html: str) -> str:
    if "</body>" in html:
        return html.replace("</body>", PROBE + "</body>", 1)
    return html + PROBE


def _serve(directory: Path):
    hits = []

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, fmt, *args):
            hits.append(fmt % args if args else str(fmt))

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.hits = hits
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


def _copy_sibling_assets(html_path: Path, dest: Path) -> None:
    src = html_path.parent / "assets"
    if src.is_dir():
        shutil.copytree(src, dest / "assets", dirs_exist_ok=True)


def _chrome_report_probe(chrome: str, html_path: Path, probe: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="xdash-chrome-") as td:
        td = Path(td)
        page = td / "page.html"
        wrap = td / "wrap.html"
        html = html_path.read_text(encoding="utf-8")
        if "</body>" in html:
            html = html.replace("</body>", probe + "</body>", 1)
        else:
            html += probe
        page.write_text(html, encoding="utf-8")
        _copy_sibling_assets(html_path, td)
        wrap.write_text(
            """<!doctype html><meta charset="utf-8">
<iframe id="f" src="page.html" width="375" height="812"
  style="border:0;width:375px;height:812px"></iframe>
<script>
(function(){
  const f=document.getElementById('f');
  function pick(){
    try{
      const el=f.contentDocument && f.contentDocument.getElementById('layout-report');
      if(el && el.textContent){
        const out=document.createElement('pre');
        out.id='layout-report';
        out.textContent=el.textContent;
        document.documentElement.replaceChildren(out);
        return;
      }
    }catch(e){}
    setTimeout(pick,40);
  }
  f.addEventListener('load', function(){ setTimeout(pick,80); });
  setTimeout(pick,200);
})();
</script>
""",
            encoding="utf-8",
        )
        httpd = _serve(td)
        try:
            url = f"http://127.0.0.1:{httpd.server_address[1]}/wrap.html"
            for _ in range(50):
                try:
                    urllib.request.urlopen(url, timeout=0.2).read()
                    break
                except Exception:
                    time.sleep(0.02)
            else:
                raise AssertionError(f"layout server never became ready at {url}")
            r = subprocess.run(
                _chrome_args(chrome, url, "375,812"),
                capture_output=True, text=True, timeout=60,
            )
        finally:
            httpd.shutdown()
            httpd.server_close()
        blob = r.stdout or ""
        if 'id="layout-report"' not in blob:
            raise AssertionError(f"chrome dump missing layout-report\n{blob[-500:]}")
        part = blob.split('id="layout-report"', 1)[1]
        text = part.split(">", 1)[1].split("</pre>", 1)[0]
        text = (text.replace("&quot;", '"').replace("&#34;", '"')
                .replace("&amp;", "&").strip())
        return json.loads(text)


def _chrome_report(chrome: str, html_path: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="xdash-chrome-") as td:
        td = Path(td)
        page = td / "page.html"
        wrap = td / "wrap.html"
        page.write_text(_inject_probe(html_path.read_text(encoding="utf-8")), encoding="utf-8")
        _copy_sibling_assets(html_path, td)
        wrap.write_text(
            """<!doctype html><meta charset="utf-8">
<iframe id="f" src="page.html" width="375" height="812"
  style="border:0;width:375px;height:812px"></iframe>
<script>
(function(){
  const f=document.getElementById('f');
  function pick(){
    try{
      const el=f.contentDocument && f.contentDocument.getElementById('layout-report');
      if(el && el.textContent){
        const out=document.createElement('pre');
        out.id='layout-report';
        out.textContent=el.textContent;
        document.documentElement.replaceChildren(out);
        return;
      }
    }catch(e){}
    setTimeout(pick,40);
  }
  f.addEventListener('load', function(){ setTimeout(pick,80); });
  setTimeout(pick,200);
})();
</script>
""",
            encoding="utf-8",
        )
        httpd = _serve(td)
        try:
            url = f"http://127.0.0.1:{httpd.server_address[1]}/wrap.html"
            for _ in range(50):
                try:
                    urllib.request.urlopen(url, timeout=0.2).read()
                    break
                except Exception:
                    time.sleep(0.02)
            else:
                raise AssertionError(f"layout server never became ready at {url} files={list(td.iterdir())}")
            r = subprocess.run(
                _chrome_args(chrome, url, "375,812"),
                capture_output=True, text=True, timeout=60,
            )
        finally:
            hits = list(getattr(httpd, "hits", []))
            httpd.shutdown()
            httpd.server_close()
        blob = r.stdout or ""
        if 'id="layout-report"' not in blob:
            raise AssertionError(
                f"chrome dump missing layout-report (exit {r.returncode})\n"
                f"stderr={r.stderr[-1500:]}\nstdout_tail={blob[-500:]}\n"
                f"server_hits={hits}\nfiles={list(td.iterdir())}"
            )
        part = blob.split('id="layout-report"', 1)[1]
        text = part.split(">", 1)[1].split("</pre>", 1)[0]
        text = (text.replace("&quot;", '"').replace("&#34;", '"')
                .replace("&amp;", "&").strip())
        return json.loads(text)


@unittest.skipUnless(_chrome_bin(), "no system Chrome/Chromium for 375px layout check")
class TestMobileChromeLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chrome = _chrome_bin()
        cls.data = _ensure_fixtures()
        cls.td = tempfile.TemporaryDirectory(prefix="xdash-mobile-")
        out = Path(cls.td.name)
        cls.private = out / "index.private.html"
        cls.public = out / "index.public.html"
        _build(cls.data, cls.private, "private")
        _build(cls.data, cls.public, "public")

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    def _check(self, path: Path, mode: str):
        report = _chrome_report(self.chrome, path)
        self.assertEqual(
            report.get("innerWidth") or report["clientWidth"], 375,
            f"{mode}: viewport is not 375px {report}",
        )
        self.assertEqual(
            report["scrollWidth"], report["clientWidth"],
            f"{mode}: horizontal overflow at 375px {report}",
        )
        self.assertLessEqual(
            report["stickyHeight"], 56,
            f"{mode}: sticky header taller than 56px {report}",
        )
        self.assertEqual(
            report.get("stickyPosition"), "sticky",
            f"{mode}: period bar is not sticky {report}",
        )
        if report.get("scrolledY", 0) > 40:
            self.assertLessEqual(
                abs(report.get("stickyTopAfterScroll", 99)), 2,
                f"{mode}: period bar did not stay pinned {report}",
            )
            self.assertLessEqual(
                report.get("stickyHeightAfterScroll", 99), 56,
                f"{mode}: pinned header taller than 56px {report}",
            )
        self.assertFalse(
            report.get("kpiCoveredAtRest"),
            f"{mode}: period bar covers KPI tiles at rest {report}",
        )
        self.assertFalse(
            report.get("titleCoveredAtRest"),
            f"{mode}: period bar covers a chart title at rest {report}",
        )
        self.assertTrue(
            report.get("hasCustomToggle"),
            f"{mode}: custom dates are not behind a toggle {report}",
        )
        self.assertTrue(
            report.get("customSummaryVisible"),
            f"{mode}: Custom toggle is hidden {report}",
        )
        self.assertTrue(
            report.get("dateInputsPresent"),
            f"{mode}: custom date inputs missing {report}",
        )
        self.assertEqual(
            report.get("presetOverflow", 99), 0,
            f"{mode}: period chips still scroll sideways {report}",
        )
        self.assertTrue(
            report.get("chipsInBar"),
            f"{mode}: a period chip sits outside the header {report}",
        )
        self.assertTrue(
            report.get("titleVisible"),
            f"{mode}: header title is truncated or clipped {report}",
        )
        labels = " ".join(report.get("chipLabels") or [])
        self.assertRegex(labels, r"\b7d\b", f"{mode}: missing 7d chip {report}")
        self.assertRegex(labels, r"\b30d\b", f"{mode}: missing 30d chip {report}")
        self.assertRegex(labels, r"\b90d\b", f"{mode}: missing 90d chip {report}")
        self.assertEqual(
            report.get("metColVisible") or 0, 0,
            f"{mode}: metric column still visible at 375 {report}",
        )
        self.assertEqual(
            report.get("topMetricDupes") or 0, 0,
            f"{mode}: top-5 shows the same number twice {report}",
        )
        self.assertGreater(report["noteCount"], 0, f"{mode}: no top-posts meta notes {report}")
        self.assertEqual(
            report["truncatedNotes"], [],
            f"{mode}: top-posts meta truncated {report}",
        )
        self.assertEqual(
            report.get("truncatedNums") or [], [],
            f"{mode}: top-posts numeric cells truncated {report}",
        )
        self.assertEqual(
            report.get("wrappedMetrics") or [], [],
            f"{mode}: top-posts metrics wrapped {report}",
        )
        self.assertEqual(
            report.get("unknownMeta") or [], [],
            f"{mode}: unknown media line still shown {report}",
        )
        pressed = [x for x in report["ariaPressed"] if x["pressed"] == "true"]
        self.assertEqual(len(pressed), 1, f"{mode}: expected one aria-pressed period {report}")
        self.assertEqual(pressed[0]["p"], "30")
        self.assertGreaterEqual(
            report.get("axTickH") or 0, 10,
            f"{mode}: visible axis tick is under 10px on screen {report}",
        )
        if report.get("outLabH") is not None:
            self.assertGreaterEqual(
                report["outLabH"], 10,
                f"{mode}: outlier label is under 10px on screen {report}",
            )
        self.assertGreaterEqual(
            report.get("mainYCharts") or 0, 1,
            f"{mode}: no main y-axis charts to measure {report}",
        )
        self.assertEqual(
            report.get("foldYCharts") or 0, 0,
            f"{mode}: unexpected fold charts in the main view {report}",
        )
        self.assertEqual(
            report.get("miniLabelClipped") or [], [],
            f"{mode}: What works best row labels clipped {report}",
        )
        self.assertGreaterEqual(
            report.get("heatCount") or 0, 1,
            f"{mode}: no heatmap to measure {report}",
        )
        self.assertEqual(
            report.get("heatLabelClipped") or [], [],
            f"{mode}: heatmap labels clipped at 375 {report}",
        )
        self.assertFalse(
            report.get("heatCaptionOverlap"),
            f"{mode}: heatmap hour caption overlaps hour labels {report}",
        )

    def test_private_375(self):
        self._check(self.private, "private")

    def test_public_375(self):
        self._check(self.public, "public")

    def test_more_menu_closes_after_option_and_outside(self):
        probe = r"""
<script>
(function(){
  function write(report){
    let el=document.getElementById('layout-report');
    if(!el){el=document.createElement('pre');el.id='layout-report';document.body.appendChild(el);}
    el.textContent=JSON.stringify(report);
  }
  function go(){
    const more=document.getElementById('more-btn');
    const tools=document.getElementById('bar-tools');
    const theme=document.getElementById('theme-toggle');
    const main=document.querySelector('main');
    const out={hasMore:!!more,hasTools:!!tools};
    if(!more||!tools){write(out);return;}
    more.click();
    out.opened=tools.classList.contains('open');
    const hint=document.getElementById('cmp-hint');
    const shown=document.getElementById('shown-range');
    out.hintText=hint?hint.textContent:'';
    out.hintOn=!!(hint&&hint.classList.contains('is-on'));
    out.hintVisible=!!(hint&&hint.classList.contains('is-on')&&hint.getClientRects().length>0);
    out.shownText=shown?shown.textContent:'';
    if(theme){
      theme.click();
      out.closedAfterTheme=!document.getElementById('bar-tools').classList.contains('open');
    }
    const more2=document.getElementById('more-btn');
    const tools2=document.getElementById('bar-tools');
    if(more2&&tools2){
      more2.click();
      out.reopened=tools2.classList.contains('open');
      document.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,clientX:8,clientY:400}));
      out.closedAfterOutside=!document.getElementById('bar-tools').classList.contains('open');
    }
    write(out);
  }
  if(document.readyState==='complete') setTimeout(go,120);
  else window.addEventListener('load', function(){ setTimeout(go,120); });
})();
</script>
"""
        report = _chrome_report_probe(self.chrome, self.private, probe)
        self.assertTrue(report.get("hasMore"), report)
        self.assertTrue(report.get("opened"), report)
        self.assertIn("Not enough history", report.get("hintText") or "", report)
        self.assertTrue(report.get("hintOn"), report)
        self.assertTrue(report.get("hintVisible"), report)
        self.assertTrue(report.get("closedAfterTheme"), report)
        self.assertTrue(report.get("reopened"), report)
        self.assertTrue(report.get("closedAfterOutside"), report)


class TestChromeFlags(unittest.TestCase):
    def test_headless_chrome_disables_dev_shm(self):
        src = Path(__file__).read_text(encoding="utf-8")
        self.assertIn("--disable-dev-shm-usage", src)
        self.assertIn("disable-dev-shm-usage", "".join(_chrome_args("chrome", "http://x")))


DESKTOP_PROBE = r"""
<script>
(function(){
  function write(report){
    let el = document.getElementById('layout-report');
    if (!el) {
      el = document.createElement('pre');
      el.id = 'layout-report';
      document.body.appendChild(el);
    }
    el.textContent = JSON.stringify(report);
  }
  function tickH(el){
    if(!el) return 0;
    const b=el.getBoundingClientRect();
    return b.height;
  }
  function yTickGap(host){
    if(!host) return null;
    const ticks=Array.from(host.querySelectorAll('text')).filter(t=>{
      const b=t.getBoundingClientRect();
      const hb=host.getBoundingClientRect();
      return b.width>1 && b.height>1 && b.left < hb.left + 80;
    });
    const boxes=ticks.map(t=>t.getBoundingClientRect()).sort((a,b)=>a.top-b.top);
    if(boxes.length<2) return {n:boxes.length, minGap:null};
    let min=Infinity;
    for(let i=1;i<boxes.length;i++) min=Math.min(min, boxes[i].top-boxes[i-1].bottom);
    return {n:boxes.length, minGap:min};
  }
  function minYGap(hosts){
    let min=Infinity, n=0;
    hosts.forEach(host=>{
      const g=yTickGap(host);
      if(g && g.minGap!=null){ min=Math.min(min, g.minGap); n++; }
    });
    return {minGap:isFinite(min)?min:null, n};
  }
  function plotSvgs(root){
    return Array.from((root||document).querySelectorAll('.echart'))
      .filter(el=>el.clientHeight>20 && !el.classList.contains('echart-spark') && !el.classList.contains('echart-heat') && !el.classList.contains('echart-hbar'));
  }
  function openConvFold(){
    const folds=Array.from(document.querySelectorAll('#s4 details.fold'));
    const fold=folds.find(d=>/conversion/i.test((d.querySelector('summary')||{}).textContent||''))||folds[0];
    if(fold) fold.open=true;
    return fold;
  }
  function convTick(){
    const h3=Array.from(document.querySelectorAll('#s4 h3')).find(h=>/Conversion per week/.test(h.textContent||''));
    const host=h3 && h3.parentElement && h3.parentElement.querySelector('.echart');
    return host && host.querySelector('text');
  }
  function txt(n){ return (n.textContent || '').replace(/\s+/g, ' ').trim(); }
  function overlapBox(a,b){
    return a && b && a.bottom > b.top + 1 && a.top < b.bottom - 1
      && a.right > b.left + 1 && a.left < b.right - 1;
  }
  function openNamedFold(root, re){
    const folds=Array.from((root||document).querySelectorAll('details.fold'));
    const fold=folds.find(d=>re.test((d.querySelector('summary')||{}).textContent||''));
    if(fold) fold.open=true;
    return fold;
  }
  function heatCaptionHits(){
    const svgs=Array.from(document.querySelectorAll('.hmwrap .echart'));
    const hits=[];
    svgs.forEach((svg,si)=>{
      const texts=Array.from(svg.querySelectorAll('text')).filter(t=>{
        const b=t.getBoundingClientRect();
        return b.width>1 && b.height>1;
      });
      const caps=texts.filter(t=>/^hour →$/.test(txt(t)));
      caps.forEach(cap=>{
        const cb=cap.getBoundingClientRect();
        texts.forEach(t=>{
          if(t===cap) return;
          if(overlapBox(cb, t.getBoundingClientRect())){
            hits.push({svg:si, cap:txt(cap), label:txt(t)});
          }
        });
      });
    });
    return {heatCount: svgs.length, captionHits: hits};
  }
  function measure(){
    const s=document.querySelector('#filterbar details.bar-custom > summary');
    const cs=s?getComputedStyle(s):null;
    const det=document.querySelector('#filterbar details.bar-custom');
    const thirty=document.querySelector('#filterbar button[data-p="30"]');
    if(det) det.open=true;
    openConvFold();
    openNamedFold(document.querySelector('#s6'), /best time to post/i);
    openNamedFold(document.querySelector('#s8'), /best reply time/i);
    setTimeout(function(){
      if (typeof fitAxisFonts === 'function') fitAxisFonts();
      const vis=document.querySelector('.echart text');
      const foldTick=convTick();
      const out=document.querySelector('.echart text');
      const mains=plotSvgs().filter(s=>!s.closest('details.fold'));
      const folds=plotSvgs().filter(s=>s.closest('#s4 details.fold'));
      const mainY=minYGap(mains);
      const foldY=minYGap(folds);
      const heat=heatCaptionHits();
      write({
        innerWidth: window.innerWidth,
        customSummaryVisible: !!(s && cs && cs.display!=='none' && s.getClientRects().length>0),
        dateInputsPresent: !!document.getElementById('fs') && !!document.getElementById('fe'),
        customOpen: !!(det && det.open),
        customHighlighted: !!(det && (det.open || det.classList.contains('on'))),
        thirtyOnWhileCustomOpen: !!(thirty && thirty.classList.contains('on')),
        thirtyPressedWhileCustomOpen: thirty?thirty.getAttribute('aria-pressed'):null,
        visTickH: tickH(vis),
        foldTickH: tickH(foldTick),
        outLabH: out?tickH(out):null,
        minMainYGap: mainY.minGap,
        mainYCharts: mainY.n,
        minFoldYGap: foldY.minGap,
        foldYCharts: foldY.n,
        heatCount: heat.heatCount,
        heatCaptionHits: heat.captionHits,
      });
    }, 200);
  }
  function go(){ setTimeout(measure, 120); }
  if (document.readyState === 'complete') go();
  else window.addEventListener('load', go);
})();
</script>
"""


@unittest.skipUnless(_chrome_bin(), "no system Chrome/Chromium for desktop layout check")
class TestDesktopChromeLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chrome = _chrome_bin()
        cls.data = _ensure_fixtures()
        cls.td = tempfile.TemporaryDirectory(prefix="xdash-desktop-")
        cls.private = Path(cls.td.name) / "index.private.html"
        _build(cls.data, cls.private, "private")

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    def test_custom_dates_reachable_and_axis_readable(self):
        with tempfile.TemporaryDirectory(prefix="xdash-chrome-d-") as td:
            td = Path(td)
            page = td / "page.html"
            html = self.private.read_text(encoding="utf-8")
            if "</body>" in html:
                html = html.replace("</body>", DESKTOP_PROBE + "</body>", 1)
            else:
                html += DESKTOP_PROBE
            page.write_text(html, encoding="utf-8")
            _copy_sibling_assets(self.private, td)
            httpd = _serve(td)
            try:
                url = f"http://127.0.0.1:{httpd.server_address[1]}/page.html"
                for _ in range(50):
                    try:
                        urllib.request.urlopen(url, timeout=0.2).read()
                        break
                    except Exception:
                        time.sleep(0.02)
                else:
                    raise AssertionError(f"desktop layout server never became ready at {url}")
                r = subprocess.run(
                    _chrome_args(self.chrome, url, "1280,800"),
                    capture_output=True, text=True, timeout=60,
                )
            finally:
                httpd.shutdown()
                httpd.server_close()
            blob = r.stdout or ""
            if 'id="layout-report"' not in blob:
                raise AssertionError(
                    f"chrome dump missing layout-report (exit {r.returncode})\n"
                    f"stderr={r.stderr[-1500:]}\nstdout_tail={blob[-500:]}"
                )
            part = blob.split('id="layout-report"', 1)[1]
            text = part.split(">", 1)[1].split("</pre>", 1)[0]
            text = (text.replace("&quot;", '"').replace("&#34;", '"')
                    .replace("&amp;", "&").strip())
            report = json.loads(text)
        self.assertGreaterEqual(report.get("innerWidth") or 0, 1000, report)
        self.assertTrue(report.get("customSummaryVisible"), report)
        self.assertTrue(report.get("dateInputsPresent"), report)
        self.assertTrue(report.get("customOpen"), report)
        self.assertTrue(report.get("customHighlighted"), report)
        self.assertFalse(
            report.get("thirtyOnWhileCustomOpen"),
            f"30 days still highlighted while Custom is open {report}",
        )
        self.assertNotEqual(report.get("thirtyPressedWhileCustomOpen"), "true", report)
        self.assertGreaterEqual(
            report.get("visTickH") or 0, 10,
            f"visible axis tick under 10px at 1280 {report}",
        )
        self.assertGreaterEqual(
            report.get("mainYCharts") or 0, 1,
            f"no main y-axis charts to measure at 1280 {report}",
        )
        self.assertGreaterEqual(
            report.get("heatCount") or 0, 2,
            f"expected both heatmap folds at 1280 {report}",
        )
        self.assertEqual(
            report.get("heatCaptionHits") or [], [],
            f"hour → caption overlaps an axis label at 1280 {report}",
        )


HEAT_CAPTION_PROBE = r"""
<script>
(function(){
  function txt(n){ return (n.textContent || '').replace(/\s+/g, ' ').trim(); }
  function overlapBox(a,b){
    return a && b && a.bottom > b.top + 1 && a.top < b.bottom - 1
      && a.right > b.left + 1 && a.left < b.right - 1;
  }
  function openNamedFold(root, re){
    const folds=Array.from((root||document).querySelectorAll('details.fold'));
    const fold=folds.find(d=>re.test((d.querySelector('summary')||{}).textContent||''));
    if(fold) fold.open=true;
    return fold;
  }
  function write(report){
    let el = document.getElementById('layout-report');
    if (!el) {
      el = document.createElement('pre');
      el.id = 'layout-report';
      document.body.appendChild(el);
    }
    el.textContent = JSON.stringify(report);
  }
  function measure(){
    openNamedFold(document.querySelector('#s6'), /best time to post/i);
    openNamedFold(document.querySelector('#s8'), /best reply time/i);
    setTimeout(function(){
      if (typeof fitAxisFonts === 'function') fitAxisFonts();
      const svgs=Array.from(document.querySelectorAll('.hmwrap .echart'));
      const hits=[];
      svgs.forEach((svg,si)=>{
        const texts=Array.from(svg.querySelectorAll('text')).filter(t=>{
          const b=t.getBoundingClientRect();
          return b.width>1 && b.height>1;
        });
        texts.filter(t=>/^hour →$/.test(txt(t))).forEach(cap=>{
          const cb=cap.getBoundingClientRect();
          texts.forEach(t=>{
            if(t===cap) return;
            if(overlapBox(cb, t.getBoundingClientRect())){
              hits.push({svg:si, cap:txt(cap), label:txt(t)});
            }
          });
        });
      });
      write({innerWidth: window.innerWidth, heatCount: svgs.length, captionHits: hits});
    }, 220);
  }
  function go(){ setTimeout(measure, 80); }
  if (document.readyState === 'complete') go();
  else window.addEventListener('load', go);
})();
</script>
"""


def _parse_layout_report(blob: str) -> dict:
    if 'id="layout-report"' not in blob:
        raise AssertionError(f"chrome dump missing layout-report\nstdout_tail={blob[-500:]}")
    part = blob.split('id="layout-report"', 1)[1]
    text = part.split(">", 1)[1].split("</pre>", 1)[0]
    text = (text.replace("&quot;", '"').replace("&#34;", '"')
            .replace("&amp;", "&").strip())
    return json.loads(text)


def _chrome_probe_at(chrome: str, html_path: Path, window: str, probe: str) -> dict:
    width = int(window.split(",", 1)[0])
    height = int(window.split(",", 1)[1])
    with tempfile.TemporaryDirectory(prefix="xdash-chrome-w-") as td:
        td = Path(td)
        page = td / "page.html"
        html = html_path.read_text(encoding="utf-8")
        if "</body>" in html:
            html = html.replace("</body>", probe + "</body>", 1)
        else:
            html += probe
        page.write_text(html, encoding="utf-8")
        _copy_sibling_assets(html_path, td)
        url_name = "page.html"
        if width <= 500:
            wrap = td / "wrap.html"
            wrap.write_text(
                f"""<!doctype html><meta charset="utf-8">
<iframe id="f" src="page.html" width="{width}" height="{height}"
  style="border:0;width:{width}px;height:{height}px"></iframe>
<script>
(function(){{
  const f=document.getElementById('f');
  function pick(){{
    try{{
      const el=f.contentDocument && f.contentDocument.getElementById('layout-report');
      if(el && el.textContent){{
        const out=document.createElement('pre');
        out.id='layout-report';
        out.textContent=el.textContent;
        document.documentElement.replaceChildren(out);
        return;
      }}
    }}catch(e){{}}
    setTimeout(pick,40);
  }}
  f.addEventListener('load', function(){{ setTimeout(pick,80); }});
  setTimeout(pick,200);
}})();
</script>
""",
                encoding="utf-8",
            )
            url_name = "wrap.html"
        httpd = _serve(td)
        try:
            url = f"http://127.0.0.1:{httpd.server_address[1]}/{url_name}"
            for _ in range(50):
                try:
                    urllib.request.urlopen(url, timeout=0.2).read()
                    break
                except Exception:
                    time.sleep(0.02)
            else:
                raise AssertionError(f"heatmap caption server never became ready at {url}")
            r = subprocess.run(
                _chrome_args(chrome, url, window),
                capture_output=True, text=True, timeout=60,
            )
        finally:
            httpd.shutdown()
            httpd.server_close()
        return _parse_layout_report(r.stdout or "")


@unittest.skipUnless(_chrome_bin(), "no system Chrome/Chromium for heatmap caption check")
class TestHeatmapHourCaptionChrome(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chrome = _chrome_bin()
        cls.data = _ensure_fixtures()
        cls.td = tempfile.TemporaryDirectory(prefix="xdash-heatcap-")
        cls.private = Path(cls.td.name) / "index.private.html"
        _build(cls.data, cls.private, "private")

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    def _check(self, window: str, expect_w: int):
        report = _chrome_probe_at(self.chrome, self.private, window, HEAT_CAPTION_PROBE)
        self.assertGreaterEqual(
            report.get("innerWidth") or 0, expect_w - 16,
            f"{window}: viewport too narrow {report}",
        )
        self.assertLessEqual(
            report.get("innerWidth") or 0, expect_w + 16,
            f"{window}: viewport too wide {report}",
        )
        self.assertGreaterEqual(
            report.get("heatCount") or 0, 2,
            f"{window}: expected both heatmap folds {report}",
        )
        self.assertEqual(
            report.get("captionHits") or [], [],
            f"{window}: hour → caption overlaps an axis label {report}",
        )

    def test_caption_clear_of_axis_labels_375(self):
        self._check("375,812", 375)

    def test_caption_clear_of_axis_labels_768(self):
        self._check("768,900", 768)

    def test_caption_clear_of_axis_labels_1280(self):
        self._check("1280,800", 1280)

    def test_caption_clear_of_axis_labels_1920(self):
        self._check("1920,1080", 1920)
