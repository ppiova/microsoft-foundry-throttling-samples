"""Export the public HTML deck to a linked PDF. Requires reportlab.

Run from any directory: python scripts/export_slides_pdf.py
The public deck is the content source. Presenter assets are never read.
"""
from html.parser import HTMLParser
from html import escape
from pathlib import Path
import textwrap

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output/pdf/understanding-and-mitigating-http-429.pdf'
REPO = 'https://github.com/ppiova/microsoft-foundry-throttling-samples'
VOID = {'br', 'meta', 'link', 'img', 'input', 'hr'}


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []


class Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def descendants(node, tag):
    if isinstance(node, str):
        return []
    return ([node] if node.tag == tag else []) + [n for child in node.children for n in descendants(child, tag)]


def plain(node):
    return node if isinstance(node, str) else ''.join(plain(c) for c in node.children)


def inline(node):
    if isinstance(node, str):
        return escape(node.replace('\u2192', ' > ').replace('\u2197', '').replace('\u25c7', ''))
    inner = ''.join(inline(c) for c in node.children)
    if node.tag == 'br':
        return '<br/>'
    if node.tag == 'a':
        href = node.attrs.get('href', '')
        if href.startswith('/'):
            href = REPO + '#explore-the-ui-and-slides'
        return f'<a href="{escape(href, quote=True)}" color="#0067b8"><u>{inner}</u></a>'
    if node.tag in ('strong', 'b', 'h3', 'dt'):
        return '<b>' + inner + '</b>'
    return inner


def build(slide, scale):
    def para(content, size=18, color='#172b40', **kwargs):
        return Paragraph(content, ParagraphStyle('slide', fontName='Helvetica', fontSize=size*scale,
                         leading=size*1.3*scale, textColor=colors.HexColor(color), spaceAfter=9*scale, **kwargs))

    def blocks(node, width):
        if isinstance(node, str):
            return []
        tag, cls = node.tag, node.attrs.get('class', '')
        if tag in ('aside', 'script', 'style'):
            return []
        if tag in ('h1', 'h2'):
            return [
                Paragraph(inline(node), ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=(38 if tag=='h1' else 29)*scale,
                leading=(43 if tag=='h1' else 34)*scale, textColor=colors.HexColor('#172b40'), spaceAfter=15*scale))]
        if tag == 'h3':
            return [para(inline(node), 20, '#0067b8')]
        if tag in ('p', 'a'):
            if tag == 'a' and node.attrs.get('href', '').startswith('/'):
                return [para(f'<a href="{REPO}#quick-start-with-docker" color="#0067b8"><u>Get the demo instructions</u></a>',18)]
            if 'The demo opens in another tab.' in plain(node):
                return [para('Follow the repository instructions to run the interactive demo.',13)]
            size = 11 if cls == 'source' else 13 if cls in ('caption', 'eyebrow') else 18
            if cls == 'takeaway':
                return [Spacer(1, 5*scale), Table([[para(inline(node), 16)]], colWidths=[width], style=TableStyle([
                    ('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#edf5fc')),('LINEBEFORE',(0,0),(0,-1),3,colors.HexColor('#0078d4')),
                    ('LEFTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),4)])), Spacer(1, 7*scale)]
            return [para(inline(node), size, '#0067b8' if cls=='eyebrow' else '#172b40')]
        if tag == 'pre':
            lines = []
            for line in plain(node).splitlines():
                lines.extend(textwrap.wrap(line, max(30, int(width/(12*scale*.6))-3), replace_whitespace=False,
                                           drop_whitespace=False) or [''])
            content = '<br/>'.join(escape(x).replace(' ', '&nbsp;') for x in lines)
            return [Paragraph(content, ParagraphStyle('code', fontName='Courier', fontSize=12*scale,
                    leading=16*scale, backColor=colors.HexColor('#edf5fc'), borderPadding=8, spaceAfter=12*scale))]
        if tag == 'table':
            rows = descendants(node, 'tr')
            count = len([c for c in rows[0].children if isinstance(c, Node) and c.tag in ('td','th')])
            data=[]
            for row in rows:
                data.append([para(inline(cell), 13 if cell.tag=='th' else 15, '#0067b8' if cell.tag=='th' else '#172b40')
                             for cell in row.children if isinstance(cell, Node) and cell.tag in ('td','th')])
            return [Table(data, colWidths=[width/count]*count, style=TableStyle([
                ('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),1.5,colors.HexColor('#0078d4')),
                ('LINEBELOW',(0,1),(-1,-1),.5,colors.HexColor('#d5dfe8')),('TOPPADDING',(0,0),(-1,-1),9*scale),
                ('BOTTOMPADDING',(0,0),(-1,-1),9*scale)])), Spacer(1,8*scale)]
        if tag in ('ol','ul'):
            return [para(('&#8226; ' if tag=='ul' else str(i)+'. ')+inline(item).replace('</b>','</b> '),16)
                    for i,item in enumerate([c for c in node.children if isinstance(c,Node) and c.tag=='li'],1)]
        if tag == 'dl':
            return [para(inline(c).replace('</b>','</b> &nbsp; '),18) for c in node.children if isinstance(c,Node)]
        if cls in ('split','code-columns'):
            cols=[c for c in node.children if isinstance(c,Node)]
            cell_width=(width-24)/2
            return [Table([[blocks(cols[0],cell_width), '', blocks(cols[1],cell_width)]],colWidths=[cell_width,24,cell_width],
                    style=TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]))]
        if cls in ('request-row','token-bar','equation'):
            return [para(' &nbsp; '.join(inline(c).replace('</b>','</b> ') for c in node.children if isinstance(c,Node)),20,'#0067b8')]
        return [b for child in node.children for b in blocks(child,width)]
    return blocks(slide,864)


def main():
    parser=Parser()
    parser.feed((ROOT/'demo/slides.html').read_text(encoding='utf-8'))
    slides=descendants(parser.root,'section')
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    pdf=canvas.Canvas(str(OUTPUT),pagesize=(960,540),pageCompression=1)
    pdf.setTitle('Understanding and mitigating HTTP 429')
    pdf.setAuthor('Pablo Piovano')
    pdf.setSubject('Public presentation: Azure OpenAI, Claude and Microsoft MAI. No speaker notes.')
    for number,slide in enumerate(slides,1):
        for scale in (1,.95,.9,.85,.8):
            flow=build(slide,scale)
            heights=[item.wrap(864,10000)[1]+item.getSpaceBefore()+item.getSpaceAfter() for item in flow]
            if sum(heights)<=435:
                break
        else:
            raise ValueError(f'Slide {number} does not fit')
        pdf.setFillColor(colors.HexColor('#0067b8'));pdf.rect(0,506,960,34,fill=1,stroke=0)
        pdf.setFillColor(colors.white);pdf.setFont('Helvetica-Bold',12);pdf.drawString(48,518,'Foundry Lab')
        pdf.setFont('Helvetica',10);pdf.drawRightString(912,518,'Independent community presentation')
        y=482
        for item in flow:
            _,height=item.wrap(864,10000)
            y-=item.getSpaceBefore()+height
            item.drawOn(pdf,48,y)
            y-=item.getSpaceAfter()
        pdf.setFillColor(colors.HexColor('#637587'));pdf.setFont('Helvetica',9)
        pdf.drawString(48,18,'Pablo Piovano | Microsoft MVP | Docker Captain')
        pdf.drawRightString(912,18,f'{number} / {len(slides)}')
        pdf.showPage()
    pdf.save()
    print(f'{len(slides)} slides exported to {OUTPUT}')


if __name__=='__main__':
    main()
