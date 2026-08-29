# -*- coding: utf-8 -*-
"""
make_icon.py —— 生成"书籍百科 BookPedia"应用图标
==================================================
设计说明（仿 macOS Big Sur 风格）：
  - 1024×1024 画布，大圆角方块（圆角半径约 22%，苹果图标比例）；
  - 蓝色对角渐变背景（#54A8FF → #0A5BD3），顶部一层极淡高光；
  - 白色"翻开的书"主体（左右页对称，书页边缘带弧度）；
  - 右下角叠一枚白色描边"放大镜"，点出"检索/百科"的产品含义。

产物：
  icon.png   1024×1024 母版（用于 README / 窗口图标）
  icon.ico   16/24/32/48/64/128/256 多尺寸（用于 exe 文件图标）

运行：python make_icon.py
"""

import os
import sys

# 离屏渲染，不弹出任何窗口
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import (QColor, QGuiApplication, QLinearGradient, QPainter,
                         QPainterPath, QPen, QPixmap, QBrush)

SIZE = 1024
CORNER = 224          # 大圆角（苹果图标比例约 22%）
OUT_PNG = "icon.png"
OUT_ICO = "icon.ico"


def rounded_path(r: float) -> QPainterPath:
    """整幅画布的大圆角轮廓（同时作为裁剪路径）"""
    p = QPainterPath()
    p.addRoundedRect(QRectF(0, 0, SIZE, SIZE), r, r)
    return p


def book_page(mirror: bool) -> QPainterPath:
    """构造"翻开的书"的半边页面（带弧度书页边缘）。

    mirror=False 画左页（书脊在右），True 画右页（书脊在左）。
    坐标以画布中心为书脊，左右镜像。
    """
    spine_x = 500.0            # 书脊 x（略偏左，给右侧放大镜留视觉重心）
    outer_x = 248.0            # 页面外缘 x
    top_spine, top_outer = 402.0, 368.0     # 书脊侧与外缘的书页上沿
    bot_spine, bot_outer = 648.0, 616.0     # 书页下沿

    def x(v):                  # 右页做镜像
        return (SIZE - v) if mirror else v

    path = QPainterPath()
    path.moveTo(x(spine_x), top_spine)
    # 上沿：从书脊向外缘的弧线（书页微微翻起）
    path.cubicTo(x(spine_x - 90), top_spine - 26,
                 x(outer_x + 110), top_outer - 8,
                 x(outer_x), top_outer)
    # 外缘竖边
    path.lineTo(x(outer_x), bot_outer)
    # 下沿：从外缘回到书脊
    path.cubicTo(x(outer_x + 110), bot_outer + 8,
                 x(spine_x - 90), bot_spine + 26,
                 x(spine_x), bot_spine)
    path.closeSubpath()
    return path


def draw_icon() -> QPixmap:
    pm = QPixmap(SIZE, SIZE)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # ---------- 背景：蓝色对角渐变 + 大圆角 ----------
    grad = QLinearGradient(0, 0, SIZE * 0.35, SIZE)
    grad.setColorAt(0.0, QColor("#5FAEFF"))
    grad.setColorAt(1.0, QColor("#0A54C8"))
    clip = rounded_path(CORNER)
    painter.setClipPath(clip)
    painter.fillPath(clip, QBrush(grad))

    # ---------- 顶部高光：极淡的白色圆角块，增加玻璃质感 ----------
    gloss = QPainterPath()
    gloss.addRoundedRect(QRectF(24, 20, SIZE - 48, 430), 190, 190)
    painter.fillPath(gloss, QColor(255, 255, 255, 26))

    # ---------- 主体：白色翻开的书 ----------
    painter.setPen(Qt.PenStyle.NoPen)
    painter.fillPath(book_page(False), QColor(255, 255, 255, 247))
    painter.fillPath(book_page(True), QColor(255, 255, 255, 247))

    # 书脊缝隙：中央细缝用背景色勾出立体感
    painter.setPen(QPen(QColor(10, 84, 200, 70), 10))
    painter.drawLine(QPointF(500, 402), QPointF(500, 648))

    # ---------- 点缀：右下角放大镜（白描边 + 圆头手柄） ----------
    pen = QPen(QColor(255, 255, 255, 245), 42)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QPointF(648, 610), 96, 96)
    painter.drawLine(QPointF(718, 680), QPointF(796, 758))

    painter.end()
    return pm


def pack_ico(png_path: str, ico_path: str):
    """用 Pillow 把 1024 母版缩成多尺寸打包为 .ico"""
    from PIL import Image
    img = Image.open(png_path)
    img.save(ico_path, format="ICO",
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                    (64, 64), (128, 128), (256, 256)])


def main():
    app = QGuiApplication(sys.argv)
    pm = draw_icon()
    ok_png = pm.save(OUT_PNG, "PNG")
    pack_ico(OUT_PNG, OUT_ICO)
    print("icon.png saved:", ok_png,
          "| icon.ico bytes:", os.path.getsize(OUT_ICO))


if __name__ == "__main__":
    main()
