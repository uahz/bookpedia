# 📚 书籍百科 BookPedia

> 输入任意书名，自动联网检索权威出版信息 —— **出版社 / 出版时间 / 定价 / ISBN / 评分 / 简介 / 封面**，
> 以仿 macOS 风格的卡片展示，并支持**出版社官网核实**。

![结果页](selftest_e2e.png)

## ✨ 功能特性

- **多源自动降级检索**：豆瓣阅读（主源）→ Google Books API → Open Library API，
  任一来源有结果即返回；全部失败才提示网络错误。
- **出版社官网核实**：检索结果若出自已适配官网的出版社（当前支持上海译文出版社），
  程序自动到其官网按 **ISBN 精确匹配同一版次**，用官网数据核实/补充
  定价、出版时间等字段，并打上「✓ 官网核实」徽标；主链路全部无结果时，
  还会直接向出版社官网发起书名检索兜底。
- **输入即搜**：停止输入 700ms 后自动触发检索（防抖），也支持回车或点击"搜索"。
- **卡片式展示**：封面（异步加载、圆角裁剪）+ 书名 / 评分徽标 / 作者 /
  出版社 / 出版时间 / 定价 / ISBN / 简介（超长截断，悬浮看全文）/ 来源与原页面链接。
- **友好的状态管理**：加载动画（旋转圆弧）、空状态、网络错误（附"重新搜索"按钮），
  任何异常都不会让程序闪退（全局异常钩子 + 后台线程全兜底）。
- **仿 Apple 视觉**：`#F5F5F7` 浅色背景、无边框大圆角窗口（带投影）、
  macOS 红绿灯按钮（标题栏可拖拽）、居中半透明搜索框、
  扁平化按钮（按下轻微渐变反馈）、系统无衬线字体栈（SF Pro / PingFang SC / 微软雅黑）。

| 错误状态 | 空状态 |
| --- | --- |
| ![错误状态](selftest_error.png) | ![空状态](selftest_notfound.png) |

## 🚀 快速开始

**方式一：直接下载 exe（Windows）**

前往 [Releases](../../releases) 下载 `书籍百科.exe`，双击即用，无需安装 Python。

**方式二：源码运行（Python 3.10+，Windows / macOS / Linux）**

```bash
git clone https://github.com/uahz/bookpedia.git
cd bookpedia
pip install -r requirements.txt
python book_encyclopedia.py
```

辅助命令（维护用）：

```bash
python book_encyclopedia.py --probe 三体          # 无界面验证检索链路，打印 JSON
python book_encyclopedia.py --selftest            # 隐藏窗口渲染各状态并截图
python book_encyclopedia.py --selftest --e2e 三体 # 端到端真实检索验证
python make_icon.py                               # 重新生成应用图标
```

## 📦 打包成 exe

```bash
pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --onefile ^
    --name 书籍百科 --icon icon.ico --add-data "icon.png;." book_encyclopedia.py
```

生成 `dist/书籍百科.exe`（单文件）。`书籍百科.spec` 是 PyInstaller 配置，
之后可直接 `pyinstaller 书籍百科.spec` 重新打包。程序未做代码签名，
首次运行如遇 SmartScreen 提示，点"仍要运行"即可。

## 🗂️ 代码结构（单文件 `book_encyclopedia.py`）

| 区块 | 内容 |
|---|---|
| 一、全局设计常量 | 颜色、字体栈、全局 QSS 样式表 |
| 二、网络检索层 | `BookInfo` 数据类；`DoubanSource`（requests 拉取网页 + BeautifulSoup4 解析）；`GoogleBooksSource` / `OpenLibrarySource`（JSON API）；`YiwenAdapter` 等出版社官网适配器（`PUBLISHER_ADAPTERS` 注册表）；`run_search` 编排器 |
| 三、后台检索线程 | `SearchWorker(QThread)`，信号回传结果 / 无结果 / 网络错误 |
| 四、界面组件层 | `CoverLabel`（封面异步下载）、`Spinner`（加载动画）、`TitleBar`（红绿灯 + 拖拽）、`BookCard`（结果卡片）、`StateView`（状态页） |
| 五、主窗口 | 无边框圆角窗口、搜索区、`QStackedWidget` 五态切换、防抖自动检索 |
| 六、入口 | `main()`、`probe_cli()`、`selftest()`、全局异常钩子 |

## 🏗️ 检索流程

```
输入书名 ──► 豆瓣阅读 ─┬─ 有结果 ──► 出版社在注册表中？
            Google Books ├─            │ 是 → 到官网按 ISBN 核实/补充 → 卡片加「✓ 官网核实」
            Open Library ┘            └ 否 → 直接展示
                 │
                 └─ 全部无结果 ──► 直接向出版社官网发起书名检索兜底
                 │
                 └─ 全部网络异常 ──► 友好错误提示（可一键重试）
```

## ➕ 接入更多出版社官网

各官网结构各异，代码采用**适配器注册表**：仿照 `YiwenAdapter` 写一个类
（实现 `key` / `display` / `search()`，用 requests + BeautifulSoup4 解析），
加入 `PUBLISHER_ADAPTERS` 列表即可，官网核实与兜底检索自动生效。
已探测待适配：清华大学出版社（检索接口报错）、商务印书馆（结果 JS 渲染）。

## ⚠️ 已知说明

- 豆瓣为非官方公开页面解析，若其调整结构或加强反爬，程序会自动降级到
  Google Books / Open Library，卡片上会标注实际数据来源；
- 豆瓣图床要求携带 Referer（已处理），封面经 Qt 网络模块异步下载；
- Google Books / Open Library 在中国大陆网络可能不可达，属正常降级。

---

License: [MIT](LICENSE)
