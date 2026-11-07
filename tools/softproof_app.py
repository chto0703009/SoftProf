#!/usr/bin/env python3
# Copyright (c) 2026 Christer Törnkvist <christer@borgasundsfotografiska.se>
# SPDX-License-Identifier: GPL-3.0-or-later
"""SoftProf: Python application with colour-managed macOS views.

PyObjC is isolated in local-config/softproof-python/vendor; the project
Python environment and colour engine are used without changing their packages.
"""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading

FROZEN = bool(getattr(sys, 'frozen', False))
ROOT = Path(sys._MEIPASS) if FROZEN else Path(__file__).resolve().parents[1]
if '--worker' in sys.argv:
    import softproof_engine
    index = sys.argv.index('--worker')
    sys.argv = [sys.argv[0], *sys.argv[index+1:]]
    raise SystemExit(softproof_engine.main())
if not FROZEN:
    sys.path.insert(0, str(ROOT / 'local-config/softproof-python/vendor'))
import objc
import AppKit as A
import Foundation as F
import Quartz as Q
from PyObjCTools import AppHelper
from runtime_architecture import detect_runtime
from cloud_view import CloudPlot

APP_VERSION = (ROOT/'VERSION').read_text().strip()
AUTHOR = 'Christer Törnkvist'
CONTACT = 'christer@borgasundsfotografiska.se'
GITHUB = 'https://github.com/chto0703009/SoftProf'

ROLES = ('source', 'working', 'printer')
ROLE_KEYS = ('1 Original', '2 Arbetsfärgrymd', '2 Utskrift')
COLORS = (A.NSColor.systemBlueColor(), A.NSColor.systemOrangeColor(), A.NSColor.systemPurpleColor())
AXES = ((1, 2),)
ACTIVE = None


def guarded(callback, *args):
    try:
        return callback(*args)
    except Exception as error:
        import traceback
        traceback.print_exc()
        if ACTIVE and ACTIVE.args.smoke_test:
            ACTIVE.fail_smoke(error)
        elif ACTIVE:
            ACTIVE.ui.message(ACTIVE.status, str(error))


def later(delay, callback, *args):
    AppHelper.callLater(delay, guarded, callback, *args)


def after(callback, *args):
    AppHelper.callAfter(guarded, callback, *args)

R = F.NSMakeRect
P = F.NSMakePoint


class UI:
    def __init__(self):
        self.catalog = json.loads((ROOT / 'tools/softproof.en.json').read_text())
        self.bindings = {}
        self.targets = []
        suite = os.environ.get('INKPROF_SOFTPROOF_PREFERENCES_SUITE', 'se.inkprof.softproof')
        bundle_id = F.NSBundle.mainBundle().bundleIdentifier()
        self.defaults = (F.NSUserDefaults.alloc().initWithSuiteName_(suite) if suite != bundle_id else None) or F.NSUserDefaults.standardUserDefaults()
        self.language = 'en' if self.defaults.stringForKey_('language') == 'en' else 'sv'

    def text(self, key, *args):
        template = self.catalog.get(key, key) if self.language == 'en' else key
        if args:
            for arg in args:
                template = template.replace('%@', str(arg), 1)
            return template
        if key in self.catalog or self.language == 'sv':
            return template
        for pattern in ('Profilens färgrymd stöds inte: %@', '%@ stöder inte %@. Välj TIFF eller en annan färgrymd.'):
            match = re.fullmatch('(.*?)'.join(map(re.escape, pattern.split('%@'))), key)
            if match:
                return self.text(pattern, *match.groups())
        return key

    def bind(self, obj, render, setter='setStringValue_'):
        self.bindings[(id(obj), setter)] = (obj, render, setter)
        getattr(obj, setter)(render())

    def message(self, field, key, *args):
        self.bind(field, lambda: self.text(key, *args))

    def refresh(self):
        for obj, render, setter in list(self.bindings.values()):
            getattr(obj, setter)(render())

    def label(self, key='', wrap=False, size=13):
        field = A.NSTextField.wrappingLabelWithString_('') if wrap else A.NSTextField.labelWithString_('')
        field.setFont_(A.NSFont.systemFontOfSize_(size))
        self.message(field, key)
        return field


class Action(A.NSObject):
    def action_(self, sender):
        guarded(self.callback, sender)


def button(ui, key, callback, checkbox=False):
    target = Action.alloc().init()
    target.callback = callback
    result = (A.NSButton.checkboxWithTitle_target_action_('', target, 'action:') if checkbox
              else A.NSButton.buttonWithTitle_target_action_('', target, 'action:'))
    ui.targets.append(target)  # Cocoa controls do not retain their targets.
    ui.bind(result, lambda: ui.text(key), 'setTitle_')
    return result


def stack(views, vertical=False, spacing=10):
    result = A.NSStackView.stackViewWithViews_(views)
    result.setOrientation_(A.NSUserInterfaceLayoutOrientationVertical if vertical else A.NSUserInterfaceLayoutOrientationHorizontal)
    result.setAlignment_(A.NSLayoutAttributeLeading if vertical else A.NSLayoutAttributeCenterY)
    result.setSpacing_(spacing)
    return result


def popup(ui, keys, callback):
    control = A.NSPopUpButton.alloc().initWithFrame_pullsDown_(R(0, 0, 200, 28), False)
    for key in keys:
        control.addItemWithTitle_(' ')
        item = control.lastItem()
        ui.bind(item, lambda key=key: ui.text(key), 'setTitle_')
    target = Action.alloc().init(); target.callback = callback
    control.setTarget_(target); control.setAction_('action:'); ui.targets.append(target)
    return control


class ImageView(A.NSImageView):
    def initWithFrame_(self, frame):
        self = objc.super(ImageView, self).initWithFrame_(frame)
        if self is not None:
            self.selected = None
            self.on_pick = None
        return self

    @objc.python_method
    def drawn_rect(self):
        if self.image() is None:
            return R(0, 0, 0, 0)
        bounds, size = self.bounds(), self.image().size()
        return R((bounds.size.width-size.width)/2, (bounds.size.height-size.height)/2, size.width, size.height)

    def mouseDown_(self, event):
        point, rect = self.convertPoint_fromView_(event.locationInWindow(), None), self.drawn_rect()
        if self.image() is not None and F.NSPointInRect(point, rect) and self.on_pick:
            self.on_pick((point.x-rect.origin.x)/rect.size.width, 1-(point.y-rect.origin.y)/rect.size.height)

    def drawRect_(self, dirty):
        objc.super(ImageView, self).drawRect_(dirty)
        if self.selected is None or self.image() is None:
            return
        rect = self.drawn_rect()
        x = rect.origin.x+self.selected[0]*rect.size.width
        y = rect.origin.y+(1-self.selected[1])*rect.size.height
        for color, width in ((A.NSColor.blackColor(), 4), (A.NSColor.whiteColor(), 1.5)):
            color.setStroke()
            path = A.NSBezierPath.bezierPathWithOvalInRect_(R(x-7, y-7, 14, 14)); path.setLineWidth_(width)
            path.moveToPoint_(P(x-13, y)); path.lineToPoint_(P(x+13, y))
            path.moveToPoint_(P(x, y-13)); path.lineToPoint_(P(x, y+13)); path.stroke()


class Pane(A.NSView):
    def initWithFrame_(self, frame):
        self = objc.super(Pane, self).initWithFrame_(frame)
        if self is not None:
            self.heading = A.NSTextField.labelWithString_('')
            self.heading.setFont_(A.NSFont.boldSystemFontOfSize_(16))
            self.detail = A.NSTextField.wrappingLabelWithString_('')
            self.detail.setFont_(A.NSFont.systemFontOfSize_(11)); self.detail.setMaximumNumberOfLines_(3)
            self.detail.setTextColor_(A.NSColor.secondaryLabelColor())
            self.scroll = A.NSScrollView.alloc().initWithFrame_(R(0, 0, 100, 100))
            self.scroll.setHasHorizontalScroller_(True); self.scroll.setHasVerticalScroller_(True)
            self.scroll.setAutohidesScrollers_(True); self.scroll.setBackgroundColor_(A.NSColor.colorWithWhite_alpha_(0.24, 1))
            self.picture = ImageView.alloc().initWithFrame_(R(0, 0, 1, 1))
            self.picture.setImageScaling_(A.NSImageScaleNone)
            self.scroll.setDocumentView_(self.picture)
            self.image_size = (1, 1)
            for view in (self.heading, self.detail, self.scroll): self.addSubview_(view)
        return self

    def layout(self):
        objc.super(Pane, self).layout()
        w, h = self.bounds().size
        self.heading.setFrame_(R(10, h-30, w-20, 24))
        self.detail.setFrame_(R(10, h-76, w-20, 42))
        self.scroll.setFrame_(R(0, 0, w, max(0, h-82)))

    @objc.python_method
    def set_image(self, image, original_size):
        self.picture.setImage_(image); self.image_size = original_size

    @objc.python_method
    def zoom(self, scale):
        viewport = self.scroll.contentView().bounds().size
        w, h = self.image_size[0]*scale, self.image_size[1]*scale
        self.picture.setFrame_(R(0, 0, max(viewport.width, w), max(viewport.height, h)))
        if self.picture.image() is not None: self.picture.image().setSize_((w, h))
        self.picture.setNeedsDisplay_(True)


class GamutPlot(A.NSView):
    def initWithFrame_(self, frame):
        self = objc.super(GamutPlot, self).initWithFrame_(frame)
        if self is not None:
            self.data, self.previous = {}, []
            self.projection = 0; self.visible_roles = set(ROLES)
            self.extents = [120, 160, 160]
            self.tint, self.strength = True, 0.5
            self.manual_lightness = None
            cg_lab = Q.CGColorSpaceCreateWithName(Q.kCGColorSpaceGenericLab)
            self.lab_space = A.NSColorSpace.alloc().initWithCGColorSpace_(cg_lab)
            self.color_key, self.colors = None, []
        return self

    @objc.python_method
    def lightness(self):
        if self.manual_lightness is not None:
            return self.manual_lightness
        points = self.data.get('points', [])
        return min(100, max(0, points[0]['lab'][0])) if points else 65

    @objc.python_method
    def update(self, response):
        self.previous = self.data.get('points', []) if self.data.get('pixel') is not None and self.data.get('pixel') == response.get('pixel') else []
        self.data = response
        for profile in response.get('profiles', []):
            for axes, vertices in zip(AXES, profile['projections']):
                for vertex in vertices:
                    for axis, value in zip(axes, vertex): self.extents[axis] = max(self.extents[axis], math.ceil(abs(value)/20)*20)
        for point in response.get('points', []):
            for axis, value in enumerate(point['lab']): self.extents[axis] = max(self.extents[axis], math.ceil(abs(value)/20)*20)
        self.setNeedsDisplay_(True)

    def drawRect_(self, dirty):
        A.NSBezierPath.bezierPathWithRect_(self.bounds()).addClip()
        A.NSColor.textBackgroundColor().setFill(); A.NSRectFill(self.bounds())
        w, h = self.bounds().size; xi, yi = AXES[self.projection]
        xmin, xmax = -self.extents[xi], self.extents[xi]
        ymin, ymax = (-20 if yi == 0 else -self.extents[yi]), self.extents[yi]
        unit = min(max(1, w-90)/(xmax-xmin), max(1, h-74)/(ymax-ymin))
        pw, ph = unit*(xmax-xmin), unit*(ymax-ymin)
        x0, y0 = 62+(max(1, w-90)-pw)/2, 46+(max(1, h-74)-ph)/2
        rect = R(x0, y0, pw, ph)
        def pos(x, y): return P(x0+(x-xmin)*unit, y0+(y-ymin)*unit)
        def labpos(lab): return pos(lab[xi], lab[yi])
        def text(value, x, y, color=None):
            F.NSString.stringWithString_(str(value)).drawAtPoint_withAttributes_(P(x, y), {A.NSFontAttributeName: A.NSFont.systemFontOfSize_(11), A.NSForegroundColorAttributeName: color or A.NSColor.secondaryLabelColor()})
        if self.tint and self.lab_space:
            cells = 80; key = (self.projection, tuple(self.extents), self.lightness())
            if key != self.color_key:
                colors = []
                for row in range(cells):
                    for col in range(cells):
                        lab = [self.lightness(), 0., 0., 1.]
                        lab[xi] = xmin+(col+0.5)/cells*(xmax-xmin); lab[yi] = ymin+(row+0.5)/cells*(ymax-ymin)
                        color = (A.NSColor.colorWithColorSpace_components_count_(self.lab_space, lab, 4).colorUsingColorSpace_(A.NSColorSpace.displayP3ColorSpace())
                                 if 0 <= lab[0] <= 100 else A.NSColor.colorWithWhite_alpha_(0.85, 1))
                        colors.append(color or A.NSColor.grayColor())
                self.colors, self.color_key = colors, key
            A.NSGraphicsContext.saveGraphicsState()
            A.NSBezierPath.bezierPathWithRect_(rect).addClip()
            for index, color in enumerate(self.colors):
                color.setFill(); A.NSRectFill(R(x0+index%cells*pw/cells, y0+index//cells*ph/cells, pw/cells+0.5, ph/cells+0.5))
            A.NSColor.whiteColor().colorWithAlphaComponent_(1-self.strength).setFill(); A.NSRectFillUsingOperation(rect, A.NSCompositingOperationSourceOver)
            A.NSGraphicsContext.restoreGraphicsState()
        for index in range(9):
            x = xmin+(xmax-xmin)*index/8; y = ymin+(ymax-ymin)*index/8
            A.NSColor.separatorColor().setStroke(); path = A.NSBezierPath.bezierPath(); path.setLineWidth_(0.5)
            path.moveToPoint_(pos(x, ymin)); path.lineToPoint_(pos(x, ymax)); path.moveToPoint_(pos(xmin, y)); path.lineToPoint_(pos(xmax, y)); path.stroke()
            text(f'{x:.0f}', pos(x, ymin).x-12, y0-20); text(f'{y:.0f}', max(4, x0-44), pos(xmin, y).y-6)
        text(('L*','a*','b*')[xi], x0+pw/2, 8); text(('L*','a*','b*')[yi], max(4, x0-32), y0+ph+8)
        for profile in self.data.get('profiles', []):
            if profile['role'] not in self.visible_roles: continue
            vertices = profile['projections'][self.projection]
            if not vertices: continue
            color = COLORS[ROLES.index(profile['role'])]
            path = A.NSBezierPath.bezierPath(); path.moveToPoint_(pos(*vertices[0]))
            for vertex in vertices[1:]: path.lineToPoint_(pos(*vertex))
            if len(vertices)>2: path.closePath()
            color.colorWithAlphaComponent_(0.065).setFill(); path.fill()
            if self.tint:
                A.NSColor.whiteColor().colorWithAlphaComponent_(0.8).setStroke(); path.setLineWidth_(3.6); path.stroke()
            color.setStroke(); path.setLineWidth_(1.8); path.stroke()
        for sample in self.previous:
            if sample['role'] not in self.visible_roles: continue
            p = labpos(sample['lab']); A.NSColor.grayColor().setStroke()
            ring = A.NSBezierPath.bezierPathWithOvalInRect_(R(p.x-6, p.y-6, 12, 12)); ring.stroke()
        samples = [p for p in self.data.get('points', []) if p['role'] in self.visible_roles]
        for first, second in zip(samples, samples[1:]):
            start, end = labpos(first['lab']), labpos(second['lab'])
            dx, dy = end.x-start.x, end.y-start.y; length = math.hypot(dx, dy)
            A.NSColor.labelColor().setStroke(); path = A.NSBezierPath.bezierPath(); path.setLineWidth_(1.6)
            path.moveToPoint_(start); path.lineToPoint_(end)
            if length>12:
                ux, uy = dx/length, dy/length
                path.moveToPoint_(P(end.x-9*ux+4*uy, end.y-9*uy-4*ux)); path.lineToPoint_(end); path.lineToPoint_(P(end.x-9*ux-4*uy, end.y-9*uy+4*ux))
            path.stroke()
        for index, sample in enumerate(samples):
            p, radius, color = labpos(sample['lab']), 9-index*2, COLORS[ROLES.index(sample['role'])]
            marker = A.NSBezierPath.bezierPathWithOvalInRect_(R(p.x-radius, p.y-radius, radius*2, radius*2))
            color.setFill(); marker.fill(); A.NSColor.whiteColor().setStroke(); marker.setLineWidth_(1.2); marker.stroke()
            text('1' if sample['role']=='source' else '2', p.x+12, p.y+16-index*15, color)


class GamutWindow:
    def __init__(self, controller):
        self.owner, self.ui = controller, controller.ui
        ui = self.ui
        self.window = make_window(820, 820); self.window.setReleasedWhenClosed_(False)
        ui.bind(self.window, lambda: ui.text('SoftProf · Färgomfång och färgprov'), 'setTitle_')
        body = make_body(self.window)
        body.addArrangedSubview_(ui.label('Färgens väg genom profilerna · CIELAB D50', size=18))
        self.is3d = False
        self.cloud_context = self.previous_cloud_context = None
        self.mode = button(ui, 'Visa 3D-färgrymd', self.change_mode)
        ui.bind(self.mode, lambda: ui.text('Visa 2D' if self.is3d else 'Visa 3D-färgrymd'), 'setTitle_')
        self.cloud_role = popup(ui, ROLE_KEYS, self.change_cloud)
        self.cloud_role.selectItemAtIndex_(2)
        self.movement = button(ui, 'Visa förflyttning', self.change_cloud, True)
        self.movement.setState_(A.NSControlStateValueOn)
        self.compare_reference = button(ui, 'Jämför vänster → höger', lambda _: controller.schedule_gamut(), True)
        body.addArrangedSubview_(stack([self.compare_reference]))
        self.reset3d = button(ui, 'Återställ 3D-vy', lambda _: self.cloud.reset_camera())
        body.addArrangedSubview_(stack([self.mode, self.cloud_role, self.movement, self.reset3d]))
        self.toggles = [button(ui, key, self.change_roles, True) for key in ROLE_KEYS]
        for toggle, color in zip(self.toggles, COLORS): toggle.setState_(A.NSControlStateValueOn); toggle.setContentTintColor_(color)
        body.addArrangedSubview_(stack(self.toggles, spacing=14))
        self.background = button(ui, 'Färgtonad bakgrund', self.change_background, True); self.background.setState_(A.NSControlStateValueOn)
        self.strength = A.NSSlider.sliderWithValue_minValue_maxValue_target_action_(50, 10, 100, None, None)
        target = Action.alloc().init(); target.callback = self.change_background
        self.strength.setTarget_(target); self.strength.setAction_('action:'); ui.targets.append(target)
        self.strength.widthAnchor().constraintEqualToConstant_(130).setActive_(True)
        body.addArrangedSubview_(stack([self.background, ui.label('Styrka:'), self.strength]))
        self.follow_lightness = button(ui, 'Följ färgprovets L*', self.change_lightness, True)
        self.follow_lightness.setState_(A.NSControlStateValueOn)
        self.lightness_slider = A.NSSlider.sliderWithValue_minValue_maxValue_target_action_(65, 0, 100, None, None)
        self.lightness_slider.widthAnchor().constraintEqualToConstant_(180).setActive_(True)
        self.lightness_value = A.NSTextField.alloc().initWithFrame_(R(0, 0, 64, 24))
        self.lightness_value.widthAnchor().constraintEqualToConstant_(64).setActive_(True)
        formatter = F.NSNumberFormatter.alloc().init()
        formatter.setMinimum_(0); formatter.setMaximum_(100)
        formatter.setMaximumFractionDigits_(1)
        self.lightness_value.setFormatter_(formatter); self.lightness_value.setDoubleValue_(65)
        for control in (self.lightness_slider, self.lightness_value):
            target = Action.alloc().init(); target.callback = self.change_lightness
            control.setTarget_(target); control.setAction_('action:'); ui.targets.append(target)
        body.addArrangedSubview_(stack([self.follow_lightness, ui.label('L* (0–100):'), self.lightness_slider, self.lightness_value]))
        self.hint = ui.label(wrap=True, size=11); self.hint.setMaximumNumberOfLines_(2)
        self.plot = GamutPlot.alloc().initWithFrame_(R(0, 0, 600, 360))
        self.cloud = CloudPlot.alloc().initWithFrame_(R(0, 0, 600, 360))
        self.cloud.setHidden_(True)
        self.canvas = A.NSView.alloc().initWithFrame_(R(0, 0, 600, 360))
        for plot in (self.plot, self.cloud):
            plot.setTranslatesAutoresizingMaskIntoConstraints_(False); self.canvas.addSubview_(plot)
            for edge in ('leadingAnchor','trailingAnchor','topAnchor','bottomAnchor'):
                getattr(plot,edge)().constraintEqualToAnchor_(getattr(self.canvas,edge)()).setActive_(True)
        self.direction = ui.label(wrap=True, size=12)
        self.direction.setMaximumNumberOfLines_(5); self.direction.setHidden_(True)
        ui.bind(self.direction, self.direction_text)
        self.message = ui.label('Klicka i bilden för att välja ett färgprov.', True)
        self.values = ui.label(wrap=True, size=12); self.values.setFont_(A.NSFont.monospacedSystemFontOfSize_weight_(12, A.NSFontWeightRegular))
        self.values.setMaximumNumberOfLines_(8)
        self.profiles = ui.label(wrap=True, size=11); self.profiles.setMaximumNumberOfLines_(3)
        note = ui.label('Konturer: ungefärliga konvexa ytterhöljen av samplade ICC-värden, projicerade på a*/b*-planet. De visar inte exakt om en färg ryms. Grå ringar: föregående inställning för samma pixel. Lab-punkterna visar profilernas absoluta D50-värden; skärm och pappersvitssimulering ingår inte.', True, 11)
        self.plot_note=note
        ui.bind(note, lambda: ui.text('L*: mörkt → ljust · a*: grönt → rött · b*: blått → gult. Dra för att rotera.' if self.is3d and self.compare_reference.state() else '3D visar bildens samplade färggrupper. L* ökar mot ljusare färger uppåt; a* går från grönt (−) till rött (+), b* från blått (−) till gult (+). Vid rotation följer riktningarna axlarnas märkning. Punktstorlek anger ungefärlig förekomst. Skärmfärgerna är approximativa; punkterna är inte hela profilens omfång.' if self.is3d else 'Konturer: ungefärliga konvexa ytterhöljen av samplade ICC-värden, projicerade på a*/b*-planet. De visar inte exakt om en färg ryms. Grå ringar: föregående inställning för samma pixel. Lab-punkterna visar profilernas absoluta D50-värden; skärm och pappersvitssimulering ingår inte.'))
        for view in (self.hint, self.canvas, self.direction, self.message, self.values, self.profiles, note):
            body.addArrangedSubview_(view); view.widthAnchor().constraintEqualToAnchor_constant_(body.widthAnchor(), -32).setActive_(True)
        self.canvas.heightAnchor().constraintGreaterThanOrEqualToConstant_(300).setActive_(True)
        self.canvas.setContentHuggingPriority_forOrientation_(1, A.NSLayoutConstraintOrientationVertical)
        self.window.setMinSize_((780, 820)); self.window.center(); self.change_lightness()

    def change_mode(self, sender=None):
        self.is3d = not self.is3d
        self.plot.setHidden_(self.is3d); self.cloud.setHidden_(not self.is3d)
        self.direction.setHidden_(not self.is3d)
        self.ui.refresh(); self.update_hint()
        self.canvas.setNeedsDisplay_(True)

    def direction_text(self):
        return self.direction_description()+'\n'+self.ui.text('Svaga, tunna pilar = sällsynta färger. Starka pilar = vanligare färger. Pilens längd visar färgskillnaden, inte hur vanlig färgen är.')

    def direction_description(self):
        ui=self.ui
        if self.compare_reference.state() and self.plot.data.get('referenceCloud'):
            return ui.text('Gul pil: vänster bild → höger bild. Pilspetsen visar högerbildens färg.')
        if self.owner.workflow=='printers':
            points=ui.text(ROLE_KEYS[ROLES.index(self.cloud.role)])
            text=ui.text('Punkter: %@. Gula pilar: original → utskrift. Pilens början är originalfärgen; pilspetsen är skrivarens beräknade färg.',points)
            if not self.movement.state():
                text+='\n'+ui.text('Markera Visa förflyttning för att visa pilarna.')
            return text
        text=ui.text('Gula pilar: tidigare läge → nytt läge. Pilspetsen visar resultatet efter byte av färgrymd eller andra inställningar.')
        if not self.movement.state():
            text=ui.text('Markera Visa förflyttning för gula pilar från tidigare läge till nytt läge vid byte av färgrymd eller inställningar.')
        if self.cloud_context:
            space,role=self.cloud_context
            current=ui.text('%@ · %@',space,ui.text(ROLE_KEYS[ROLES.index(role)]))
            if self.previous_cloud_context:
                old_space,old_role=self.previous_cloud_context
                previous=ui.text('%@ · %@',old_space,ui.text(ROLE_KEYS[ROLES.index(old_role)]))
                text+='\n'+ui.text('Före: %@ → Efter: %@',previous,current)
            else:
                text+='\n'+ui.text('Nu: %@. Ändra färgrymd eller inställningar för att jämföra.',current)
        return text

    def change_cloud(self, sender=None):
        same_image=self.cloud.data.get('identity')==self.plot.data.get('cloud',{}).get('identity')
        self.previous_cloud_context=self.cloud_context if same_image else None
        comparing=bool(self.compare_reference.state())
        if comparing:
            stages={s['role'] for s in self.plot.data.get('cloud',{}).get('stages',[])}
            self.cloud_role.selectItemAtIndex_(2 if 'printer' in stages else 1)
        self.cloud.role = ROLES[self.cloud_role.indexOfSelectedItem()]
        space=self.plot.data.get('working')
        self.cloud_context=(space,self.cloud.role) if space else None
        self.cloud.motion = bool(self.movement.state()) or comparing
        self.cloud.update_cloud(self.plot.data.get('cloud', {}), self.plot.data.get('points', []), self.plot.data.get('referenceCloud') if self.compare_reference.state() else None)
        self.ui.bind(self.direction,self.direction_text)
        self.ui.refresh()
        self.update_hint()

    def change_roles(self, sender=None):
        self.plot.visible_roles = {role for role, button in zip(ROLES, self.toggles) if button.state() and not button.isHidden()}
        self.change_lightness()

    def change_background(self, sender=None):
        self.plot.tint = bool(self.background.state()); self.plot.strength = self.strength.doubleValue()/100
        self.strength.setEnabled_(self.plot.tint); self.change_lightness()

    def change_lightness(self, sender=None):
        if sender is self.lightness_value:
            self.lightness_slider.setDoubleValue_(min(100, max(0, sender.doubleValue())))
        self.plot.manual_lightness = (None if self.follow_lightness.state()
                                      else self.lightness_slider.doubleValue())
        self.update_hint(); self.plot.setNeedsDisplay_(True)

    def update_hint(self):
        comparing=self.is3d and bool(self.compare_reference.state())
        for view in (self.message,self.values,self.profiles): view.setHidden_(comparing)
        self.compare_reference.setEnabled_(self.is3d and self.owner.reference_request is not None)
        enabled = self.plot.tint and not self.is3d
        self.background.setEnabled_(not self.is3d); self.strength.setEnabled_(enabled)
        for toggle in self.toggles: toggle.setEnabled_(not self.is3d)
        for control in (self.cloud_role,self.movement,self.reset3d): control.setEnabled_(self.is3d)
        if comparing:
            self.cloud_role.setEnabled_(False); self.movement.setEnabled_(False)
        self.follow_lightness.setEnabled_(enabled)
        manual = enabled and not self.follow_lightness.state()
        self.lightness_slider.setEnabled_(manual); self.lightness_value.setEnabled_(manual)
        value = self.plot.lightness()
        self.lightness_value.setDoubleValue_(value)
        if self.follow_lightness.state(): self.lightness_slider.setDoubleValue_(value)
        if self.is3d:
            cloud=self.plot.data.get('cloud',{})
            self.ui.message(self.hint, '3D: %@ vanliga färggrupper ur %@ samplade pixlar. Dra för att rotera, rulla för att zooma. Pilar visar föregående → nytt läge.', len(cloud.get('ids',[])), cloud.get('sampled',0))
            if self.owner.workflow=='printers':
                self.ui.message(self.hint, '3D: %@ färggrupper. Dra för att rotera, rulla för att zooma. Pilar: original → utskrift, oavsett valda punkter.',len(cloud.get('ids',[])))
            if self.compare_reference.state():
                self.ui.message(self.hint, 'Vänster: %@ → Höger: %@', Path(self.owner.reference_request.get('printer','')).name or self.owner.reference_caption().split(' · ')[0], Path(self.owner.printer or '').name or self.owner.proof_caption().split(' · ')[0])
        else:
            self.ui.message(self.hint, 'Kulörguide: a*/b* vid L*=%@. L* 0 är svart, 100 är vitt. Endast bakgrunden ändras; konturer och färgprov är oförändrade.', f'{value:.1f}')

    def update(self, response):
        self.plot.update(response)
        available={'source','printer'} if self.owner.workflow=='printers' else {'source','working'}
        stages={s['role'] for s in response.get('cloud',{}).get('stages',[])} & available
        for role,toggle in zip(ROLES,self.toggles): toggle.setHidden_(role not in available)
        self.plot.visible_roles={role for role,toggle in zip(ROLES,self.toggles) if role in available and toggle.state()}
        for i,role in enumerate(ROLES):
            self.cloud_role.itemAtIndex_(i).setEnabled_(role in stages)
            self.cloud_role.itemAtIndex_(i).setHidden_(role not in available)
        if ROLES[self.cloud_role.indexOfSelectedItem()] not in stages and stages:
            self.cloud_role.selectItemAtIndex_(2 if 'printer' in stages else 1 if 'working' in stages else 0)
        self.change_cloud(); ui = self.ui
        def message():
            pixel = response.get('pixel')
            text = (ui.text('Originalpixel x=%@, y=%@ · Pilar: original → arbetsfärgrymd → förväntad utskrift', pixel[0]+1, pixel[1]+1)
                    if pixel else ui.text('Klicka i någon av bildvyerna för att följa en färg.'))
            if pixel and self.owner.workflow=='printers': text=ui.text('Originalpixel x=%@, y=%@ · Pilar: original → förväntad utskrift',pixel[0]+1,pixel[1]+1)
            elif pixel: text=ui.text('Originalpixel x=%@, y=%@ · Pilar: original → arbetsfärgrymd',pixel[0]+1,pixel[1]+1)
            if self.is3d and pixel: text=ui.text('Originalpixel x=%@, y=%@',pixel[0]+1,pixel[1]+1)
            if 'alpha' in response: text += ui.text(' · Alfa %@/%@ (prov före bakgrundsblandning)', response['alpha'], response.get('alphaMax',255))
            return text
        ui.bind(self.message, message)
        def values():
            rows = []
            name_width=max(len(ui.text(key)) for key in ROLE_KEYS)
            channel_width=5 if response.get('bits',8)==16 else 3
            for sample in response.get('points', []):
                if sample['role'] not in available: continue
                name = ui.text(ROLE_KEYS[ROLES.index(sample['role'])]); l, a, b = sample['lab']
                channels="["+", ".join(f"{v:>{channel_width}}" for v in sample['channels'])+"]"
                rows.append(f"{name:<{name_width}}  L* {l:6.2f}  a* {a:7.2f}  b* {b:7.2f}  ΔE76 {sample['deltaE76']:6.2f}  {sample['mode']:<4} {channels}")
            return '\n'.join(rows)
        ui.bind(self.values, values)
        ui.bind(self.profiles, lambda: '\n'.join(f"{ui.text(ROLE_KEYS[ROLES.index(p['role'])])}: {p['name']}" for p in response.get('profiles', []) if p['role'] in available))


def make_window(w, h):
    style = A.NSWindowStyleMaskTitled | A.NSWindowStyleMaskClosable | A.NSWindowStyleMaskMiniaturizable | A.NSWindowStyleMaskResizable
    window = A.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(R(0, 0, w, h), style, A.NSBackingStoreBuffered, False)
    window.setReleasedWhenClosed_(False)
    return window


def make_body(window):
    body = BodyStack.stackViewWithViews_([])
    body.setOrientation_(A.NSUserInterfaceLayoutOrientationVertical)
    body.setAlignment_(A.NSLayoutAttributeLeading); body.setSpacing_(10)
    body.setEdgeInsets_(A.NSEdgeInsetsMake(16, 16, 16, 16))
    window.setContentView_(body)
    return body


class BodyStack(A.NSStackView):
    def drawRect_(self, dirty):
        A.NSColor.windowBackgroundColor().setFill(); A.NSRectFill(self.bounds())
        objc.super(BodyStack, self).drawRect_(dirty)


class Delegate(A.NSObject):
    def applicationDidFinishLaunching_(self, notification):
        try:
            self.owner.start()
        except Exception:
            import traceback
            traceback.print_exc()
            self.owner.exit_code = 1
            self.owner.stop()
            os._exit(1)
    def tabView_didSelectTabViewItem_(self, tabview, item):
        if hasattr(self.owner,'save'): self.owner.change_workflow(str(item.identifier()))

    def applicationShouldTerminate_(self, app):
        process = self.owner.processes.get('save')
        if process is None or process.poll() is not None:
            return A.NSTerminateNow
        self.owner.ui.message(self.owner.status, 'Sparar klart innan appen avslutas…')
        def finish():
            if process.poll() is None:
                later(0.1, finish)
            else:
                app.replyToApplicationShouldTerminate_(True)
        later(0.1, finish)
        return A.NSTerminateLater

    def applicationShouldTerminateAfterLastWindowClosed_(self, app): return True
    def applicationWillTerminate_(self, notification): self.owner.stop()
    def windowDidResize_(self, notification): self.owner.update_zoom()
    def windowDidChangeScreen_(self, notification): self.owner.screen_changed()
    def windowDidChangeBackingProperties_(self, notification): self.owner.update_zoom()
    def windowWillClose_(self, notification):
        if self.owner.gamut is not None: self.owner.gamut.window.close()
    def synchronizeScroll_(self, notification): self.owner.synchronize_scroll(notification.object())


class Controller:
    def __init__(self, args):
        self.args, self.ui = args, UI()
        self.runtime = detect_runtime()
        self.temporary = Path(tempfile.mkdtemp(prefix='SoftProf-Python-'))
        self.processes = {}; self.revisions = {'render': 0, 'gamut': 0}
        self.closing = False; self.ready = False; self.exporting = False
        self.path = self.printer = self.pixel = None
        self.reference_request = None
        self.source_prompt_pending = False
        self.workflow = 'spaces'; self.workflow_states = {}
        self.gamut = None; self.original = self.proof = self.reference = None
        self.original_caption = self.proof_caption = self.reference_caption = lambda: ''
        self.original_size = (1, 1); self.syncing = False
        self.delegate = Delegate.alloc().init(); self.delegate.owner = self
        self.smoke_phase = 0; self.exit_code = 0
        self.scheduled = 0
        self.profile_paths = {}
        for name, space in [('Display P3', A.NSColorSpace.displayP3ColorSpace()), ('Adobe RGB (1998)', A.NSColorSpace.adobeRGB1998ColorSpace())]:
            path = self.temporary/(name+'.icc'); path.write_bytes(bytes(space.ICCProfileData())); self.profile_paths[name] = str(path)
        self.profile_paths['sRGB'] = 'srgb'
        romm = Path('/System/Library/ColorSync/Profiles/ROMM RGB.icc')
        if romm.exists(): self.profile_paths['ProPhoto RGB'] = str(romm)
        for architecture in (() if 'ProPhoto RGB' in self.profile_paths else ('arm64', 'x86_64')):
            path = ROOT/f'third_party/argyll/{architecture}/Argyll_V3.5.0/ref/ProPhoto.icm'
            if path.exists(): self.profile_paths['ProPhoto RGB'] = str(path); break

    def start(self):
        self.build()
        A.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        if self.args.startup_check or self.args.language_check:
            if self.args.language_check: assert self.ui.language == self.args.language_check
            assert self.language.indexOfSelectedItem() == (self.ui.language == 'en')
            assert self.runtime['process'] in self.runtime_label.stringValue()
            print('PASS: Python app startup, native windows, saved language and architecture:', self.runtime, flush=True)
            A.NSApplication.sharedApplication().terminate_(None); return
        if self.args.smoke_test:
            self.tabs.selectTabViewItemWithIdentifier_('printers')
            self.path, self.printer, self.smoke_output = self.args.smoke_test
            self.ui.bind(self.image_label, lambda: Path(self.path).name)
            self.ui.bind(self.printer_label, lambda: Path(self.printer).name)
            self.working.selectItemAtIndex_(1)
            self.settings_changed()
            # The integration check repeatedly serialises full 16-bit TIFF
            # references, which is substantially slower under Rosetta.
            later(120, self.smoke_timeout)

    def build(self):
        ui = self.ui
        self.window = make_window(1240, 880); self.window.setMinSize_((1040, 770))
        self.window.setTitle_('SoftProf · Python'); self.window.setDelegate_(self.delegate)
        body = make_body(self.window)
        self.language = popup(ui, ('Svenska', 'English'), self.change_language)
        self.language.selectItemAtIndex_(1 if ui.language == 'en' else 0)
        body.addArrangedSubview_(stack([ui.label('Jämför färgrymd och utskrift', size=23), ui.label('Språk / Language:'), self.language]))
        self.image_label = ui.label('Ingen bild vald')
        body.addArrangedSubview_(stack([button(ui, 'Öppna bild…', self.open_image), self.image_label]))
        self.tab_buttons=[button(ui,key,lambda _,identifier=identifier:self.select_workflow(identifier)) for identifier,key in (('spaces','1 Färgrymder'),('printers','2 Skrivarprofiler'))]
        for control in self.tab_buttons:
            control.setButtonType_(A.NSPushOnPushOffButton)
            control.widthAnchor().constraintEqualToConstant_(200).setActive_(True)
        body.addArrangedSubview_(stack(self.tab_buttons))
        self.tabs=A.NSTabView.alloc().initWithFrame_(R(0,0,1000,36))
        self.tabs.setTabViewType_(A.NSNoTabsNoBorder)
        self.tabs.heightAnchor().constraintEqualToConstant_(36).setActive_(True)
        for identifier,key,hint in (
            ('spaces','1 Färgrymder','Välj en arbetsfärgrymd för höger bild. Originalet visas till vänster. Utforska färgerna i 2D eller 3D.'),
            ('printers','2 Skrivarprofiler','Välj en skrivarprofil för höger bild. Jämför med originalet eller välj en andra skrivarprofil.')):
            item=A.NSTabViewItem.alloc().initWithIdentifier_(identifier)
            ui.bind(item,lambda key=key:ui.text(key),'setLabel_')
            content=A.NSView.alloc().initWithFrame_(R(0,0,1000,36))
            label=ui.label(hint,True,12);label.setTranslatesAutoresizingMaskIntoConstraints_(False);content.addSubview_(label)
            label.leadingAnchor().constraintEqualToAnchor_(content.leadingAnchor()).setActive_(True)
            label.trailingAnchor().constraintEqualToAnchor_(content.trailingAnchor()).setActive_(True)
            label.centerYAnchor().constraintEqualToAnchor_(content.centerYAnchor()).setActive_(True)
            item.setView_(content)
            self.tabs.addTabViewItem_(item)
        body.addArrangedSubview_(self.tabs)
        self.tabs.widthAnchor().constraintEqualToAnchor_constant_(body.widthAnchor(),-32).setActive_(True)
        names = list(self.profile_paths)
        # Keep the familiar order while storing paths independently of labels.
        names = [name for name in ('sRGB', 'Adobe RGB (1998)', 'Display P3', 'ProPhoto RGB') if name in names]
        self.source_paths = [None]+[self.profile_paths[name] for name in names]
        self.working_paths = self.source_paths.copy()
        self.source = popup(ui, ['Inbäddad profil (om den finns)']+names, self.settings_changed)
        self.working = popup(ui, ['Behåll bildens färgrymd']+names, self.settings_changed)
        self.source_row=stack([ui.label('Källprofil för bild utan profil:'), self.source, button(ui, 'Annan källprofil…', lambda _: self.choose_profile('source'))])
        body.addArrangedSubview_(self.source_row)
        self.working_label=ui.label('Arbetsfärgrymd:')
        self.working_row=stack([self.working_label, self.working])
        self.custom_working=button(ui, 'Annan färgrymd…', lambda _: self.choose_profile('working'))
        self.printer_label = ui.label('Välj skrivarens och papperets ICC-profil')
        self.printer_row=stack([button(ui, 'Välj skrivar-/pappersprofil…', lambda _: self.choose_profile('printer')), self.printer_label])
        body.addArrangedSubview_(self.printer_row)
        self.intent = popup(ui, ('Relativ kolorimetrisk', 'Absolut kolorimetrisk', 'Perceptuell'), self.settings_changed)
        self.bpc = button(ui, 'Svartpunktskompensation', self.settings_changed, True); self.bpc.setState_(A.NSControlStateValueOn)
        self.paper = button(ui, 'Simulera pappersvitt', self.settings_changed, True)
        self.ink = button(ui, 'Simulera trycksvärta', self.settings_changed, True); self.ink.setState_(A.NSControlStateValueOn)
        self.render_settings=stack([stack([ui.label('Återgivning:'),self.intent]),stack([self.bpc,self.ink,self.paper])],vertical=True)
        self.print_render_container=stack([],vertical=True)
        body.addArrangedSubview_(self.print_render_container)
        self.pin = button(ui, 'Lås simulering som referens', self.pin_reference)
        self.compare = button(ui, 'Jämför med annan profil…', self.compare_profile)
        self.compare.setEnabled_(False)
        self.unpin = button(ui, 'Återställ vänster till original', self.clear_reference)
        self.swap = button(ui, 'Byt vänster ↔ höger', self.swap_comparison)
        self.swap.setEnabled_(False)
        self.pin.setEnabled_(False); self.unpin.setEnabled_(False)
        self.zoom = popup(ui, ('Anpassa', '25 %', '50 %', '100 %'), self.update_zoom)
        self.comparison_actions=stack([self.pin,self.compare])
        body.addArrangedSubview_(self.comparison_actions)
        body.addArrangedSubview_(stack([self.swap, self.unpin, ui.label('Gemensam zoom:'), self.zoom]))
        self.colour_controls=stack([self.working_row,self.custom_working],vertical=True)
        self.colour_controls_row=stack([A.NSView.alloc().initWithFrame_(R(0,0,1,1)),self.colour_controls],spacing=14)
        self.colour_controls_row.setDistribution_(A.NSStackViewDistributionFillEqually)
        body.addArrangedSubview_(self.colour_controls_row)
        self.colour_controls_row.widthAnchor().constraintEqualToAnchor_constant_(body.widthAnchor(),-32).setActive_(True)
        self.left, self.right = (Pane.alloc().initWithFrame_(R(0, 0, 600, 360)) for _ in range(2))
        panes = stack([self.left, self.right], spacing=14); panes.setDistribution_(A.NSStackViewDistributionFillEqually)
        panes.heightAnchor().constraintGreaterThanOrEqualToConstant_(260).setActive_(True)
        panes.setContentHuggingPriority_forOrientation_(1, A.NSLayoutConstraintOrientationVertical)
        body.addArrangedSubview_(panes)
        ui.message(self.left.heading, 'Original'); ui.message(self.right.heading, 'Simulering')
        ui.message(self.left.detail, 'Bildens färger med källprofilen'); ui.message(self.right.detail, 'Välj en bild och en skrivarprofil')
        self.left.picture.on_pick = self.right.picture.on_pick = self.pick_color
        self.save = button(ui, 'Konvertera och spara…', self.export_image); self.save.setEnabled_(False)
        self.gamut_button=button(ui, 'Färgomfång…', self.show_gamut)
        save_spacer=A.NSView.alloc().initWithFrame_(R(0,0,1,1))
        save_spacer.setContentHuggingPriority_forOrientation_(1,A.NSLayoutConstraintOrientationHorizontal)
        actions=stack([stack([ui.label('Klicka i bilden för att följa en färg')]),stack([self.gamut_button,save_spacer,self.save])],spacing=14)
        actions.setDistribution_(A.NSStackViewDistributionFillEqually)
        body.addArrangedSubview_(actions)
        self.status = ui.label('Öppna en bild. Originalfilen ändras aldrig.', True, 12)
        self.display_label = ui.label(wrap=True, size=11)
        self.runtime_label = ui.label(wrap=True, size=11)
        def runtime_text():
            host = self.runtime['hardware']
            if host == 'unknown': host = ui.text('Okänd')
            execution = ui.text({'native':'Direkt (native)', 'rosetta':'Via Rosetta (Intel på Apple Silicon)', 'unknown':'Okänd'}[self.runtime['execution']])
            return ui.text('Dator: %@ · Python: %@ · Körning: %@', host, self.runtime['process'], execution)
        ui.bind(self.runtime_label, runtime_text)
        note = ui.label('Förhandsvisning: högst 1600 pixlar, approximativ • Export: full upplösning, 8 eller 16 bitar/kanal', True, 11)
        for view in (self.status, self.display_label, self.runtime_label, note): body.addArrangedSubview_(view)
        for view in (panes, actions, self.status, self.display_label, self.runtime_label, note): view.widthAnchor().constraintEqualToAnchor_constant_(body.widthAnchor(), -32).setActive_(True)
        spacer = A.NSView.alloc().initWithFrame_(R(0, 0, 1, 1))
        spacer.setContentHuggingPriority_forOrientation_(1, A.NSLayoutConstraintOrientationHorizontal)
        self.quit_button = button(ui, 'Avsluta', lambda _: A.NSApplication.sharedApplication().terminate_(None))
        footer = stack([spacer, self.quit_button])
        body.addArrangedSubview_(footer)
        footer.widthAnchor().constraintEqualToAnchor_constant_(body.widthAnchor(), -32).setActive_(True)
        for pane in (self.left, self.right):
            clip = pane.scroll.contentView(); clip.setPostsBoundsChangedNotifications_(True)
            F.NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(self.delegate, 'synchronizeScroll:', A.NSViewBoundsDidChangeNotification, clip)
        self.build_menu()
        self.refresh_workflow(); self.tabs.setDelegate_(self.delegate)
        self.window.center(); self.window.makeKeyAndOrderFront_(None); self.screen_changed()

    def select_workflow(self, workflow):
        self.tabs.selectTabViewItemWithIdentifier_(workflow)
        self.refresh_workflow()

    def workflow_state(self):
        return dict(source=self.source.indexOfSelectedItem(),working=self.working.indexOfSelectedItem(),
                    printer=self.printer,intent=self.intent.indexOfSelectedItem(),bpc=self.bpc.state(),
                    paper=self.paper.state(),ink=self.ink.state(),reference=self.reference,
                    reference_request=self.reference_request,reference_caption=self.reference_caption,
                    compare3d=bool(self.gamut and self.gamut.compare_reference.state()))

    def change_workflow(self, workflow):
        if workflow==self.workflow: return
        self.workflow_states[self.workflow]=self.workflow_state()
        state=self.workflow_states.get(workflow,dict(source=self.source.indexOfSelectedItem(),working=0,
            printer=None,intent=0,bpc=1,paper=0,ink=1,reference=None,reference_request=None,
            reference_caption=lambda:'',compare3d=False))
        self.workflow=workflow
        self.source.selectItemAtIndex_(state['source']); self.working.selectItemAtIndex_(state['working'])
        self.printer=state['printer']; self.intent.selectItemAtIndex_(state['intent'])
        self.bpc.setState_(state['bpc']); self.paper.setState_(state['paper']); self.ink.setState_(state['ink'])
        if workflow=='spaces': state.update(reference=None,reference_request=None,reference_caption=lambda:'',compare3d=False)
        self.reference=state['reference']; self.reference_request=state['reference_request']
        self.reference_caption=state['reference_caption']
        self.ui.bind(self.printer_label,lambda:Path(self.printer).name if self.printer else self.ui.text('Välj skrivarens och papperets ICC-profil'))
        self.unpin.setEnabled_(self.reference is not None)
        self.left.set_image(self.reference if self.reference is not None else None,self.original_size)
        self.ui.bind(self.left.detail,self.reference_caption if self.reference is not None else self.original_caption)
        self.ui.message(self.left.heading,'Låst referens' if self.reference is not None else 'Original')
        self.right.set_image(None,self.original_size)
        if self.gamut:
            self.gamut.compare_reference.setState_(state['compare3d'])
            self.gamut.plot.data={};self.gamut.plot.previous=[];self.gamut.plot.setNeedsDisplay_(True)
            self.gamut.cloud.update_cloud({},[])
            self.gamut.update_hint()
        self.refresh_workflow();self.settings_changed()

    def refresh_workflow(self):
        printing=self.workflow=='printers'
        for index,control in enumerate(self.tab_buttons): control.setState_(index==int(printing))
        self.printer_row.setHidden_(not printing)
        self.working_row.setHidden_(printing)
        self.colour_controls_row.setHidden_(printing)
        self.print_render_container.setHidden_(not printing)
        destination=self.print_render_container if printing else self.colour_controls
        parent=self.render_settings.superview()
        if parent is not destination:
            if parent is not None:
                parent.removeArrangedSubview_(self.render_settings); self.render_settings.removeFromSuperview()
            destination.addArrangedSubview_(self.render_settings)
        self.paper.setHidden_(not printing);self.ink.setHidden_(not printing)
        self.compare.setHidden_(not printing);self.pin.setHidden_(True)
        self.comparison_actions.setHidden_(not printing)
        self.swap.setHidden_(not printing);self.unpin.setHidden_(not printing)
        self.ui.bind(self.pin,lambda:self.ui.text('Lås färgrymden till vänster'),'setTitle_')
        self.save.setHidden_(not printing)
        self.ui.message(self.right.heading,'Simulerad utskrift' if printing else 'Efter byte av färgrymd')
        self.ui.bind(self.gamut_button,lambda:self.ui.text('Färgomfång…'),'setTitle_')
        if self.gamut:
            self.ui.bind(self.gamut.window,lambda:self.ui.text('SoftProf · Skrivarprofiler · 2D / 3D' if self.workflow=='printers' else 'SoftProf · Färgrymder · 2D / 3D'),'setTitle_')

    def build_menu(self):
        ui = self.ui; main = A.NSMenu.alloc().init()
        for title, items in [('', [('Om SoftProf', '', self.show_about), ('Visa GPL-licensen', '', self.show_license), ('Avsluta SoftProf', 'q', lambda _: A.NSApplication.sharedApplication().terminate_(None))]),
                             ('Redigera', [('Kopiera','c','copy:'), ('Klistra in','v','paste:'), ('Markera allt','a','selectAll:')])]:
            top = A.NSMenuItem.alloc().init(); main.addItem_(top)
            submenu = A.NSMenu.alloc().initWithTitle_('')
            ui.bind(submenu, lambda title=title: ui.text(title), 'setTitle_')
            for key, shortcut, action in items:
                item = A.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('', action if isinstance(action, str) else 'action:', shortcut)
                if not isinstance(action, str):
                    target = Action.alloc().init(); target.callback = action; item.setTarget_(target); ui.targets.append(target)
                ui.bind(item, lambda key=key: ui.text(key), 'setTitle_'); submenu.addItem_(item)
            top.setSubmenu_(submenu)
        A.NSApplication.sharedApplication().setMainMenu_(main)

    def show_about(self, sender=None):
        alert = A.NSAlert.alloc().init()
        alert.setMessageText_(f'SoftProf {APP_VERSION}')
        alert.setInformativeText_(f'Copyright (c) 2026 {AUTHOR}\n{CONTACT}\n{GITHUB}\n\n'+self.ui.text('Fri programvara under GNU GPL version 3 eller senare. Programmet tillhandahålls utan garanti.'))
        alert.addButtonWithTitle_(self.ui.text('Stäng'))
        alert.runModal()

    def show_license(self, sender=None):
        path = ROOT/'Notices/SoftProf-GPL-3.0.txt' if FROZEN else ROOT/'LICENSE'
        A.NSWorkspace.sharedWorkspace().openURL_(F.NSURL.fileURLWithPath_(str(path)))

    def change_language(self, sender=None):
        self.ui.language = 'en' if self.language.indexOfSelectedItem() else 'sv'
        self.ui.defaults.setObject_forKey_(self.ui.language, 'language')
        self.ui.refresh()
        for menu in (self.source, self.working, self.intent, self.zoom, self.language): menu.synchronizeTitleAndSelectedItem()

    def screen_changed(self):
        screen = self.window.screen() if hasattr(self, 'window') else None
        self.ui.message(self.display_label, 'Skärm: %@ · ICC-märkta Display P3-bilder visas genom macOS ColorSync.', screen.localizedName() if screen else self.ui.text('aktuell skärm'))
        self.update_zoom()

    def dialog(self, key, image=False):
        panel = A.NSOpenPanel.openPanel(); panel.setTitle_(self.ui.text(key)); panel.setPrompt_(self.ui.text('Öppna'))
        panel.setAllowsMultipleSelection_(False); panel.setCanChooseDirectories_(False)
        panel.setAllowedFileTypes_(['tif','tiff','png','jpg','jpeg'] if image else ['icc','icm'])
        preference='imageDirectory' if image else 'profileDirectory'
        remembered=self.ui.defaults.stringForKey_(preference)
        default=Path.home()/'Desktop' if image else Path('/Library/ColorSync/Profiles')
        directory=Path(remembered) if remembered and Path(remembered).is_dir() else default
        panel.setDirectoryURL_(F.NSURL.fileURLWithPath_(str(directory)))
        if panel.runModal()!=A.NSModalResponseOK: return None
        selected=str(panel.URL().path())
        self.ui.defaults.setObject_forKey_(str(Path(selected).parent),preference)
        return selected

    def open_image(self, sender=None):
        path = self.dialog('Öppna bild', True)
        if not path: return
        self.path = path; self.source.selectItemAtIndex_(0); self.pixel = None
        self.source_prompt_pending = True
        self.source_row.setHidden_(False)
        for state in self.workflow_states.values():
            state.update(reference=None,reference_request=None,reference_caption=lambda:'',compare3d=False,source=0)
        self.reference_request = None
        if self.gamut: self.gamut.compare_reference.setState_(0)
        self.original = self.proof = self.reference = None
        self.ui.bind(self.image_label, lambda: Path(self.path).name)
        self.ui.message(self.left.heading, 'Original'); self.ui.message(self.left.detail, 'Bildens färger med källprofilen')
        self.unpin.setEnabled_(False)
        for pane in (self.left, self.right): pane.set_image(None, self.original_size); pane.picture.selected = None
        if self.gamut:
            self.gamut.plot.data = {}; self.gamut.plot.previous = []; self.gamut.plot.setNeedsDisplay_(True)
            self.gamut.cloud.update_cloud({}, [])
            self.gamut.update_hint()
        self.settings_changed()

    def prompt_source_profile(self):
        alert = A.NSAlert.alloc().init()
        alert.setMessageText_(self.ui.text('Bilden saknar ICC-profil'))
        alert.setInformativeText_(self.ui.text('Välj den källprofil som bilden skapades med. Profilen används för visningen; originalfilen ändras inte.'))
        choices = A.NSPopUpButton.alloc().initWithFrame_pullsDown_(R(0, 0, 360, 28), False)
        choices.addItemWithTitle_(self.ui.text('Välj källprofil…'))
        for index in range(1, len(self.source_paths)):
            choices.addItemWithTitle_(self.source.itemAtIndex_(index).title())
        alert.setAccessoryView_(choices)
        apply = alert.addButtonWithTitle_(self.ui.text('Visa bilden'))
        apply.setEnabled_(False)
        target = Action.alloc().init()
        target.callback = lambda _: apply.setEnabled_(choices.indexOfSelectedItem() > 0)
        choices.setTarget_(target); choices.setAction_('action:')
        alert.addButtonWithTitle_(self.ui.text('Annan källprofil…'))
        alert.addButtonWithTitle_(self.ui.text('Avbryt'))
        result = alert.runModal()
        if result == A.NSAlertFirstButtonReturn and choices.indexOfSelectedItem() > 0:
            self.source.selectItemAtIndex_(choices.indexOfSelectedItem())
            self.settings_changed()
        elif result == A.NSAlertSecondButtonReturn:
            self.choose_profile('source')

    def choose_profile(self, role):
        key = {'source':'Välj källprofil', 'working':'Välj arbetsfärgrymdens ICC-profil','printer':'Välj skrivarens och papperets ICC-profil'}[role]
        path = self.dialog(key)
        if not path: return
        if role == 'printer':
            self.printer = path; self.ui.bind(self.printer_label, lambda: Path(self.printer).name)
        else:
            menu, paths = (self.source, self.source_paths) if role == 'source' else (self.working, self.working_paths)
            menu.addItemWithTitle_(Path(path).name); paths.append(path); menu.selectItemAtIndex_(len(paths)-1)
        self.settings_changed()

    def request(self):
        request = dict(image=self.path, intent=(1,3,0)[self.intent.indexOfSelectedItem()], bpc=bool(self.bpc.state()), paper=bool(self.paper.state()), ink=bool(self.ink.state()) or bool(self.paper.state()), display=self.profile_paths['Display P3'])
        source, working = self.source_paths[self.source.indexOfSelectedItem()], self.working_paths[self.working.indexOfSelectedItem()]
        if source: request['source'] = source
        if working and self.workflow=='spaces': request['working'] = working
        if self.workflow=='printers' and self.printer: request['printer'] = self.printer
        if self.workflow=='spaces': request.update(paper=False,ink=False)
        return request

    def caption(self):
        ui = self.ui
        working = self.working.titleOfSelectedItem() if self.workflow=='spaces' and self.working.indexOfSelectedItem() else None
        printer = Path(self.printer).name if self.printer else None
        intent = ('Relativ kolorimetrisk', 'Absolut kolorimetrisk', 'Perceptuell')[self.intent.indexOfSelectedItem()]
        bpc, paper = bool(self.bpc.state()), bool(self.paper.state())
        ink = bool(self.ink.state()) or paper
        if self.workflow=='spaces':
            return lambda:ui.text('Arbetsfärgrymd: %@ · %@ · BPC %@',working or ui.text('Behåll bildens färgrymd'),ui.text(intent),ui.text('på' if bpc else 'av'))
        return lambda: ui.text('%@ → %@\n%@ · BPC %@ · Pappersvitt %@', ui.text('Original'), printer or ui.text('Ingen skrivarprofil'), ui.text(intent), ui.text('på' if bpc else 'av'), ui.text('på' if paper else 'av')) + ui.text(' · Trycksvärta %@', ui.text('på' if ink else 'av'))

    def settings_changed(self, sender=None):
        if self.paper.state(): self.ink.setState_(A.NSControlStateValueOn)
        self.ink.setEnabled_(not self.paper.state())
        self.revisions['render'] += 1; self.revisions['gamut'] += 1
        self.ready = False; self.compare.setEnabled_(False); self.pin.setEnabled_(False); self.save.setEnabled_(False); self.swap.setEnabled_(False)
        for kind in ('render','gamut'):
            process=self.processes.get(kind)
            if process and process.poll() is None: process.terminate()
        if self.gamut: self.ui.message(self.gamut.message, 'Uppdaterar profiler och färgprov…')
        if not self.path: return
        self.ui.message(self.status, 'Uppdaterar simuleringen…')
        self.ui.message(self.right.detail, 'Uppdaterar… föregående visning är ännu inte aktuell.')
        revision = self.revisions['render']
        later(0.2, lambda: self.render(revision) if revision == self.revisions['render'] and not self.closing else None)

    def worker(self, kind, request, done):
        if self.closing: return
        old = self.processes.get(kind)
        if old and old.poll() is None: old.terminate()
        folder = Path(tempfile.mkdtemp(dir=self.temporary))
        request = {**request, 'output': str(folder)}
        req, response = folder/'request.json', folder/'response.json'
        req.write_text(json.dumps(request)); error_log = open(folder/'worker.log', 'wb')
        try:
            command = ([sys.executable, '--worker', str(req), str(response)] if FROZEN else
                       [sys.executable, str(ROOT/'tools/softproof_engine.py'), str(req), str(response)])
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=error_log, cwd=ROOT)
        except Exception as error:
            error_log.close(); done({'ok':False, 'error':str(error)}, folder); shutil.rmtree(folder, ignore_errors=True); return
        error_log.close(); self.processes[kind] = process
        def wait():
            process.wait()
            try: result = json.loads(response.read_text())
            except (OSError, ValueError):
                result = {'ok':False, 'error':'Bildberäkningen avbröts eller kunde inte starta.'}
                log = (folder/'worker.log').read_text(errors='replace')
                if log: print(log, file=sys.stderr)
            def complete():
                try:
                    if not self.closing: done(result, folder)
                finally: shutil.rmtree(folder, ignore_errors=True)
            after(complete)
        threading.Thread(target=wait, daemon=True).start()

    def render(self, revision):
        caption = self.caption()
        def done(response, folder):
            if revision != self.revisions['render']: return
            if not response.get('ok'):
                self.ui.message(self.status, response.get('error', 'Kunde inte läsa förhandsvisningen.'))
                self.right.set_image(None, self.original_size)
                self.ui.message(self.right.detail, 'Ingen aktuell simulering')
                if self.gamut:
                    self.ui.message(self.gamut.message, 'Ingen aktuell simulering. Kontrollera bild och profiler i huvudfönstret.')
                    self.gamut.plot.data = {}; self.gamut.plot.previous = []; self.gamut.plot.setNeedsDisplay_(True)
                    self.gamut.cloud.update_cloud({}, [])
                    self.ui.message(self.gamut.values, '')
                if response.get('code') == 'missing_source_profile' and self.source_prompt_pending:
                    self.source_prompt_pending = False
                    self.prompt_source_profile()
                    return
                if self.args.smoke_test: self.fail_smoke(response.get('error'))
                return
            def image(name): return A.NSImage.alloc().initWithData_(F.NSData.dataWithContentsOfFile_(str(folder/name)))
            self.original, self.proof = image('original.png'), image('proof.png')
            if self.original is None or self.proof is None: self.fail_smoke('Missing preview data'); return
            self.source_prompt_pending = False
            self.original_size = (response['width'], response['height'])
            self.image_bits = response.get('bits',8)
            if self.args.smoke_test:
                representation = self.proof.representations()[0]
                assert (representation.pixelsWide(), representation.pixelsHigh()) == (response['previewWidth'], response['previewHeight'])
                if self.image_bits==16: assert representation.bitsPerSample() >= 16
            source, embedded = response['source'], response['embedded']
            self.source_row.setHidden_(embedded)
            self.original_caption = lambda: source+' · '+self.ui.text('inbäddad källprofil' if embedded else 'tilldelad källprofil')+self.ui.text(' · %@ bitar/kanal',response.get('bits',8))
            self.proof_caption = caption
            if self.reference is None:
                self.left.set_image(self.original, self.original_size); self.ui.bind(self.left.detail, self.original_caption)
            self.right.set_image(self.proof, self.original_size); self.ui.bind(self.right.detail, caption)
            self.ui.message(self.right.heading, 'Simulerad utskrift' if self.printer else 'Efter byte av färgrymd')
            self.ui.message(self.status, 'Simuleringen är aktuell. Lås den som referens och ändra inställningar för A/B-jämförelse.' if self.printer else ('Välj arbetsfärgrymd ovan. Öppna Färgomfång för 2D och 3D.' if self.workflow=='spaces' else 'Välj en skrivar-/pappersprofil för höger bild.'))
            self.ready = True; self.compare.setEnabled_(self.workflow=='printers' and bool(self.printer)); self.pin.setEnabled_(True); self.swap.setEnabled_(self.reference_request is not None); self.save.setEnabled_(bool(self.printer) and not self.exporting)
            self.update_zoom(); self.schedule_gamut()
            if self.args.smoke_test: self.smoke_rendered()
        self.worker('render', {**self.request(),'previewLimit':1600,'originalCache':str(self.temporary/'original-cache'),'renderCache':str(self.temporary/'render-cache')}, done)

    def update_zoom(self, sender=None):
        if not hasattr(self, 'left') or self.original is None: return
        a, b = self.left.scroll.contentView().bounds().size, self.right.scroll.contentView().bounds().size
        fit = min(a.width, b.width)/self.original_size[0]
        fit = min(fit, min(a.height,b.height)/self.original_size[1])
        backing = max(1, self.window.backingScaleFactor())
        scale = (max(0.01,fit),0.25/backing,0.5/backing,1/backing)[self.zoom.indexOfSelectedItem()]
        self.left.zoom(scale); self.right.zoom(scale)

    def synchronize_scroll(self, clip):
        if self.syncing or not hasattr(self, 'left'): return
        other = self.right if clip == self.left.scroll.contentView() else self.left
        self.syncing = True
        try:
            other.scroll.contentView().scrollToPoint_(clip.bounds().origin)
            other.scroll.reflectScrolledClipView_(other.scroll.contentView())
        finally: self.syncing = False

    def compare_profile(self, sender=None):
        if not self.ready or not self.printer or self.workflow!='printers':
            return
        path = self.dialog('Välj skrivar-/pappersprofil…')
        if not path:
            return
        self.pin_reference()
        self.printer = path
        self.ui.bind(self.printer_label, lambda: Path(self.printer).name)
        self.settings_changed()

    def pin_reference(self, sender=None):
        if not self.ready or self.workflow!='printers': return
        self.reference = self.proof.copy(); self.reference_caption = self.proof_caption
        self.reference_request = self.request().copy()
        if self.gamut: self.schedule_gamut()
        self.left.set_image(self.reference, self.original_size); self.ui.bind(self.left.detail, self.reference_caption)
        self.ui.message(self.left.heading, 'Låst referens'); self.unpin.setEnabled_(True); self.swap.setEnabled_(True); self.update_zoom()

    def swap_comparison(self, sender=None):
        if not self.ready or self.reference_request is None or self.workflow!='printers':
            return
        previous = self.reference_request.copy()
        self.reference = self.proof.copy()
        self.reference_caption = self.proof_caption
        self.reference_request = self.request().copy()
        for role, menu, paths in (('source',self.source,self.source_paths),
                                  ('working',self.working,self.working_paths)):
            path=previous.get(role)
            if path not in paths:
                paths.append(path); menu.addItemWithTitle_(Path(path).name)
            menu.selectItemAtIndex_(paths.index(path))
        self.printer=previous.get('printer')
        self.ui.bind(self.printer_label,lambda: Path(self.printer).name if self.printer else self.ui.text('Välj skrivarens och papperets ICC-profil'))
        self.intent.selectItemAtIndex_((1,3,0).index(previous['intent']))
        self.bpc.setState_(previous['bpc']); self.paper.setState_(previous['paper'])
        self.ink.setState_(previous['ink'])
        self.left.set_image(self.reference,self.original_size)
        self.ui.bind(self.left.detail,self.reference_caption)
        self.ui.message(self.left.heading,'Låst referens')
        self.settings_changed()

    def clear_reference(self, sender=None):
        self.reference = None; self.reference_request = None; self.unpin.setEnabled_(False); self.swap.setEnabled_(False)
        if self.gamut:
            self.gamut.compare_reference.setState_(0); self.schedule_gamut()
        self.left.set_image(self.original, self.original_size); self.ui.bind(self.left.detail, self.original_caption)
        self.ui.message(self.left.heading, 'Original'); self.update_zoom()

    def show_gamut(self, sender=None):
        if self.gamut is None: self.gamut = GamutWindow(self)
        self.refresh_workflow(); self.gamut.window.makeKeyAndOrderFront_(None); self.schedule_gamut()

    def pick_color(self, x, y):
        if not self.ready: return
        w, h = self.original_size
        self.pixel = [min(w-1,max(0,int(x*w))), min(h-1,max(0,int(y*h)))]
        marker = ((self.pixel[0]+0.5)/w, (self.pixel[1]+0.5)/h)
        for pane in (self.left,self.right): pane.picture.selected = marker; pane.picture.setNeedsDisplay_(True)
        self.show_gamut()

    def schedule_gamut(self):
        self.revisions['gamut'] += 1; revision = self.revisions['gamut']
        if not self.gamut or not self.gamut.window.isVisible() or not self.ready: return
        self.ui.message(self.gamut.message, 'Beräknar färgomfång och färgprov…')
        request = {**self.request(), 'action':'gamut', 'gamutCache':str(self.temporary/'gamut-cache'), 'cloud':True}
        if self.pixel is not None: request['pixel'] = self.pixel.copy()
        if self.gamut.compare_reference.state() and self.reference_request:
            request['reference'] = self.reference_request.copy()
        def done(response, folder):
            if revision != self.revisions['gamut']: return
            if response.get('ok'):
                self.gamut.update(response)
                if self.args.smoke_test: self.smoke_gamut(response)
            else:
                self.ui.message(self.gamut.message, response.get('error', 'Färgomfånget kunde inte beräknas.'))
                self.ui.message(self.gamut.values, '')
                self.gamut.plot.data = {}; self.gamut.plot.previous = []; self.gamut.plot.setNeedsDisplay_(True)
                self.gamut.cloud.update_cloud({}, [])
                if self.args.smoke_test: self.fail_smoke(response.get('error'))
        self.worker('gamut', request, done)

    def export_image(self, sender=None):
        if not self.ready or not self.printer or self.exporting or self.workflow!='printers': return
        panel = A.NSSavePanel.savePanel(); panel.setTitle_(self.ui.text('Spara bild konverterad till skrivarprofilen'))
        panel.setPrompt_(self.ui.text('Spara')); panel.setAllowedFileTypes_(['tif','tiff','png'] if getattr(self,'image_bits',8)==16 else ['tif','tiff','png','jpg','jpeg'])
        panel.setNameFieldStringValue_(Path(self.path).stem+('_print.tif' if self.ui.language=='en' else '_utskrift.tif'))
        panel.setMessage_(self.ui.text('Sparar full upplösning med skrivarprofilen inbäddad. Skriv ut utan ytterligare färgkonvertering. Skärmens simulering av pappersvitt sparas inte.'))
        if panel.runModal() != A.NSModalResponseOK: return
        destination = str(panel.URL().path())
        self.save_request(destination)

    def save_request(self, destination, callback=None):
        self.exporting = True; self.save.setEnabled_(False)
        self.ui.message(self.status, 'Konverterar och sparar hela bilden…')
        request = {**self.request(), 'action':'save', 'destination':destination}
        def done(response, folder):
            self.exporting = False; self.save.setEnabled_(self.ready and bool(self.printer))
            if response.get('ok'): self.ui.message(self.status, 'Sparad: %@ · Vid utskrift: stäng av ytterligare färgkonvertering.', destination)
            else: self.ui.message(self.status, response.get('error', 'Kunde inte spara bilden.'))
            if callback: callback(response)
        self.worker('save', request, done)

    def stop(self):
        self.closing = True
        F.NSNotificationCenter.defaultCenter().removeObserver_(self.delegate)
        for process in self.processes.values():
            if process.poll() is None: process.terminate()
        for process in self.processes.values():
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        self.ui.defaults.synchronize()
        shutil.rmtree(self.temporary, ignore_errors=True)
        if self.args.clear_test_preferences and os.environ.get('INKPROF_SOFTPROOF_PREFERENCES_SUITE','').startswith('se.inkprof.softproof.tests.'):
            suite = os.environ['INKPROF_SOFTPROOF_PREFERENCES_SUITE']
            self.ui.defaults.removePersistentDomainForName_(suite); self.ui.defaults.synchronize()

    def smoke_rendered(self):
        if self.smoke_phase == 0:
            self.pin_reference(); self.smoke_reference = bytes(self.reference.TIFFRepresentation())
            self.smoke_phase = 1; self.paper.setState_(1); self.bpc.setState_(0); self.intent.selectItemAtIndex_(2)
            self.settings_changed()
        elif self.smoke_phase == 1:
            assert self.ink.state() and not self.ink.isEnabled()
            assert bytes(self.reference.TIFFRepresentation()) == self.smoke_reference
            assert bytes(self.proof.TIFFRepresentation()) != self.smoke_reference
            self.zoom.selectItemAtIndex_(3); self.update_zoom()
            drawn = self.right.picture.image().size()
            assert abs(drawn.width*self.window.backingScaleFactor()-self.original_size[0]) < .01
            self.left.scroll.contentView().scrollToPoint_(P(20,20))
            assert self.left.scroll.contentView().bounds().origin == self.right.scroll.contentView().bounds().origin
            self.zoom.selectItemAtIndex_(0); self.update_zoom()
            self.smoke_phase = 2
            picture = self.right.picture; rect = picture.drawn_rect(); w, h = self.original_size
            nx, ny = (int(w*0.8)+0.5)/w, (int(h*0.25)+0.5)/h
            local = P(rect.origin.x+nx*rect.size.width, rect.origin.y+(1-ny)*rect.size.height)
            location = picture.convertPoint_toView_(local, None)
            event = A.NSEvent.mouseEventWithType_location_modifierFlags_timestamp_windowNumber_context_eventNumber_clickCount_pressure_(A.NSEventTypeLeftMouseDown, location, 0, 0, self.window.windowNumber(), None, 1, 1, 1)
            picture.mouseDown_(event)
            assert self.pixel == [int(w*0.8),int(h*0.25)], self.pixel

    def smoke_gamut(self, response):
        if self.smoke_phase == 2:
            self.smoke_channels = response['points'][2]['channels']; self.smoke_phase = 3
            self.intent.selectItemAtIndex_(0); self.bpc.setState_(1); self.settings_changed(); return
        if self.smoke_phase != 3: return
        self.smoke_phase = 4
        assert self.gamut.plot.lab_space is not None, 'Missing colour-managed Lab background'
        assert len(self.gamut.plot.previous) == 3
        assert response['points'][2]['channels'] != self.smoke_channels
        assert len(response['profiles']) == len(response['points']) == 3
        assert '→' in self.gamut.direction.stringValue()
        assert self.gamut.cloud.arrow_pair is not None
        import time
        import numpy as np
        cloud=self.gamut.cloud
        assert cloud.old is not None and np.any(np.abs(cloud.target-cloud.old)>1e-6)
        cloud.start_time=time.monotonic()-.425; cloud.tick(cloud.token)
        assert 0<cloud.progress<1
        np.testing.assert_allclose(cloud.current, cloud.old+(cloud.target-cloud.old)*(cloud.progress**2*(3-2*cloud.progress)))
        cloud.start_time=time.monotonic()-1; cloud.tick(cloud.token)
        assert cloud.progress==1
        np.testing.assert_allclose(cloud.current,cloud.target)

        before = self.request(); reference = bytes(self.reference.TIFFRepresentation()); pixel = self.pixel.copy()
        for language in ('en','sv','en'):
            self.language.selectItemAtIndex_(language=='en'); self.change_language()
            assert self.request() == before and self.pixel == pixel
            assert bytes(self.reference.TIFFRepresentation()) == reference
            assert self.bpc.title() == self.ui.text('Svartpunktskompensation')
            assert self.ui.text('2 Arbetsfärgrymd') not in self.gamut.values.stringValue()
            assert self.working_label.stringValue().rstrip(':') == self.ui.text('2 Arbetsfärgrymd').split(' ',1)[1]
            rows=self.gamut.values.stringValue().splitlines()
            for token in ('L*','a*','b*','ΔE76'):
                assert len({row.index(token) for row in rows}) == 1, 'Misaligned colour coordinates'
            assert self.ui.defaults.stringForKey_('language') == language
        self.gamut.plot.display()
        for enabled in (False,True):
            self.gamut.background.setState_(int(enabled)); self.gamut.change_background(); self.gamut.plot.display()
        points_before = json.dumps(self.gamut.plot.data)
        self.gamut.follow_lightness.setState_(0)
        for value in (0, 25, 65, 100):
            self.gamut.lightness_slider.setDoubleValue_(value); self.gamut.change_lightness()
            assert self.gamut.plot.lightness() == value
            self.gamut.plot.display()
        self.gamut.lightness_value.setDoubleValue_(42.5)
        self.gamut.change_lightness(self.gamut.lightness_value)
        assert self.gamut.plot.lightness() == 42.5
        assert json.dumps(self.gamut.plot.data) == points_before
        self.gamut.follow_lightness.setState_(1); self.gamut.change_lightness()
        assert self.gamut.plot.lightness() == min(100, max(0, response['points'][0]['lab'][0]))
        self.gamut.lightness_slider.setDoubleValue_(65)
        self.gamut.follow_lightness.setState_(0); self.gamut.change_lightness()
        self.gamut.strength.setDoubleValue_(40); self.gamut.change_background()
        output = Path(self.smoke_output)
        self.save_request(str(output.with_suffix('.tif')), lambda result: self.smoke_exported(result, output))

    def smoke_exported(self, result, output):
        if not result.get('ok'): self.fail_smoke(result); return
        from PIL import Image
        from softproof_engine import load_profile, load_image
        reloaded,_,_=load_image(output.with_suffix('.tif'))
        assert getattr(reloaded,'bits',8)==self.image_bits
        with Image.open(output.with_suffix('.tif')) as saved:
            assert saved.size == self.original_size
            assert saved.info['icc_profile'] == Path(self.printer).read_bytes()
        self.window.contentView().layoutSubtreeIfNeeded()
        self.gamut.window.contentView().layoutSubtreeIfNeeded()
        later(0.3, self.smoke_screenshot, output)

    def smoke_screenshot(self, output):
        for window, path in ((self.window, output), (self.gamut.window, output.with_name(output.stem+'-gamut.png'))):
            view = window.contentView(); bitmap = view.bitmapImageRepForCachingDisplayInRect_(view.bounds())
            view.cacheDisplayInRect_toBitmapImageRep_(view.bounds(), bitmap)
            bitmap.representationUsingType_properties_(A.NSBitmapImageFileTypePNG, {}).writeToFile_atomically_(str(path), True)
        import numpy as np
        from PIL import Image
        rgb = np.asarray(Image.open(output.with_name(output.stem+'-gamut.png')).convert('RGB'), dtype=int)
        assert ((rgb.max(axis=2)-rgb.min(axis=2)) > 30).mean() > 0.12, 'Gamut colour background is missing'
        assert self.gamut.cloud.data['ids'], 'Empty image colour cloud'
        assert self.gamut.cloud.old is not None, 'Cloud colours did not retain identity across settings'
        self.gamut.change_mode()
        assert self.gamut.is3d and self.gamut.plot.isHidden() and not self.gamut.cloud.isHidden()
        self.gamut.cloud_role.selectItemAtIndex_(0); self.gamut.change_cloud()
        import time, io
        self.gamut.cloud.start_time=time.monotonic()-1; self.gamut.cloud.tick(self.gamut.cloud.token)
        self.gamut.cloud.yaw += .3; self.gamut.cloud.zoom = 1.1
        self.gamut.window.contentView().layoutSubtreeIfNeeded()
        def pixels():
            plot=self.gamut.cloud; plot.display()
            rep=plot.bitmapImageRepForCachingDisplayInRect_(plot.bounds())
            plot.cacheDisplayInRect_toBitmapImageRep_(plot.bounds(),rep)
            return np.asarray(Image.open(io.BytesIO(bytes(rep.representationUsingType_properties_(A.NSBitmapImageFileTypePNG,{})))).convert('RGB'),dtype=int)
        with_arrows=pixels()
        self.gamut.cloud.motion=False; without_arrows=pixels(); self.gamut.cloud.motion=True
        changed=np.any(with_arrows!=without_arrows,axis=2)
        yellow=(with_arrows[:,:,0]>180)&(with_arrows[:,:,1]>160)&(with_arrows[:,:,2]<110)
        assert (yellow&changed).sum()>200, 'Movement arrows are not visibly yellow'
        assert 'Yellow arrows:' in self.gamut.direction.stringValue()
        self.gamut.cloud.display()
        self.gamut.window.contentView().layoutSubtreeIfNeeded()
        view=self.gamut.window.contentView(); bitmap=view.bitmapImageRepForCachingDisplayInRect_(view.bounds())
        view.cacheDisplayInRect_toBitmapImageRep_(view.bounds(),bitmap)
        cloud_path=output.with_name(output.stem+'-cloud.png')
        bitmap.representationUsingType_properties_(A.NSBitmapImageFileTypePNG,{}).writeToFile_atomically_(str(cloud_path),True)
        cloud_rgb=np.asarray(Image.open(cloud_path).convert('RGB'),dtype=int)
        assert ((cloud_rgb.max(axis=2)-cloud_rgb.min(axis=2))>40).sum()>1000, 'Cloud colours missing'
        self.gamut.cloud.zoom=4.; self.gamut.cloud.display()
        rep=view.bitmapImageRepForCachingDisplayInRect_(view.bounds())
        view.cacheDisplayInRect_toBitmapImageRep_(view.bounds(),rep)
        zoomed=np.asarray(Image.open(io.BytesIO(bytes(rep.representationUsingType_properties_(A.NSBitmapImageFileTypePNG,{})))).convert('RGB'),dtype=int)
        rectangle=self.gamut.canvas.convertRect_toView_(self.gamut.canvas.bounds(),view)
        scale=zoomed.shape[1]/view.bounds().size.width
        x0=max(0,int(rectangle.origin.x*scale));x1=min(zoomed.shape[1],math.ceil((rectangle.origin.x+rectangle.size.width)*scale))
        y0=max(0,int((view.bounds().size.height-rectangle.origin.y-rectangle.size.height)*scale));y1=min(zoomed.shape[0],math.ceil((view.bounds().size.height-rectangle.origin.y)*scale))
        outside=np.ones(zoomed.shape[:2],dtype=bool);outside[y0:y1,x0:x1]=False
        assert np.array_equal(zoomed[outside],cloud_rgb[outside]), '3D drawing escaped the plot frame'
        self.gamut.movement.setState_(0); self.gamut.change_cloud()
        assert self.gamut.cloud.old is None
        self.gamut.movement.setState_(1); self.gamut.change_cloud()
        self.gamut.cloud.reset_camera(); assert self.gamut.cloud.zoom == 1
        self.gamut.change_mode(); assert not self.gamut.is3d
        print('PASS: Python native UI, ICC previews, A/B, zoom/scroll, pixel selection, 2D/3D colour space, movement, tint, languages and full-resolution export', flush=True)
        self.smoke_phase = 5
        A.NSApplication.sharedApplication().terminate_(None)

    def fail_smoke(self, error):
        print(f'FAIL: {error}', file=sys.stderr, flush=True); self.exit_code = 1
        self.stop(); os._exit(1)

    def smoke_timeout(self):
        if self.smoke_phase != 5: self.fail_smoke(f'timeout in phase {self.smoke_phase}')


def main():
    global ACTIVE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--startup-check', action='store_true')
    parser.add_argument('--language-check', choices=['sv','en'])
    parser.add_argument('--smoke-test', nargs=3, metavar=('IMAGE','PRINTER_ICC','SCREENSHOT'))
    parser.add_argument('--clear-test-preferences', action='store_true')
    args = parser.parse_args()
    app = A.NSApplication.sharedApplication(); app.setActivationPolicy_(A.NSApplicationActivationPolicyRegular)
    controller = Controller(args); ACTIVE = controller; app.setDelegate_(controller.delegate)
    AppHelper.runEventLoop()
    return controller.exit_code


if __name__ == '__main__':
    raise SystemExit(main())
