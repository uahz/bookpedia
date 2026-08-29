# -*- coding: utf-8 -*-
"""
书籍百科 BookPedia —— 一款仿苹果设计风格的图书信息检索程序
================================================================
功能概述：
  1. 用户输入任意书名，程序自动联网检索该书的权威出版信息；
  2. 数据来源（自动降级）：豆瓣阅读（主源，requests + BeautifulSoup4 解析网页）
                          → Google Books API → Open Library API；
  3. 检索结果以「卡片」形式结构化展示：书名 / 作者 / 出版社 / 出版时间 /
     定价 / ISBN / 评分 / 简介 / 封面；
  4. 全程仿 Apple 设计语言：#F5F5F7 浅色背景、无边框大圆角窗口、
     macOS 红绿灯按钮、居中半透明搜索框、扁平化蓝色按钮（点击带轻微渐变反馈）；
  5. 完善的错误处理：网络异常 / 无结果 / 意外错误均有友好空状态提示，绝不闪退。

运行方式：
  python book_encyclopedia.py            # 正常启动 GUI
  python book_encyclopedia.py --probe 书名   # 无界面模式验证检索链路
  python book_encyclopedia.py --selftest     # 隐藏窗口渲染各状态并截图（自检用）
  python book_encyclopedia.py --selftest --e2e 书名   # 端到端真实检索验证

依赖（Python 3.10+）：PyQt6、requests、beautifulsoup4
  pip install PyQt6 requests beautifulsoup4
"""

import os
import re
import sys
import time
import json
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, List, Optional
from urllib.parse import urljoin

# 调试开关：设置 BOOKPEDIA_DEBUG=1 可在控制台看到检索流程日志
DEBUG = os.environ.get("BOOKPEDIA_DEBUG") == "1"


def dbg(*args):
    if DEBUG:
        print("[dbg]", *args, flush=True)


if "--probe" in sys.argv:
    try:  # 保证命令行中文输出不因控制台编码而报错
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import requests
from bs4 import BeautifulSoup

from PyQt6.QtCore import Qt, QTimer, QThread, QUrl, pyqtSignal, QSize
from PyQt6.QtGui import (QAction, QColor, QFont, QFontMetrics, QIcon, QImage,
                         QPainter, QPainterPath, QPixmap, QLinearGradient, QPen)
from PyQt6.QtNetwork import (QNetworkAccessManager, QNetworkReply,
                             QNetworkRequest)
from PyQt6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QSizeGrip,
    QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
    QGraphicsDropShadowEffect,
)

# ============================================================================
# 一、全局设计常量（仿 Apple 设计语言）
# ============================================================================
COLOR_BG = "#F5F5F7"          # 苹果官网经典浅灰背景
COLOR_CARD = "#FFFFFF"        # 卡片底色
COLOR_TEXT = "#1D1D1F"        # 主文字（Apple 近黑）
COLOR_TEXT_2 = "#6E6E73"      # 次要文字
COLOR_TEXT_3 = "#86868B"      # 辅助说明文字
COLOR_BLUE = "#0071E3"        # Apple 官网按钮蓝
COLOR_LINE = "rgba(0, 0, 0, 0.06)"

FONT_STACK = ('"SF Pro Text", "SF Pro Display", "PingFang SC", '
              '"Microsoft YaHei UI", "Microsoft YaHei", sans-serif')

# 全局样式表：统一控制字体栈与各控件外观（关键部分均有中文注释）
GLOBAL_QSS = f"""
* {{
    font-family: {FONT_STACK};              /* 系统无衬线字体栈 */
    outline: none;
}}

/* ---------- 卡片容器 ---------- */
QFrame#bookCard {{
    background-color: {COLOR_CARD};
    border: 1px solid {COLOR_LINE};
    border-radius: 18px;                    /* 大圆角卡片 */
}}
QFrame#bookCard:hover {{
    border: 1px solid rgba(0, 0, 0, 0.12);  /* 悬停时边框轻微加深 */
}}

/* ---------- 居中半透明搜索框 ---------- */
QLineEdit#searchInput {{
    background-color: rgba(255, 255, 255, 0.55);   /* 半透明背景 */
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 21px;
    padding: 0 16px 0 40px;
    font-size: 15px;
    color: {COLOR_TEXT};
    selection-background-color: {COLOR_BLUE};
}}
QLineEdit#searchInput:focus {{
    background-color: rgba(255, 255, 255, 0.92);   /* 聚焦时略微实化 */
    border: 1px solid rgba(0, 113, 227, 0.55);
}}

/* ---------- 扁平化搜索按钮（点击带轻微渐变反馈） ---------- */
QPushButton#searchBtn {{
    background-color: {COLOR_BLUE};
    color: white;
    border: none;
    border-radius: 21px;
    padding: 0 28px;
    font-size: 14px;
    font-weight: 500;
}}
QPushButton#searchBtn:hover  {{ background-color: #0077ED; }}
QPushButton#searchBtn:pressed {{
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                     stop:0 #0A63C6, stop:1 #0C7CE9);   /* 按下渐变反馈 */
}}
QPushButton#searchBtn:disabled {{ background-color: rgba(0, 113, 227, 0.35); }}

/* ---------- macOS 红绿灯窗口控制按钮 ---------- */
QPushButton#tlClose, QPushButton#tlMin, QPushButton#tlMax {{
    border: none; border-radius: 7px;
    min-width: 14px; max-width: 14px; min-height: 14px; max-height: 14px;
    color: transparent; font-size: 9px; font-weight: 700;
    padding: 0; margin: 0;
}}
QPushButton#tlClose {{ background-color: #FF5F57; }}
QPushButton#tlMin   {{ background-color: #FEBC2E; }}
QPushButton#tlMax   {{ background-color: #28C840; }}
QPushButton#tlClose:hover {{ color: rgba(77, 0, 0, 0.65); }}
QPushButton#tlMin:hover   {{ color: rgba(77, 54, 0, 0.65); }}
QPushButton#tlMax:hover   {{ color: rgba(0, 77, 15, 0.65); }}

/* ---------- 空状态 / 错误状态的"重试"按钮 ---------- */
QPushButton#retryBtn {{
    background-color: {COLOR_BLUE};
    color: white; border: none; border-radius: 17px;
    padding: 8px 26px; font-size: 13px; font-weight: 500;
}}
QPushButton#retryBtn:hover  {{ background-color: #0077ED; }}
QPushButton#retryBtn:pressed {{
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                     stop:0 #0A63C6, stop:1 #0C7CE9);
}}

/* ---------- 滚动条：细圆角，尽量隐身 ---------- */
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 6px; margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: rgba(0, 0, 0, 0.18); border-radius: 3px; min-height: 36px;
}}
QScrollBar::handle:vertical:hover {{ background: rgba(0, 0, 0, 0.32); }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ height: 0; }}
"""

# ============================================================================
# 二、数据模型与网络检索层（requests + BeautifulSoup4）
# ============================================================================


@dataclass
class BookInfo:
    """一本书的结构化信息（界面卡片的数据来源）"""
    title: str = ""
    authors: str = ""
    publisher: str = ""
    pub_date: str = ""
    price: str = ""
    isbn: str = ""
    intro: str = ""
    rating: str = ""
    cover_url: str = ""
    detail_url: str = ""
    source: str = ""
    verified: bool = False     # True 表示已到出版社官网核实过


class NetworkError(Exception):
    """网络层异常（连接失败 / 超时 / 接口不可用），用于触发友好错误提示"""


class SearchCancelled(Exception):
    """新一轮搜索开始时，用于中止旧的检索任务"""


# 全局共享的 requests 会话：统一 User-Agent，降低被反爬拦截的概率
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
})

_RE_FLOAT = re.compile(r"[\d.]+")


def _clean(text: Optional[str]) -> str:
    """去除 HTML 文本中的多余空白"""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


# ----------------------------------------------------------------------------
# 数据源 1（主源）：豆瓣阅读 —— suggest 接口 + 条目页 HTML 解析
# ----------------------------------------------------------------------------


class DoubanSource:
    """从豆瓣检索图书：先用 suggest 接口拿候选，再解析条目页拿详情"""
    name = "豆瓣阅读"

    @staticmethod
    def search(query: str, limit: int = 4,
               should_cancel: Optional[Callable[[], bool]] = None) -> List[BookInfo]:
        # 1) 候选列表
        try:
            r = SESSION.get("https://book.douban.com/j/subject_suggest",
                            params={"q": query}, timeout=(4, 8))
            r.raise_for_status()
            entries = r.json() or []
        except (requests.RequestException, ValueError) as exc:
            raise NetworkError(f"豆瓣接口暂不可用（{type(exc).__name__}）") from exc

        results: List[BookInfo] = []
        for i, entry in enumerate(entries[:limit]):
            if should_cancel and should_cancel():
                raise SearchCancelled()
            url = entry.get("url") or ""
            if not url or "/subject/" not in url:
                continue
            # 条目之间稍作停顿，礼貌抓取
            if i > 0:
                time.sleep(0.25)
            try:
                info = DoubanSource._fetch_subject(url)
                info.source = DoubanSource.name
                results.append(info)
            except SearchCancelled:
                raise
            except Exception:
                # 单个条目解析失败不影响整体，直接跳过
                continue
        return results

    @staticmethod
    def _fetch_subject(url: str) -> BookInfo:
        """抓取并解析豆瓣条目页（BeautifulSoup4 的用武之地）"""
        resp = SESSION.get(url, timeout=(4, 10))
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        title_el = soup.select_one("h1 span")
        info = BookInfo(
            title=_clean(title_el.get_text() if title_el else ""),
            detail_url=url,
        )

        # —— 信息区：以 “标签: 值” 的方式逐字段解析（字段顺序因书而异）——
        info_box = soup.select_one("#info")
        fields: dict = {}
        if info_box:
            for label_span in info_box.select("span.pl"):
                key = _clean(label_span.get_text()).rstrip(":：")
                parts: List[str] = []
                for node in label_span.next_siblings:
                    name = getattr(node, "name", None)
                    if name == "span":          # 遇到下一个字段标签即停止
                        break
                    if name == "br":
                        continue
                    if key in ("作者", "译者") and name == "a":
                        parts.append(_clean(node.get_text()))
                    elif isinstance(node, str):
                        # 剔除 "作者: " 这类冒号/斜杠分隔符文本节点
                        t = _clean(node).strip(" :：/ ")
                        if t:
                            parts.append(t)
                    elif name:
                        parts.append(_clean(node.get_text()))
                value = " / ".join(p for p in parts if p)
                if key and value and key not in fields:
                    fields[key] = value
            # ISBN 兜底：直接正则匹配全文
            if "ISBN" not in fields:
                m = re.search(r"ISBN[：:]\s*([\dXx-]+)", info_box.get_text())
                if m:
                    fields["ISBN"] = m.group(1)

        info.authors = fields.get("作者", "")
        info.publisher = fields.get("出版社", "")
        info.pub_date = fields.get("出版年", "")
        info.isbn = fields.get("ISBN", "")
        info.price = fields.get("定价", "")

        # —— 评分 ——
        rating_el = soup.select_one("strong.rating_num")
        if rating_el:
            info.rating = _clean(rating_el.get_text())

        # —— 封面 ——
        cover_el = soup.select_one("#mainpic a.nbg img") or soup.select_one("#mainpic img")
        if cover_el:
            info.cover_url = cover_el.get("src") or ""

        # —— 简介：取第一个 intro 区块内的所有段落 ——
        intro_box = soup.select_one("div.intro")
        if intro_box:
            paras = [_clean(p.get_text()) for p in intro_box.select("p")]
            info.intro = "\n".join(p for p in paras if p)
        return info


# ----------------------------------------------------------------------------
# 数据源 2（降级源 1）：Google Books API（返回 JSON）
# ----------------------------------------------------------------------------


class GoogleBooksSource:
    name = "Google 图书"

    @staticmethod
    def search(query: str, limit: int = 4,
               should_cancel: Optional[Callable[[], bool]] = None) -> List[BookInfo]:
        if should_cancel and should_cancel():
            raise SearchCancelled()
        try:
            r = SESSION.get("https://www.googleapis.com/books/v1/volumes",
                            params={"q": query, "printType": "books",
                                    "maxResults": min(limit, 10)},
                            timeout=(4, 8))
            r.raise_for_status()
            items = r.json().get("items", [])
        except (requests.RequestException, ValueError) as exc:
            raise NetworkError(f"Google 图书接口暂不可用（{type(exc).__name__}）") from exc

        results: List[BookInfo] = []
        for it in items[:limit]:
            if should_cancel and should_cancel():
                raise SearchCancelled()
            v = it.get("volumeInfo", {})
            sale = it.get("saleInfo", {}) or {}
            # 组合 ISBN（优先 13 位）
            isbn = ""
            for ident in v.get("industryIdentifiers", []) or []:
                if ident.get("type") == "ISBN_13":
                    isbn = ident.get("identifier", "")
                    break
                if not isbn and ident.get("type") == "ISBN_10":
                    isbn = ident.get("identifier", "")
            # 价格
            price = ""
            lp = sale.get("listPrice") or {}
            if lp.get("amount") is not None:
                price = f"{lp['amount']:.2f} {lp.get('currencyCode', '')}".strip()
            links = v.get("imageLinks", {}) or {}
            cover = links.get("thumbnail") or links.get("smallThumbnail") or ""
            results.append(BookInfo(
                title=_clean(v.get("title", "")),
                authors=" / ".join(v.get("authors", []) or []),
                publisher=_clean(v.get("publisher", "")),
                pub_date=_clean(str(v.get("publishedDate", ""))),
                price=price,
                isbn=isbn,
                intro=_clean(v.get("description", "")),
                rating=(str(v["averageRating"]) if v.get("averageRating") else ""),
                cover_url=cover.replace("http://", "https://"),
                detail_url=v.get("infoLink", ""),
                source=GoogleBooksSource.name,
            ))
        return results


# ----------------------------------------------------------------------------
# 数据源 3（降级源 2）：Open Library API（返回 JSON）
# ----------------------------------------------------------------------------


class OpenLibrarySource:
    name = "Open Library"

    @staticmethod
    def search(query: str, limit: int = 4,
               should_cancel: Optional[Callable[[], bool]] = None) -> List[BookInfo]:
        if should_cancel and should_cancel():
            raise SearchCancelled()
        try:
            r = SESSION.get("https://openlibrary.org/search.json",
                            params={"q": query, "limit": limit,
                                    "fields": ("title,author_name,publisher,"
                                               "first_publish_year,isbn,cover_i,"
                                               "first_sentence")},
                            timeout=(4, 8))
            r.raise_for_status()
            docs = r.json().get("docs", [])
        except (requests.RequestException, ValueError) as exc:
            raise NetworkError(f"Open Library 接口暂不可用（{type(exc).__name__}）") from exc

        results: List[BookInfo] = []
        for d in docs[:limit]:
            if should_cancel and should_cancel():
                raise SearchCancelled()
            # 从 isbn 列表里挑一个 13 位的
            isbn = next((x for x in (d.get("isbn") or [])
                         if re.fullmatch(r"97[89]\d{10}", x)), "")
            sentences = d.get("first_sentence") or []
            intro = sentences[0] if sentences and isinstance(sentences, list) else ""
            cover = (f"https://covers.openlibrary.org/b/id/{d['cover_i']}-M.jpg"
                     if d.get("cover_i") else "")
            results.append(BookInfo(
                title=_clean(d.get("title", "")),
                authors=" / ".join((d.get("author_name") or [])[:3]),
                publisher=(d.get("publisher") or [""])[0],
                pub_date=str(d.get("first_publish_year", "") or ""),
                isbn=isbn,
                intro=_clean(intro),
                cover_url=cover,
                source=OpenLibrarySource.name,
            ))
        return results


# 检索优先级：豆瓣（中文图书最权威）→ Google → Open Library
ALL_SOURCES = [DoubanSource, GoogleBooksSource, OpenLibrarySource]


# ----------------------------------------------------------------------------
# 数据源 4（权威核实源）：出版社官网直查
# ----------------------------------------------------------------------------
# 各出版社官网结构各异，采用「适配器注册表」：每个官网一个适配器类，统一提供
# search(query) -> List[BookInfo]。新增出版社时仿照 YiwenAdapter 写一个类，
# 加入 PUBLISHER_ADAPTERS 即可（官网核实与官网兜底检索会自动生效）。
# 已知待适配：清华大学出版社（检索接口报错）、商务印书馆（结果为 JS 渲染）。


def _excel_serial_to_date(value: str) -> str:
    """部分官网把日期存成 Excel 序列号（如 43255），转成可读的 YYYY-M-D"""
    if not re.fullmatch(r"\d{4,6}", value.strip()):
        return value
    try:
        dt = datetime(1899, 12, 30) + timedelta(days=int(value))
        return f"{dt.year}-{dt.month}-{dt.day}"
    except (ValueError, OverflowError):
        return value


class YiwenAdapter:
    """上海译文出版社官网（yiwen.com.cn）检索适配器。

    页面结构（2026-08 探测）：
      - 检索：GET /search?keyword=书名，条目为 a.link[href*='bookDetail']，
        文本形如 “《挪威的森林》[日]村上春树 著林少华 译”；
      - 详情：/bookDetail?id=xxx，字段为 div.listbookd strong.titwsl 标签
        （“定价：”“ISBN：”等）+ 相邻兄弟文本；封面 img 的 src 含 fengmian。
    """
    key = "上海译文"              # 与出版社名匹配的关键词
    display = "上海译文出版社"
    base = "https://www.yiwen.com.cn"

    @classmethod
    def search(cls, query: str, limit: int = 3,
               should_cancel: Optional[Callable[[], bool]] = None) -> List[BookInfo]:
        if should_cancel and should_cancel():
            raise SearchCancelled()
        try:
            r = SESSION.get(f"{cls.base}/search", params={"keyword": query},
                            timeout=(4, 8))
            r.raise_for_status()
        except requests.RequestException as exc:
            raise NetworkError(f"{cls.display}官网暂不可用（{type(exc).__name__}）") from exc
        r.encoding = r.apparent_encoding or "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")

        results: List[BookInfo] = []
        for a in soup.select("a[href*='bookDetail']")[:limit * 2]:
            if should_cancel and should_cancel():
                raise SearchCancelled()
            raw = _clean(a.get_text())
            m = re.match(r"《(.+?)》\s*(.*)", raw)
            if not m:
                continue                      # 非《书名》格式的条目直接跳过
            info = cls._fetch_detail(urljoin(cls.base, a.get("href", "")))
            if info is None:
                continue
            # 详情页一般不含书名/作者行，从检索条目文本中解析
            info.title = info.title or m.group(1)
            info.authors = _clean(m.group(2).replace("著", "·", 1)) or info.authors
            results.append(info)
            if len(results) >= limit:
                break
        return results

    @classmethod
    def _fetch_detail(cls, url: str) -> Optional[BookInfo]:
        """解析详情页的 定价/ISBN/出版时间/出版社/简介/封面"""
        try:
            r = SESSION.get(url, timeout=(4, 8))
            r.raise_for_status()
        except requests.RequestException:
            return None                        # 单个条目失败不影响整体
        r.encoding = r.apparent_encoding or "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")

        info = BookInfo(detail_url=url, source=f"{cls.display}官网", verified=True)
        fields: dict = {}
        for lab in soup.select("div.listbookd strong.titwsl"):
            key = _clean(lab.get_text()).rstrip(":：")
            sib = lab.next_sibling             # 值是紧邻的兄弟文本节点
            if sib is None:
                continue
            val = _clean(sib.get_text() if hasattr(sib, "get_text") else str(sib))
            if key and val and key not in fields:
                fields[key] = val
        info.price = fields.get("定价", "")
        info.isbn = fields.get("ISBN", "").replace("-", "")
        info.pub_date = _excel_serial_to_date(fields.get("出版时间", ""))
        info.publisher = fields.get("出版社", cls.display)

        cover = soup.select_one("img[src*='fengmian']")
        if cover:
            info.cover_url = urljoin(cls.base, cover.get("src", ""))

        # 简介：紧跟“作者简介/内容简介”标签后的同区块文本
        lab = soup.find(string=lambda t: t and t.strip().rstrip("：") in
                        ("作者简介", "内容简介"))
        if lab:
            block = lab.find_parent("div")
            if block:
                txt = _clean(block.get_text())
                txt = txt.split(lab.strip(), 1)[-1].strip(" ：:.")
                info.intro = txt
        return info


# 出版社官网适配器注册表（官网核实 + 主链路失败后的兜底检索都从这里取）
PUBLISHER_ADAPTERS = [YiwenAdapter]


def _match_publisher_adapter(publisher: str):
    """按出版社名找到对应的官网适配器（没有注册的出版社返回 None）"""
    if not publisher:
        return None
    for ad in PUBLISHER_ADAPTERS:
        if ad.key in publisher:
            return ad
    return None


def enrich_with_publisher_sites(books: List[BookInfo],
                                should_cancel: Optional[Callable[[], bool]] = None
                                ) -> List[BookInfo]:
    """把检索结果送到其出版社官网核实/补充信息（权威数据优先采纳）。

    成功核实后打上 verified 标记（界面显示「✓ 官网核实」徽标）；
    官网不可达时保留原数据，不影响主检索结果。
    """
    for b in books:
        if should_cancel and should_cancel():
            raise SearchCancelled()
        adapter = _match_publisher_adapter(b.publisher)
        if adapter is None:
            continue
        try:
            hits = adapter.search(b.title, limit=3, should_cancel=should_cancel)
        except SearchCancelled:
            raise
        except NetworkError:
            continue
        # 优先用 ISBN 精确匹配同一版次；豆瓣侧缺 ISBN 时才退回书名匹配。
        # 版次对不上就不核实，避免把别版的定价/出版日期错并进来。
        off = next((h for h in hits if h.isbn and b.isbn
                    and h.isbn.replace("-", "") == b.isbn.replace("-", "")), None)
        if off is None and not b.isbn:
            off = next((h for h in hits if h.title and b.title
                        and (h.title == b.title or h.title in b.title
                             or b.title in h.title)), None)
        if off is None:
            continue
        b.publisher = off.publisher or b.publisher
        b.pub_date = off.pub_date or b.pub_date
        b.price = off.price or b.price
        b.isbn = b.isbn or off.isbn
        b.intro = b.intro or off.intro
        b.cover_url = b.cover_url or off.cover_url
        b.detail_url = off.detail_url or b.detail_url
        b.source = f"{b.source} + {adapter.display}官网"
        b.verified = True
    return books


def run_search(query: str, limit: int = 4,
               should_cancel: Optional[Callable[[], bool]] = None) -> List[BookInfo]:
    """检索编排：
    1. 主链路按优先级尝试（豆瓣 → Google → Open Library），取第一个非空结果集；
    2. 对结果中已注册官网的出版社，到官网核实/补充信息（数据更权威）；
    3. 主链路无结果时，直接向各出版社官网发起书名检索兜底；
    4. 所有数据源都网络异常 → 抛 NetworkError；有数据源正常但无结果 → 返回 []。
    """
    any_source_ok = False
    last_err: List[str] = []

    # —— 主链路 ——
    primary: List[BookInfo] = []
    for src in ALL_SOURCES:
        if should_cancel and should_cancel():
            raise SearchCancelled()
        try:
            res = src.search(query, limit=limit, should_cancel=should_cancel)
        except SearchCancelled:
            raise
        except NetworkError as exc:
            last_err.append(str(exc))
            continue
        any_source_ok = True
        if res:
            primary = res
            break

    # —— 出版社官网核实 / 兜底 ——
    if primary:
        try:
            primary = enrich_with_publisher_sites(primary, should_cancel)
        except SearchCancelled:
            raise
        except NetworkError:
            pass                           # 核实失败不影响已有结果
        return primary

    for ad in PUBLISHER_ADAPTERS:
        if should_cancel and should_cancel():
            raise SearchCancelled()
        try:
            res = ad.search(query, limit=limit, should_cancel=should_cancel)
        except SearchCancelled:
            raise
        except NetworkError as exc:
            last_err.append(str(exc))
            continue
        any_source_ok = True
        if res:
            return res

    if not any_source_ok:
        raise NetworkError("；".join(last_err) or "所有数据源均无法连接")
    return []


# ============================================================================
# 三、后台检索线程（保证界面不卡顿）
# ============================================================================


class SearchWorker(QThread):
    """在子线程中执行联网检索，通过信号把结果/错误回传给界面线程。

    注意：信号里的 seq 是递增序号（32 位 int 安全范围）。
    不要用 id() 作代号 —— 64 位地址经 Qt 信号传输会被截断为 32 位！
    """
    results_ready = pyqtSignal(int, list)   # (检索序号, 结果列表)
    no_result = pyqtSignal(int, str)        # (检索序号, 查询词)
    network_error = pyqtSignal(int, str)    # (检索序号, 错误信息)

    def __init__(self, query: str, seq: int = 0, parent=None):
        super().__init__(parent)
        self.query = query
        self.seq = seq
        self._cancelled = False

    def cancel(self):
        """请求中止（开始新一轮搜索时调用）"""
        self._cancelled = True

    def run(self):
        dbg("worker 开始检索：", self.query)
        try:
            books = run_search(self.query, limit=4,
                               should_cancel=lambda: self._cancelled)
        except SearchCancelled:
            dbg("worker 被取消")
            return                      # 已被新一轮搜索取代，静默退出
        except NetworkError as exc:
            dbg("worker 网络错误：", str(exc))
            self.network_error.emit(self.seq, f"{exc}")
            return
        except Exception as exc:        # 兜底：任何意外都不允许让程序崩溃
            dbg("worker 意外异常：", repr(exc))
            self.network_error.emit(self.seq, f"检索出现意外问题：{exc}")
            return
        if self._cancelled:
            dbg("worker 完成但已取消")
            return
        dbg("worker 完成，结果数：", len(books))
        if books:
            self.results_ready.emit(self.seq, books)
        else:
            self.no_result.emit(self.seq, self.query)


# ============================================================================
# 四、界面组件层（仿 Apple 设计）
# ============================================================================


def _elide(text: str, width: int, font: QFont) -> str:
    """按像素宽度把文本截断成带省略号的形式"""
    return QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, width)


def rounded_pixmap(src: QPixmap, radius: float) -> QPixmap:
    """把图片裁剪为圆角矩形"""
    out = QPixmap(src.size())
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, src.width(), src.height(), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, src)
    painter.end()
    return out


class CoverLabel(QLabel):
    """书籍封面标签：先显示渐变占位图，封面图片异步下载完成后淡入展示"""

    WIDTH, HEIGHT = 96, 134

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pixmap: Optional[QPixmap] = None
        self.loaded = False
        self.setText("📖")
        self.setStyleSheet(f"""
            font-size: 30px;
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                             stop:0 #EDEDF0, stop:1 #DFDFE4);
            border-radius: 10px;
            color: {COLOR_TEXT_3};
        """)

    def load_from_url(self, url: str):
        """通过 QNetworkAccessManager 异步下载封面（不阻塞界面）"""
        if not url or self._pixmap is not None:
            return
        req = QNetworkRequest(QUrl(url))
        # 豆瓣图床要求携带 Referer，否则返回 403
        req.setRawHeader(b"Referer", b"https://book.douban.com/")
        reply = _network_manager().get(req)
        reply.finished.connect(lambda: self._on_downloaded(reply))

    def _on_downloaded(self, reply: QNetworkReply):
        reply.deleteLater()
        if self._pixmap is not None:
            return
        if reply.error() != QNetworkReply.NetworkError.NoError:
            return                  # 下载失败：保留占位图即可
        image = QImage.fromData(reply.readAll())
        if image.isNull():
            return
        # 2x 分辨率缩放以保证高分屏清晰，再裁圆角
        scaled = image.scaled(self.WIDTH * 2, self.HEIGHT * 2,
                              Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                              Qt.TransformationMode.SmoothTransformation)
        pm = QPixmap.fromImage(scaled)
        pm.setDevicePixelRatio(2.0)
        self._pixmap = rounded_pixmap(pm, 10)
        self.loaded = True
        self.setText("")
        self.setStyleSheet(f"background: {COLOR_CARD}; border: 1px solid {COLOR_LINE};"
                           f"border-radius: 10px;")
        self.update()               # 触发 paintEvent

    def paintEvent(self, event):
        """封面已下载则自绘，否则走默认占位样式"""
        if self._pixmap is not None:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.drawPixmap(0, 0, self._pixmap)
            painter.end()
        else:
            super().paintEvent(event)


_NAM: Optional[QNetworkAccessManager] = None


def _network_manager() -> QNetworkAccessManager:
    """惰性创建全局 QNetworkAccessManager（必须在 QApplication 之后创建）"""
    global _NAM
    if _NAM is None:
        _NAM = QNetworkAccessManager()
    return _NAM


class Spinner(QWidget):
    """极简加载动画：一段旋转的圆弧（Apple 风格的克制）"""

    def __init__(self, diameter: int = 30, parent=None):
        super().__init__(parent)
        self._angle = 0
        self.setFixedSize(diameter, diameter)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(60)

    def _tick(self):
        self._angle = (self._angle + 24) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(29, 29, 31, 120), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        m = 4
        painter.drawArc(m, m, self.width() - 2 * m, self.height() - 2 * m,
                        self._angle * 16, 260 * 16)


class TitleBar(QWidget):
    """无边框窗口的自定义标题栏：macOS 红绿灯 + 可拖拽区域"""

    HEIGHT = 46

    def __init__(self, window: "MainWindow", parent=None):
        super().__init__(parent)
        self._window = window
        self._press_pos = None
        self.setFixedHeight(self.HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)

        # —— 红绿灯 ——
        btn_close = QPushButton("×")
        btn_close.setObjectName("tlClose")
        btn_close.setToolTip("关闭")
        btn_min = QPushButton("−")
        btn_min.setObjectName("tlMin")
        btn_min.setToolTip("最小化")
        btn_max = QPushButton("+")
        btn_max.setObjectName("tlMax")
        btn_max.setToolTip("最大化 / 还原")
        for b, slot in ((btn_close, window.close),
                        (btn_min, window.showMinimized),
                        (btn_max, window._toggle_maximized)):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)

        title = QLabel("书籍百科 · BookPedia")
        title.setStyleSheet(f"font-size:13px; font-weight:600; color:{COLOR_TEXT};"
                            f"background:transparent;")

        layout.addWidget(btn_close)
        layout.addWidget(btn_min)
        layout.addWidget(btn_max)
        layout.addStretch(1)
        layout.addWidget(title)
        layout.addStretch(1)
        layout.addSpacing(42)       # 视觉配重，让标题真正居中

    # —— 标题栏拖拽移动窗口 ——
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = (event.globalPosition().toPoint()
                               - self._window.frameGeometry().topLeft())

    def mouseMoveEvent(self, event):
        if self._press_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._press_pos)

    def mouseReleaseEvent(self, event):
        self._press_pos = None

    def mouseDoubleClickEvent(self, event):
        self._window._toggle_maximized()


class BookCard(QFrame):
    """书籍信息卡片：封面 + 标题/作者 + 四项出版信息 + 简介 + 来源"""

    def __init__(self, book: BookInfo, parent=None):
        super().__init__(parent)
        self.setObjectName("bookCard")
        self.setFixedWidth(760)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        root = QHBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(18)

        # —— 左侧：封面 ——
        self.cover = CoverLabel()
        self.cover.load_from_url(book.cover_url)
        root.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignTop)

        # —— 右侧：信息列 ——
        col = QVBoxLayout()
        col.setSpacing(6)
        root.addLayout(col, 1)

        # 标题行（标题 + 评分徽标）
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_label = QLabel(_elide(book.title, 380, QFont("Microsoft YaHei UI", 11)))
        title_label.setToolTip(book.title)
        title_label.setWordWrap(False)
        title_label.setStyleSheet(
            f"font-size:17px; font-weight:700; color:{COLOR_TEXT}; background:transparent;")
        title_row.addWidget(title_label)
        title_row.addStretch(1)
        if book.verified:
            v_chip = QLabel("✓ 官网核实")
            v_chip.setToolTip("本书信息已到出版社官网核对/补充")
            v_chip.setStyleSheet("""
                font-size:12px; font-weight:600; color:#1D7A3E;
                background:rgba(52,199,89,0.16); border-radius:10px; padding:2px 9px;""")
            title_row.addWidget(v_chip)
        if book.rating:
            chip = QLabel(f"★ {book.rating}")
            chip.setStyleSheet("""
                font-size:12px; font-weight:600; color:#B25B00;
                background:rgba(255,159,10,0.14); border-radius:10px; padding:2px 9px;""")
            title_row.addWidget(chip)
        col.addLayout(title_row)

        if book.authors:
            author = QLabel(_elide(book.authors, 500, self.font()))
            author.setToolTip(book.authors)
            author.setStyleSheet(
                f"font-size:13px; color:{COLOR_TEXT_3}; background:transparent;")
            col.addWidget(author)

        # —— 出版信息四宫格：出版社 / 出版时间 / 定价 / ISBN ——
        price_text = book.price
        if price_text and _RE_FLOAT.fullmatch(price_text):
            price_text = f"¥ {price_text}"      # 纯数字定价自动补货币符号
        details = [
            ("出版社", book.publisher),
            ("出版时间", book.pub_date),
            ("定价", price_text or "—"),
            ("ISBN", book.isbn or "—"),
        ]
        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(2)
        grid.setContentsMargins(0, 6, 0, 0)
        for i, (label, value) in enumerate(details):
            lab = QLabel(label)
            lab.setStyleSheet(f"font-size:11px; color:{COLOR_TEXT_3};"
                              f"background:transparent;")
            val_font = QFont("Microsoft YaHei UI", 10)
            val = QLabel(_elide(value or "—", 150, val_font))
            val.setToolTip(value or "")
            val.setStyleSheet(f"font-size:13px; color:{COLOR_TEXT};"
                              f"background:transparent;")
            grid.addWidget(lab, 0, i)
            grid.addWidget(val, 1, i)
            grid.setColumnStretch(i, 1)
        col.addLayout(grid)

        # —— 简介（过长自动截断，完整内容放悬浮提示） ——
        if book.intro:
            intro = QLabel(book.intro if len(book.intro) <= 120
                           else book.intro[:120].rstrip() + "…")
            intro.setToolTip(book.intro)
            intro.setWordWrap(True)
            intro.setStyleSheet(f"font-size:13px; color:{COLOR_TEXT_2};"
                                f"background:transparent;")
            col.addSpacing(4)
            col.addWidget(intro)

        # —— 底部：来源标注 + 原页面链接 ——
        foot = QHBoxLayout()
        foot.setSpacing(10)
        src = QLabel(f"来源：{book.source}")
        src.setStyleSheet(f"font-size:11px; color:{COLOR_TEXT_3};"
                          f"background:transparent;")
        foot.addWidget(src)
        foot.addStretch(1)
        if book.detail_url:
            link = QLabel(f'<a href="{book.detail_url}" '
                          f'style="color:{COLOR_BLUE}; text-decoration:none;">'
                          f'查看原页面 ↗</a>')
            link.setOpenExternalLinks(True)
            link.setStyleSheet("font-size:11px; background:transparent;")
            foot.addWidget(link)
        col.addSpacing(6)
        col.addLayout(foot)


class StateView(QWidget):
    """统一构建三种非结果状态：空状态 / 加载中 / 错误提示（暴露标题/副标题引用）"""

    def __init__(self, emoji: str, title: str, subtitle: str = "",
                 spinner: bool = False, retry: bool = False, parent=None):
        super().__init__(parent)
        self.retry_btn: Optional[QPushButton] = None
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        if spinner:
            spin_wrap = QHBoxLayout()
            spin_wrap.addStretch(1)
            spin_wrap.addWidget(Spinner(34))
            spin_wrap.addStretch(1)
            layout.addLayout(spin_wrap)
        else:
            emoji_label = QLabel(emoji)
            emoji_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            emoji_label.setStyleSheet("font-size:46px; background:transparent;")
            layout.addWidget(emoji_label)

        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet(f"font-size:17px; font-weight:600;"
                                       f"color:{COLOR_TEXT}; background:transparent;")
        layout.addWidget(self.title_label)

        # 副标题始终创建（文案可后续动态更新），为空时暂时隐藏
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet(f"font-size:13px; color:{COLOR_TEXT_3};"
                                          f"background:transparent;")
        self.subtitle_label.setVisible(bool(subtitle))
        layout.addWidget(self.subtitle_label)

        if retry:
            layout.addSpacing(8)
            btn = QPushButton("重新搜索")
            btn.setObjectName("retryBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            # 保存引用，由主窗口稍后连接（构造时还未加入窗口树，取不到主窗口）
            self.retry_btn = btn
            wrap = QHBoxLayout()
            wrap.addStretch(1)
            wrap.addWidget(btn)
            wrap.addStretch(1)
            layout.addLayout(wrap)


# ============================================================================
# 五、主窗口
# ============================================================================

# 底部 QStackedWidget 的页面索引
(PAGE_EMPTY, PAGE_LOADING, PAGE_ERROR,
 PAGE_NOTFOUND, PAGE_RESULTS) = 0, 1, 2, 3, 4


class MainWindow(QMainWindow):
    """无边框圆角主窗口：标题栏 + 搜索区 + 状态/结果区"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("书籍百科 BookPedia")
        self.resize(940, 700)
        self.setMinimumSize(880, 620)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._worker: Optional[SearchWorker] = None
        self._seq = 0                 # 检索序号（用于丢弃过期回调）
        self._last_query = ""
        self._cards: List[BookCard] = []

        # ---------- 外层透明容器（为窗口阴影留出边距） ----------
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(22, 22, 22, 26)
        self.setCentralWidget(container)

        # ---------- 圆角面板（真正的内容区） ----------
        panel = QWidget()
        panel.setObjectName("rootPanel")
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        panel.setStyleSheet(f"""
            QWidget#rootPanel {{
                background-color: {COLOR_BG};
                border: 1px solid rgba(0, 0, 0, 0.05);
                border-radius: 20px;            /* 大圆角窗口 */
            }}
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(44)
        shadow.setXOffset(0)
        shadow.setYOffset(10)
        shadow.setColor(QColor(0, 0, 0, 46))
        panel.setGraphicsEffect(shadow)
        container_layout.addWidget(panel)

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # ---------- 1) 自定义标题栏 ----------
        panel_layout.addWidget(TitleBar(self))

        # ---------- 2) 标题区 ----------
        hero = QVBoxLayout()
        hero.setSpacing(6)
        hero.setContentsMargins(0, 22, 0, 0)
        h_title = QLabel("书籍百科")
        h_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_title.setStyleSheet(f"font-size:32px; font-weight:700; color:{COLOR_TEXT};"
                              f"background:transparent;")
        h_sub = QLabel("输入书名，一键检索权威出版信息 · 出版社 / 出版时间 / 定价 / ISBN / 简介")
        h_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_sub.setStyleSheet(f"font-size:13px; color:{COLOR_TEXT_3};"
                            f"background:transparent;")
        hero.addWidget(h_title)
        hero.addWidget(h_sub)
        panel_layout.addLayout(hero)

        # ---------- 3) 居中搜索区（半透明输入框 + 扁平化按钮） ----------
        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 20, 0, 6)
        search_row.addStretch(1)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setFixedSize(470, 42)
        self.search_input.setPlaceholderText("搜索书名，例如：三体")
        self.search_input.addAction(self._make_search_icon(),
                                    QLineEdit.ActionPosition.LeadingPosition)
        self.search_input.setClearButtonEnabled(True)
        self.search_btn = QPushButton("搜索")
        self.search_btn.setObjectName("searchBtn")
        self.search_btn.setFixedSize(84, 42)
        self.search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_btn.setEnabled(False)
        self.search_btn.clicked.connect(self._start_search_now)
        search_row.addWidget(self.search_input)
        search_row.addSpacing(10)
        search_row.addWidget(self.search_btn)
        search_row.addStretch(1)
        panel_layout.addLayout(search_row)

        # 输入即自动检索（700ms 防抖，避免每敲一个字都发请求）
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(700)
        self._debounce.timeout.connect(self._start_search_now)
        self.search_input.textChanged.connect(self._on_text_changed)
        self.search_input.returnPressed.connect(self._start_search_now)

        # ---------- 4) 状态区 / 结果区（QStackedWidget 切换五种页面） ----------
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding,
                                 QSizePolicy.Policy.Expanding)

        self.empty_view = StateView(
            "📚", "从一本书开始探索",
            "在上方输入任意书名并回车，程序将自动联网检索\n"
            "出版社、出版时间、定价、ISBN 与内容简介。")
        self.loading_view = StateView("", "正在检索…", "", spinner=True)
        self.error_view = StateView(
            "🛰️", "网络好像出了点问题",
            "无法连接到图书数据服务，请检查网络后重试。",
            retry=True)
        self.notfound_view = StateView(
            "🔍", "没有找到相关书籍",
            "试试更简短的书名关键词，或检查是否有错别字。")

        # 结果页：滚动区 + 卡片列表
        results_holder = QWidget()
        results_layout = QVBoxLayout(results_holder)
        results_layout.setContentsMargins(0, 10, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(24, 4, 24, 32)
        self.cards_layout.setSpacing(14)
        self.cards_layout.addStretch(1)
        self.scroll.setWidget(self.cards_container)
        results_layout.addWidget(self.scroll)

        for page in (self.empty_view, self.loading_view, self.error_view,
                     self.notfound_view, results_holder):
            self.stack.addWidget(page)
        self.error_view.retry_btn.clicked.connect(self.retry_last_search)

        panel_layout.addWidget(self.stack, 1)

        # ---------- 5) 底部状态栏 + 窗口缩放手柄 ----------
        bottom = QHBoxLayout()
        bottom.setContentsMargins(24, 0, 24, 12)
        self.status_label = QLabel("就绪 · 数据来源：豆瓣阅读 / Google 图书 / Open Library / 出版社官网")
        self.status_label.setStyleSheet(f"font-size:11px; color:{COLOR_TEXT_3};"
                                        f"background:transparent;")
        bottom.addWidget(self.status_label)
        bottom.addStretch(1)
        grip = QSizeGrip(panel)
        grip.setFixedSize(16, 16)
        bottom.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom)
        panel_layout.addLayout(bottom)

        self.stack.setCurrentIndex(PAGE_EMPTY)

    # ------------------------------------------------------------------ 工具
    @staticmethod
    def _make_search_icon() -> QIcon:
        """用 QPainter 画一枚放大镜图标（避免依赖图片资源）"""
        pm = QPixmap(20, 20)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(134, 134, 139), 1.8)
        p.setPen(pen)
        p.drawEllipse(3, 3, 10, 10)
        p.drawLine(12, 12, 17, 17)
        p.end()
        return QIcon(pm)

    def _toggle_maximized(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ------------------------------------------------------------------ 搜索
    def _on_text_changed(self, text: str):
        """输入变化：启停自动检索防抖器，并同步按钮可用态"""
        t = text.strip()
        self.search_btn.setEnabled(bool(t))
        if len(t) >= 2:
            self._debounce.start()          # 停止输入 700ms 后自动检索
        else:
            self._debounce.stop()

    def _start_search_now(self):
        """立即发起一次检索（回车 / 点击按钮 / 防抖触发共用）"""
        query = self.search_input.text().strip()
        if not query:
            return
        dbg("开始检索：", query)
        self._debounce.stop()
        self._last_query = query

        # 取消上一轮仍在进行的检索（结果通过序号校验后自动作废）
        if self._worker is not None:
            dbg("取消旧 worker")
            self._worker.cancel()
        self._seq += 1
        self._worker = SearchWorker(query, seq=self._seq, parent=self)
        self._worker.results_ready.connect(self._on_results)
        self._worker.no_result.connect(self._on_no_result)
        self._worker.network_error.connect(self._on_network_error)
        self._worker.start()

        # 进入加载态
        self.loading_view.title_label.setText(f"正在检索《{query}》")
        self.loading_view.subtitle_label.setText("正在访问豆瓣阅读等数据源，通常几秒内完成…")
        self.loading_view.subtitle_label.setVisible(True)
        self.stack.setCurrentIndex(PAGE_LOADING)
        self.status_label.setText(f"正在检索：{query}")

    def retry_last_search(self):
        """错误空状态里的"重新搜索"按钮"""
        if self._last_query:
            self._start_search_now()

    # -------------------------------------------------------------- 结果回调
    def _is_stale(self, worker_id: int) -> bool:
        """校验回调是否来自已过期的旧检索（以检索序号为准）"""
        if self._worker is None:
            return False                # 无进行中的检索（自检注入场景），放行
        stale = worker_id != self._seq
        if stale:
            dbg("忽略过期回调：seq =", worker_id, "当前 seq =", self._seq)
        return stale

    def _clear_cards(self):
        for card in self._cards:
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

    def _on_results(self, worker_id: int, books: list):
        dbg("_on_results 进入，seq =", worker_id, "数量 =", len(books))
        if self._is_stale(worker_id):
            return
        self._clear_cards()
        layout = self.cards_layout
        stretch = layout.takeAt(layout.count() - 1)     # 暂时取出底部弹簧
        for book in books:
            card = BookCard(book)
            self._cards.append(card)
            layout.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        self.stack.setCurrentIndex(PAGE_RESULTS)
        self.status_label.setText(
            f"共找到 {len(books)} 条结果 · 数据来源：豆瓣阅读 / Google 图书 / Open Library / 出版社官网")

    def _on_no_result(self, worker_id: int, query: str):
        if self._is_stale(worker_id):
            return
        self.notfound_view.subtitle_label.setText(
            f"没有找到与《{query}》相关的书籍。\n"
            "试试更简短的书名关键词，或检查是否有错别字。")
        self.stack.setCurrentIndex(PAGE_NOTFOUND)
        self.status_label.setText(f"未找到《{query}》")

    def _on_network_error(self, worker_id: int, message: str):
        if self._is_stale(worker_id):
            return
        # 详情写到副标题，主标题保持简短友好
        self.error_view.subtitle_label.setText(
            f"无法连接到图书数据服务，请检查网络后重试。\n（{message}）")
        self.stack.setCurrentIndex(PAGE_ERROR)
        self.status_label.setText("检索失败：网络异常")

    def closeEvent(self, event):
        """窗口关闭时停掉后台检索线程，避免退出崩溃"""
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        super().closeEvent(event)


# ============================================================================
# 六、入口
# ============================================================================


def resource_path(name: str) -> str:
    """获取资源文件绝对路径。

    兼容两种运行形态：
    - PyInstaller 打包后：资源解包在 sys._MEIPASS 临时目录；
    - 源码直接运行：资源与脚本同目录。
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def apply_app_icon(app: "QApplication"):
    """设置窗口/任务栏图标（exe 文件本身的图标由 PyInstaller 写入）"""
    icon_path = resource_path("icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))


def _install_excepthook():
    """全局异常钩子：任何未捕获异常都用对话框友好提示，而不是让程序闪退"""
    def handler(etype, value, tb):
        text = "".join(traceback.format_exception(etype, value, tb))[-1500:]
        try:
            QMessageBox.critical(
                None, "书籍百科遇到问题",
                f"程序遇到了一个意外错误，但没有退出。\n\n{text}")
        except Exception:
            pass
        sys.__excepthook__(etype, value, tb)
    sys.excepthook = handler


def main():
    _install_excepthook()
    app = QApplication(sys.argv)
    app.setApplicationName("书籍百科 BookPedia")
    apply_app_icon(app)                             # 窗口/任务栏图标
    app.setFont(QFont("Microsoft YaHei UI", 10))    # 中文环境下的基础字体
    app.setStyleSheet(GLOBAL_QSS)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


def probe_cli(query: str):
    """无界面模式：验证检索链路（--probe 书名）"""
    try:
        books = run_search(query, limit=3)
    except NetworkError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True))
        return
    print(json.dumps({"ok": True, "count": len(books),
                      "books": [b.__dict__ for b in books]}, ensure_ascii=True))


def selftest():
    """隐藏窗口渲染自检（--selftest）：截取各状态截图，便于回归检查界面。
    追加 `--e2e 书名` 可用真实网络完整跑一遍检索链路。"""
    argv = sys.argv[1:]
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(GLOBAL_QSS)

    def step(msg):
        print(f"[selftest] {msg}", flush=True)

    step("创建主窗口…")
    win = MainWindow()
    # 不真正弹窗，仅离屏合成渲染（使用系统真实字体库）
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.resize(940, 700)
    win.show()
    app.processEvents()
    step("窗口创建完成")

    sample = [
        BookInfo(
            title="三体", authors="刘慈欣", publisher="重庆出版社",
            pub_date="2008-1", price="23.00", isbn="9787536692930",
            rating="8.9", verified=True,
            intro=("文化大革命如火如荼进行的同时，军方探寻外星文明的绝秘计划"
                   "“红岸工程”取得了突破性进展。但在按下发射键的那一刻，"
                   "历经劫难的叶文洁没有意识到，她彻底改变了人类的命运。"),
            cover_url="https://img1.doubanio.com/view/subject/s/public/s2768378.jpg",
            detail_url="https://book.douban.com/subject/2567698/",
            source="豆瓣阅读 + 出版社官网"),
        BookInfo(
            title="活着", authors="余华", publisher="作家出版社",
            pub_date="2012-8-1", price="20.00", isbn="9787506365437",
            rating="9.4",
            intro="《活着》讲述了农村人福贵悲惨的人生遭遇。地主少爷福贵嗜赌成性，"
                  "终于赌光了家业一贫如洗。",
            source="豆瓣阅读"),
        BookInfo(
            title="The Pragmatic Programmer", authors="David Thomas / Andrew Hunt",
            publisher="Addison-Wesley", pub_date="2019-09-13",
            price="49.95 USD", isbn="9780135957059",
            intro="Straight from the programming trenches, The Pragmatic "
                  "Programmer cuts through the increasing specialization.",
            source="Google 图书"),
    ]
    win._on_results(1, sample)
    step("已注入样例结果")

    # 给封面图一点下载时间（有网络则封面淡入，无网络则保留占位图）
    for _ in range(80):
        app.processEvents()
        time.sleep(0.05)
        if all(c.cover.loaded for c in win._cards):
            break
    app.processEvents()
    step("开始保存结果页截图")
    win.grab().save("selftest_results.png")
    step("结果页截图完成")

    win._on_network_error(1, "所有数据源均无法连接（测试文案）")
    app.processEvents()
    win.grab().save("selftest_error.png")
    step("错误页截图完成")

    win._on_no_result(1, "测试书名")
    app.processEvents()
    win.grab().save("selftest_notfound.png")
    step("空状态截图完成")

    win.stack.setCurrentIndex(1)     # 加载态（不真正发起网络检索）
    app.processEvents()
    win.grab().save("selftest_loading.png")
    step("加载页截图完成")

    # —— 端到端链路验证：真实发起一次检索（后台线程 → 信号 → 卡片渲染）——
    query = (argv[argv.index("--e2e") + 1] if "--e2e" in argv
             and len(argv) > argv.index("--e2e") + 1 else "三体")
    step(f"端到端检索：{query}")
    win.search_input.setText(query)
    win._start_search_now()
    deadline = time.time() + 150     # 最多等待 150 秒
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.25)
        if win.stack.currentIndex() in (PAGE_RESULTS, PAGE_NOTFOUND, PAGE_ERROR):
            break
    app.processEvents()
    win.grab().save("selftest_e2e.png")
    step(f"端到端完成，当前页面索引：{win.stack.currentIndex()}（4=结果页）")

    # 自检结束前确保后台检索线程已退出，避免解释器关闭阶段崩溃
    if win._worker is not None and win._worker.isRunning():
        win._worker.cancel()
        win._worker.wait(3000)
    app.processEvents()
    print("selftest done", flush=True)


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--probe" in argv:
        idx = argv.index("--probe")
        probe_cli(argv[idx + 1] if idx + 1 < len(argv) else "三体")
    elif "--selftest" in argv:
        selftest()
    else:
        main()
