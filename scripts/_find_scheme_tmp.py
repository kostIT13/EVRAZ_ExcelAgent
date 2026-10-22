# -*- coding: utf-8 -*-
"""Поиск оставшихся schemeClr в слайде 4."""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pptx import Presentation
from pptx.oxml.ns import qn
from lxml import etree

p = Presentation("data/EVRAZ_Agent_defense.pptx")
s = p.slides[3]
for el in s._element.iter(qn("a:schemeClr")):
    parent = el.getparent()
    ptag = parent.tag.split("}")[-1] if parent is not None else "?"
    gtag = parent.getparent().tag.split("}")[-1] if (parent is not None and parent.getparent() is not None) else "?"
    print("schemeClr val=", el.get("val"), "| parent:", ptag, "| grandparent:", gtag)
    print("   ", etree.tostring(el).decode()[:200].replace("\n", " "))
