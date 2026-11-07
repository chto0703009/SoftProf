#!/usr/bin/env python3
# Copyright (c) 2026 Christer Törnkvist <christer@borgasundsfotografiska.se>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Render the Swedish and English Markdown guides as paginated PDF manuals."""
from pathlib import Path
import hashlib
import html
import re
import shutil

from reportlab.lib import colors
from reportlab.lib import enums
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Flowable
from reportlab.platypus import Image as PDFImage
from PIL import Image, ImageCms
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT/'VERSION').read_text().strip()
OUTPUT = ROOT/'output/pdf'
AUTHOR = 'Christer Törnkvist'
EMAIL = 'christer@borgasundsfotografiska.se'
GITHUB = 'https://github.com/chto0703009/SoftProf'
NAVY = colors.HexColor('#17324d')
TEAL = colors.HexColor('#168a9c')
pdfmetrics.registerFont(TTFont('Guide', str(ROOT/'resources/fonts/DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('GuideBold', str(ROOT/'resources/fonts/DejaVuSans-Bold.ttf')))
pdfmetrics.registerFontFamily('Guide', normal='Guide', bold='GuideBold', italic='Guide', boldItalic='GuideBold')
WIDTH = A4[0]-84
STYLES = {
    'body': ParagraphStyle('body', fontName='Guide', fontSize=9.5, leading=13.4, textColor=NAVY, spaceAfter=7),
    'title': ParagraphStyle('title', fontName='GuideBold', fontSize=20, leading=25, textColor=NAVY, spaceAfter=11, keepWithNext=True),
    'h3': ParagraphStyle('h3', fontName='GuideBold', fontSize=11, leading=14, spaceBefore=8, spaceAfter=5, textColor=TEAL, keepWithNext=True),
    'small': ParagraphStyle('small', fontName='Guide', fontSize=8, leading=11, textColor=NAVY, spaceAfter=5),
    'table': ParagraphStyle('table', fontName='Guide', fontSize=8.7, leading=12, textColor=NAVY),
    'tablehead': ParagraphStyle('tablehead', fontName='GuideBold', fontSize=8.7, leading=12, textColor=colors.white),
}


def markup(text):
    text = html.escape(text.replace('\u2013','-').replace('\u2014','-').replace('\u2011','-'))
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'`([^`]+)`', r'<font size="8.6">\1</font>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<link color="#168a9c" href="\2">\1</link>', text)
    return text


class Pipeline(Flowable):
    def __init__(self, language):
        Flowable.__init__(self); self.width=WIDTH; self.height=64; self.language=language
    def draw(self):
        c=self.canv
        names = ['1  Källprofil → Arbetsfärgrymd','2  Källprofil → Skrivarprofil'] if self.language=='sv' else ['1  Source → Working space','2  Source → Printer profile']
        box=(WIDTH-16)/2
        for index,name in enumerate(names):
            x=index*(box+16)
            c.setFillColor(colors.HexColor('#e9f5f6')); c.setStrokeColor(TEAL)
            c.roundRect(x,14,box,36,7,stroke=1,fill=1)
            c.setFillColor(NAVY);c.setFont('GuideBold',9);c.drawCentredString(x+box/2,27,name)


class GamutIllustration(Flowable):
    def __init__(self, language):
        Flowable.__init__(self);self.width=WIDTH;self.height=144;self.language=language
        n=18;lab=Image.new('LAB',(n,n));lab.putdata([(166,round(128+(x+.5)/n*200-100),round(128+(y+.5)/n*200-100)) for y in range(n) for x in range(n)])
        self.rgb=ImageCms.profileToProfile(lab,ImageCms.createProfile('LAB'),ImageCms.createProfile('sRGB'),outputMode='RGB');self.n=n
    def draw(self):
        c=self.canv; x0,y0,size=16,17,112
        for y in range(self.n):
            for x in range(self.n):
                rgb=self.rgb.getpixel((x,y));c.setFillColor(colors.Color(*[(v/255)*.5+.5 for v in rgb]));c.rect(x0+x*size/self.n,y0+y*size/self.n,size/self.n+.2,size/self.n+.2,stroke=0,fill=1)
        c.setStrokeColor(colors.HexColor('#82a1ad'));c.setLineWidth(.5);c.line(x0,y0+size/2,x0+size,y0+size/2);c.line(x0+size/2,y0,x0+size/2,y0+size)
        for vertices,color in [([(10,57),(28,97),(79,94),(104,60),(76,16),(32,12)],'#3180df'), ([(22,59),(40,82),(77,76),(91,46),(62,24),(32,32)],'#bb48bf')]:
            path=c.beginPath();path.moveTo(x0+vertices[0][0],y0+vertices[0][1])
            for x,y in vertices[1:]:path.lineTo(x0+x,y0+y)
            path.close();c.setStrokeColor(colors.HexColor(color));c.setLineWidth(1.7);c.drawPath(path)
        c.setFillColor(NAVY);c.setFont('Guide',8);c.drawString(x0+size+4,y0+size/2,'a*');c.drawString(x0+size/2-4,y0+size+4,'b*')
        c.setStrokeColor(NAVY);c.line(x0+81,y0+70,x0+68,y0+62)
        c.setFillColor(colors.HexColor('#3180df'));c.circle(x0+81,y0+70,3.5,stroke=0,fill=1)
        c.setFillColor(colors.HexColor('#bb48bf'));c.circle(x0+68,y0+62,3.5,stroke=0,fill=1)
        if self.language=='sv':
            caption='<b>Så orienterar du dig</b><br/>Grönt åt vänster, rött åt höger, gult uppåt och blått nedåt i a*/b*-vyn. Konturerna jämför profilernas ungefärliga omfång. Punkter och pilar visar färgens beräknade väg.<br/><br/><b>Principskiss.</b> Formen här är inte en mätning eller en viss ICC-profil. Appens färgtoning är också en visuell guide.'
        else:
            caption='<b>Find your way around</b><br/>Green to the left, red to the right, yellow upwards and blue downwards in a*/b*. Outlines compare approximate profile gamuts. Points and arrows show the predicted colour path.<br/><br/><b>Schematic illustration.</b> These shapes are not measured data or a particular ICC profile. The app background is also a visual guide.'
        paragraph=Paragraph(caption,STYLES['small']);w,h=paragraph.wrap(WIDTH-172,140);paragraph.drawOn(c,168,(self.height-h)/2)


def table(lines):
    rows=[]
    for index,line in enumerate(lines):
        if re.fullmatch(r'[| :\-]+',line):continue
        cells=[part.strip() for part in line.strip('|').split('|')]
        rows.append([Paragraph(markup(cell),STYLES['tablehead'] if not rows else STYLES['table']) for cell in cells])
    widths=[135,WIDTH-135]
    result=Table(rows,colWidths=widths,repeatRows=1,hAlign='LEFT')
    result.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#eff5f8'),colors.white]),('LINEBELOW',(0,-1),(-1,-1),.5,colors.HexColor('#cad9e0'))]))
    return result


def blocks(lines, language):
    output=[];index=0
    while index<len(lines):
        line=lines[index].strip()
        if not line or line=='---':index+=1;continue
        if line.startswith('### '):output.append(Paragraph(markup(line[4:]),STYLES['h3']));index+=1;continue
        if line=='<!-- pipeline -->':output.append(Pipeline(language));index+=1;continue
        if line=='<!-- gamut -->':output.append(GamutIllustration(language));index+=1;continue
        if line=='<!-- cloud -->':
            illustration=ROOT/'resources/colour-cloud-example.png'
            with Image.open(illustration) as picture: ratio=picture.height/picture.width
            output.append(PDFImage(str(illustration),width=WIDTH,height=WIDTH*ratio))
            caption=('Exempel från en syntetisk testbild. Punkterna i färgrymden beror på vald bild och inställningar.' if language=='sv' else 'Example from a synthetic test image. The colour-space points depend on the selected image and settings.')
            output.append(Paragraph(caption,STYLES['small']));index+=1;continue

        if line.startswith('|'):
            data=[]
            while index<len(lines) and lines[index].strip().startswith('|'):data.append(lines[index].strip());index+=1
            output.extend([table(data),Spacer(1,8)]);continue
        paragraph=[]
        while index<len(lines) and lines[index].strip() and not lines[index].startswith(('### ','|','<!--')):
            paragraph.append(lines[index]);index+=1
        text=' '.join(x.strip() for x in paragraph)
        output.append(Paragraph(markup(text),STYLES['body']))
    return output


def render(language):
    data=(ROOT/f'docs/softproof.{language}.md').read_text()
    sections=re.split(r'^## ',data,flags=re.MULTILINE)[1:]
    label='HANDBOK / SV' if language=='sv' else 'USER GUIDE / EN'
    destination=OUTPUT/f'SoftProf-Manual-{language}.pdf'
    document=SimpleDocTemplate(str(destination),pagesize=A4,leftMargin=42,rightMargin=42,topMargin=74,bottomMargin=51,
                              title=f'SoftProf {VERSION} - '+('Handbok' if language=='sv' else 'User guide'),author=f'{AUTHOR} <{EMAIL}>',subject='GPL-3.0-or-later; ICC soft proof and gamut analysis')
    def furniture(c,doc):
        c.saveState();w,h=A4
        c.setFillColor(NAVY);c.setFont('GuideBold',10);c.drawString(42,h-31,'SOFTPROF')
        c.setFont('Guide',8);c.drawRightString(w-42,h-31,f'{VERSION}  |  {label}  |  2026-11-07')
        c.setStrokeColor(TEAL);c.setLineWidth(2);c.line(42,h-43,w-42,h-43)
        c.setFont('Guide',7.2);c.setFillColor(NAVY)
        c.drawString(42,29,f'Christer Törnkvist  |  {EMAIL}  |  GPL-3.0-or-later')
        c.drawRightString(w-42,29,str(doc.page))
        c.linkURL('mailto:'+EMAIL,(42,24,w-75,36),relative=0,thickness=0)
        c.setFont('Guide',7)
        c.drawString(42,16,'GitHub: '+GITHUB.removeprefix('https://'))
        c.linkURL(GITHUB,(42,11,310,23),relative=0,thickness=0)
        c.restoreState()
    story=[]
    for index,section in enumerate(sections):
        heading,_,body=section.partition('\n')
        if index:story.append(PageBreak())
        story.append(Paragraph(markup(heading.strip()),STYLES['title']))
        story.extend(blocks(body.splitlines(),language))
    document.build(story,onFirstPage=furniture,onLaterPages=furniture)
    reader=PdfReader(destination)
    assert len(reader.pages)==len(sections),(language,'Unexpected pagination',len(reader.pages))
    for page in reader.pages:
        text=page.extract_text();assert AUTHOR in text and EMAIL in text and 'GPL-3.0-or-later' in text and GITHUB.removeprefix('https://') in text
    copy=Path.home()/'Downloads'/destination.name
    shutil.copyfile(destination,copy)
    assert hashlib.sha256(destination.read_bytes()).digest()==hashlib.sha256(copy.read_bytes()).digest()
    print(f'{language}: {len(reader.pages)} pages; {destination}; verified Downloads copy')


if __name__=='__main__':
    OUTPUT.mkdir(parents=True,exist_ok=True)
    for language in ('sv','en'):render(language)
