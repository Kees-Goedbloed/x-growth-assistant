#!/usr/bin/env python3
"""Enterprise BI layer: ECharts is vendored, screenshots at 375/1440, no console errors."""
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
  function txt(n){ return (n.textContent || '').replace(/\s+/g, ' ').trim(); }
  function overlap(a,b){
    return a && b && a.bottom > b.top + 1 && a.top < b.bottom - 1
      && a.right > b.left + 1 && a.left < b.right - 1;
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
  function visibleText(){
    return Array.from(document.querySelectorAll('#filterbar h1, #filterbar .bar-presets button, #filterbar .tog, .kpi .k, .kpi .v, main.dash > section > h2, main.dash > section > h3'))
      .filter(n => n.offsetParent !== null && txt(n))
      .map(n => ({t:txt(n), b:n.getBoundingClientRect()}))
      .filter(x => x.b.width>2 && x.b.height>2);
  }
  function chartTextHits(){
    const raw=[], iso=[], unknown=[], clipped=[];
    document.querySelectorAll('.echart text').forEach(t=>{
      const label=txt(t);
      if(!label) return;
      const b=t.getBoundingClientRect();
      const host=t.closest('.echart');
      if(host){
        const hb=host.getBoundingClientRect();
        if(b.width>1 && b.height>1){
          if(b.left < hb.left - 6 || b.right > hb.right + 6 || b.top < hb.top - 6 || b.bottom > hb.bottom + 6){
            clipped.push(label.slice(0,40));
          }
        }
      }
      if(/\d+\.\d{3,}/.test(label)) raw.push(label);
      if(/(^|[^0-9])\d{4}-\d{2}-\d{2}([^0-9]|$)/.test(label)) iso.push(label);
      if(/\bunknown\b/i.test(label)) unknown.push(label);
    });
    return {raw, iso, unknown, clipped};
  }
  function bodyHits(){
    const raw=[], iso=[], unknown=[];
    const walk=n=>{
      if(!n) return;
      if(n.nodeType===3){
        const t=txt(n);
        if(!t) return;
        if(/\d+\.\d{3,}/.test(t)) raw.push(t.slice(0,40));
        if(/(^|[^0-9])\d{4}-\d{2}-\d{2}([^0-9]|$)/.test(t) && !/TESTFIXTURE/.test(t)) iso.push(t.slice(0,40));
        if(/\bunknown\b/i.test(t)) unknown.push(t.slice(0,40));
        return;
      }
      if(n.nodeType!==1) return;
      if(n.id==='dash-data' || n.id==='layout-report') return;
      if(n.tagName==='SCRIPT' || n.tagName==='STYLE') return;
      if(n.classList && (n.classList.contains('txt') || n.closest && n.closest('td.txt, a'))) return;
      n.childNodes.forEach(walk);
    };
    walk(document.querySelector('main')||document.body);
    const bar=document.querySelector('#filterbar');
    if(bar) walk(bar);
    return {raw, iso, unknown};
  }
  function measure(){
    if (typeof resizeCharts === 'function') resizeCharts();
    setTimeout(function(){
      const nodes = visibleText();
      const hits = [];
      for (let i=0;i<nodes.length;i++) for (let j=i+1;j<nodes.length;j++){
        if (overlap(nodes[i].b, nodes[j].b)) hits.push(nodes[i].t+'|'+nodes[j].t);
      }
      const clipped = nodes.filter(n => n.b.left < -1 || n.b.right > document.documentElement.clientWidth + 1)
        .map(n => n.t);
      const chart=chartTextHits();
      const body=bodyHits();
      const bar=document.querySelector('#filterbar');
      write({
        innerWidth: window.innerWidth,
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
        scrollHeight: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight),
        headerH: bar ? Math.round(bar.getBoundingClientRect().height) : 0,
        echarts: typeof echarts !== 'undefined',
        chartCount: document.querySelectorAll('.echart').length,
        heatCount: document.querySelectorAll('.hmwrap .echart').length,
        kpiCount: document.querySelectorAll('.kpi').length,
        tableWrap: !!document.getElementById('top-wrap'),
        theme: document.documentElement.getAttribute('data-theme'),
        detailsMain: document.querySelectorAll('main details').length,
        noteMain: document.querySelectorAll('main .note').length,
        sliderCount: document.querySelectorAll('.echart .ec-dataZoom-slider, .echart [class*="dataZoom"]').length,
        unknown: (body.unknown||[]).concat(chart.unknown||[]).slice(0,8),
        rawFloats: (body.raw||[]).concat(chart.raw||[]).slice(0,8),
        isoDates: (body.iso||[]).concat(chart.iso||[]).slice(0,8),
        chartClipped: (chart.clipped||[]).slice(0,8),
        kpiDeltas: document.querySelectorAll('.kpi .delta').length,
        errors: window.__xdashErrors || [],
        overlap: hits.slice(0, 12),
        clipped: clipped.slice(0, 12)
      });
    }, 500);
  }
  function go(){ setTimeout(measure, 160); }
  if (document.readyState === 'complete') go();
  else window.addEventListener('load', go);
})();
</script>
"""


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


def _serve(directory: Path):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, fmt, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


def _parse_report(blob: str) -> dict:
    if 'id="layout-report"' not in blob:
        raise AssertionError(f"chrome dump missing layout-report\nstdout_tail={blob[-800:]}")
    part = blob.split('id="layout-report"', 1)[1]
    text = part.split(">", 1)[1].split("</pre>", 1)[0]
    text = (text.replace("&quot;", '"').replace("&#34;", '"')
            .replace("&amp;", "&").strip())
    return json.loads(text)


def _copy_sibling_assets(html_path: Path, dest: Path) -> None:
    src = html_path.parent / "assets"
    if src.is_dir():
        shutil.copytree(src, dest / "assets", dirs_exist_ok=True)


def _chrome_report(chrome: str, html_path: Path, window: str, probe: str | None = None) -> dict:
    width = int(window.split(",", 1)[0])
    height = int(window.split(",", 1)[1])
    with tempfile.TemporaryDirectory(prefix="xdash-bi-") as td:
        td = Path(td)
        page = td / "page.html"
        html = html_path.read_text(encoding="utf-8")
        blob = probe if probe is not None else PROBE
        if "</body>" in html:
            html = html.replace("</body>", blob + "</body>", 1)
        else:
            html += blob
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
            r = subprocess.run(
                [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
                 "--disable-dev-shm-usage", "--hide-scrollbars",
                 "--force-device-scale-factor=1", f"--window-size={window}",
                 "--virtual-time-budget=16000", "--dump-dom", url],
                capture_output=True, text=True, timeout=90,
            )
        finally:
            httpd.shutdown()
            httpd.server_close()
        return _parse_report(r.stdout or "")


class TestVendoredCharts(unittest.TestCase):
    def test_template_has_no_runtime_cdn(self):
        t = (ROOT / "template.html").read_text(encoding="utf-8")
        self.assertIn("<!--__ECHARTS__-->", t)
        self.assertIn("/*__INTER__*/", t)
        self.assertNotIn("cdn.jsdelivr", t)
        self.assertNotIn("unpkg.com", t)
        self.assertNotIn("cdnjs.cloudflare", t)
        self.assertNotIn("fonts.googleapis", t)
        self.assertTrue((ROOT / "vendor" / "echarts" / "echarts.min.js").is_file())
        self.assertTrue((ROOT / "vendor" / "fonts" / "inter-latin-400.woff2").is_file())

    def test_built_html_inlines_echarts_and_inter(self):
        data = _ensure_fixtures()
        with tempfile.TemporaryDirectory(prefix="xdash-inline-") as td:
            out = Path(td) / "index.html"
            _build(data, out, "private")
            html = out.read_text(encoding="utf-8")
        self.assertIn("echarts", html)
        self.assertIn("@font-face", html)
        self.assertIn("font-family:'Inter'", html)
        self.assertNotIn("cdn.jsdelivr", html)
        self.assertNotIn("unpkg.com", html)
        self.assertIn("Compare previous", html)
        self.assertIn("theme-toggle", html)


@unittest.skipUnless(_chrome_bin(), "no system Chrome/Chromium for BI screenshot check")
class TestBiScreenshots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chrome = _chrome_bin()
        cls.data = _ensure_fixtures()
        cls.td = tempfile.TemporaryDirectory(prefix="xdash-bi-html-")
        out = Path(cls.td.name)
        cls.private = out / "index.private.html"
        cls.public = out / "index.public.html"
        _build(cls.data, cls.private, "private")
        _build(cls.data, cls.public, "public")

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    def _themed(self, src: Path, theme: str) -> Path:
        html = src.read_text(encoding="utf-8")
        html = html.replace('data-theme="dark"', f'data-theme="{theme}"', 1)
        html = html.replace('data-theme="light"', f'data-theme="{theme}"', 1)
        dest = src.with_name(src.name.replace(".html", f".{theme}.html"))
        dest.write_text(html, encoding="utf-8")
        return dest

    def _check(self, path: Path, mode: str, window: str, expect_w: int, theme: str = "dark"):
        report = _chrome_report(self.chrome, path, window)
        w = int(window.split(",", 1)[0])
        self.assertTrue(report.get("echarts"), f"{mode} {theme} {window}: echarts missing {report}")
        self.assertGreaterEqual(report.get("chartCount") or 0, 6, f"{mode} {theme} {window}: {report}")
        self.assertGreaterEqual(report.get("heatCount") or 0, 2, f"{mode} {theme} {window}: heats {report}")
        self.assertGreaterEqual(report.get("kpiCount") or 0, 4, f"{mode} {theme} {window}: {report}")
        self.assertEqual(report.get("errors") or [], [], f"{mode} {theme} {window}: console errors {report}")
        self.assertEqual(report.get("overlap") or [], [], f"{mode} {theme} {window}: overlapping text {report}")
        self.assertEqual(report.get("clipped") or [], [], f"{mode} {theme} {window}: clipped text {report}")
        self.assertEqual(report.get("detailsMain") or 0, 0, f"{mode} {theme} {window}: details in main {report}")
        self.assertEqual(report.get("noteMain") or 0, 0, f"{mode} {theme} {window}: notes in main {report}")
        self.assertEqual(report.get("unknown") or [], [], f"{mode} {theme} {window}: unknown {report}")
        self.assertEqual(report.get("rawFloats") or [], [], f"{mode} {theme} {window}: raw floats {report}")
        self.assertEqual(report.get("isoDates") or [], [], f"{mode} {theme} {window}: raw ISO dates {report}")
        self.assertEqual(report.get("chartClipped") or [], [], f"{mode} {theme} {window}: chart clip {report}")
        self.assertEqual(
            report.get("scrollWidth"), report.get("clientWidth"),
            f"{mode} {theme} {window}: horizontal overflow {report}",
        )
        self.assertGreaterEqual(
            report.get("innerWidth") or 0, expect_w - 20,
            f"{mode} {theme} {window}: viewport {report}",
        )
        if w >= 1400:
            self.assertLessEqual(report.get("headerH") or 99, 64, f"{mode} {theme} header {report}")
            self.assertLessEqual(report.get("scrollHeight") or 99999, 4500, f"{mode} {theme} page height {report}")
            self.assertEqual(report.get("kpiDeltas") or 0, 0, f"{mode} {theme} 30d must hide uncovered deltas {report}")
        if w <= 400:
            self.assertLessEqual(report.get("headerH") or 99, 56, f"{mode} {theme} header {report}")

    def test_private_375(self):
        self._check(self.private, "private", "375,812", 375)

    def test_public_375(self):
        self._check(self.public, "public", "375,812", 375)

    def test_private_1440(self):
        self._check(self.private, "private", "1440,900", 1440)

    def test_public_1440(self):
        self._check(self.public, "public", "1440,900", 1440)

    def test_private_375_light(self):
        self._check(self._themed(self.private, "light"), "private", "375,812", 375, "light")

    def test_public_375_light(self):
        self._check(self._themed(self.public, "light"), "public", "375,812", 375, "light")

    def test_private_1440_light(self):
        self._check(self._themed(self.private, "light"), "private", "1440,900", 1440, "light")

    def test_public_1440_light(self):
        self._check(self._themed(self.public, "light"), "public", "1440,900", 1440, "light")

    def test_7d_shows_deltas_when_prev_covered(self):
        probe = r"""
<script>
(function(){
  function write(report){
    let el=document.getElementById('layout-report');
    if(!el){el=document.createElement('pre');el.id='layout-report';document.body.appendChild(el);}
    el.textContent=JSON.stringify(report);
  }
  function go(){
    const b=document.querySelector('#filterbar button[data-p="7"]');
    if(b) b.click();
    setTimeout(function(){
      write({
        preset: (window.state&&state.preset)||null,
        deltas: document.querySelectorAll('.kpi .delta').length,
        vs: Array.from(document.querySelectorAll('.kpi .delta .vs')).map(n=>n.textContent.trim())
      });
    }, 400);
  }
  if(document.readyState==='complete') setTimeout(go,80);
  else window.addEventListener('load', function(){ setTimeout(go,80); });
})();
</script>
"""
        report = _chrome_report(self.chrome, self.private, "1440,900", probe)
        self.assertGreaterEqual(report.get("deltas") or 0, 1, report)
        self.assertTrue(any("vs prev. 7d" in x for x in (report.get("vs") or [])), report)

    def test_round3_charts_outlier_heat_axis_compare_hover(self):
        probe = r"""
<script>
(function(){
  function write(report){
    let el=document.getElementById('layout-report');
    if(!el){el=document.createElement('pre');el.id='layout-report';document.body.appendChild(el);}
    el.textContent=JSON.stringify(report);
  }
  function inst(sel){
    const el=document.querySelector(sel);
    if(!el||typeof echarts==='undefined') return null;
    return echarts.getInstanceByDom(el);
  }
  function opt(sel){
    const c=inst(sel);
    return c?c.getOption():null;
  }
  function axisDays(sel){
    const o=opt(sel); if(!o) return [];
    const x=o.xAxis&&o.xAxis[0]; return (x&&x.data)||[];
  }
  function texts(sel){
    return Array.from(document.querySelectorAll(sel+' text')).map(t=>(t.textContent||'').replace(/\s+/g,' ').trim()).filter(Boolean);
  }
  function go(){
    setTimeout(function(){
      const impDays=axisDays('#s4 .echart');
      const folDays=axisDays('#s2 .echart');
      const oImp=opt('#s4 .echart')||{};
      const series=oImp.series||[];
      const impSer=series.find(s=>s.name==='Impressions')||{};
      const mp=(impSer.markPoint&&impSer.markPoint.data)||[];
      const legend=(oImp.legend&&oImp.legend[0]&&oImp.legend[0].data)||[];
      const heatEl=document.querySelector('#hp .echart')||document.querySelector('.hmwrap .echart');
      const heat=opt('#hp .echart')||opt('.hmwrap .echart')||{};
      const vm=(heat.visualMap&&heat.visualMap[0])||{};
      const heatMeta=(heatEl&&typeof echarts!=='undefined'&&echarts.getInstanceByDom(heatEl)&&echarts.getInstanceByDom(heatEl).__xdashHeat)||{};
      const cmp=document.getElementById('cmp-prev');
      const s8=document.getElementById('s8');
      const s8txt=(s8&&s8.textContent)||'';
      const labels=texts('#s4 .echart');
      const hasOutlier=labels.some(t=>/289[,\s]?780|458[,\s]?009|400[,\s]?000/.test(t));
      let hoverFol=null, lastHover=null, otherTip=null;
      const ci=inst('#s4 .echart'), cf=inst('#s2 .echart');
      const idx=impDays.indexOf('2026-09-25');
      if(ci&&idx>=0){
        try{
          ci.dispatchAction({type:'showTip',seriesIndex:0,dataIndex:idx});
          ci.dispatchAction({type:'updateAxisPointer',currTrigger:'show',xAxisIndex:0,value:'2026-09-25'});
        }catch(e){}
        lastHover=window.__xdashLastHover||null;
        hoverFol=cf && cf.__xdashDays ? cf.__xdashDays.indexOf('2026-09-25') : -2;
        const tip=document.querySelector('#s2 .echarts-tooltip, #s2 div[class*="tooltip"]');
        otherTip=tip && tip.style && tip.style.display!=='none' ? (tip.textContent||'').slice(0,80) : '';
      }
      const b90=document.querySelector('#filterbar button[data-p="90"]');
      if(b90) b90.click();
      setTimeout(function(){
        const days90=axisDays('#s4 .echart');
        const per=document.getElementById('perlabel');
        const shown=document.getElementById('shown-range');
        write({
          markCount: mp.length,
          markValues: mp.map(d=>d&&d.value),
          markNames: mp.map(d=>d&&d.name),
          legendHasOut: legend.some(x=>String(x).indexOf('out-mark')>=0),
          hasOutlier: hasOutlier,
          heatMin: heatMeta.min!=null?heatMeta.min:vm.min,
          heatMax: heatMeta.max!=null?heatMeta.max:vm.max,
          heatVmMin: vm.min,
          heatVmMax: vm.max,
          cmpDisabled: !!(cmp&&cmp.disabled),
          cmpTitle: (cmp&&(cmp.title||(cmp.closest('label')||{}).title))||'',
          cmpHint: (document.getElementById('cmp-hint')&&document.getElementById('cmp-hint').textContent)||'',
          cmpHintOn: !!(document.getElementById('cmp-hint')&&document.getElementById('cmp-hint').classList.contains('is-on')),
          longForm: /Long-form/.test(s8txt),
          lengthTitle: /Length · median impressions/.test(s8txt),
          hoverLast: lastHover,
          hoverFolHasDate: hoverFol,
          otherTip: otherTip,
          days90first: days90[0]||null,
          days90hasJune: days90.some(d=>String(d)<'2026-08-20'),
          per90: (per&&per.textContent)||'',
          shown90: (shown&&shown.textContent)||'',
          b90title: (b90&&b90.title)||'',
          folHorizonShare: folDays.length ? (impDays.length/Math.max(folDays.length,1)) : 0,
          connectUsed: typeof echarts!=='undefined' && echarts.getInstanceByDom(document.querySelector('#s2 .echart')) && echarts.getInstanceByDom(document.querySelector('#s2 .echart')).group==='dash-time'
        });
      }, 500);
    }, 400);
  }
  if(document.readyState==='complete') setTimeout(go,80);
  else window.addEventListener('load', function(){ setTimeout(go,80); });
})();
</script>
"""
        report = _chrome_report(self.chrome, self.private, "1440,900", probe)
        self.assertGreaterEqual(report.get("markCount") or 0, 1, report)
        self.assertTrue(
            any(int(v) >= 289780 for v in (report.get("markValues") or []) if v is not None),
            report,
        )
        self.assertIn("out-mark", report.get("markNames") or [], report)
        self.assertFalse(report.get("legendHasOut"), report)
        self.assertTrue(report.get("hasOutlier"), report)
        self.assertGreater(report.get("heatMax") or 0, 1, report)
        self.assertGreaterEqual(report.get("heatMax") or 0, 144, report)
        self.assertGreater(
            (report.get("heatMax") or 0) - (report.get("heatMin") or 0), 1, report
        )
        self.assertLessEqual(report.get("heatMin") or 99, 14, report)
        self.assertEqual(report.get("heatVmMin"), 0, report)
        self.assertEqual(report.get("heatVmMax"), 1, report)
        self.assertTrue(report.get("cmpDisabled"), report)
        self.assertEqual(report.get("cmpTitle"), "Not enough history", report)
        self.assertIn("Not enough history", report.get("cmpHint") or "", report)
        self.assertTrue(report.get("cmpHintOn"), report)
        self.assertFalse(report.get("longForm"), report)
        self.assertTrue(report.get("lengthTitle"), report)
        self.assertFalse(report.get("days90hasJune"), report)
        self.assertEqual(report.get("days90first"), "2026-08-20", report)
        self.assertIn("Aug 20", report.get("per90") or "", report)
        self.assertNotIn("Jun", report.get("per90") or "", report)
        self.assertIn("Aug 20", report.get("shown90") or "", report)
        self.assertIn("Aug 20", report.get("b90title") or "", report)
        self.assertFalse(report.get("connectUsed"), report)
        self.assertNotIn("Oct 17", report.get("otherTip") or "")

    def test_round4_current_axis_followers_band_heat_hint(self):
        probe = r"""
<script>
(function(){
  function write(report){
    let el=document.getElementById('layout-report');
    if(!el){el=document.createElement('pre');el.id='layout-report';document.body.appendChild(el);}
    el.textContent=JSON.stringify(report);
  }
  function inst(sel){
    const el=document.querySelector(sel);
    if(!el||typeof echarts==='undefined') return null;
    return echarts.getInstanceByDom(el);
  }
  function opt(sel){
    const c=inst(sel);
    return c?c.getOption():null;
  }
  function axisDays(sel){
    const o=opt(sel); if(!o) return [];
    const x=o.xAxis&&o.xAxis[0]; return (x&&x.data)||[];
  }
  function contrast(a,b){
    function lum(hex){
      let h=String(hex||'').replace('#','');
      if(h.length===3)h=h[0]+h[0]+h[1]+h[1]+h[2]+h[2];
      if(h.length<6)return 0;
      const r=parseInt(h.slice(0,2),16)/255,g=parseInt(h.slice(2,4),16)/255,bl=parseInt(h.slice(4,6),16)/255;
      const lin=c=>c<=0.03928?c/12.92:Math.pow((c+0.055)/1.055,2.4);
      return 0.2126*lin(r)+0.7152*lin(g)+0.0722*lin(bl);
    }
    const L1=lum(a),L2=lum(b);const hi=Math.max(L1,L2),lo=Math.min(L1,L2);
    return (hi+0.05)/(lo+0.05);
  }
  function go(){
    const b7=document.querySelector('#filterbar button[data-p="7"]');
    if(b7) b7.click();
    setTimeout(function(){
      const oImp=opt('#s4 .echart')||{};
      const y=(oImp.yAxis&&oImp.yAxis[0])||{};
      const series=oImp.series||[];
      const prev=series.find(s=>/Prev/.test(s.name||''))||{};
      const prevMarks=((prev.markPoint&&prev.markPoint.data)||[]);
      const prevVals=(prev.data||[]).map(p=>p&&(typeof p==='object'?p.value:p));
      const D=JSON.parse((document.getElementById('dash-data').textContent)||'{}');
      const start=(window.__xdash&&__xdash.state&&__xdash.state.start)||'2026-09-19';
      const end=(window.__xdash&&__xdash.state&&__xdash.state.end)||'2026-09-25';
      const by={};
      (D.posts||[]).forEach(p=>{
        if(p.type==='repost'||p.impressions==null)return;
        if(p.local_date<start||p.local_date>end)return;
        by[p.local_date]=(by[p.local_date]||0)+p.impressions;
      });
      const tots=Object.values(by);
      const cap=(window.__xdash&&__xdash.robustYMax)?__xdash.robustYMax(tots):Math.max.apply(null,tots.concat([1]));
      const folDays=axisDays('#s2 .echart');
      const oFol=opt('#s2 .echart')||{};
      const folSer=oFol.series||[];
      const band=folSer.find(s=>s.name==='band-hi');
      const bandW=(band&&band.data||[]).reduce((m,v)=>{const n=typeof v==='object'?v&&v.value:v;return n==null?m:Math.max(m,n);},0);
      const bandLo=folSer.find(s=>s.name==='band-lo');
      const loMax=(bandLo&&bandLo.data||[]).reduce((m,v)=>{const n=typeof v==='object'?v&&v.value:v;return n==null?m:Math.max(m,n);},0);
      const firstFol=(window.__xdash&&__xdash.firstFollowerDate)?__xdash.firstFollowerDate():null;
      const heatC=inst('#hp .echart');
      const meta=heatC&&heatC.__xdashHeat||{};
      const emptyTip=(()=>{
        const cf=inst('#s2 .echart');
        if(!cf||!folDays.length)return null;
        const before=folDays[0];
        try{cf.dispatchAction({type:'showTip',seriesIndex:0,dataIndex:-1});}catch(e){}
        const tip=document.querySelector('#s2 div[class*="tooltip"], #s2 .echarts-tooltip');
        return tip&&tip.style&&tip.style.display!=='none'?(tip.textContent||''):'';
      })();
      const hint=document.getElementById('cmp-hint');
      write({
        yMax: y.max,
        cap,
        prevMarks: prevMarks.map(d=>d&&d.value),
        prevMax: Math.max.apply(null, prevVals.filter(v=>v!=null).concat([0])),
        folFirst: folDays[0]||null,
        firstFol,
        bandPresent: !!band,
        bandWidth: bandW && loMax!=null ? bandW : 0,
        heatLow: meta.low,
        heatEmpty: meta.empty,
        heatCard: meta.card,
        lowC: meta.low&&meta.card?contrast(meta.low,meta.card):0,
        emptyC: meta.empty&&meta.card?contrast(meta.empty,meta.card):0,
        cmpHint: hint?hint.textContent:'',
        cmpHintOn: !!(hint&&hint.classList.contains('is-on')),
        cmpDisabled: !!(document.getElementById('cmp-prev')&&document.getElementById('cmp-prev').disabled),
        emptyTip
      });
    }, 500);
  }
  if(document.readyState==='complete') setTimeout(go,80);
  else window.addEventListener('load', function(){ setTimeout(go,80); });
})();
</script>
"""
        report = _chrome_report(self.chrome, self.private, "1440,900", probe)
        self.assertLess(report.get("yMax") or 999999, 100000, report)
        self.assertLessEqual(report.get("yMax") or 999999, (report.get("cap") or 1) * 2 + 1, report)
        self.assertTrue(
            any(int(v) >= 400000 for v in (report.get("prevMarks") or []) if v is not None),
            report,
        )
        self.assertLessEqual(report.get("prevMax") or 0, report.get("yMax") or 0, report)
        self.assertEqual(report.get("folFirst"), "2026-09-19", report)
        self.assertGreaterEqual(report.get("folFirst") or "", report.get("firstFol") or "", report)
        self.assertTrue(report.get("bandPresent"), report)
        self.assertGreater(report.get("bandWidth") or 0, 0, report)
        self.assertGreater(report.get("lowC") or 0, report.get("emptyC") or 0, report)
        self.assertGreaterEqual(report.get("lowC") or 0, 2.0, report)
        self.assertIn("Not enough history", report.get("cmpHint") or "", report)
        # 7d prev is covered, so the hint is off; 30d default is tested in round3.
        self.assertFalse(report.get("cmpDisabled"), report)
        self.assertFalse(report.get("cmpHintOn"), report)

    def test_round5_cards_colors_and_deeplinks(self):
        probe = r"""
<script>
(function(){
  function write(report){
    let el=document.getElementById('layout-report');
    if(!el){el=document.createElement('pre');el.id='layout-report';document.body.appendChild(el);}
    el.textContent=JSON.stringify(report);
  }
  function go(){
    setTimeout(function(){
      const cards=Array.from(document.querySelectorAll('#s6 .pcard'));
      const links=cards.map(c=>c.querySelector('a.pcard-hit')).filter(Boolean);
      const lefts=[...new Set(cards.map(c=>Math.round(c.getBoundingClientRect().left)))].sort((a,b)=>a-b);
      const widths=cards.map(c=>c.getBoundingClientRect().width);
      const acc=(window.__xdash&&__xdash.state&&document.getElementById('dash-data'))? (JSON.parse(document.getElementById('dash-data').textContent||'{}').meta||{}).account : '';
      const badge=document.getElementById('demo-badge');
      write({
        cardCount: cards.length,
        cols: lefts.length,
        minW: widths.length?Math.min.apply(null,widths):0,
        maxW: widths.length?Math.max.apply(null,widths):0,
        inner: window.innerWidth,
        hrefs: links.slice(0,3).map(a=>a.getAttribute('href')||''),
        targets: links.map(a=>a.getAttribute('target')),
        blank: links.every(a=>a.getAttribute('target')==='_blank'),
        status: links.every(a=>/\/status\//.test(a.getAttribute('href')||'')),
        xStatus: links.filter(a=>/x\.com\/.+\/status\//.test(a.getAttribute('href')||'')).length,
        demoBadge: !!(badge && !badge.hidden && /Demo data/.test(badge.textContent||'')),
        demoMeta: !!(window.F||true) && !!(JSON.parse((document.getElementById('dash-data')||{}).textContent||'{}').meta||{}).demo,
        tones: cards.map(c=>Array.from(c.classList).find(x=>x.indexOf('tl-')===0)).filter(Boolean),
        badges: document.querySelectorAll('#s6 .pcard-badge').length,
        kpiTl: document.querySelectorAll('.kpi-tl').length,
        cal: !!document.getElementById('consistency-cal'),
        calCells: document.querySelectorAll('.cal-cell.tl-green, .cal-cell.tl-yellow, .cal-cell.tl-orange, .cal-cell.tl-red').length,
        legend: !!document.getElementById('tl-legend'),
        tabs: Array.from(document.querySelectorAll('[data-card-tab]')).map(b=>b.getAttribute('data-card-tab')),
        consKpi: !!Array.from(document.querySelectorAll('.kpi .k')).some(n=>/Consistency/.test(n.textContent||'')),
        replies: cards.map(c=>(c.querySelector('.pcard-reply')||{}).textContent||'').filter(Boolean),
        acc: acc||''
      });
    }, 500);
  }
  if(document.readyState==='complete') setTimeout(go,80);
  else window.addEventListener('load', function(){ setTimeout(go,80); });
})();
</script>
"""
        r1440 = _chrome_report(self.chrome, self.private, "1440,900", probe)
        self.assertGreaterEqual(r1440.get("cardCount") or 0, 3, r1440)
        self.assertGreaterEqual(r1440.get("cols") or 0, 2, r1440)
        self.assertLessEqual(r1440.get("cols") or 99, 3, r1440)
        self.assertFalse(r1440.get("blank"), r1440)
        self.assertFalse(r1440.get("status"), r1440)
        self.assertEqual(r1440.get("xStatus") or 0, 0, r1440)
        self.assertTrue(all(h == "#" for h in (r1440.get("hrefs") or [])), r1440)
        self.assertTrue(r1440.get("demoBadge"), r1440)
        self.assertTrue(r1440.get("demoMeta"), r1440)
        self.assertGreaterEqual(len(r1440.get("tones") or []), 1, r1440)
        self.assertGreaterEqual(r1440.get("kpiTl") or 0, 1, r1440)
        self.assertTrue(r1440.get("cal"), r1440)
        self.assertGreaterEqual(r1440.get("calCells") or 0, 7, r1440)
        self.assertTrue(r1440.get("legend"), r1440)
        self.assertEqual(r1440.get("tabs"), ["top", "latest", "posts", "replies"], r1440)
        self.assertTrue(r1440.get("consKpi"), r1440)
        r375 = _chrome_report(self.chrome, self.private, "375,812", probe)
        self.assertGreaterEqual(r375.get("cardCount") or 0, 1, r375)
        self.assertEqual(r375.get("cols") or 0, 1, r375)
        self.assertFalse(r375.get("blank"), r375)
        self.assertFalse(r375.get("status"), r375)
        self.assertEqual(r375.get("xStatus") or 0, 0, r375)
        self.assertTrue(r375.get("demoBadge"), r375)
        self.assertLessEqual(r375.get("maxW") or 999, 375, r375)
        pub = _chrome_report(self.chrome, self.public, "1440,900", probe)
        self.assertGreaterEqual(pub.get("cardCount") or 0, 1, pub)
        self.assertFalse(pub.get("blank"), pub)
        self.assertFalse(pub.get("status"), pub)
        self.assertTrue(pub.get("demoBadge"), pub)
        self.assertTrue(all(r == "Replying to a post" for r in (pub.get("replies") or [])), pub)

    def test_round6_incomplete_top_mix_dscore_calendar(self):
        probe = r"""
<script>
(function(){
  function write(report){
    let el=document.getElementById('layout-report');
    if(!el){el=document.createElement('pre');el.id='layout-report';document.body.appendChild(el);}
    el.textContent=JSON.stringify(report);
  }
  function inst(sel){
    const el=document.querySelector(sel);
    if(!el||typeof echarts==='undefined') return null;
    return echarts.getInstanceByDom(el);
  }
  function opt(sel){
    const c=inst(sel);
    return c?c.getOption():null;
  }
  function go(){
    setTimeout(function(){
      const today=document.querySelector('.cal-cell[data-date="2026-09-25"]');
      const scored=Array.from(document.querySelectorAll('.cal-cell.tl-green, .cal-cell.tl-yellow, .cal-cell.tl-orange, .cal-cell.tl-red'));
      const box=scored[0]?scored[0].getBoundingClientRect():{width:0,height:0};
      const o3=opt('#s3 .echart')||{};
      const bars=(o3.series||[]).filter(s=>s.type==='bar');
      const barColors={};
      bars.forEach(s=>{
        const items=(s.data||[]).map(d=>d&&d.itemStyle&&d.itemStyle.color).filter(Boolean);
        barColors[s.name]={series:s.itemStyle&&s.itemStyle.color, items};
      });
      const metrics=Array.from(document.querySelectorAll('.pcard-metrics, #perlabel')).map(n=>n.textContent||'').join(' ');
      const badPlural=metrics.match(/\b1 (views|likes|replies|reposts|bookmarks|days|posts)\b/);
      const topKinds=Array.from(document.querySelectorAll('#s6 .pcard')).map(c=>c.getAttribute('data-kind'));
      const sparkEl=document.querySelector('#cons-panel .spark');
      let sparkTail=null;
      if(sparkEl){
        try{const v=JSON.parse(sparkEl.getAttribute('data-spark')||'[]');sparkTail=v.length?v[v.length-1]:null;}catch(e){sparkTail='err';}
      }
      const first={
        todayIncomplete: !!(today&&today.classList.contains('is-incomplete')),
        todayTones: today?Array.from(today.classList).filter(x=>x.indexOf('tl-')===0):[],
        calCells: scored.length,
        calW: box.width,
        calH: box.height,
        wd: (document.querySelector('.cal-wd')&&document.querySelector('.cal-wd').textContent)||'',
        months: (document.querySelector('.cal-months')&&document.querySelector('.cal-months').textContent)||'',
        consPanel: !!document.getElementById('cons-panel'),
        split: !!document.getElementById('post-split'),
        topHeads: Array.from(document.querySelectorAll('#s6 .split-h')).map(n=>n.textContent.trim()),
        topKinds,
        dscore3: document.querySelectorAll('#s3 .dscore').length,
        dscore5: document.querySelectorAll('#s5 .dscore').length,
        barColors,
        badPlural: badPlural?badPlural[0]:null,
        sparkTail,
        lastComplete: window.__xdash&&__xdash.lastCompleteDay?__xdash.lastCompleteDay():null,
        todayIncFn: window.__xdash&&__xdash.isIncompleteDay?__xdash.isIncompleteDay('2026-09-25'):null
      };
      const btn=document.querySelector('[data-card-tab="replies"]');
      if(btn) btn.click();
      setTimeout(function(){
        first.replySplit=!!document.getElementById('post-split');
        first.replyKinds=Array.from(document.querySelectorAll('#s6 .pcard')).map(c=>c.getAttribute('data-kind'));
        first.replyHeads=Array.from(document.querySelectorAll('#s6 .split-h')).map(n=>n.textContent.trim());
        write(first);
      }, 400);
    }, 500);
  }
  if(document.readyState==='complete') setTimeout(go,80);
  else window.addEventListener('load', function(){ setTimeout(go,80); });
})();
</script>
"""
        r1440 = _chrome_report(self.chrome, self.private, "1440,900", probe)
        self.assertTrue(r1440.get("todayIncomplete"), r1440)
        self.assertEqual(r1440.get("todayTones"), [], r1440)
        self.assertGreaterEqual(r1440.get("calCells") or 0, 7, r1440)
        self.assertGreaterEqual(r1440.get("calW") or 0, 16, r1440)
        self.assertGreaterEqual(r1440.get("calH") or 0, 16, r1440)
        self.assertIn("Mon", r1440.get("wd") or "", r1440)
        self.assertIn("Tue", r1440.get("wd") or "", r1440)
        self.assertTrue(
            ("Aug" in (r1440.get("months") or "")) or ("Sep" in (r1440.get("months") or "")),
            r1440,
        )
        self.assertTrue(r1440.get("consPanel"), r1440)
        self.assertTrue(r1440.get("split"), r1440)
        self.assertEqual(r1440.get("topHeads"), ["Top posts", "Top replies"], r1440)
        self.assertIn("post", r1440.get("topKinds") or [], r1440)
        self.assertIn("reply", r1440.get("topKinds") or [], r1440)
        self.assertGreaterEqual(r1440.get("dscore3") or 0, 1, r1440)
        self.assertGreaterEqual(r1440.get("dscore5") or 0, 1, r1440)
        posts = ((r1440.get("barColors") or {}).get("posts") or {})
        self.assertFalse(posts.get("items"), r1440)
        self.assertEqual((posts.get("series") or "").lower(), "#1d9bf0", r1440)
        self.assertIsNone(r1440.get("badPlural"), r1440)
        self.assertIsNone(r1440.get("sparkTail"), r1440)
        self.assertEqual(r1440.get("lastComplete"), "2026-09-24", r1440)
        self.assertTrue(r1440.get("todayIncFn"), r1440)
        self.assertFalse(r1440.get("replySplit"), r1440)
        self.assertTrue(r1440.get("replyKinds"), r1440)
        self.assertTrue(all(k == "reply" for k in (r1440.get("replyKinds") or [])), r1440)
        self.assertEqual(r1440.get("replyHeads") or [], [], r1440)
        r375 = _chrome_report(self.chrome, self.private, "375,812", probe)
        self.assertTrue(r375.get("todayIncomplete"), r375)
        self.assertTrue(r375.get("consPanel"), r375)
        self.assertTrue(r375.get("split"), r375)
        self.assertIn("post", r375.get("topKinds") or [], r375)
        self.assertIn("reply", r375.get("topKinds") or [], r375)

    def test_round7_owner_avatar_header_and_cards(self):
        probe = r"""
<script>
(function(){
  function write(report){
    let el=document.getElementById('layout-report');
    if(!el){el=document.createElement('pre');el.id='layout-report';document.body.appendChild(el);}
    el.textContent=JSON.stringify(report);
  }
  function box(sel){
    const n=document.querySelector(sel);
    if(!n) return null;
    const b=n.getBoundingClientRect();
    const cs=getComputedStyle(n);
    return {w:Math.round(b.width),h:Math.round(b.height),r:cs.borderRadius,src:(n.querySelector('img')||{}).src||'',text:(n.textContent||'').trim()};
  }
  function go(){
    setTimeout(function(){
      const imgs=Array.from(document.querySelectorAll('img')).map(i=>i.getAttribute('src')||i.src||'');
      const cards=Array.from(document.querySelectorAll('#s6 .pcard-av img')).map(i=>i.getAttribute('src')||'');
      const dash=document.querySelector('#dash-av img');
      const handle=document.querySelector('#s6 .pcard-handle');
      const name=document.querySelector('#s6 .pcard-name');
      const bar=document.querySelector('#filterbar');
      write({
        headerH: bar?Math.round(bar.getBoundingClientRect().height):0,
        dash: box('#dash-av'),
        card: box('#s6 .pcard-av'),
        dashSrc: dash? (dash.getAttribute('src')||'') : '',
        cardSrcs: cards.slice(0,6),
        cardCount: cards.length,
        names: name?(name.textContent||''):'',
        handles: handle?(handle.textContent||''):'',
        hot: imgs.filter(s=>/pbs\.twimg|unavatar\.io|twimg\.com/.test(s)),
        otherAv: document.querySelectorAll('.pcard-av img').length === document.querySelectorAll('#s6 .pcard-av img').length,
        init: !dash && ((document.querySelector('#dash-av')||{}).textContent||'').trim()
      });
    }, 500);
  }
  if(document.readyState==='complete') setTimeout(go,80);
  else window.addEventListener('load', function(){ setTimeout(go,80); });
})();
</script>
"""
        for window, max_h, av_min, av_max in (("1440,900", 64, 36, 44), ("375,812", 56, 20, 28)):
            report = _chrome_report(self.chrome, self.private, window, probe)
            self.assertLessEqual(report.get("headerH") or 99, max_h, report)
            self.assertIn("assets/avatar", report.get("dashSrc") or "", report)
            self.assertGreaterEqual(report.get("cardCount") or 0, 1, report)
            self.assertTrue(all("assets/avatar" in s for s in (report.get("cardSrcs") or [])), report)
            self.assertEqual(report.get("hot") or [], [], report)
            dash = report.get("dash") or {}
            card = report.get("card") or {}
            self.assertGreaterEqual(dash.get("w") or 0, av_min, report)
            self.assertLessEqual(dash.get("w") or 99, av_max, report)
            self.assertGreaterEqual(card.get("w") or 0, 36, report)
            self.assertLessEqual(card.get("w") or 99, 44, report)
            self.assertTrue("50%" in str(dash.get("r") or "") or "999" in str(dash.get("r") or ""), report)
            self.assertIn("Demo Owner", report.get("names") or "", report)
            self.assertIn("@demo_owner", report.get("handles") or "", report)
        pub = _chrome_report(self.chrome, self.public, "1440,900", probe)
        self.assertIn("assets/avatar", pub.get("dashSrc") or "", pub)
        self.assertTrue(all("assets/avatar" in s for s in (pub.get("cardSrcs") or [])), pub)
        self.assertEqual(pub.get("hot") or [], [], pub)

        blank = self.private.with_name("index.private.noav.html")
        html = self.private.read_text(encoding="utf-8")
        html = html.replace('"avatar": "assets/avatar.jpg"', '"avatar": ""', 1)
        html = html.replace('"avatar": "assets/avatar.png"', '"avatar": ""', 1)
        blank.write_text(html, encoding="utf-8")
        init = _chrome_report(self.chrome, blank, "1440,900", probe)
        self.assertEqual(init.get("dashSrc") or "", "", init)
        self.assertEqual(init.get("init"), "D", init)
        self.assertEqual(init.get("cardSrcs") or [], [], init)

    def test_round8_streak_sparks_empty_range_calendar_cards(self):
        probe = r"""
<script>
(function(){
  function write(report){
    let el=document.getElementById('layout-report');
    if(!el){el=document.createElement('pre');el.id='layout-report';document.body.appendChild(el);}
    el.textContent=JSON.stringify(report);
  }
  function streakText(){
    const n=document.querySelector('#cons-panel .streak');
    return n?(n.textContent||'').trim():'';
  }
  function sparkTails(){
    return Array.from(document.querySelectorAll('.kpi .spark')).map(el=>{
      try{const v=JSON.parse(el.getAttribute('data-spark')||'[]');return v.length?v[v.length-1]:'empty';}
      catch(e){return 'err';}
    });
  }
  function kpiVals(){
    return Array.from(document.querySelectorAll('.kpi .k')).map(k=>{
      const card=k.closest('.kpi');
      const v=card?card.querySelector('.v'):null;
      return {k:(k.textContent||'').trim(), v:v?(v.textContent||'').trim():'', tone:card?Array.from(card.classList).filter(x=>x.indexOf('tl-')===0):[], delta:(card&&card.querySelector('.delta'))?(card.querySelector('.delta').textContent||'').trim():''};
    });
  }
  function calInfo(){
    const wrap=document.querySelector('.cal-wrap');
    const grid=document.querySelector('.cal-grid');
    const cells=Array.from(document.querySelectorAll('.cal-grid .cal-cell[data-date]'));
    const wb=wrap?wrap.getBoundingClientRect():{width:0,right:0};
    const gb=grid?grid.getBoundingClientRect():{width:0,right:0};
    return {
      weeks: cells.length?cells.length/7:0,
      inRange: document.querySelectorAll('.cal-cell.is-in-range').length,
      out: document.querySelectorAll('.cal-cell.is-out').length,
      wrapW: Math.round(wb.width),
      gridW: Math.round(gb.width),
      slack: Math.round(wb.right-gb.right),
      fill: wb.width?gb.width/wb.width:0
    };
  }
  function pairH(){
    const left=Array.from(document.querySelectorAll('.post-col[data-split="posts"] .pcard'));
    const right=Array.from(document.querySelectorAll('.post-col[data-split="replies"] .pcard'));
    const n=Math.min(left.length,right.length);
    const diffs=[];
    for(let i=0;i<n;i++){
      diffs.push(Math.abs(Math.round(left[i].getBoundingClientRect().height)-Math.round(right[i].getBoundingClientRect().height)));
    }
    return {n, max: diffs.length?Math.max.apply(null,diffs):99, diffs};
  }
  function go(){
    setTimeout(function(){
      const first={
        streak30: streakText(),
        tails30: sparkTails(),
        cal30: calInfo(),
        lastComplete: window.__xdash&&__xdash.lastCompleteDay?__xdash.lastCompleteDay():null,
        streakFn30: window.__xdash&&__xdash.currentStreak&&__xdash.streakDays?__xdash.currentStreak(__xdash.streakDays()):null,
        pairs: pairH(),
        dashOnerror: !!(document.querySelector('#dash-av img')&&/avatarImgFallback/.test(document.querySelector('#dash-av img').getAttribute('onerror')||''))
      };
      const b7=document.querySelector('#filterbar button[data-p="7"]');
      if(b7) b7.click();
      setTimeout(function(){
        first.streak7=streakText();
        first.tails7=sparkTails();
        first.cal7=calInfo();
        first.streakFn7=window.__xdash&&__xdash.currentStreak&&__xdash.streakDays?__xdash.currentStreak(__xdash.streakDays()):null;
        const fs=document.getElementById('fs'), fe=document.getElementById('fe'), ap=document.getElementById('fapply');
        if(fs) fs.value='2026-09-25';
        if(fe) fe.value='2026-09-25';
        if(ap) ap.click();
        setTimeout(function(){
          first.today=kpiVals();
          first.todayDeltas=document.querySelectorAll('.kpi .delta').length;
          first.todayTl=document.querySelectorAll('.kpi.kpi-tl').length;
          first.preset=window.__xdash&&__xdash.state?__xdash.state.preset:null;
          const img=document.querySelector('#dash-av img');
          if(img && window.__xdash && __xdash.avatarImgFallback){
            __xdash.avatarImgFallback(img);
          } else if(img){
            img.src='assets/missing-avatar-r8.png';
          }
          first.fallback=(document.querySelector('#dash-av')||{}).textContent||'';
          first.fallbackImg=!!document.querySelector('#dash-av img');
          write(first);
        }, 450);
      }, 450);
    }, 500);
  }
  if(document.readyState==='complete') setTimeout(go,80);
  else window.addEventListener('load', function(){ setTimeout(go,80); });
})();
</script>
"""
        r1440 = _chrome_report(self.chrome, self.private, "1440,900", probe)
        self.assertEqual(r1440.get("streak7"), r1440.get("streak30"), r1440)
        self.assertTrue(r1440.get("streak7"), r1440)
        self.assertEqual(r1440.get("streakFn7"), r1440.get("streakFn30"), r1440)
        act30 = [t for t in (r1440.get("tails30") or [])]
        self.assertTrue(len(act30) >= 6, r1440)
        cal30 = r1440.get("cal30") or {}
        cal7 = r1440.get("cal7") or {}
        self.assertLessEqual(cal30.get("weeks") or 99, 10, r1440)
        self.assertGreaterEqual(cal30.get("weeks") or 0, 4, r1440)
        self.assertEqual(cal30.get("weeks"), cal7.get("weeks"), r1440)
        self.assertGreater(cal30.get("inRange") or 0, cal7.get("inRange") or 0, r1440)
        self.assertGreaterEqual((r1440.get("pairs") or {}).get("n") or 0, 1, r1440)
        self.assertLessEqual((r1440.get("pairs") or {}).get("max", 99), 2, r1440)
        self.assertEqual(r1440.get("preset"), "custom", r1440)
        today = r1440.get("today") or []
        self.assertTrue(today, r1440)
        activity = [row for row in today if row.get("k") != "Followers"]
        self.assertTrue(activity, r1440)
        self.assertTrue(all(row.get("v") == "—" for row in activity), r1440)
        fol = next((row for row in today if row.get("k") == "Followers"), None)
        self.assertTrue(fol and fol.get("v") and fol.get("v") != "—", r1440)
        self.assertTrue(r1440.get("dashOnerror"), r1440)

        r375 = _chrome_report(self.chrome, self.private, "375,812", probe)
        self.assertEqual(r375.get("streak7"), r375.get("streak30"), r375)
        self.assertLessEqual((r375.get("cal30") or {}).get("weeks") or 99, 10, r375)
        activity375 = [row for row in (r375.get("today") or []) if row.get("k") != "Followers"]
        self.assertTrue(all(row.get("v") == "—" for row in activity375), r375)

    def test_round9_avatar_followers_calendar_top_gap(self):
        probe = r"""
<script>
(function(){
  function write(report){
    let el=document.getElementById('layout-report');
    if(!el){el=document.createElement('pre');el.id='layout-report';document.body.appendChild(el);}
    el.textContent=JSON.stringify(report);
  }
  function kpiVal(label){
    const row=Array.from(document.querySelectorAll('.kpi .k')).find(n=>n.textContent.trim()===label);
    if(!row) return null;
    const v=row.closest('.kpi').querySelector('.v');
    return v?(v.textContent||'').trim():null;
  }
  function monthOverlap(){
    const nodes=Array.from(document.querySelectorAll('.cal-mon')).filter(n=>(n.textContent||'').trim());
    const boxes=nodes.map(n=>({t:(n.textContent||'').trim(),b:n.getBoundingClientRect()}));
    const hits=[];
    for(let i=0;i<boxes.length;i++) for(let j=i+1;j<boxes.length;j++){
      const a=boxes[i].b,b=boxes[j].b;
      if(a.right>b.left+1 && a.left<b.right-1 && a.bottom>b.top+1 && a.top<b.bottom-1)
        hits.push(boxes[i].t+boxes[j].t);
    }
    return {labels:boxes.map(x=>x.t), hits};
  }
  function go(){
    setTimeout(function(){
      const cell=document.querySelector('.cal-grid .cal-cell');
      const box=cell?cell.getBoundingClientRect():{width:0,height:0};
      const split=document.getElementById('post-split');
      const cards=Array.from(document.querySelectorAll('#post-split .pcard'));
      const last=cards[cards.length-1];
      const more=document.getElementById('card-more');
      const leftN=document.querySelectorAll('.post-col[data-split="posts"] .pcard').length;
      const rightN=document.querySelectorAll('.post-col[data-split="replies"] .pcard').length;
      const col=document.querySelector('.post-col[data-split="posts"]');
      const head=col&&col.querySelector('.split-h');
      const colCards=col?Array.from(col.querySelectorAll('.pcard')):[];
      const headGap=(head&&colCards[0])?Math.round(colCards[0].getBoundingClientRect().top-head.getBoundingClientRect().bottom):null;
      const cardGap=(colCards[0]&&colCards[1])?Math.round(colCards[1].getBoundingClientRect().top-colCards[0].getBoundingClientRect().bottom):null;
      const snaps=((window.F&&F.snapshots)||(function(){
        try{return JSON.parse(document.getElementById('dash-data').textContent).followers.snapshots;}catch(e){return [];}
      })());
      let latest=null;
      (snaps||[]).forEach(s=>{if(s&&s.followers_count!=null) latest=s.followers_count;});
      const latestFn=window.__xdash&&__xdash.latestFollowers?__xdash.latestFollowers():null;
      write({
        folKpi: kpiVal('Followers'),
        latestSnap: latest,
        latestFn,
        cellW: Math.round(box.width),
        cellH: Math.round(box.height),
        weeks: document.querySelectorAll('.cal-grid .cal-cell[data-date]').length/7,
        wdSum: !!document.getElementById('weekday-sum'),
        calH: document.getElementById('consistency-cal')?Math.round(document.getElementById('consistency-cal').getBoundingClientRect().height):0,
        splitN: split?getComputedStyle(split).getPropertyValue('--split-n').trim():'',
        leftN, rightN, headGap, cardGap,
        moreGap: (more&&last)?Math.round(more.getBoundingClientRect().top-last.getBoundingClientRect().bottom):null,
        globalFn: typeof window.avatarImgFallback,
        months: monthOverlap()
      });
    }, 700);
  }
  if(document.readyState==='complete') setTimeout(go,80);
  else window.addEventListener('load', function(){ setTimeout(go,80); });
})();
</script>
"""
        r1440 = _chrome_report(self.chrome, self.private, "1440,900", probe)
        self.assertEqual(r1440.get("globalFn"), "function", r1440)
        self.assertEqual(r1440.get("latestFn"), r1440.get("latestSnap"), r1440)
        self.assertTrue(r1440.get("latestSnap"), r1440)
        fol = (r1440.get("folKpi") or "").replace(",", "")
        self.assertEqual(fol, str(r1440.get("latestSnap")), r1440)
        self.assertLessEqual(r1440.get("cellW") or 99, 33, r1440)
        self.assertLessEqual(r1440.get("cellH") or 99, 33, r1440)
        self.assertGreaterEqual(r1440.get("cellW") or 0, 14, r1440)
        self.assertLessEqual(r1440.get("weeks") or 99, 10, r1440)
        self.assertTrue(r1440.get("wdSum"), r1440)
        self.assertLessEqual(r1440.get("calH") or 999, 340, r1440)
        self.assertEqual(int(r1440.get("splitN") or 0), max(r1440.get("leftN") or 0, r1440.get("rightN") or 0, 1), r1440)
        self.assertEqual(r1440.get("leftN"), 3, r1440)
        self.assertLessEqual(r1440.get("moreGap") if r1440.get("moreGap") is not None else 99, 40, r1440)
        self.assertIsNotNone(r1440.get("headGap"), r1440)
        self.assertIsNotNone(r1440.get("cardGap"), r1440)
        self.assertLessEqual(abs((r1440.get("headGap") or 0) - (r1440.get("cardGap") or 0)), 3, r1440)

        r375 = _chrome_report(self.chrome, self.private, "375,812", probe)
        self.assertLessEqual(r375.get("cellW") or 99, 33, r375)
        self.assertLessEqual(r375.get("weeks") or 99, 10, r375)
        self.assertEqual((r375.get("months") or {}).get("hits") or [], [], r375)
        self.assertTrue(r375.get("wdSum"), r375)
        self.assertIsNotNone(r375.get("headGap"), r375)
        self.assertIsNotNone(r375.get("cardGap"), r375)
        self.assertLessEqual(abs((r375.get("headGap") or 0) - (r375.get("cardGap") or 0)), 3, r375)

        missing = self.private.with_name("index.private.missing-av.html")
        html = self.private.read_text(encoding="utf-8")
        html = html.replace('"avatar": "assets/avatar.png"', '"avatar": "assets/missing-r9.png"', 1)
        html = html.replace('"avatar": "assets/avatar.jpg"', '"avatar": "assets/missing-r9.png"', 1)
        missing.write_text(html, encoding="utf-8")
        miss_probe = r"""
<script>
(function(){
  function write(report){
    let el=document.getElementById('layout-report');
    if(!el){el=document.createElement('pre');el.id='layout-report';document.body.appendChild(el);}
    el.textContent=JSON.stringify(report);
  }
  function done(){
    const errs=(window.__xdashErrors||[]).filter(x=>/avatarImgFallback|is not defined/i.test(String(x)));
    write({
      globalFn: typeof window.avatarImgFallback,
      dashText: ((document.querySelector('#dash-av')||{}).textContent||'').trim(),
      dashImg: !!document.querySelector('#dash-av img'),
      cardImgs: document.querySelectorAll('#s6 .pcard-av img').length,
      cardInit: Array.from(document.querySelectorAll('#s6 .pcard-av')).slice(0,4).map(n=>(n.textContent||'').trim()),
      errors: errs,
      allErrors: (window.__xdashErrors||[]).slice(0,8)
    });
  }
  const imgs=Array.from(document.querySelectorAll('#dash-av img, .pcard-av img'));
  if(!imgs.length){ setTimeout(done, 200); return; }
  let left=imgs.length;
  const tick=()=>{ if(--left<=0) setTimeout(done, 60); };
  imgs.forEach(img=>{
    if(img.complete && !img.naturalWidth){ tick(); return; }
    img.addEventListener('error', tick);
    img.addEventListener('load', tick);
  });
  setTimeout(done, 1800);
})();
</script>
"""
        miss = _chrome_report(self.chrome, missing, "1440,900", miss_probe)
        self.assertEqual(miss.get("globalFn"), "function", miss)
        self.assertEqual((miss.get("dashText") or "").strip(), "D", miss)
        self.assertFalse(miss.get("dashImg"), miss)
        self.assertEqual(miss.get("cardImgs") or 0, 0, miss)
        self.assertTrue(all(t == "D" for t in (miss.get("cardInit") or ["D"])), miss)
        self.assertEqual(miss.get("errors") or [], [], miss)

    def test_what_works_bar_labels_no_overlap(self):
        probe = r"""
<script>
(function(){
  function write(report){
    let el=document.getElementById('layout-report');
    if(!el){el=document.createElement('pre');el.id='layout-report';document.body.appendChild(el);}
    el.textContent=JSON.stringify(report);
  }
  function txt(n){return (n.textContent||'').replace(/\s+/g,' ').trim();}
  function overlap(a,b){
    return a && b && a.bottom>b.top+1 && a.top<b.bottom-1 && a.right>b.left+1 && a.left<b.right-1;
  }
  function go(){
    setTimeout(function(){
      const hosts=Array.from(document.querySelectorAll('#s8 .echart-hbar'));
      const overlaps=[];
      const clipped=[];
      const longOnBar=[];
      const catsSeen=[];
      const valsSeen=[];
      hosts.forEach(host=>{
        const sb=host.getBoundingClientRect();
        const texts=Array.from(host.querySelectorAll('text')).filter(t=>{
          const b=t.getBoundingClientRect();
          return b.width>1 && b.height>1;
        });
        const cats=texts.filter(t=>/text only|article|thread|link|within|later|Short|Medium|Long|image|video|GIF|poll|post|reply|quote/i.test(txt(t)));
        const vals=texts.filter(t=>/^\d+(\.\d+)?[KM]?$/.test(txt(t)));
        cats.forEach(c=>{
          const cb=c.getBoundingClientRect();
          catsSeen.push(txt(c));
          if(cb.left<sb.left-2) clipped.push('L:'+txt(c));
          if(cb.right>sb.right+2) clipped.push('R:'+txt(c));
          if(cb.top<sb.top-2) clipped.push('T:'+txt(c));
          vals.forEach(v=>{
            if(overlap(cb,v.getBoundingClientRect())) overlaps.push(txt(c)+'~'+txt(v));
          });
        });
        vals.forEach(v=>valsSeen.push(txt(v)));
        texts.forEach(t=>{
          if(/median /i.test(txt(t))) longOnBar.push(txt(t));
        });
      });
      write({
        n:hosts.length,
        overlaps,
        clipped,
        longOnBar,
        catsSeen,
        valsSeen,
        inner:window.innerWidth,
        compact: typeof (window.__xdash&&__xdash.compactN)==='function'?__xdash.compactN(1525):null
      });
    }, 800);
  }
  if(document.readyState==='complete') setTimeout(go,80);
  else window.addEventListener('load', function(){ setTimeout(go,80); });
})();
</script>
"""
        for window in ("1440,900", "1024,768", "375,812"):
            report = _chrome_report(self.chrome, self.private, window, probe)
            self.assertGreaterEqual(report.get("n") or 0, 1, report)
            self.assertEqual(report.get("overlaps") or [], [], report)
            self.assertEqual(report.get("clipped") or [], [], report)
            self.assertEqual(report.get("longOnBar") or [], [], report)
            self.assertEqual(report.get("compact"), "1.5K", report)
            cats = " ".join(report.get("catsSeen") or []).lower()
            self.assertTrue(
                any(k in cats for k in ("text only", "article", "thread", "link", "later", "within")),
                report,
            )
            self.assertTrue(report.get("valsSeen"), report)
            self.assertTrue(
                all(not v.endswith("k") for v in (report.get("valsSeen") or [])),
                report,
            )

    def test_minibars_tooltip_stays_on_screen(self):
        probe = r"""
<script>
(function(){
  function write(report){
    let el=document.getElementById('layout-report');
    if(!el){el=document.createElement('pre');el.id='layout-report';document.body.appendChild(el);}
    el.textContent=JSON.stringify(report);
  }
  function box(n){
    const b=n.getBoundingClientRect();
    return {x:b.left,y:b.top,r:b.right,b:b.bottom,w:b.width,h:b.height};
  }
  function findTip(){
    const nodes=Array.from(document.querySelectorAll('div'));
    return nodes.find(el=>{
      const t=(el.textContent||'');
      if(!/median |impressions|n=\d/.test(t)) return false;
      const cs=getComputedStyle(el);
      if(cs.display==='none'||+cs.opacity===0) return false;
      const b=el.getBoundingClientRect();
      return b.width>20 && b.height>10 && (cs.position==='absolute'||cs.position==='fixed');
    })||null;
  }
  function go(){
    setTimeout(function(){
      const hosts=Array.from(document.querySelectorAll('#s8 .echart-hbar'));
      const vw=document.documentElement.clientWidth;
      const vh=Math.max(window.innerHeight, document.documentElement.scrollHeight);
      const cuts=[];
      const confined=[];
      const tips=[];
      const jobs=[];
      hosts.forEach((host,hi)=>{
        const c=typeof echarts!=='undefined'?echarts.getInstanceByDom(host):null;
        if(!c) return;
        const opt=c.getOption()||{};
        const tipOpt=(opt.tooltip&&opt.tooltip[0])||{};
        confined.push(!!tipOpt.confine);
        const n=((opt.series&&opt.series[0]&&opt.series[0].data)||[]).length;
        for(let i=0;i<n;i++) jobs.push({c,hi,i});
      });
      function step(k){
        if(k>=jobs.length){
          write({
            n:hosts.length,
            confined,
            cuts,
            tips,
            inner:window.innerWidth,
            compactK: window.__xdash&&__xdash.compactN?__xdash.compactN(1525):null
          });
          return;
        }
        const job=jobs[k];
        try{job.c.dispatchAction({type:'showTip',seriesIndex:0,dataIndex:job.i});}catch(e){}
        setTimeout(function(){
          const tip=findTip();
          if(!tip){cuts.push('missing:'+job.hi+':'+job.i);}
          else{
            const t=box(tip);
            const leftCut=Math.max(0, Math.round(-t.x));
            const rightCut=Math.max(0, Math.round(t.r-vw));
            const topCut=Math.max(0, Math.round(-t.y));
            const botCut=Math.max(0, Math.round(t.b-vh));
            if(leftCut>1||rightCut>1||topCut>1||botCut>1){
              cuts.push({hi:job.hi,i:job.i,leftCut,rightCut,topCut,botCut,w:Math.round(t.w)});
            }
            if(tips.length<4) tips.push({hi:job.hi,i:job.i,x:Math.round(t.x),r:Math.round(t.r),txt:(tip.textContent||'').slice(0,90)});
          }
          try{job.c.dispatchAction({type:'hideTip'});}catch(e){}
          setTimeout(function(){ step(k+1); }, 20);
        }, 40);
      }
      step(0);
    }, 500);
  }
  if(document.readyState==='complete') setTimeout(go,80);
  else window.addEventListener('load', function(){ setTimeout(go,80); });
})();
</script>
"""
        for window in ("375,812", "1024,768", "1440,900"):
            report = _chrome_report(self.chrome, self.private, window, probe)
            self.assertGreaterEqual(report.get("n") or 0, 1, report)
            self.assertTrue(report.get("confined"), report)
            self.assertTrue(all(report.get("confined") or []), report)
            self.assertEqual(report.get("cuts") or [], [], report)
            self.assertEqual(report.get("compactK"), "1.5K", report)

    def test_header_stays_one_line_at_1024(self):
        probe = r"""
<script>
(function(){
  function write(report){
    let el=document.getElementById('layout-report');
    if(!el){el=document.createElement('pre');el.id='layout-report';document.body.appendChild(el);}
    el.textContent=JSON.stringify(report);
  }
  function go(){
    setTimeout(function(){
      const title=document.getElementById('dash-title');
      if(title) title.textContent='Helena Whitmore';
      const bar=document.getElementById('filterbar');
      const chip=document.querySelector('#filterbar button[data-p="7"]');
      const tb=title?title.getBoundingClientRect():null;
      const cb=chip?chip.getBoundingClientRect():null;
      const bb=bar?bar.getBoundingClientRect():null;
      const sameRow=!!(tb&&cb&&tb.bottom>cb.top+2&&tb.top<cb.bottom-2);
      const chipTxt=((chip&&(chip.innerText||chip.textContent))||'').replace(/\s+/g,' ').trim();
      write({
        inner:window.innerWidth,
        headerH: bb?Math.round(bb.height):0,
        titleH: tb?Math.round(tb.height):0,
        chipH: cb?Math.round(cb.height):0,
        titleW: tb?Math.round(tb.width):0,
        titleText: title?(title.textContent||''):'',
        titleOverflow: title?getComputedStyle(title).textOverflow:'',
        titleWrap: title?getComputedStyle(title).whiteSpace:'',
        chipTxt,
        sameRow,
        titleLines: tb&&title? Math.round(tb.height/parseFloat(getComputedStyle(title).lineHeight||'16')):0,
        barOverflow: bb&&bar? Math.round(bar.scrollWidth-bar.clientWidth):0,
        pShortOn: !!(chip&&chip.querySelector('.p-short')&&getComputedStyle(chip.querySelector('.p-short')).display!=='none'),
        pFullOff: !!(chip&&chip.querySelector('.p-full')&&getComputedStyle(chip.querySelector('.p-full')).display==='none')
      });
    }, 400);
  }
  if(document.readyState==='complete') setTimeout(go,80);
  else window.addEventListener('load', function(){ setTimeout(go,80); });
})();
</script>
"""
        report = _chrome_report(self.chrome, self.private, "1024,768", probe)
        self.assertEqual(report.get("inner"), 1024, report)
        self.assertLessEqual(report.get("headerH") or 99, 64, report)
        self.assertLessEqual(report.get("titleH") or 99, 32, report)
        self.assertLessEqual(report.get("chipH") or 99, 36, report)
        self.assertTrue(report.get("sameRow"), report)
        self.assertEqual(report.get("titleOverflow"), "ellipsis", report)
        self.assertEqual(report.get("titleWrap"), "nowrap", report)
        self.assertTrue(report.get("pShortOn"), report)
        self.assertTrue(report.get("pFullOff"), report)
        self.assertIn("7d", report.get("chipTxt") or "", report)
        self.assertNotIn("7 days", report.get("chipTxt") or "", report)
        self.assertLessEqual(int(report.get("barOverflow") if report.get("barOverflow") is not None else 99), 1, report)
