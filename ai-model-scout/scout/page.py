"""Shared HTML shell and styles for the report and the model profile pages."""

HTML_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--fg:#1d1d1f;--muted:#6b6b70;--line:#e3e3e0;--accent:#3b5bdb;
--good:#2b8a3e;--ok:#b7791f;--bad:#c92a2a;--newbg:#fff3bf;--newfg:#7a5c00;
--s5:#b2f2bb;--s4:#d3f9d8;--s3:#fff3bf;--s2:#ffe8cc;--s1:#ffc9c9;--s0:transparent;--refbg:#f1f3f5}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--card:#1c1c1f;--fg:#ececee;--muted:#9a9aa2;
--line:#2c2c31;--accent:#8ea2ff;--good:#69db7c;--ok:#ffd43b;--bad:#ff8787;--newbg:#5c4a00;--newfg:#ffe066;
--s5:#1e5a2a;--s4:#2b4a31;--s3:#4d4417;--s2:#5a3b1c;--s1:#5c2626;--refbg:#232327}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 64px}
h1{margin:0;font-size:28px}h2{font-size:20px;margin:0 0 8px}h3{font-size:16px;margin:18px 0 6px}
.sub,.blurb,small,.empty{color:var(--muted)}a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin:16px 0}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.stat b{display:block;font-size:26px}.stat span{color:var(--muted);font-size:13px}
.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:8px;border-top:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;border-top:0}td small{display:block}
td.notes{color:var(--muted);min-width:260px}
.fit{white-space:nowrap;font-weight:600}.fit.gpu{color:var(--good)}.fit.offload,.fit.offload_slow,.fit.check{color:var(--ok)}
.fit.too_big{color:var(--bad)}.new{background:var(--newbg);color:var(--newfg);border-radius:6px;padding:1px 6px;
margin-left:6px;font-size:11px;font-weight:700}
ul.news{list-style:none;padding:0;margin:0}ul.news li{padding:7px 0;border-top:1px solid var(--line)}
ul.news small{display:block}.src{display:inline-block;min-width:92px;font-size:12px;color:var(--muted)}
table.matrix td:first-child{min-width:190px}table.matrix td.notes{min-width:220px}
table.matrix td.score{text-align:center;font-weight:700;min-width:44px}
.s5{background:var(--s5)}.s4{background:var(--s4)}.s3{background:var(--s3)}.s2{background:var(--s2)}
.s1{background:var(--s1)}.s0{color:var(--muted)}tr.ref td{background:var(--refbg)}
tr.ref td.score.s5{background:var(--s5)}tr.ref td.score.s4{background:var(--s4)}
tr.ref td.score.s3{background:var(--s3)}tr.ref td.score.s2{background:var(--s2)}tr.ref td.score.s1{background:var(--s1)}
.filter{display:block;margin:16px 0 0;font-weight:600;cursor:pointer}
body.onlyhere tr[data-fit=too_big]{display:none}
.brief li{margin:4px 0}code{background:var(--line);padding:1px 4px;border-radius:4px}
.goodfor{font-size:13px}.goodfor small{display:block;color:var(--muted)}
.profile-link{font-size:12px;white-space:nowrap}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:16px 0}
.facts div{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.facts span{display:block;color:var(--muted);font-size:13px}.facts b{font-weight:600}
.facts small{display:block;color:var(--muted);font-weight:400;font-size:13px}
.bars{display:grid;gap:10px;margin:12px 0}
.bar{display:grid;grid-template-columns:150px 1fr 190px;grid-template-rows:auto auto;column-gap:10px;align-items:center}
.bar span{grid-row:1/3;font-size:14px}.bar b{font-size:14px}
.track{height:12px;background:var(--line);border-radius:6px;overflow:hidden}
.track i{display:block;height:100%;border-radius:6px}.track i.me{background:var(--good)}
.track.ref{height:6px;margin-top:3px}.track.ref i{background:var(--muted)}.bar small{font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.proscons{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
ul.src{padding-left:18px;margin:6px 0}ul.src li{margin:4px 0;word-break:break-word}
@media (max-width:520px){.bar{grid-template-columns:96px 1fr 84px}}
</style></head><body><main>
{{BODY}}
</main>
<script>
const box = document.getElementById("onlyhere");
if (box) {
  try { box.checked = localStorage.getItem("onlyhere") === "1"; } catch (e) {}
  const apply = () => document.body.classList.toggle("onlyhere", box.checked);
  box.addEventListener("change", () => {
    apply();
    try { localStorage.setItem("onlyhere", box.checked ? "1" : "0"); } catch (e) {}
  });
  apply();
}
</script>
</body></html>
"""
