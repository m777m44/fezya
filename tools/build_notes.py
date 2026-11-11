#!/usr/bin/env python3
"""يبني صفحة notes.html من ملفات content/muayad/*.md

كل ملف = لوحة واحدة من ملفات PDF المصدر، مع frontmatter يحوي:
title / chapter / subject / page

الاستعمال:  python3 tools/build_notes.py
"""
from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "content" / "muayad"
OUT = ROOT / "notes.html"

FILE1 = "الملف الأول"
FILE2 = "الملف الثاني"

# ----------------------------------------------------------------------------
# قراءة الملفات
# ----------------------------------------------------------------------------


def read_front(text: str):
    meta = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            body = parts[2]
    return meta, body.strip()


def source_of(path: Path) -> str:
    return FILE2 if path.name.startswith("f2_") else FILE1


def load_sections():
    items = []
    for path in sorted(SRC.glob("*.md")):
        meta, body = read_front(path.read_text(encoding="utf-8"))
        items.append(
            {
                "slug": path.stem.replace("_", "-"),
                "title": meta.get("title", path.stem),
                "chapter": meta.get("chapter", "غير محدد"),
                "subject": meta.get("subject", ""),
                "page": int(meta.get("page", 0) or 0),
                "source": source_of(path),
                "body": body,
                "file": path.name,
            }
        )
    # الملف الأول أولاً (بحسب الصفحة) ثم الملف الثاني (بحسب الصفحة)
    items.sort(key=lambda s: (0 if s["source"] == FILE1 else 1, s["page"]))
    return items


# ----------------------------------------------------------------------------
# تحويل ماركداون مبسّط
# ----------------------------------------------------------------------------

PH = "\x00{}\x00"
MATH_RE = re.compile(r"\$\$(.+?)\$\$|(?<!\$)\$([^$\n]+?)\$", re.S)


def stash_math(text: str, store: list) -> str:
    """يستبدل الرياضيات بعناصر مؤقتة قبل الهروب من HTML."""

    def repl(m):
        if m.group(1) is not None:
            store.append(("block", m.group(1).strip()))
        else:
            store.append(("inline", m.group(2).strip()))
        return PH.format(len(store) - 1)

    return MATH_RE.sub(repl, text)


def inline(text: str) -> str:
    """تهيئة سطر واحد: هروب HTML ثم عريض/مائل."""
    store: list = []
    text = stash_math(text, store)
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\\)\*([^*\n]+?)\*", r"<em>\1</em>", text)
    text = text.replace("\\*", "*")
    text = re.sub(r"`([^`]+?)`", r"<code>\1</code>", text)

    def restore(m):
        kind, raw = store[int(m.group(1))]
        if kind == "inline":
            return '<span class="math-inline">$' + html.escape(raw, quote=False) + "$</span>"
        return '<div class="math-block">$$' + html.escape(raw, quote=False) + "$$</div>"

    return re.sub(PH.format(r"(\d+)"), restore, text)


def render_table(rows: list[str]) -> str:
    cells = []
    for r in rows:
        r = r.strip().strip("|")
        cells.append([c.strip() for c in r.split("|")])
    # حذف سطر الفواصل
    cells = [c for c in cells if not all(re.fullmatch(r":?-{2,}:?", x or "--") for x in c)]
    if not cells:
        return ""
    head, *body = cells
    out = ['<div class="table-wrap"><table><thead><tr>']
    out += [f"<th>{inline(c)}</th>" for c in head]
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def render_body(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # عنوان
        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            level = min(len(m.group(1)) + 2, 6)
            out.append(f'<h{level} class="sec-h">{inline(m.group(2))}</h{level}>')
            i += 1
            continue

        # رياضيات معروضة على عدّة أسطر
        if stripped.startswith("$$"):
            buf = [stripped]
            if stripped.count("$$") < 2:
                i += 1
                while i < n:
                    buf.append(lines[i])
                    if "$$" in lines[i]:
                        break
                    i += 1
            out.append(inline("\n".join(buf)))
            i += 1
            continue

        # جدول
        if stripped.startswith("|"):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(render_table(rows))
            continue

        # اقتباس
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            inner = render_body("\n".join(buf))
            out.append(f'<blockquote class="callout">{inner}</blockquote>')
            continue

        # قائمة نقطية أو مرقمة (مع إلحاق الرياضيات المعروضة بالعنصر)
        m_list = re.match(r"^([-*]|\d+[.)])\s+", stripped)
        if m_list:
            ordered = m_list.group(1) not in ("-", "*")
            if ordered:
                is_marker = lambda t: bool(re.match(r"^\d+[.)]\s+", t))
                strip_m = lambda t: re.sub(r"^\d+[.)]\s+", "", t)
            else:
                is_marker = lambda t: bool(re.match(r"^[-*]\s+", t))
                strip_m = lambda t: re.sub(r"^[-*]\s+", "", t)

            items: list[list[str]] = []
            cur: list[str] | None = None
            last_kind = ""

            while i < n:
                txt = lines[i].strip()

                if not txt:
                    if cur is not None and cur and cur[-1] != "":
                        cur.append("")
                    i += 1
                    continue

                if is_marker(txt):
                    if cur is not None:
                        items.append(cur)
                    cur = [strip_m(txt)]
                    last_kind = "marker"
                    i += 1
                    continue

                # رياضيات معروضة: تلحق بالعنصر الحالي
                if txt.startswith("$$") and cur is not None:
                    block = [txt]
                    if txt.count("$$") < 2:
                        i += 1
                        while i < n:
                            block.append(lines[i].strip())
                            if "$$" in lines[i]:
                                break
                            i += 1
                    cur.extend(block)
                    last_kind = "math"
                    i += 1
                    continue

                # سطر نصي يلحق بالعنصر فقط إذا جاء بعد رياضيات ولا يبدأ بعنوان عريض
                if (cur is not None and last_kind == "math" and not txt.startswith("**")
                        and not txt.startswith(("#", "|", ">"))
                        and not re.match(r"^([-*]|\d+[.)])\s+", txt)):
                    cur.append(txt)
                    i += 1
                    continue

                break

            if cur is not None:
                items.append(cur)
            tag = "ol" if ordered else "ul"
            rendered = "".join(
                f"<li>{render_body(chr(10).join(it))}</li>" for it in items
            )
            out.append(f"<{tag}>{rendered}</{tag}>")
            continue

        # فقرة (حتى سطر فارغ أو بداية عنصر آخر)
        buf = []
        while i < n:
            s = lines[i].strip()
            if (not s or s.startswith(("#", "$$", "|", ">")) or re.match(r"^[-*]\s+", s)
                    or re.match(r"^\d+[.)]\s+", s)):
                break
            buf.append(s)
            i += 1
        out.append(f"<p>{inline(' '.join(buf))}</p>")
    return "".join(out)


# ----------------------------------------------------------------------------
# بناء الصفحة
# ----------------------------------------------------------------------------

CSS = """
:root{
  --bg:#0b1220; --bg2:#0f172a; --card:#131c2e; --card2:#182238;
  --line:#233149; --ink:#e8eefc; --muted:#93a4c3;
  --brand:#3b82f6; --brand2:#22d3ee; --gold:#fbbf24; --green:#34d399;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0;background:var(--bg);color:var(--ink);
  font-family:'Tajawal','Cairo',system-ui,'Segoe UI',sans-serif;
  line-height:1.9;font-size:16.5px;
}
a{color:var(--brand2);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{display:flex;min-height:100vh}

/* الشريط العلوي */
.topbar{
  position:sticky;top:0;z-index:40;display:flex;align-items:center;gap:16px;
  padding:10px 22px;background:rgba(11,18,32,.92);backdrop-filter:blur(10px);
  border-bottom:1px solid var(--line);
}
.topbar .logo{
  width:42px;height:42px;border-radius:12px;display:grid;place-items:center;
  background:linear-gradient(135deg,#2563eb,#0ea5e9);font-size:20px;
  box-shadow:0 8px 24px rgba(37,99,235,.35);
}
.topbar h1{font-size:17px;margin:0;font-weight:800;letter-spacing:.2px}
.topbar .sub{font-size:12px;color:var(--muted);margin-top:-4px}
.topbar .spacer{flex:1}
.topbar .ghostbtn{background:#16233b;color:#dbe7fb;border:1px solid var(--line);cursor:pointer;font-family:inherit}
.topbar .back{
  font-size:13px;font-weight:700;color:#0b1220;background:linear-gradient(135deg,#38bdf8,#22d3ee);
  padding:9px 16px;border-radius:11px;
}
.topbar .back:hover{text-decoration:none;filter:brightness(1.08)}
#menuBtn{display:none;background:var(--card2);border:1px solid var(--line);color:var(--ink);
  padding:8px 12px;border-radius:10px;font-size:16px;cursor:pointer}

/* الشريط الجانبي */
aside{
  width:330px;flex:0 0 330px;border-left:1px solid var(--line);
  background:linear-gradient(180deg,#0d1526,#0b1220);
  position:sticky;top:0;height:100vh;overflow-y:auto;padding:18px 14px 40px;
}
aside .search{
  width:100%;padding:10px 12px;border-radius:11px;border:1px solid var(--line);
  background:#0a1121;color:var(--ink);font-family:inherit;font-size:14px;margin-bottom:14px;
}
aside .search::placeholder{color:#64748b}
.chap{margin-bottom:10px;border:1px solid var(--line);border-radius:13px;overflow:hidden;background:#101a2c}
.chap>button{
  width:100%;display:flex;align-items:center;gap:8px;justify-content:space-between;
  background:#152037;border:0;color:var(--ink);padding:11px 13px;cursor:pointer;
  font-family:inherit;font-size:13.5px;font-weight:700;text-align:right;
}
.chap>button:hover{background:#1a2742}
.chap>button .cnt{color:var(--brand2);font-size:11.5px;font-weight:700;white-space:nowrap}
.chap ul{list-style:none;margin:0;padding:4px 0 8px;display:block}
.chap li a{
  display:block;padding:7px 14px;font-size:13px;color:#c7d2e5;border-right:2px solid transparent;
}
.chap li a:hover{background:#16223a;color:#fff;text-decoration:none;border-right-color:var(--brand)}
.chap li a.active{background:#16233d;color:#fff;border-right-color:var(--brand2)}
.chap li a .pg{color:#64748b;font-size:11px;margin-inline-start:6px}

/* المحتوى */
main{flex:1;min-width:0;padding:26px 34px 90px}
.hero{
  border:1px solid var(--line);border-radius:22px;padding:26px 28px;margin-bottom:24px;
  background:
    radial-gradient(900px 240px at 90% -20%,rgba(34,211,238,.16),transparent),
    radial-gradient(700px 240px at 10% 0%,rgba(59,130,246,.18),transparent),
    #0e1728;
}
.hero h2{margin:0 0 6px;font-size:29px;letter-spacing:.2px}
.hero p{margin:0;color:var(--muted);font-size:14.5px}
.stats{display:flex;flex-wrap:wrap;gap:12px;margin-top:18px}
.stat{background:#111c30;border:1px solid var(--line);border-radius:14px;padding:11px 16px;min-width:120px}
.stat b{display:block;font-size:20px;color:var(--brand2)}
.stat span{font-size:11.5px;color:var(--muted)}
.sourcecards{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin:18px 0 6px}
.sc{background:#101a2c;border:1px solid var(--line);border-radius:16px;padding:16px 17px}
.sc h4{margin:0 0 8px;font-size:15px;color:var(--gold)}
.sc p{margin:0;font-size:13px;color:var(--muted);line-height:1.85}
.note-mini{margin-top:16px;font-size:12.5px;color:#9fb0cc;background:#12203a;border:1px dashed #2b3d5e;
  border-radius:12px;padding:11px 14px}


.booknav{
  margin:6px 0 12px;padding:9px 12px;border-radius:11px;font-size:12.5px;font-weight:800;
  color:#0b1220;background:linear-gradient(135deg,#fcd34d,#f59e0b);display:flex;align-items:center;gap:8px;
}
.booknav span{margin-inline-start:auto;font-weight:700;font-size:11px;background:rgba(0,0,0,.12);
  padding:2px 8px;border-radius:999px}
.bookhead{margin:30px 0 4px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.bookhead .bk{
  font-size:12px;font-weight:800;color:#0b1220;background:linear-gradient(135deg,#7dd3fc,#22d3ee);
  padding:4px 12px;border-radius:999px;
}
.bookhead h2{margin:0;font-size:20px;color:#e8eefc}
.chapter-block{margin:26px 0 8px}
.chapter-title{
  display:flex;align-items:center;gap:12px;font-size:21px;font-weight:800;margin:0 0 6px;
  padding:12px 18px;border-radius:16px;color:#fff;
  background:linear-gradient(135deg,rgba(37,99,235,.35),rgba(14,165,233,.18));
  border:1px solid #26405f;
}
.chapter-title .badge{
  font-size:11.5px;background:#0b1220;border:1px solid var(--line);color:var(--brand2);
  padding:4px 10px;border-radius:999px;font-weight:700;
}

article.card{
  background:linear-gradient(180deg,var(--card),#101929);
  border:1px solid var(--line);border-radius:18px;padding:20px 22px;margin:14px 0;
  box-shadow:0 10px 30px rgba(2,6,23,.25);
}
article.card>header{display:flex;align-items:flex-start;gap:12px;margin-bottom:10px;
  border-bottom:1px dashed #26344c;padding-bottom:10px}
article.card h3{margin:0;font-size:18.5px;line-height:1.6}
.pill{
  font-size:11px;font-weight:700;color:#0b1220;background:linear-gradient(135deg,#fbbf24,#f59e0b);
  padding:3px 9px;border-radius:999px;white-space:nowrap;
}
.pill.src{background:linear-gradient(135deg,#38bdf8,#0ea5e9)}
.meta{font-size:12px;color:#7f90ae;margin-top:2px}
.card-body h4.sec-h{font-size:16px;margin:16px 0 8px;color:#bfe3ff}
.card-body h3.sec-h{font-size:17.5px;margin:16px 0 8px;color:#d8ecff}
.card-body h5.sec-h{font-size:15px;margin:14px 0 6px;color:#b7c9e4}
.card-body h6.sec-h{font-size:14.5px;margin:12px 0 6px;color:#b7c9e4}
.card-body p{margin:8px 0}
.card-body strong{color:#fff}
.card-body ul,.card-body ol{margin:8px 0;padding-inline-start:24px}
.card-body li{margin:4px 0}

.math-block{
  direction:ltr;text-align:center;margin:12px 0;padding:10px 12px;
  background:#0b1424;border:1px solid #1e2c44;border-radius:12px;overflow-x:auto;
}
.math-inline{direction:ltr;unicode-bidi:isolate;display:inline-block}

.table-wrap{overflow-x:auto;margin:12px 0;border-radius:12px;border:1px solid var(--line)}
table{border-collapse:collapse;width:100%;font-size:14px;background:#0d1626}
thead th{background:#16233b;color:#dbe7fb;font-weight:700;padding:10px 12px;border:1px solid #22314a;
  white-space:nowrap}
tbody td{padding:9px 12px;border:1px solid #1d2a40;vertical-align:top}
tbody tr:nth-child(even) td{background:#0f1a2c}

blockquote.callout{
  margin:14px 0;padding:12px 16px;border-radius:12px;
  background:rgba(251,191,36,.07);border-inline-start:3px solid var(--gold);color:#f6e7c8;
}
blockquote.callout p:first-child{margin-top:0}
blockquote.callout p:last-child{margin-bottom:0}

footer.pagefoot{margin-top:44px;border-top:1px solid var(--line);padding-top:18px;
  color:#7f90ae;font-size:12.5px;text-align:center}

.hidden{display:none !important}

/* موبايل */
@media (max-width:1000px){
  aside{position:fixed;inset-inline-end:0;top:0;height:100vh;z-index:60;transform:translateX(110%);
    transition:transform .25s ease;box-shadow:-10px 0 40px rgba(0,0,0,.5)}
  aside.open{transform:translateX(0)}
  #menuBtn{display:inline-block}
  main{padding:18px 14px 70px}
  .hero h2{font-size:23px}
}

@media print{
  body{background:#fff;color:#000}
  aside,.topbar,#menuBtn,.back{display:none !important}
  main{padding:0}
  article.card{border:1px solid #bbb;box-shadow:none;break-inside:avoid;background:#fff;color:#000}
  .card-body h3.sec-h,.card-body h4.sec-h{color:#000}
  .math-block{background:#f7f7f7;border-color:#ccc;color:#000}
  table{background:#fff}thead th{background:#eee;color:#000}
  tbody td{color:#000}
  .chapter-title{color:#000;background:#eee;border-color:#bbb}
}

/* وضع التركيز — إخفاء كل شيء عدا اللوحة */
body.focus article.card:not(.focused){display:none}
"""

JS = """
// فتح/إغلاق الشريط الجانبي على الموبايل
const menuBtn=document.getElementById('menuBtn'), asideEl=document.querySelector('aside');
menuBtn.addEventListener('click',()=>asideEl.classList.toggle('open'));
asideEl.addEventListener('click',e=>{if(e.target.closest('a')&&window.innerWidth<=1000)asideEl.classList.remove('open')});

// طيّ مجموعات الفصول
document.querySelectorAll('.chap>button').forEach(btn=>{
  btn.addEventListener('click',()=>{
    const ul=btn.parentElement.querySelector('ul');
    const hidden=ul.classList.toggle('hidden');
    btn.querySelector('.caret').textContent=hidden?'▸':'▾';
  });
});

// البحث الفوري
const search=document.getElementById('search');
search.addEventListener('input',()=>{
  const q=search.value.trim();
  document.querySelectorAll('article.card').forEach(card=>{
    card.classList.toggle('hidden', q && !card.textContent.includes(q));
  });
  document.querySelectorAll('.chap').forEach(chap=>{
    const links=[...chap.querySelectorAll('li')];
    let shown=0;
    links.forEach(li=>{
      const hit=!q || li.textContent.includes(q);
      li.classList.toggle('hidden',!hit);
      if(hit)shown++;
    });
    chap.classList.toggle('hidden', q && shown===0);
  });
  document.querySelectorAll('.chapter-block').forEach(b=>{
    const any=[...b.querySelectorAll('article.card')].some(c=>!c.classList.contains('hidden'));
    b.classList.toggle('hidden', q && !any);
  });
});

// تمييز العنصر الحالي في الفهرس
const links=[...document.querySelectorAll('.chap a[href^="#"]')];
const map=new Map(links.map(a=>[a.getAttribute('href').slice(1),a]));
const obs=new IntersectionObserver(entries=>{
  entries.forEach(en=>{
    if(en.isIntersecting){
      links.forEach(l=>l.classList.remove('active'));
      const a=map.get(en.target.id);
      if(a){a.classList.add('active');}
    }
  });
},{rootMargin:'-40% 0px -55% 0px'});
document.querySelectorAll('article.card').forEach(c=>obs.observe(c));
"""


def build() -> None:
    sections = load_sections()

    # ترتيب: الملف الأول (فصوله المتسلسلة) ثم الملف الثاني، وكل ملف يُقسّم على فصوله
    books = [(FILE1, [s for s in sections if s["source"] == FILE1]),
             (FILE2, [s for s in sections if s["source"] == FILE2])]

    def group(items):
        order, groups = [], {}
        for s in items:
            if s["chapter"] not in groups:
                groups[s["chapter"]] = []
                order.append(s["chapter"])
            groups[s["chapter"]].append(s)
        return order, groups

    nav, main = [], []
    chapter_total = 0
    for book_name, items in books:
        order, groups = group(items)
        chapter_total += len(order)
        nav.append(
            f'<div class="booknav"><i class="fas fa-layer-group"></i> {html.escape(book_name)}'
            f'<span>{len(items)} لوحة</span></div>'
        )
        main.append(
            f'<div class="bookhead"><span class="bk">{html.escape(book_name)}</span>'
            f'<h2>{len(items)} لوحة مفرّغة</h2></div>'
        )
        for chapter in order:
            ch_items = groups[chapter]
            nav.append(
                f'<div class="chap"><button><span>{html.escape(chapter)}</span>'
                f'<span class="cnt">{len(ch_items)} <span class="caret">▾</span></span></button><ul>'
            )
            for s in ch_items:
                nav.append(
                    f'<li><a href="#p-{s["slug"]}">{html.escape(s["title"])}'
                    f'<span class="pg">ص {s["page"]}</span></a></li>'
                )
            nav.append("</ul></div>")

            main.append('<section class="chapter-block">')
            main.append(
                f'<h3 class="chapter-title">{html.escape(chapter)}'
                f'<span class="badge">{len(ch_items)} لوحة</span></h3>'
            )
            for s in ch_items:
                src_cls = "src" if s["source"] == FILE2 else ""
                main.append(
                    f'<article class="card" id="p-{s["slug"]}">'
                    f'<header><div><h3>{html.escape(s["title"])}</h3>'
                    f'<div class="meta">صفحة {s["page"]} — {html.escape(s["subject"])}</div></div>'
                    f'<div style="margin-inline-start:auto;display:flex;gap:8px;flex-wrap:wrap">'
                    f'<span class="pill">صفحة {s["page"]}</span>'
                    f'<span class="pill {src_cls}">{html.escape(s["source"])}</span>'
                    f"</div></header>"
                    f'<div class="card-body">{render_body(s["body"])}</div></article>'
                )
            main.append("</section>")

    f1 = books[0][1]
    f2 = books[1][1]

    doc = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>الموسوعة الكاملة لقوانين الفيزياء — نصّ اللوحتين كاملاً</title>
<meta name="description" content="تفريغ نصي كامل ومنظّم لجميع لوحات ملخصات قوانين الفيزياء للاستاذين مؤيد سليم وعلي السوداني، مع الصيغ الرياضية والجداول والملاحظات كما وردت في الأصل.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;600;700;800&family=Tajawal:wght@300;400;500;700;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<script>
window.MathJax = {{
  tex: {{inlineMath: [['$','$']], displayMath: [['$$','$$']], processEscapes: true}},
  options: {{skipHtmlTags: ['script','noscript','style','textarea','pre','code']}},
  chtml: {{scale: 1.02, mtextInheritFont: true}}
}};
</script>
<script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <aside>
    <input id="search" class="search" type="search" placeholder="ابحث في القوانين والملاحظات…">
    {''.join(nav)}
  </aside>
  <div style="flex:1;min-width:0">
    <div class="topbar">
      <button id="menuBtn" aria-label="الفهرس"><i class="fas fa-bars"></i></button>
      <div class="logo"><i class="fas fa-atom"></i></div>
      <div>
        <h1>الموسوعة الكاملة لقوانين الفيزياء</h1>
        <div class="sub">تفريغ نصي كامل للوحتين — السادس العلمي</div>
      </div>
      <div class="spacer"></div>
      <button class="back ghostbtn" onclick="window.print()"><i class="fas fa-print"></i> طباعة</button>
      <a class="back" href="index.html"><i class="fas fa-house"></i> الصفحة الرئيسية</a>
    </div>
    <main>
      <section class="hero">
        <h2>كل ما في اللوحتين… <span style="color:#22d3ee">نصّاً</span> كما ورد</h2>
        <p>تفريغ منظّم لكل لوحة وصفحة في ملفَّي القوانين الممسوحين ضوئياً، مع الحفاظ على الصياغة الأصلية
        للعناوين والملاحظات والجداول والرموز، وإظهار كل صيغة رياضية بترميز رياضي قابل للتكبير والطباعة.</p>
        <div class="stats">
          <div class="stat"><b>{len(f1)}</b><span>لوحة من الملف الأول</span></div>
          <div class="stat"><b>{len(f2)}</b><span>لوحة من الملف الثاني</span></div>
          <div class="stat"><b>{len(sections)}</b><span>لوحة مفرّغة كاملة</span></div>
          <div class="stat"><b>{chapter_total}</b><span>فصلاً ومجموعة</span></div>
        </div>
      </section>

      <section class="sourcecards">
        <div class="sc">
          <h4>الملف الأول — قوانين فيزياء للاستاذ مؤيد سليم (جميع الفصول)</h4>
          <p>56 صفحة ممسوحة ضوئياً، تتوزّع على: المتسعات، الحث الكهرومغناطيسي، التيار المتناوب (توالي وتوازي)،
          التداخل والحيود والاستقطاب، الفيزياء الحديثة، الترانزستور، الأطياف الذرية والفيزياء النووية.</p>
        </div>
        <div class="sc">
          <h4>الملف الثاني — ملخص قوانين الفيزياء بالتفصيل (الاستاذ علي السوداني)</h4>
          <p>27 صفحة مرقّمة من 68 إلى 94، منظّمة على طريقة «الجواهر»: المتسعة الواحدة وربط المتسعات ودوائر RC،
          الحث، التيار المتناوب والرنين، الموجات، التداخل والحيود، الكهروضوئية، الترانزستور، الأطياف.</p>
        </div>
      </section>

      <div class="note-mini">
        <strong>ملاحظة على الترقيم:</strong> صفحة 2 من الملف الأول مطابقة لصفحة 1، وصفحة 40 مطابقة لصفحة 39
        (نفس اللوحة مكرّرة في الملف الممسوح)، ولذلك لم تُكرّر هنا؛ وعدد اللوحات المفرّغة {len(sections)} لوحة
        تغطّي كامل المحتوى الفريد للملفين. كلّ ما أُضيف من توضيح خارج الأصل موسوم صراحةً بـ«ملاحظة المحرر».
      </div>

      {''.join(main)}

      <footer class="pagefoot">
        تفريغ نصي للمحتوى العلمي كما ورد في الملفين المرفقين — للاستعمال الدراسي.
      </footer>
    </main>
  </div>
</div>
<script>{JS}</script>
</body>
</html>
"""
    OUT.write_text(doc, encoding="utf-8")
    print(f"تم بناء {OUT.name}: {len(sections)} لوحة، {chapter_total} فصلاً/مجموعة.")


if __name__ == "__main__":
    build()
