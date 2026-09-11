"""MetaCLS's own visual identity — one source of truth for the CSS used
by both the local web UI (`web.py`) and the HTML report
(`report/templates/`).

Deliberately *not* MetaScout's look. MetaScout is blue-on-black, dark
only. MetaCLS is emerald/slate with a "swept clean" motif and a proper
light theme (follows `prefers-color-scheme`). Keeping the palette here,
rather than copy-pasted into two files, is what keeps the two surfaces
looking like one product.
"""
from __future__ import annotations

# Design tokens. Dark is the primary look; the light block is a full
# re-theme, not an afterthought.
TOKENS_CSS = """
:root {
  --bg:        #0c1110;
  --panel:     #141b1a;
  --panel-2:   #1a2321;
  --border:    #263230;
  --text:      #e9efed;
  --muted:     #93a5a0;
  --accent:    #2dd4a7;   /* emerald-teal — MetaCLS's signature */
  --accent-ink:#04140f;
  --link:      #5ad1c4;
  --good:      #2dd4a7;
  --warn:      #f6c454;
  --bad:       #f2778d;
  --sweep: linear-gradient(100deg, rgba(45,212,167,.16), rgba(45,212,167,0) 60%);
}
@media (prefers-color-scheme: light) {
  :root {
    --bg:        #f4f7f6;
    --panel:     #ffffff;
    --panel-2:   #eef3f1;
    --border:    #dde5e3;
    --text:      #13201d;
    --muted:     #5c6b67;
    --accent:    #0f9e78;
    --accent-ink:#ffffff;
    --link:      #0c7c6a;
    --good:      #0f9e78;
    --warn:      #b57d12;
    --bad:       #c2405a;
    --sweep: linear-gradient(100deg, rgba(15,158,120,.10), rgba(15,158,120,0) 60%);
  }
}
"""

# Shared element + component styles. The `msc-` prefix keeps these from
# colliding with anything in a report card's own escaped content.
BASE_CSS = """
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text);
  font-family:"Inter",-apple-system,"Segoe UI",Roboto,sans-serif; font-size:14px;
  line-height:1.5; -webkit-font-smoothing:antialiased; }
a { color:var(--link); }
code, .mono { font-family:ui-monospace,"SF Mono",SFMono-Regular,Menlo,monospace; }

.msc-header { padding:26px 40px 20px; border-bottom:1px solid var(--border);
  background:var(--sweep); background-repeat:no-repeat; }
.msc-mark { font-weight:800; font-size:21px; letter-spacing:-.01em; }
.msc-mark b { color:var(--accent); font-weight:800; }
.msc-mark::before { content:""; display:inline-block; width:22px; height:3px; border-radius:2px;
  background:var(--accent); margin:0 10px 5px 0; vertical-align:middle; }
.msc-tag { color:var(--muted); font-size:12.5px; margin-top:5px; }
.msc-nav { margin-top:12px; display:flex; gap:18px; }
.msc-nav a { color:var(--muted); text-decoration:none; font-size:12.5px; font-weight:600;
  padding-bottom:3px; border-bottom:2px solid transparent; }
.msc-nav a.on, .msc-nav a:hover { color:var(--accent); border-bottom-color:var(--accent); }
.msc-lang a { color:var(--muted); text-decoration:none; border:1px solid var(--border);
  border-radius:999px; padding:3px 10px; font-size:11.5px; font-weight:700; margin-left:6px; }
.msc-lang a.on { background:var(--accent); color:var(--accent-ink); border-color:var(--accent); }

.msc-main { padding:26px 40px 72px; max-width:880px; margin:0 auto; }

.msc-hero { border:1px solid var(--border); border-radius:14px; overflow:hidden;
  background:var(--panel); margin-bottom:22px; }
.msc-hero-band { padding:18px 22px; background:var(--sweep), var(--panel-2);
  border-bottom:1px solid var(--border); display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; }
.msc-hero-state { font-size:19px; font-weight:800; letter-spacing:.02em; }
.msc-hero-state.ok { color:var(--good); }
.msc-hero-state.warn { color:var(--warn); }
.msc-hero-state.bad { color:var(--bad); }
.msc-hero-sub { color:var(--muted); font-size:12.5px; }
.msc-stats { display:flex; flex-wrap:wrap; gap:10px; padding:16px 22px; }
.msc-stat { flex:1; min-width:120px; background:var(--panel-2); border:1px solid var(--border);
  border-radius:10px; padding:12px 14px; }
.msc-stat .n { font-size:20px; font-weight:800; }
.msc-stat .l { color:var(--muted); font-size:11.5px; margin-top:2px; letter-spacing:.02em; }
.msc-stat.warn .n { color:var(--warn); }
.msc-stat.bad .n { color:var(--bad); }

.msc-card { background:var(--panel); border:1px solid var(--border); border-left:3px solid var(--border);
  border-radius:12px; padding:18px 20px; margin-bottom:14px; }
.msc-card.is-cleaned { border-left-color:var(--good); }
.msc-card.is-skipped { border-left-color:var(--warn); }
.msc-card.is-error   { border-left-color:var(--bad); }
.msc-card.is-unsupported { border-left-color:var(--muted); }
.msc-file { font-family:ui-monospace,"SF Mono",SFMono-Regular,Menlo,monospace; font-size:13px;
  word-break:break-all; }
.msc-meta { color:var(--muted); font-size:12px; }

.msc-pill { display:inline-block; font-size:10.5px; font-weight:800; padding:2px 9px;
  border-radius:999px; text-transform:uppercase; letter-spacing:.05em; }
.msc-pill.cleaned{ background:color-mix(in srgb,var(--good) 18%,transparent); color:var(--good); }
.msc-pill.skipped{ background:color-mix(in srgb,var(--warn) 18%,transparent); color:var(--warn); }
.msc-pill.error{ background:color-mix(in srgb,var(--bad) 18%,transparent); color:var(--bad); }
.msc-pill.unsupported{ background:color-mix(in srgb,var(--muted) 18%,transparent); color:var(--muted); }

table.msc-diff { width:100%; border-collapse:collapse; margin-top:10px; font-size:12.5px; }
table.msc-diff th, table.msc-diff td { text-align:left; padding:6px 10px;
  border-bottom:1px solid var(--border); vertical-align:top; }
table.msc-diff th { color:var(--muted); font-weight:600; }
table.msc-diff td.was { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; color:var(--muted);
  text-decoration:line-through; text-decoration-color:color-mix(in srgb,var(--bad) 60%,transparent);
  word-break:break-word; }
.msc-kept { color:var(--good); font-size:12px; margin-top:10px; }
.msc-residual { color:var(--bad); font-size:12px; margin-top:10px; font-weight:600; }
.msc-empty { color:var(--muted); font-size:12.5px; margin-top:8px; }

.msc-btn { background:var(--accent); color:var(--accent-ink); border:0; border-radius:9px;
  padding:12px 22px; font-weight:800; font-size:14px; cursor:pointer; }
.msc-btn:disabled { opacity:.6; cursor:wait; }
.msc-actions a { margin-right:16px; font-weight:600; font-size:13px; }
"""


def full_css() -> str:
    return TOKENS_CSS + BASE_CSS
