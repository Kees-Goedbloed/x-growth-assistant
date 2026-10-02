#!/usr/bin/env python3
"""Shrinkage judge: Lein-shape, tiny/large synthetics, monotonic n, bars, fixtures."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import repo_guard  # noqa: E402,F401

TEMPLATE = (ROOT / "template.html").read_text(encoding="utf-8")


def _extract_fn(src: str, name: str) -> str:
    needle = f"function {name}("
    i = src.find(needle)
    if i < 0:
        raise AssertionError(f"missing function {name}")
    brace = src.find("{", i)
    depth = 0
    for j, ch in enumerate(src[brace:], brace):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[i : j + 1]
    raise AssertionError(f"unclosed function {name}")


def _node_bin():
    return shutil.which("node") or shutil.which("nodejs")


def _prelude() -> str:
    fns = [
        "med",
        "mean",
        "percentileRank",
        "trafficLightScore",
        "tlHex",
        "heatTheme",
        "heatEmptyColor",
        "heatLowColor",
        "heatColors",
        "heatMapped",
        "heatThinDecal",
        "heatRange",
        "judgePeers",
        "judgeImps",
        "judgePrior",
        "judgeWeight",
        "judgeFull",
        "judgeOpacity",
        "judgeLow",
        "judgeHintable",
        "shrinkLog",
        "shrinkImp",
        "poolHour",
        "judgeToneFromShrink",
        "judgeTone",
        "judgeLabel",
        "judgeColor",
        "judgeLegend",
        "pluralize",
        "slotLbl",
        "topSlots",
        "hintSlots",
        "slotAdviceHtml",
        "heatSvg",
        "miniBars",
    ]
    bits = [
        "const MINN=5;",
        "const JUDGE_K=3;",
        "const HINT_MIN_W=0.5;",
        "const SCORE={lights:{green:75,yellow:50,orange:25}};",
        "const WD=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];",
        r"""
const globalDocument={documentElement:{_t:'dark',getAttribute(){return this._t;}},createElement(){return {getContext(){return null;}};}};
global.document=globalDocument;
global.innerWidth=1440;
function chartDisplayWidth(){return 900;}
function fN(v){return String(v);}
function f1(v){return String(v);}
function fP(v){return String(v);}
function esc(s){return String(s);}
function axFmt(v){return String(v);}
function compactN(v){return String(v);}
function yCatLabelWidth(){return 80;}
function metricBarShort(r,valKey){return String(r[valKey]);}
function metricBarLabel(r,valKey){return 'median '+r[valKey]+' impressions';}
function contrastRatio(){return 2;}
function hexLum(){return 0.5;}
let lastHeat=null, lastBars=null;
function enqueueChart(kind,option,h,cls){
  if(kind==='heat') lastHeat={kind,option,h,cls};
  if(kind==='hbar') lastBars={kind,option,h,cls};
  return '<div class="echart echart-'+kind+'"></div>';
}
function post(wd,hour,impressions,type,extra){
  extra=extra||{};
  return Object.assign({weekday:wd,hour,impressions,type:type||'post',er:impressions?20/impressions:0,profile_visits:1,new_follows:0}, extra);
}
function ownOf(posts){return posts.filter(p=>p.type==='post'||p.type==='quote');}
function heatOf(posts){
  lastHeat=null;
  const kind=posts.some(p=>p.type==='reply')&&posts.every(p=>p.type==='reply')?'reply':'post';
  return heatSvg(posts,a=>med(a.map(p=>p.impressions)),kind);
}
function cell(stats,d,h){return stats[d+'-'+h]||null;}
function mappedCell(d,h){
  const data=(lastHeat&&lastHeat.option&&lastHeat.option.series&&lastHeat.option.series[0]&&lastHeat.option.series[0].data)||[];
  return data.find(x=>x&&x.value&&x.value[0]===h&&x.value[1]===d)||null;
}
function tonesOf(){
  const data=(lastHeat&&lastHeat.option&&lastHeat.option.series&&lastHeat.option.series[0]&&lastHeat.option.series[0].data)||[];
  return data.filter(x=>x&&!x.empty&&x.tone).map(x=>x.tone);
}
function hexOf(c){return String(c||'').toLowerCase();}
function leinPosts(){
  const posts=[];
  for(let w=0;w<4;w++){
    posts.push(post(1,20,5900+w*40));
    posts.push(post(1,19,3100+w*20));
    posts.push(post(1,21,3000+w*15));
    posts.push(post(2,20,3300+w*10));
    posts.push(post(3,19,3050+w*12));
    posts.push(post(4,18,2900+w*10));
  }
  posts.push(post(4,3,52000), post(4,3,48000));
  const scatter=[[0,10],[0,14],[0,18],[2,9],[2,13],[3,8],[3,12],[3,16],[5,11],[5,15],[6,12],[6,17],[0,21],[2,17],[5,19]];
  scatter.forEach(([d,h],i)=>{
    const n=i%3===0?1:2;
    for(let k=0;k<n;k++) posts.push(post(d,h,2700+d*30+h+k*12));
  });
  for(let d=0;d<7;d++){
    for(const h of [9,12,15,18]){
      const n=(d===2&&h===12)?8:5;
      for(let i=0;i<n;i++) posts.push(post(d,h,400+i*10,'reply'));
    }
  }
  for(let d=0;d<7;d++){
    for(const h of [8,10,11,14,16,19]){
      for(let i=0;i<4;i++) posts.push(post(d,h,360+i*6,'reply'));
    }
  }
  for(let d=0;d<7;d++){
    for(const h of [7,13,17,20,21,22]){
      for(let i=0;i<4;i++) posts.push(post(d,h,340+i,'reply'));
    }
  }
  return posts;
}
function tinyPosts(){
  return [post(1,20,5000),post(2,10,2000),post(3,15,3000),post(4,8,2500)];
}
function largePosts(){
  const posts=[];
  for(let i=0;i<40;i++) posts.push(post(1,20,8000+i));
  for(let i=0;i<40;i++) posts.push(post(2,10,2000+i));
  for(let d=0;d<7;d++){
    for(let h=8;h<18;h++){
      if(d===1&&h===20) continue;
      if(d===2&&h===10) continue;
      for(let i=0;i<6;i++) posts.push(post(d,h,3000+i));
    }
  }
  posts.push(post(5,3,150000));
  return posts;
}
function fixturePosts(){
  const posts=[];
  for(let i=0;i<6;i++) posts.push(post(1,20,4000+i*10));
  for(let i=0;i<6;i++) posts.push(post(2,21,3800+i*10));
  for(let i=0;i<6;i++) posts.push(post(3,20,3600+i*10));
  posts.push(post(4,3,900), post(4,3,910));
  for(let i=0;i<20;i++) posts.push(post(0,12,2000+i));
  return posts;
}
""",
    ]
    bits.extend(_extract_fn(TEMPLATE, name) for name in fns)
    return "\n".join(bits)


def _run(script: str) -> dict:
    node = _node_bin()
    if not node:
        raise unittest.SkipTest("node is required to execute extracted judge helpers")
    r = subprocess.run(
        [node, "-e", _prelude() + "\n" + script],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise AssertionError(f"node shrink helpers failed\n{r.stdout}\n{r.stderr}")
    lines = [ln for ln in r.stdout.strip().splitlines() if ln.strip()]
    return json.loads(lines[-1])


class TestJudgeShrinkSource(unittest.TestCase):
    def test_template_exports_shrink_helpers(self):
        for name in (
            "JUDGE_K",
            "judgeWeight",
            "judgeFull",
            "judgeOpacity",
            "judgeLow",
            "judgeHintable",
            "shrinkLog",
            "shrinkImp",
            "poolHour",
            "hintSlots",
            "slotAdviceHtml",
        ):
            self.assertIn(name, TEMPLATE, name)
        self.assertIn("worse → better vs your usual post", TEMPLATE)
        self.assertIn("fainter = fewer posts, treat as a hint", TEMPLATE)
        self.assertNotIn("fainter / hatched", TEMPLATE)
        self.assertIn("No hour is proven yet.", TEMPLATE)
        self.assertIn("hint (not proven)", TEMPLATE)
        self.assertIn("judge-advice", TEMPLATE)


@unittest.skipUnless(_node_bin(), "node is required to execute extracted judge helpers")
class TestLeinRealDataShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = _run(
            r"""
const all=leinPosts();
const own=ownOf(all);
const heat=heatOf(own);
const tue=cell(heat.stats,1,20);
const fluke=cell(heat.stats,4,3);
const tueM=mappedCell(1,20);
const flukeM=mappedCell(4,3);
const tops=topSlots(heat.stats,3);
const hints=hintSlots(heat.stats,3);
const maxN=Math.max(...Object.values(heat.stats).map(s=>s.n||0));
const filledTones=tonesOf();
const grey=filledTones.filter(t=>!t||t==='thin').length;
const filledN=Object.values(heat.stats).filter(s=>s.n>0).length;
const neighL=mappedCell(4,2), neighR=mappedCell(4,4), tueGap=mappedCell(1,18);
const hoursFilled=Array.from({length:7},(_,d)=>{let n=0;for(let h=0;h<24;h++) if((heat.stats[d+'-'+h]||{}).n>0) n++; return n;});
const mapped=((lastHeat&&lastHeat.option&&lastHeat.option.series&&lastHeat.option.series[0]&&lastHeat.option.series[0].data)||[]);
const decals=mapped.filter(x=>x&&x.itemStyle&&x.itemStyle.decal).length;
const paintedEmpty=mapped.filter(x=>x&&x.empty&&x.tone).length;
const out={
  nAll: all.length,
  nOwn: own.length,
  maxN,
  filledN,
  hoursFilled,
  maxHoursFilled: Math.max(...hoursFilled),
  decals,
  paintedEmpty,
  neighLEmpty: !!(neighL&&neighL.empty),
  neighREmpty: !!(neighR&&neighR.empty),
  tueGapEmpty: !!(tueGap&&tueGap.empty),
  proven: tops.map(t=>({d:t.d,h:t.h,n:t.n})),
  hints: hints.map(t=>({d:t.d,h:t.h,n:t.n,low:t.low})),
  advice: heat.html,
  tueN: tue&&tue.n,
  tueTone: tue&&tue.tone,
  tueFull: !!(tue&&tue.full),
  tueOp: judgeOpacity(tue&&tue.n),
  tueHint: !!(tueM&&tueM.hint),
  tueDecal: !!(tueM&&tueM.itemStyle&&tueM.itemStyle.decal),
  tueColor: tueM&&tueM.itemStyle&&tueM.itemStyle.color,
  flukeN: fluke&&fluke.n,
  flukeTone: fluke&&fluke.tone,
  flukeFull: !!(fluke&&fluke.full),
  flukeOp: judgeOpacity(fluke&&fluke.n),
  flukeHint: !!(flukeM&&flukeM.hint),
  flukeDecal: !!(flukeM&&flukeM.itemStyle&&flukeM.itemStyle.decal),
  flukeColor: flukeM&&flukeM.itemStyle&&flukeM.itemStyle.color,
  filled: filledTones.length,
  grey,
  tones: [...new Set(filledTones)],
  prior: judgePrior(own)
};
console.log(JSON.stringify(out));
"""
        )

    def test_lein_shape_is_sparse_and_coloured(self):
        o = self.out
        self.assertGreaterEqual(o["nAll"], 500, o)
        self.assertLessEqual(o["maxN"], 4, o)
        self.assertEqual(o["tueN"], 4, o)
        self.assertEqual(o["flukeN"], 2, o)
        self.assertEqual(o["proven"], [], o)
        self.assertIn("No hour is proven yet.", o["advice"], o)
        self.assertIn("Strongest so far", o["advice"], o)
        self.assertNotIn("Best time to post", o["advice"], o)
        self.assertNotIn("03:00", o["advice"], o)
        self.assertTrue(any(h["d"] == 1 and h["h"] == 20 for h in o["hints"]), o)
        self.assertFalse(any(h["d"] == 4 and h["h"] == 3 for h in o["hints"]), o)
        self.assertLess(o["filledN"], 80, o)
        self.assertLess(o["maxHoursFilled"], 8, o)
        self.assertEqual(o["decals"], 0, o)
        self.assertEqual(o["paintedEmpty"], 0, o)
        self.assertTrue(o["neighLEmpty"], o)
        self.assertTrue(o["neighREmpty"], o)
        self.assertTrue(o["tueGapEmpty"], o)
        self.assertGreater(o["filled"], 15, o)
        self.assertEqual(o["grey"], 0, o)
        self.assertTrue(o["tones"], o)
        self.assertTrue(set(o["tones"]) <= {"green", "yellow", "orange", "red"}, o)
        self.assertIn(o["tueTone"], ("green", "yellow", "orange", "red"), o)
        self.assertIn(o["flukeTone"], ("green", "yellow", "orange", "red"), o)
        self.assertFalse(o["tueFull"], o)
        self.assertFalse(o["flukeFull"], o)
        self.assertTrue(o["tueHint"], o)
        self.assertTrue(o["flukeHint"], o)
        self.assertFalse(o["tueDecal"], o)
        self.assertFalse(o["flukeDecal"], o)
        self.assertGreater(o["tueOp"], o["flukeOp"], o)
        self.assertNotIn("#64748b", (o["tueColor"] or "").lower(), o)
        self.assertNotIn("#64748b", (o["flukeColor"] or "").lower(), o)
        self.assertFalse(any(h["d"] == 4 and h["h"] == 3 for h in o["proven"]), o)


@unittest.skipUnless(_node_bin(), "node is required to execute extracted judge helpers")
class TestTinySynthetic(unittest.TestCase):
    def test_tiny_account_has_colour_but_no_proven_hour(self):
        o = _run(
            r"""
const posts=tinyPosts();
const heat=heatOf(posts);
const tops=topSlots(heat.stats,3);
const tones=tonesOf();
const ops=Object.values(heat.stats).filter(s=>s.n>0).map(s=>judgeOpacity(s.n));
const out={
  n: posts.length,
  proven: tops.length,
  advice: heat.html,
  tones: [...new Set(tones)],
  filled: tones.length,
  maxOp: Math.max(...ops),
  grey: tones.filter(t=>!t||t==='thin').length
};
console.log(JSON.stringify(out));
"""
        )
        self.assertLess(o["n"], 8, o)
        self.assertEqual(o["proven"], 0, o)
        self.assertIn("No hour is proven yet.", o["advice"], o)
        self.assertNotIn("Strongest so far", o["advice"], o)
        self.assertGreaterEqual(o["filled"], 3, o)
        self.assertEqual(o["grey"], 0, o)
        self.assertTrue(set(o["tones"]) <= {"green", "yellow", "orange", "red"}, o)
        self.assertLess(o["maxOp"], 0.8, o)


@unittest.skipUnless(_node_bin(), "node is required to execute extracted judge helpers")
class TestLargeSynthetic(unittest.TestCase):
    def test_large_account_names_proven_hour_and_fades_outlier(self):
        o = _run(
            r"""
const posts=largePosts();
const heat=heatOf(posts);
const tue=cell(heat.stats,1,20);
const fluke=cell(heat.stats,5,3);
const tueM=mappedCell(1,20);
const flukeM=mappedCell(5,3);
const tops=topSlots(heat.stats,3);
const out={
  n: posts.length,
  advice: heat.html,
  proven: tops.map(t=>({d:t.d,h:t.h,n:t.n})),
  tueN: tue&&tue.n,
  tueFull: !!(tue&&tue.full),
  tueTone: tue&&tue.tone,
  tueOp: judgeOpacity(tue&&tue.n),
  tueHint: !!(tueM&&tueM.hint),
  flukeN: fluke&&fluke.n,
  flukeFull: !!(fluke&&fluke.full),
  flukeTone: fluke&&fluke.tone,
  flukeOp: judgeOpacity(fluke&&fluke.n),
  flukeHint: !!(flukeM&&flukeM.hint),
  flukeShrink: fluke&&fluke.shrink,
  prior: judgePrior(posts),
  rawFluke: 150000
};
console.log(JSON.stringify(out));
"""
        )
        self.assertGreaterEqual(o["n"], 200, o)
        self.assertGreaterEqual(o["tueN"], 40, o)
        self.assertEqual(o["flukeN"], 1, o)
        self.assertTrue(o["tueFull"], o)
        self.assertFalse(o["flukeFull"], o)
        self.assertFalse(o["tueHint"], o)
        self.assertTrue(o["flukeHint"], o)
        self.assertEqual(o["tueTone"], "green", o)
        self.assertGreater(o["tueOp"], 0.9, o)
        self.assertLess(o["flukeOp"], 0.6, o)
        self.assertLess(o["flukeShrink"], o["rawFluke"] * 0.2, o)
        self.assertGreater(o["flukeShrink"], o["prior"], o)
        self.assertTrue(any(p["d"] == 1 and p["h"] == 20 for p in o["proven"]), o)
        self.assertFalse(any(p["d"] == 5 and p["h"] == 3 for p in o["proven"]), o)
        self.assertIn("Best time to post", o["advice"], o)
        self.assertNotIn("No hour is proven yet.", o["advice"], o)


@unittest.skipUnless(_node_bin(), "node is required to execute extracted judge helpers")
class TestMonotonicAddOnePost(unittest.TestCase):
    def test_adding_a_matching_post_moves_shrink_toward_the_cell(self):
        o = _run(
            r"""
const prior=3000, cellImp=10000;
const rows=[];
for(let n=1;n<=20;n++){
  rows.push({
    n,
    shrink: shrinkImp(cellImp,n,prior),
    w: judgeWeight(n),
    op: judgeOpacity(n),
    full: judgeFull(n)
  });
}
const okShrink=rows.every((r,i)=>i===0||r.shrink>rows[i-1].shrink);
const okW=rows.every((r,i)=>i===0||r.w>rows[i-1].w);
const okOp=rows.every((r,i)=>i===0||r.op>rows[i-1].op);
const wrapL=poolHour({'0-0':{n:2,imp:1000},'0-23':{n:8,imp:9000}},0,0);
const wrapR=poolHour({'0-23':{n:2,imp:1000},'0-0':{n:8,imp:9000}},0,23);
console.log(JSON.stringify({
  rows,
  okShrink, okW, okOp,
  first: rows[0], last: rows[rows.length-1],
  full4: judgeFull(4), full5: judgeFull(5),
  wrapLN: wrapL.nEff, wrapRN: wrapR.nEff,
  ident500: shrinkImp(500,6,500),
  ident80: shrinkImp(80,8,80)
}));
"""
        )
        self.assertTrue(o["okShrink"], o)
        self.assertTrue(o["okW"], o)
        self.assertTrue(o["okOp"], o)
        self.assertLess(o["first"]["shrink"], 10000, o)
        self.assertGreater(o["last"]["shrink"], o["first"]["shrink"], o)
        self.assertLess(o["last"]["shrink"], 10000, o)
        self.assertFalse(o["full4"], o)
        self.assertTrue(o["full5"], o)
        self.assertAlmostEqual(o["wrapLN"], 2.0, places=5)
        self.assertAlmostEqual(o["wrapRN"], 2.0, places=5)
        self.assertEqual(o["ident500"], 500, o)
        self.assertEqual(o["ident80"], 80, o)


@unittest.skipUnless(_node_bin(), "node is required to execute extracted judge helpers")
class TestFlukeCannotLead(unittest.TestCase):
    def test_n2_spike_loses_to_n4_evening_on_conservative_rank(self):
        o = _run(
            r"""
const posts=[];
for(let i=0;i<32;i++) posts.push(post(0,8+(i%8),3000+i));
for(let i=0;i<4;i++) posts.push(post(1,20,6000+i*20));
posts.push(post(4,3,52000), post(4,3,48000));
const heat=heatOf(posts);
const hints=hintSlots(heat.stats,5);
const fluke=cell(heat.stats,4,3);
const eve=cell(heat.stats,1,20);
console.log(JSON.stringify({
  advice: heat.html,
  hints: hints.map(t=>({d:t.d,h:t.h,n:t.n,low:t.low})),
  hintable2: judgeHintable(2),
  hintable3: judgeHintable(3),
  hintable4: judgeHintable(4),
  flukeLow: fluke&&fluke.low,
  eveLow: eve&&eve.low,
  flukeShrink: fluke&&fluke.shrink,
  eveShrink: eve&&eve.shrink,
  flukeOp: judgeOpacity(2),
  eveOp: judgeOpacity(4)
}));
"""
        )
        self.assertFalse(o["hintable2"], o)
        self.assertTrue(o["hintable3"], o)
        self.assertTrue(o["hintable4"], o)
        self.assertTrue(o["hints"], o)
        self.assertEqual((o["hints"][0]["d"], o["hints"][0]["h"]), (1, 20), o)
        self.assertFalse(any(h["d"] == 4 and h["h"] == 3 for h in o["hints"]), o)
        self.assertNotIn("03:00", o["advice"], o)
        self.assertGreater(o["flukeShrink"], o["eveShrink"], o)
        self.assertLess(o["flukeOp"], 0.55, o)
        self.assertGreater(o["eveOp"], o["flukeOp"] * 1.3, o)
        self.assertIn("Strongest so far", o["advice"], o)
        self.assertIn("Tue 20:00", o["advice"], o)
        self.assertNotIn("Best time to post", o["advice"], o)


@unittest.skipUnless(_node_bin(), "node is required to execute extracted judge helpers")
class TestBarsN4VsN40(unittest.TestCase):
    def test_same_median_n4_is_fainter_hint_n40_is_full(self):
        o = _run(
            r"""
const pool=[];
for(let i=0;i<80;i++) pool.push(3000);
const rows=[
  {label:'Evening', n:4, medImp:8000},
  {label:'Morning', n:40, medImp:8000}
];
lastBars=null;
miniBars(rows,'medImp',pool);
const data=(lastBars&&lastBars.option&&lastBars.option.series&&lastBars.option.series[0]&&lastBars.option.series[0].data)||[];
const a=data[0]||{}, b=data[1]||{};
console.log(JSON.stringify({
  shrink4: shrinkImp(8000,4,3000),
  shrink40: shrinkImp(8000,40,3000),
  tone4: judgeTone(8000,pool,4,3000),
  tone40: judgeTone(8000,pool,40,3000),
  lab4: judgeLabel(judgeTone(8000,pool,4,3000),4),
  lab40: judgeLabel(judgeTone(8000,pool,40,3000),40),
  op4: a.itemStyle&&a.itemStyle.opacity,
  op40: b.itemStyle&&b.itemStyle.opacity,
  decal4: !!(a.itemStyle&&a.itemStyle.decal),
  decal40: !!(b.itemStyle&&b.itemStyle.decal),
  len4: a.value,
  len40: b.value,
  color4: a.itemStyle&&a.itemStyle.color,
  color40: b.itemStyle&&b.itemStyle.color
}));
"""
        )
        self.assertEqual(o["len4"], 8000, o)
        self.assertEqual(o["len40"], 8000, o)
        self.assertLess(o["shrink4"], o["shrink40"], o)
        self.assertLess(o["op4"], o["op40"], o)
        self.assertTrue(o["decal4"], o)
        self.assertFalse(o["decal40"], o)
        self.assertIn("hint (not proven)", o["lab4"], o)
        self.assertNotIn("hint", o["lab40"], o)
        self.assertIn(o["tone40"], ("green", "yellow"), o)
        self.assertNotIn("64748b", (o["color4"] or "").lower(), o)
        self.assertNotIn("64748b", (o["color40"] or "").lower(), o)


@unittest.skipUnless(_node_bin(), "node is required to execute extracted judge helpers")
class TestExistingFixtureShape(unittest.TestCase):
    def test_demo_like_n6_is_proven_and_n2_is_coloured_hint(self):
        o = _run(
            r"""
const posts=fixturePosts();
const heat=heatOf(posts);
const tue=cell(heat.stats,1,20);
const thin=cell(heat.stats,4,3);
const tueM=mappedCell(1,20);
const thinM=mappedCell(4,3);
const tops=topSlots(heat.stats,3);
console.log(JSON.stringify({
  advice: heat.html,
  proven: tops.map(t=>({d:t.d,h:t.h,n:t.n})),
  tueN: tue&&tue.n,
  tueFull: !!(tue&&tue.full),
  tueHint: !!(tueM&&tueM.hint),
  tueTone: tue&&tue.tone,
  thinN: thin&&thin.n,
  thinFull: !!(thin&&thin.full),
  thinHint: !!(thinM&&thinM.hint),
  thinTone: thin&&thin.tone,
  thinColor: thinM&&thinM.itemStyle&&thinM.itemStyle.color,
  legend: judgeLegend()
}));
"""
        )
        self.assertEqual(o["tueN"], 6, o)
        self.assertEqual(o["thinN"], 2, o)
        self.assertTrue(o["tueFull"], o)
        self.assertFalse(o["tueHint"], o)
        self.assertFalse(o["thinFull"], o)
        self.assertTrue(o["thinHint"], o)
        self.assertIn(o["thinTone"], ("green", "yellow", "orange", "red"), o)
        self.assertNotIn("64748b", (o["thinColor"] or "").lower(), o)
        self.assertTrue(any(p["d"] == 1 and p["h"] == 20 for p in o["proven"]), o)
        self.assertFalse(any(p["d"] == 4 and p["h"] == 3 for p in o["proven"]), o)
        self.assertIn("Best time to post", o["advice"], o)
        self.assertIn("your usual post", o["legend"], o)
        self.assertIn("hint", o["legend"].lower(), o)


if __name__ == "__main__":
    unittest.main()
