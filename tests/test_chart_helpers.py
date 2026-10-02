#!/usr/bin/env python3
"""Source + Node checks for chart helpers (outlier cap, legend, heatmap, axes)."""
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


class TestTemplateChartHelpersSource(unittest.TestCase):
    def test_axis_last_label_end_anchored_and_readable(self):
        self.assertIn("function axFont", TEMPLATE)
        self.assertIn("function xLabels", TEMPLATE)
        self.assertIn("function chartMargins", TEMPLATE)
        self.assertIn('text-anchor="${anc}"', TEMPLATE)
        self.assertIn("i===n-1", TEMPLATE)
        mq = TEMPLATE
        self.assertNotRegex(
            TEMPLATE.split("function xLabels", 1)[1].split("function ", 1)[0],
            r'text-anchor="middle"',
        )
        self.assertIn("maxTicks", TEMPLATE)

    def test_outlier_cap_and_clipped_bar_marker(self):
        self.assertIn("function pctile", TEMPLATE)
        self.assertIn("function robustYMax", TEMPLATE)
        self.assertIn("0.95", TEMPLATE)
        self.assertIn("*1.5", TEMPLATE)
        self.assertIn("function barChart", TEMPLATE)
        self.assertIn("robustYMax(", TEMPLATE)
        self.assertIn("out-mark", TEMPLATE)

    def test_zero_series_filtered_from_legend(self):
        self.assertIn("function liveSeries", TEMPLATE)
        self.assertIn("liveSeries(", TEMPLATE)
        bar = _extract_fn(TEMPLATE, "barChart")
        self.assertIn("liveSeries", bar)
        self.assertIn("function legend", TEMPLATE)

    def test_prev_period_must_be_fully_covered(self):
        self.assertIn("function prevFullyCovered", TEMPLATE)
        self.assertIn("function alignPrev", TEMPLATE)
        gate = _extract_fn(TEMPLATE, "prevFullyCovered")
        self.assertIn("minDataDate", gate)
        pair = _extract_fn(TEMPLATE, "deltaPair")
        self.assertIn("prevFullyCovered", pair)

    def test_heatmap_sparsity_fold_and_empty_copy(self):
        self.assertIn("function heatCoverage", TEMPLATE)
        self.assertIn("function heatPanel", TEMPLATE)
        self.assertIn("HEAT_MIN_COV", TEMPLATE)
        self.assertIn("0.25", TEMPLATE)
        self.assertIn("Not enough data yet", TEMPLATE)
        self.assertIn("heatPanel('Best time to post'", TEMPLATE)
        self.assertIn("heatPanel('Best reply time'", TEMPLATE)

    def test_mini_top_omits_unknown_media(self):
        self.assertIn("function topKind", TEMPLATE)
        mini = _extract_fn(TEMPLATE, "miniTop")
        self.assertIn("topKind", mini)
        self.assertNotIn("TYPE_NL[p.type])} · ${esc(mediaNL(p.media))", mini)
        self.assertIn(".top-metrics{", TEMPLATE)
        self.assertIn("white-space:nowrap", TEMPLATE)

    def test_impressions_top_list_shows_unit(self):
        mini = _extract_fn(TEMPLATE, "miniTop")
        self.assertRegex(
            mini,
            r"primary=key==='er'\?fP\(p\.er\):fN\(p\.impressions\)\+' impr\.'",
        )
        self.assertIn("function reasonLbl", TEMPLATE)
        self.assertIn("geschorst", TEMPLATE)
        self.assertIn("suspended", TEMPLATE)

    def test_desktop_custom_dates_are_reachable(self):
        base = TEMPLATE.split("@media", 1)[0]
        self.assertNotIn(".bar-custom>summary{display:none", base)
        self.assertIn(".bar-custom>summary{", base)
        self.assertIn(".bar-custom[open]", TEMPLATE)

    def test_axis_css_does_not_force_user_unit_px(self):
        self.assertIn("function leftPad", TEMPLATE)
        self.assertIn("function axFmt", TEMPLATE)
        self.assertIn("+'K'", TEMPLATE)
        self.assertNotIn("+'k'", TEMPLATE)
        css = TEMPLATE.split("<style>", 1)[1].split("</style>", 1)[0]
        self.assertNotRegex(css, r"svg\.ch[^{]*\{[^}]*font-size:\s*\d+px")
        self.assertNotRegex(css, r"svg\.ch \.ax\{[^}]*font-size:\s*\d+px")
        self.assertNotRegex(css, r"\.out-lab\{[^}]*font-size:\s*\d+px")
        self.assertIn("function chartDisplayWidth", TEMPLATE)
        self.assertIn("fitAxisFonts", TEMPLATE)

    def test_y_ticks_follow_plot_height(self):
        charts = TEMPLATE.split("/* ---------- SVG charts ---------- */", 1)[-1][:4500]
        self.assertIn("function chartPlot", charts)
        self.assertIn("function maxYTicks", charts)
        self.assertIn("function yTickVals", charts)
        plot = _extract_fn(TEMPLATE, "chartPlot")
        self.assertIn("140", plot)
        self.assertIn("120", plot)
        line = _extract_fn(TEMPLATE, "lineChart")
        bar = _extract_fn(TEMPLATE, "barChart")
        self.assertIn("chartPlot", line)
        self.assertIn("yTickVals", line)
        self.assertIn("chartPlot", bar)
        self.assertIn("yTickVals", bar)

    def test_mini_bars_keep_row_labels_on_narrow(self):
        mini = _extract_fn(TEMPLATE, "miniBars")
        self.assertIn("yCatLabelWidth", mini)
        self.assertIn("overflow:'truncate'", mini.replace(" ", ""))
        self.assertIn("hideOverlap:false", mini.replace(" ", ""))
        self.assertIn("metricBarShort", mini)
        self.assertIn("insideRight", mini)
        self.assertIn("type:'bar'", mini.replace(" ", ""))
        self.assertIn("judgeTone", mini)
        self.assertIn("judgeColor", mini)
        self.assertIn("judgeLabel", mini)
        self.assertIn("judgeOpacity", mini)
        self.assertIn("heatThinDecal", mini)

    def test_heatmap_reserves_phone_label_space(self):
        heat = _extract_fn(TEMPLATE, "heatSvg")
        self.assertIn("narrow", heat)
        self.assertIn("hour", heat)
        self.assertIn("hourStep", heat)
        self.assertRegex(heat, r"hourStep=narrow\?6")
        self.assertIn("visualMap", heat)
        self.assertIn("heatmap", heat)
        self.assertNotIn('y="12"', heat)
        yticks = _extract_fn(TEMPLATE, "yTickVals")
        self.assertIn("nextNiceStep", yticks)

    def test_mini_bars_pad_first_label_on_narrow(self):
        mini = _extract_fn(TEMPLATE, "miniBars")
        self.assertIn("containLabel:true", mini.replace(" ", ""))
        self.assertIn("yCatLabelWidth", mini)
        self.assertIn("function compactN", TEMPLATE)
        self.assertIn("judgeLegend", _extract_fn(TEMPLATE, "canvasBest"))
        self.assertIn("function judgeTone", TEMPLATE)
        self.assertIn("function judgeLegend", TEMPLATE)
        self.assertIn("const JUDGE_K=", TEMPLATE)
        self.assertIn("function shrinkImp", TEMPLATE)
        self.assertIn("function hintSlots", TEMPLATE)
        self.assertIn("function judgeLow", TEMPLATE)
        self.assertIn("function judgeHintable", TEMPLATE)
        self.assertIn("impressions", _extract_fn(TEMPLATE, "metricBarLabel"))
        self.assertIn("confine:true", mini.replace(" ", ""))

    def test_chart_tooltips_are_confined(self):
        for name in ("lineChart", "barChart", "comboChart", "miniBars", "heatSvg"):
            fn = _extract_fn(TEMPLATE, name)
            self.assertIn("confine:true", fn.replace(" ", ""), name)
        themes = TEMPLATE.split("function registerThemes", 1)[-1][:1800]
        self.assertGreaterEqual(themes.replace(" ", "").count("confine:true"), 2)


@unittest.skipUnless(_node_bin(), "node is required to execute extracted chart helpers")
class TestChartHelpersNode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = _node_bin()
        bits = [
            "const MINN=5;",
            "const HEAT_MIN_COV=0.25;",
            _extract_fn(TEMPLATE, "pctile"),
            _extract_fn(TEMPLATE, "robustYMax"),
            _extract_fn(TEMPLATE, "liveSeries"),
            _extract_fn(TEMPLATE, "heatCoverage"),
            _extract_fn(TEMPLATE, "chartDisplayWidth"),
            _extract_fn(TEMPLATE, "axFont"),
            _extract_fn(TEMPLATE, "axFmt"),
            _extract_fn(TEMPLATE, "compactN"),
            _extract_fn(TEMPLATE, "leftPad"),
            _extract_fn(TEMPLATE, "chartMargins"),
            _extract_fn(TEMPLATE, "maxYTicks"),
            _extract_fn(TEMPLATE, "nextNiceStep"),
            _extract_fn(TEMPLATE, "yTickVals"),
            _extract_fn(TEMPLATE, "chartPlot"),
            _extract_fn(TEMPLATE, "niceStep"),
            _extract_fn(TEMPLATE, "reasonLbl"),
            r"""
const spike = Array(29).fill(100).concat([29000]);
const cap = robustYMax(spike);
const even = robustYMax([10,12,11,9,10]);
const live = liveSeries([
  {name:'posts', vals:{a:1,b:0}},
  {name:'reposts', vals:{a:0,b:0}},
  {name:'quotes', vals:{}}
]);
const sparse={};
for (let d=0; d<7; d++) for (let h=0; h<24; h++) sparse[d+'-'+h] = {n: (d===0 && h<5) ? 5 : 0};
const dense={};
let nOk=0;
for (let d=0; d<7; d++) for (let h=0; h<24; h++) {
  const ok = nOk < 42;
  if (ok) nOk++;
  dense[d+'-'+h] = {n: ok ? 5 : 0};
}
const labels375 = ['8K','15%','100','40'];
const m375 = chartMargins(375, labels375);
const m580 = chartMargins(580, labels375);
const m1280 = chartMargins(1280, labels375);
const fs375 = m375.fs;
const widest = Math.max(...labels375.map(s => s.length * fs375 * 0.62));
const screenPx = (fs, w) => fs * w / 900;
const out = {
  cap,
  even,
  liveNames: live.map(s=>s.name),
  sparse: heatCoverage(sparse),
  dense: heatCoverage(dense),
  ax375: axFont(375),
  ax900: axFont(900),
  m375,
  m1280,
  fmt8k: axFmt(8000),
  fmt2k: axFmt(2000),
  fmt15: axFmt(0.15, true),
  compact1525: compactN(1525),
  compact640: compactN(640),
  compact15k: compactN(15000),
  leftCovers: m375.L >= widest + 6,
  topPad: m375.T >= fs375,
  bottomPad: m375.B >= fs375 + 8,
  px375: screenPx(m375.fs, 375),
  px580: screenPx(m580.fs, 580),
  px1280: screenPx(m1280.fs, 1280),
  reasonUnf: reasonLbl('ontvolger'),
  reasonDel: reasonLbl('verwijderd'),
  reasonSus: reasonLbl('geschorst'),
  reasonFree: reasonLbl('manual note'),
};
innerWidth = 375;
const p375 = chartPlot({});
const p375fold = chartPlot({half:1,h:180});
innerWidth = 1280;
const p1280 = chartPlot({});
const p1280fold = chartPlot({half:1,h:180});
out.p375 = p375;
out.p375fold = p375fold;
out.p1280 = p1280;
out.p1280fold = p1280fold;
out.maxY375 = maxYTicks(p375.plotPx, true);
out.maxY1280fold = maxYTicks(p1280fold.plotPx, false);
out.step3 = niceStep(100, 3);
function tickGaps(vals){
  const g=[];
  for(let i=1;i<vals.length;i++) g.push(Math.round((vals[i]-vals[i-1])*1e6)/1e6);
  return g;
}
function evenlySpaced(vals){
  if(vals.length<2) return false;
  const g=tickGaps(vals);
  return g.every(x=>Math.abs(x-g[0])<1e-6);
}
const reduced = yTickVals(0,600,200,3);
out.reduced0600 = reduced;
out.reducedEven = evenlySpaced(reduced);
const grid=[];
const maxes=[50,80,100,200,250,400,600,800,1000,1200,2500,9999];
const counts=[2,3,4,5];
for (const hi of maxes) for (const n of counts) {
  const st=niceStep(hi,n);
  const lo=0;
  const start=Math.floor(lo/st)*st;
  const end=Math.ceil(hi/st)*st;
  const vals=yTickVals(start,end,st,n);
  grid.push({hi,n,vals,even:evenlySpaced(vals),count:vals.length});
}
out.tickGrid = grid;
out.tickGridUneven = grid.filter(x=>!x.even || x.count>x.n || x.count<2);
console.log(JSON.stringify(out));
""",
        ]
        r = subprocess.run(
            [cls.node, "-e", "\n".join(bits)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise AssertionError(f"node helpers failed\n{r.stdout}\n{r.stderr}")
        cls.out = json.loads(r.stdout.strip().splitlines()[-1])

    def test_robust_ymax_clips_single_spike(self):
        self.assertLess(self.out["cap"], 1000)
        self.assertGreaterEqual(self.out["cap"], 150)
        self.assertAlmostEqual(self.out["even"], 12)

    def test_live_series_drops_all_zero(self):
        self.assertEqual(self.out["liveNames"], ["posts"])

    def test_heat_coverage_threshold(self):
        self.assertLess(self.out["sparse"], 0.25)
        self.assertGreaterEqual(self.out["dense"], 0.25)

    def test_axis_font_and_right_margin_scale(self):
        self.assertGreaterEqual(self.out["ax375"], 24)
        self.assertLessEqual(self.out["ax900"], 14)
        self.assertGreaterEqual(self.out["m375"]["R"], 44)
        self.assertGreaterEqual(self.out["m1280"]["R"], 44)
        self.assertLessEqual(self.out["m375"]["maxTicks"], 6)

    def test_y_ticks_compact_and_padded(self):
        self.assertEqual(self.out["fmt8k"], "8K")
        self.assertEqual(self.out["fmt2k"], "2K")
        self.assertEqual(self.out["fmt15"], "15%")
        self.assertEqual(self.out["compact1525"], "1.5K")
        self.assertEqual(self.out["compact640"], "640")
        self.assertEqual(self.out["compact15k"], "15K")
        self.assertTrue(self.out["leftCovers"], self.out)
        self.assertTrue(self.out["topPad"], self.out)
        self.assertTrue(self.out["bottomPad"], self.out)
        for key in ("px375", "px580", "px1280"):
            self.assertGreaterEqual(self.out[key], 11, self.out)
            self.assertLessEqual(self.out[key], 13, self.out)

    def test_reason_labels_english_passthrough_free_text(self):
        self.assertEqual(self.out["reasonUnf"], "unfollowed")
        self.assertEqual(self.out["reasonDel"], "deleted")
        self.assertEqual(self.out["reasonSus"], "suspended")
        self.assertEqual(self.out["reasonFree"], "manual note")

    def test_plot_height_and_y_tick_cap(self):
        self.assertGreaterEqual(self.out["p375"]["plotPx"], 135, self.out["p375"])
        self.assertLessEqual(self.out["p375"]["maxY"], 3, self.out["p375"])
        self.assertGreaterEqual(self.out["p375fold"]["plotPx"], 115, self.out["p375fold"])
        self.assertLessEqual(self.out["p375fold"]["maxY"], 3, self.out["p375fold"])
        self.assertLessEqual(self.out["p1280fold"]["maxY"], 6, self.out["p1280fold"])
        self.assertGreaterEqual(
            self.out["p1280fold"]["plotPx"] / max(self.out["p1280fold"]["maxY"], 1),
            16,
            self.out["p1280fold"],
        )
        self.assertLessEqual(self.out["maxY375"], 3)
        self.assertGreaterEqual(self.out["step3"], 50)

    def test_y_ticks_stay_evenly_spaced_when_reduced(self):
        reduced = self.out["reduced0600"]
        self.assertGreaterEqual(len(reduced), 2, reduced)
        self.assertLessEqual(len(reduced), 3, reduced)
        self.assertTrue(
            self.out["reducedEven"],
            f"0–600 with max 3 ticks must be even, got {reduced}",
        )
        gaps = [round(reduced[i] - reduced[i - 1], 6) for i in range(1, len(reduced))]
        self.assertEqual(len(set(gaps)), 1, f"uneven gaps {gaps} from {reduced}")
        uneven = self.out["tickGridUneven"]
        self.assertEqual(
            uneven, [],
            f"uneven or oversized tick sets: {uneven[:8]}",
        )


class TestRound3SourceGuards(unittest.TestCase):
    def test_forecast_helpers_and_no_pace_fallback(self):
        self.assertIn("function forecastHorizon", TEMPLATE)
        self.assertIn("function forecastBand", TEMPLATE)
        self.assertIn("function followersOn", TEMPLATE)
        self.assertIn("function paceOverDays", TEMPLATE)
        self.assertNotIn("if(!base)base=a[0]", TEMPLATE)
        pace = _extract_fn(TEMPLATE, "paceOverDays")
        self.assertIn("followersOn", pace)
        self.assertNotIn("base=a[0]", pace)
        band = _extract_fn(TEMPLATE, "forecastBand")
        self.assertIn("width", band)
        line = _extract_fn(TEMPLATE, "lineChart")
        self.assertIn("widths.some", line)
        self.assertIn("band-hi", line)
        self.assertIn("function chartDays", TEMPLATE)

    def test_outlier_uses_markpoint_not_legend_scatter(self):
        combo = _extract_fn(TEMPLATE, "comboChart")
        self.assertIn("markPoint", combo)
        self.assertIn("out-mark", combo)
        self.assertNotIn("type:'scatter'", combo.replace(" ", ""))
        self.assertIn("legend:{top:0,data:ser.map", combo.replace("\n", ""))
        bar = _extract_fn(TEMPLATE, "barChart")
        self.assertIn("markPoint", bar)
        self.assertIn("out-mark", bar)

    def test_heatmap_range_and_reply_tooltip(self):
        heat = _extract_fn(TEMPLATE, "heatSvg")
        self.assertIn("heatRange", heat)
        self.assertIn("cellVals", heat)
        self.assertIn("rng.min", heat)
        self.assertIn("rng.max", heat)
        self.assertIn("reply", heat)
        self.assertIn("pluralize", heat)
        self.assertIn("median ", heat)
        self.assertIn("impr.", heat)
        self.assertIn("heatMapped", heat)
        self.assertIn("heatColors", heat)
        self.assertIn("judgeTone", heat)
        self.assertIn("judgeLegend", heat)
        self.assertIn("judgeLabel", heat)
        self.assertIn("shrinkImp", heat)
        self.assertIn("judgeLow", heat)
        self.assertIn("slotAdviceHtml", heat)
        self.assertIn("judgeOpacity", heat)
        self.assertNotIn("heatThinDecal", heat)
        self.assertNotIn("not a recommendation", heat)
        self.assertIn("hint (not proven)", TEMPLATE)
        self.assertIn("tlHex", _extract_fn(TEMPLATE, "heatColors"))
        self.assertIn("22c55e", _extract_fn(TEMPLATE, "tlHex"))
        self.assertIn("function heatRange", TEMPLATE)
        self.assertNotIn("0c1929", heat)

    def test_hover_syncs_by_date_not_connect(self):
        self.assertIn("function bindDateHover", TEMPLATE)
        self.assertIn("__xdashDays", TEMPLATE)
        self.assertIn("indexOf(day)", TEMPLATE)
        self.assertNotIn("echarts.connect('dash-time')", TEMPLATE)
        self.assertNotIn("c.group='dash-time'", TEMPLATE)

    def test_compare_disabled_copy_and_prev_scale(self):
        self.assertIn("Not enough history", TEMPLATE)
        self.assertIn("function syncCompareUi", TEMPLATE)
        self.assertIn("cmp.disabled=!ok", TEMPLATE)
        combo = _extract_fn(TEMPLATE, "comboChart")
        self.assertIn("prevImp", combo)
        self.assertNotIn("scale.push", combo)
        self.assertIn("robustYMax(tot)", combo)
        self.assertIn("clipPrevLine", combo)
        self.assertIn("prevPointCount", combo)
        self.assertIn("function chartDays", TEMPLATE)
        self.assertIn("cmp-hint", TEMPLATE)
        self.assertIn("Not enough history", _extract_fn(TEMPLATE, "syncCompareUi"))

    def test_length_merge_and_metric_labels(self):
        best = _extract_fn(TEMPLATE, "canvasBest")
        self.assertIn("long_form", best)
        self.assertIn("?'long'", best)
        self.assertNotIn("Long-form", best)
        self.assertIn("median impressions", best)
        self.assertIn("function metricBarLabel", TEMPLATE)
        self.assertIn("median ", _extract_fn(TEMPLATE, "metricBarLabel"))

    def test_mobile_chips_and_menu_close(self):
        self.assertIn('class="p-short"', TEMPLATE)
        self.assertIn(">7d<", TEMPLATE)
        self.assertIn(">30d<", TEMPLATE)
        self.assertIn(">90d<", TEMPLATE)
        self.assertIn("function closeMore", TEMPLATE)
        self.assertIn("pointerdown", TEMPLATE)
        css = TEMPLATE.split("<style>", 1)[1].split("</style>", 1)[0]
        self.assertIn(".top-metrics{display:none", css)
        mq = css.split("@media (max-width:640px)", 1)[1]
        self.assertIn(".p-short{display:inline}", mq.replace(" ", ""))
        self.assertIn("overflow-x:hidden", mq)
        self.assertIn("td.met", mq)
        self.assertIn("display:none", mq)

    def test_combo_scales_current_period_only(self):
        combo = _extract_fn(TEMPLATE, "comboChart")
        bar = _extract_fn(TEMPLATE, "barChart")
        self.assertIn("robustYMax(tot)", combo)
        self.assertIn("robustYMax(tot)", bar)
        self.assertNotIn("scale.push", combo)
        self.assertNotIn("scale.push", bar)
        self.assertIn("clipPrevLine", combo)
        self.assertIn("o.prevImp", combo)
        line = _extract_fn(TEMPLATE, "lineChart")
        self.assertIn("s.prev", line)
        self.assertIn("returnn?s:''", line.replace(" ", ""))


@unittest.skipUnless(_node_bin(), "node is required to execute extracted chart helpers")
class TestRound3NodeHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = _node_bin()
        bits = [
            _extract_fn(TEMPLATE, "addDays"),
            _extract_fn(TEMPLATE, "dateDiffDays"),
            _extract_fn(TEMPLATE, "dayList"),
            _extract_fn(TEMPLATE, "heatRange"),
            _extract_fn(TEMPLATE, "forecastBand"),
            _extract_fn(TEMPLATE, "stdev"),
            _extract_fn(TEMPLATE, "dailyChanges"),
            _extract_fn(TEMPLATE, "ratesClose"),
            _extract_fn(TEMPLATE, "prevPointCount"),
            r"""
const S = [
  {date:'2026-08-01', followers_count:100},
  {date:'2026-08-20', followers_count:120},
  {date:'2026-09-18', followers_count:130},
  {date:'2026-09-25', followers_count:200}
];
function snapsWithFc(){return S.filter(s=>s.followers_count!=null);}
"""
            + _extract_fn(TEMPLATE, "followersOn")
            + "\n"
            + _extract_fn(TEMPLATE, "paceOverDays")
            + r"""
const state={start:'2026-08-27',end:'2026-09-25',preset:'30'};
function minDataDate(){return '2026-08-20';}
function prevRange(){const n=dateDiffDays(state.start,state.end)+1;const end=addDays(state.start,-1);return {start:addDays(end,-(n-1)),end};}
"""
            + _extract_fn(TEMPLATE, "forecastHorizon")
            + "\n"
            + _extract_fn(TEMPLATE, "chartDays")
            + "\n"
            + _extract_fn(TEMPLATE, "firstFollowerDate")
            + "\n"
            + _extract_fn(TEMPLATE, "followerDays")
            + "\n"
            + _extract_fn(TEMPLATE, "prevFullyCovered")
            + r"""
const p7=paceOverDays(7);
const p30=paceOverDays(30);
const fDays=['2026-09-25','2026-09-26','2026-09-27'];
const center=Object.fromEntries(fDays.map((d,i)=>[d,200+10*(i)]));
const band0=forecastBand(center,fDays,'2026-09-25',200,0);
const bandW=forecastBand(center,fDays,'2026-09-25',200,20);
const heatFlat=heatRange([14,14,14]);
const heatWide=heatRange([14,80,144,null]);
const heatEmpty=heatRange([null,undefined]);
const days90=(()=>{state.start='2026-06-28';state.end='2026-09-25';return chartDays();})();
state.start='2026-08-27';state.end='2026-09-25';
const covered30=prevFullyCovered();
state.start='2026-09-19';state.end='2026-09-25';
const covered7=prevFullyCovered();
const hor30=(()=>{state.start='2026-08-27';state.end='2026-09-25';return forecastHorizon(30);})();
const hor7=(()=>{state.start='2026-09-19';state.end='2026-09-25';return forecastHorizon(7);})();
const lateDays=(()=>{
  const saved=S.slice();
  S.length=0;
  S.push({date:'2026-09-23',followers_count:100},{date:'2026-09-24',followers_count:110},{date:'2026-09-25',followers_count:120});
  state.start='2026-09-01';state.end='2026-09-25';
  const days=followerDays();
  const nActual=days.filter(d=>S.some(s=>s.date===d)).length||days.length;
  const hor=forecastHorizon(nActual);
  const first=firstFollowerDate();
  S.length=0; saved.forEach(s=>S.push(s));
  state.start='2026-08-27';state.end='2026-09-25';
  return {first:days[0], firstDate:first, nActual, hor, share:nActual/(nActual+hor)};
})();
const shortS=[
  {date:'2026-09-15', followers_count:100},
  {date:'2026-09-25', followers_count:200}
];
const saved=S.slice();
S.length=0; shortS.forEach(s=>S.push(s));
const short30=paceOverDays(30);
const short7=paceOverDays(7);
S.length=0; saved.forEach(s=>S.push(s));
const out={
  p7: p7 && p7.perDay,
  p30: p30 && p30.perDay,
  p7from: p7 && p7.from,
  p30from: p30 && p30.from,
  band0: band0.width,
  bandW: bandW.width,
  heatFlat,
  heatWide,
  heatEmpty,
  days90first: days90[0],
  days90hasJune: days90.some(d=>d < '2026-08-20'),
  covered30,
  covered7,
  hor30,
  hor7,
  short30,
  short7: short7 && short7.perDay,
  prevPts: prevPointCount({a:1,b:null}),
  ratesSame: ratesClose(2,2),
  ratesDiff: ratesClose(2,3),
  lateFol: lateDays
};
console.log(JSON.stringify(out));
""",
        ]
        r = subprocess.run(
            [cls.node, "-e", "\n".join(bits)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise AssertionError(f"node round3 helpers failed\n{r.stdout}\n{r.stderr}")
        cls.out = json.loads(r.stdout.strip().splitlines()[-1])

    def test_band_width_positive_when_forecasts_differ(self):
        self.assertGreater(self.out["band0"], 0, self.out)
        self.assertGreater(self.out["bandW"], 0, self.out)
        self.assertGreaterEqual(self.out["band0"], 4, self.out)

    def test_forecast_paces_differ_when_growth_is_uneven(self):
        self.assertIsNotNone(self.out["p7"], self.out)
        self.assertIsNotNone(self.out["p30"], self.out)
        self.assertNotAlmostEqual(self.out["p7"], self.out["p30"], places=6)
        self.assertEqual(self.out["p7from"], "2026-09-18")
        self.assertEqual(self.out["p30from"], "2026-08-26")

    def test_short_history_does_not_invent_30d_pace(self):
        self.assertIsNone(self.out["short30"], self.out)
        self.assertIsNotNone(self.out["short7"], self.out)

    def test_heat_range_matches_data_not_zero_one(self):
        self.assertEqual(self.out["heatWide"]["min"], 14)
        self.assertEqual(self.out["heatWide"]["max"], 144)
        self.assertNotEqual(self.out["heatWide"]["max"], 1)
        self.assertEqual(self.out["heatEmpty"]["min"], 0)
        self.assertEqual(self.out["heatEmpty"]["max"], 1)

    def test_axis_starts_at_first_data_day(self):
        self.assertEqual(self.out["days90first"], "2026-08-20")
        self.assertFalse(self.out["days90hasJune"], self.out)

    def test_compare_coverage_and_horizon(self):
        self.assertFalse(self.out["covered30"])
        self.assertTrue(self.out["covered7"])
        self.assertLessEqual(self.out["hor30"], 16)
        self.assertGreater(self.out["hor30"], 0)
        actual_share = 30 / (30 + self.out["hor30"])
        self.assertGreaterEqual(actual_share, 0.64)
        self.assertLessEqual(self.out["hor7"], 7)
        self.assertEqual(self.out["prevPts"], 1)
        self.assertTrue(self.out["ratesSame"])
        self.assertFalse(self.out["ratesDiff"])

    def test_followers_axis_starts_at_first_snapshot(self):
        late = self.out["lateFol"]
        self.assertEqual(late["first"], "2026-09-23", late)
        self.assertEqual(late["firstDate"], "2026-09-23", late)
        self.assertGreaterEqual(late["share"], 0.65, late)
        self.assertLessEqual(late["hor"], 30, late)


class TestRound4SourceGuards(unittest.TestCase):
    def test_current_only_scale_and_clip_prev(self):
        self.assertIn("function clipPrevLine", TEMPLATE)
        self.assertIn("function outMarkStyle", TEMPLATE)
        combo = _extract_fn(TEMPLATE, "comboChart")
        bar = _extract_fn(TEMPLATE, "barChart")
        line = _extract_fn(TEMPLATE, "lineChart")
        self.assertIn("robustYMax(tot)", combo)
        self.assertIn("clipPrevLine(o.prevImp", combo)
        self.assertIn("robustYMax(tot)", bar)
        self.assertIn("clipPrevLine(o.prevLine.vals", bar)
        self.assertIn("s.prev", line)
        self.assertNotIn("0c1929", TEMPLATE.split("function heatSvg", 1)[1][:2500])

    def test_follower_axis_and_uncertainty_band(self):
        self.assertIn("function followerDays", TEMPLATE)
        self.assertIn("function firstFollowerDate", TEMPLATE)
        self.assertIn("function stdev", TEMPLATE)
        self.assertIn("function dailyChanges", TEMPLATE)
        fol = _extract_fn(TEMPLATE, "canvasFollowers")
        self.assertIn("followerDays()", fol)
        self.assertIn("forecastHorizon(nActual)", fol)
        self.assertIn("snaps.length>=3", fol.replace(" ", ""))
        band = _extract_fn(TEMPLATE, "forecastBand")
        self.assertIn("0.01", band)
        self.assertIn("Math.sqrt", band)
        hor = _extract_fn(TEMPLATE, "forecastHorizon")
        self.assertNotIn("periodLen", hor)

    def test_heatmap_sqrt_and_contrast_helpers(self):
        self.assertIn("function heatMapped", TEMPLATE)
        self.assertIn("function heatLowColor", TEMPLATE)
        self.assertIn("function heatEmptyColor", TEMPLATE)
        self.assertIn("function contrastRatio", TEMPLATE)
        mapped = _extract_fn(TEMPLATE, "heatMapped")
        self.assertIn("Math.sqrt", mapped)
        heat = _extract_fn(TEMPLATE, "heatSvg")
        self.assertIn("visualMap:{show:false,min:0,max:1", heat.replace("\n", ""))
        self.assertIn("__xdashHeat", heat)
        self.assertIn("emptyC", heat)

    def test_inline_compare_hint_and_shown_range(self):
        self.assertIn('id="cmp-hint"', TEMPLATE)
        self.assertIn('id="shown-range"', TEMPLATE)
        self.assertIn("function shownRangeLabel", TEMPLATE)
        sync = _extract_fn(TEMPLATE, "syncCompareUi")
        self.assertIn("cmp-hint", sync)
        self.assertIn("is-on", sync)
        render = _extract_fn(TEMPLATE, "render")
        self.assertIn("shownRangeLabel", render)
        self.assertIn("shown-range", render)
        css = TEMPLATE.split("<style>", 1)[1].split("</style>", 1)[0]
        mq = css.split("@media (max-width:640px)", 1)[1]
        self.assertIn(".shown-range{display:block}", mq.replace(" ", ""))
        self.assertIn(".cmp-hint.is-on", css.replace(" ", ""))


@unittest.skipUnless(_node_bin(), "node is required to execute extracted chart helpers")
class TestRound4NodeHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = _node_bin()
        bits = [
            _extract_fn(TEMPLATE, "addDays"),
            _extract_fn(TEMPLATE, "dateDiffDays"),
            _extract_fn(TEMPLATE, "dayList"),
            _extract_fn(TEMPLATE, "pctile"),
            _extract_fn(TEMPLATE, "robustYMax"),
            _extract_fn(TEMPLATE, "niceStep"),
            _extract_fn(TEMPLATE, "nextNiceStep"),
            _extract_fn(TEMPLATE, "yTickVals"),
            _extract_fn(TEMPLATE, "clipPrevLine"),
            _extract_fn(TEMPLATE, "forecastBand"),
            _extract_fn(TEMPLATE, "stdev"),
            _extract_fn(TEMPLATE, "dailyChanges"),
            _extract_fn(TEMPLATE, "heatMapped"),
            _extract_fn(TEMPLATE, "hexLum"),
            _extract_fn(TEMPLATE, "contrastRatio"),
            _extract_fn(TEMPLATE, "heatTheme"),
            _extract_fn(TEMPLATE, "heatEmptyColor"),
            _extract_fn(TEMPLATE, "tlHex"),
            _extract_fn(TEMPLATE, "heatLowColor"),
            _extract_fn(TEMPLATE, "heatColors"),
            r"""
const days=['2026-09-19','2026-09-20','2026-09-21','2026-09-22','2026-09-23','2026-09-24','2026-09-25'];
const tot=[1200,1800,2973,900,1100,1400,1600];
const prev={};
days.forEach((d,i)=>{prev[d]= i===0 ? 400000 : 800+i*10;});
const cap=robustYMax(tot);
const yvs=yTickVals(0,cap,niceStep(cap,5),5);
const hi=yvs[yvs.length-1];
const clipped=clipPrevLine(prev,hi,days);
const bothScale=robustYMax(tot.concat(Object.values(prev)));
const center=Object.fromEntries(['2026-09-25','2026-09-26','2026-09-27'].map((d,i)=>[d,200+i]));
const band3=forecastBand(center,['2026-09-25','2026-09-26','2026-09-27'],'2026-09-25',200,0);
const snaps=[
  {date:'2026-09-23',followers_count:100},
  {date:'2026-09-24',followers_count:108},
  {date:'2026-09-25',followers_count:120}
];
const std=stdev(dailyChanges(snaps));
const bandVar=forecastBand(center,['2026-09-25','2026-09-26','2026-09-27'],'2026-09-25',120,std);
const mappedLow=heatMapped(14,14,144);
const mappedMid=heatMapped(14+(144-14)/2,14,144);
const mappedHi=heatMapped(144,14,144);
const mappedFlat=heatMapped(14,14,14);
const globalDocument={documentElement:{_t:'dark',getAttribute(){return this._t;},setAttribute(k,v){if(k==='data-theme')this._t=v;}}};
global.document=globalDocument;
const darkLow=heatLowColor();
const darkEmpty=heatEmptyColor();
document.documentElement._t='light';
const lightLow=heatLowColor();
const lightEmpty=heatEmptyColor();
const out={
  cap, hi, bothScale,
  clippedVals: clipped.data.map(p=>p&&p.value),
  clippedRaws: clipped.data.map(p=>p&&p.raw),
  markValues: clipped.marks.map(m=>m.value),
  markNames: clipped.marks.map(m=>m.name),
  band3: band3.width,
  bandVar: bandVar.width,
  std,
  mappedLow, mappedMid, mappedHi, mappedFlat,
  darkLow, darkEmpty, lightLow, lightEmpty,
  darkLowC: contrastRatio(darkLow,'#121820'),
  darkEmptyC: contrastRatio(darkEmpty,'#121820'),
  lightLowC: contrastRatio(lightLow,'#ffffff'),
  lightEmptyC: contrastRatio(lightEmpty,'#ffffff'),
  colorsLight: (document.documentElement._t='light', heatColors()),
};
console.log(JSON.stringify(out));
""",
        ]
        r = subprocess.run(
            [cls.node, "-e", "\n".join(bits)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise AssertionError(f"node round4 helpers failed\n{r.stdout}\n{r.stderr}")
        cls.out = json.loads(r.stdout.strip().splitlines()[-1])

    def test_prev_outlier_does_not_raise_current_axis(self):
        self.assertLess(self.out["hi"], 10000, self.out)
        self.assertLessEqual(self.out["hi"], self.out["cap"] * 2 + 1, self.out)
        self.assertGreater(self.out["bothScale"], 100000, self.out)
        self.assertIn(400000, self.out["markValues"], self.out)
        self.assertIn("out-mark", self.out["markNames"], self.out)
        self.assertTrue(all(v is None or v <= self.out["hi"] for v in self.out["clippedVals"]), self.out)
        self.assertIn(400000, self.out["clippedRaws"], self.out)

    def test_uncertainty_band_always_positive_with_three_points(self):
        self.assertGreater(self.out["band3"], 0, self.out)
        self.assertGreater(self.out["bandVar"], 0, self.out)
        self.assertGreaterEqual(self.out["band3"], 4, self.out)

    def test_heatmap_sqrt_mapping_and_contrast(self):
        self.assertEqual(self.out["mappedLow"], 0)
        self.assertEqual(self.out["mappedHi"], 1)
        self.assertAlmostEqual(self.out["mappedMid"], 0.5 ** 0.5, places=6)
        self.assertEqual(self.out["mappedFlat"], 0.5)
        self.assertGreater(self.out["darkLowC"], self.out["darkEmptyC"], self.out)
        self.assertGreater(self.out["lightLowC"], self.out["lightEmptyC"], self.out)
        self.assertGreaterEqual(self.out["darkLowC"], 2.0, self.out)
        self.assertGreaterEqual(self.out["lightLowC"], 1.8, self.out)
        self.assertGreaterEqual(self.out["darkEmptyC"], 1.15, self.out)
        self.assertGreaterEqual(self.out["lightEmptyC"], 1.05, self.out)
        colors = "".join(self.out["colorsLight"])
        self.assertIn("15803d", colors)
        self.assertIn("b91c1c", colors)
        self.assertNotIn("1e3a8a", colors)
        self.assertEqual(self.out["darkLow"], "#64748b")
        self.assertEqual(self.out["lightLow"], "#94a3b8")


@unittest.skipUnless(_node_bin(), "node is required to execute extracted chart helpers")
class TestJudgeScaleNode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = _node_bin()
        bits = [
            "const MINN=5;",
            "const JUDGE_K=3;",
            "const SCORE={lights:{green:75,yellow:50,orange:25}};",
            _extract_fn(TEMPLATE, "med"),
            _extract_fn(TEMPLATE, "percentileRank"),
            _extract_fn(TEMPLATE, "trafficLightScore"),
            _extract_fn(TEMPLATE, "tlHex"),
            _extract_fn(TEMPLATE, "heatTheme"),
            _extract_fn(TEMPLATE, "heatLowColor"),
            _extract_fn(TEMPLATE, "judgePeers"),
            _extract_fn(TEMPLATE, "judgeWeight"),
            _extract_fn(TEMPLATE, "shrinkLog"),
            _extract_fn(TEMPLATE, "shrinkImp"),
            _extract_fn(TEMPLATE, "judgeToneFromShrink"),
            _extract_fn(TEMPLATE, "judgeTone"),
            _extract_fn(TEMPLATE, "judgeLabel"),
            _extract_fn(TEMPLATE, "judgeColor"),
            r"""
const globalDocument={documentElement:{_t:'dark',getAttribute(){return this._t;}}};
global.document=globalDocument;
const peers=[14,80,144,400,900,2800];
const out={
  thin: judgeTone(2800, peers, 2),
  thinLabel: judgeLabel(judgeTone(2800, peers, 2), 2),
  thinColor: judgeColor(judgeTone(2800, peers, 2)),
  strong: judgeTone(2800, peers, 6),
  strongLabel: judgeLabel(judgeTone(2800, peers, 6), 6),
  weak: judgeTone(14, peers, 6),
  weakLabel: judgeLabel(judgeTone(14, peers, 6), 6),
  midAlone: judgeTone(500, [500], 6),
  midEqual: judgeTone(80, [80,80,80], 8),
  grey: heatLowColor(),
  peers: judgePeers([null, 3, undefined, 9])
};
console.log(JSON.stringify(out));
""",
        ]
        r = subprocess.run(
            [cls.node, "-e", "\n".join(bits)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise AssertionError(f"node judge helpers failed\n{r.stdout}\n{r.stderr}")
        cls.out = json.loads(r.stdout.strip().splitlines()[-1])

    def test_thin_data_is_a_hint_not_grey(self):
        self.assertIn(self.out["thin"], ("green", "yellow", "orange", "red"), self.out)
        self.assertNotEqual(self.out["thin"], "thin", self.out)
        self.assertIn("hint (not proven)", self.out["thinLabel"], self.out)
        self.assertNotEqual(self.out["thinColor"], "#64748b", self.out)
        self.assertEqual(self.out["grey"], "#64748b")

    def test_enough_data_uses_traffic_lights(self):
        self.assertEqual(self.out["strong"], "green")
        self.assertEqual(self.out["strongLabel"], "above your usual")
        self.assertEqual(self.out["weak"], "red")
        self.assertEqual(self.out["weakLabel"], "below your usual")
        self.assertEqual(self.out["midAlone"], "yellow")
        self.assertEqual(self.out["midEqual"], "yellow")
        self.assertEqual(self.out["peers"], [3, 9])
