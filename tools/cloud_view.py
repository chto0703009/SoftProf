# Copyright (c) 2026 Christer Törnkvist <christer@borgasundsfotografiska.se>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native AppKit software-rendered, rotatable CIELAB colour cloud."""
import math
import time
import numpy as np
import objc
import AppKit as A
import Foundation as F
from PyObjCTools import AppHelper


def arrow_emphasis(counts, sampled):
    """Four visibility bands by source-pixel frequency; no colours are removed."""
    fractions=np.asarray(counts,dtype=float)/max(1,float(sampled))
    return np.searchsorted([0.0001,0.001,0.005],fractions,side='right')


class CloudPlot(A.NSView):
    def initWithFrame_(self, frame):
        self = objc.super(CloudPlot,self).initWithFrame_(frame)
        if self is not None:
            self.data={}; self.role='printer'; self.motion=True
            self.current=np.empty((0,3)); self.old=None; self.target=self.current
            self.yaw=-.65; self.pitch=.4; self.zoom=1.; self.extent=160.
            self.arrow_pair=None
            self.token=0; self.progress=1.; self.start_time=0.; self.samples=[]
        return self

    @objc.python_method
    def reset_camera(self):
        self.yaw=-.65; self.pitch=.4; self.zoom=1.; self.setNeedsDisplay_(True)

    @objc.python_method
    def update_cloud(self, cloud, samples=None, reference=None):
        stages={s['role']:s for s in cloud.get('stages',[])}
        stage=stages.get(self.role) or stages.get('working') or stages.get('source')
        target=np.asarray(stage['lab'],dtype=float).reshape(-1,3) if stage else np.empty((0,3))
        comparable=(self.data.get('identity')==cloud.get('identity') and self.data.get('ids')==cloud.get('ids') and self.current.shape==target.shape)
        self.old=self.current.copy() if comparable and self.motion and len(target) else None
        self.reference_points=None
        if reference is not None:
            reference_stage=next((s for s in reference.get('stages',[]) if s['role']==self.role),None)
            if reference_stage and reference.get('identity')==cloud.get('identity') and reference.get('ids')==cloud.get('ids'):
                self.reference_points=np.asarray(reference_stage['lab'],dtype=float).reshape(-1,3)
                if len(self.reference_points): self.extent=max(self.extent,float(np.max(np.abs(self.reference_points[:,1:]))))
                self.old=self.reference_points.copy() if self.motion else None
            else:
                self.old=None
        # Printer arrows compare two stages of this calculation, never the
        # previously selected point set or an intermediate animation frame.
        self.arrow_pair=None
        if reference is None and 'source' in stages and 'printer' in stages:
            self.arrow_pair=tuple(np.asarray(stages[role]['lab'],dtype=float).reshape(-1,3)
                                  for role in ('source','printer'))
        self.data=cloud; self.target=target
        self.samples=samples if samples is not None else self.samples
        factory = (A.NSColor.colorWithDisplayP3Red_green_blue_alpha_ if cloud.get('colourSpace')=='Display P3'
                   else A.NSColor.colorWithSRGBRed_green_blue_alpha_)
        self.colors=[factory(r/255,g/255,b/255,1) for r,g,b in stage['rgb']] if stage else []
        self.radii=[min(2.2,.5+math.log1p(c)*.16) for c in cloud.get('counts',[])]
        for s in stages.values():
            if s['lab']: self.extent=max(self.extent,float(np.max(np.abs(np.asarray(s['lab'])[:,1:]))))
        self.token+=1; self.start_time=time.monotonic()
        self.progress=0. if self.old is not None and reference is None else 1.
        self.current=self.old.copy() if self.progress==0. else target.copy()
        self.setNeedsDisplay_(True)
        if self.old is not None and reference is None: AppHelper.callLater(.025,self.tick,self.token)

    @objc.python_method
    def tick(self, token):
        if token!=self.token: return
        self.progress=min(1.,(time.monotonic()-self.start_time)/.85)
        t=self.progress*self.progress*(3-2*self.progress)
        self.current=self.old+(self.target-self.old)*t
        self.setNeedsDisplay_(True)
        if self.progress<1: AppHelper.callLater(.025,self.tick,token)

    def mouseDown_(self,event):
        self.drag_point=self.convertPoint_fromView_(event.locationInWindow(),None)

    def mouseDragged_(self,event):
        p=self.convertPoint_fromView_(event.locationInWindow(),None)
        previous=getattr(self,'drag_point',p)
        self.yaw+=(p.x-previous.x)*.009
        self.pitch=max(-1.4,min(1.4,self.pitch-(p.y-previous.y)*.009))
        self.drag_point=p; self.setNeedsDisplay_(True)

    def scrollWheel_(self,event):
        self.zoom=max(.35,min(4.,self.zoom*math.exp(-event.scrollingDeltaY()*.015)))
        self.setNeedsDisplay_(True)

    @objc.python_method
    def projected(self, lab):
        values=np.asarray(lab,dtype=float).reshape(-1,3)
        x,z,y=values[:,1],values[:,2],values[:,0]-50
        cy,sy,cp,sp=math.cos(self.yaw),math.sin(self.yaw),math.cos(self.pitch),math.sin(self.pitch)
        xx=cy*x+sy*z; zz=-sy*x+cy*z
        yy=cp*y-sp*zz; depth=sp*y+cp*zz
        w,h=self.bounds().size;scale=min(w-80,h-75)/(self.extent*2.2)*self.zoom
        return np.column_stack((w/2+xx*scale,h/2+yy*scale,depth))

    def drawRect_(self,dirty):
        A.NSBezierPath.bezierPathWithRect_(self.bounds()).addClip()
        A.NSColor.colorWithWhite_alpha_(.045,1).setFill(); A.NSRectFill(self.bounds())
        def line(a,b,color,width=1):
            p=self.projected([a,b]);color.setStroke();path=A.NSBezierPath.bezierPath()
            path.setLineWidth_(width);path.moveToPoint_((p[0,0],p[0,1]));path.lineToPoint_((p[1,0],p[1,1]));path.stroke()
        def text(label,lab,color):
            p=self.projected([lab])[0]
            F.NSString.stringWithString_(str(label)).drawAtPoint_withAttributes_((p[0]+4,p[1]+3),{A.NSFontAttributeName:A.NSFont.systemFontOfSize_(11),A.NSForegroundColorAttributeName:color})
        grid=A.NSColor.colorWithWhite_alpha_(.24,1); white=A.NSColor.colorWithWhite_alpha_(.85,1)
        extent=math.ceil(self.extent/40)*40
        for value in range(-extent,extent+1,40):
            line([0,value,-extent],[0,value,extent],grid,.5)
            line([0,-extent,value],[0,extent,value],grid,.5)
        for L in (0,25,50,75,100):
            line([L,-extent,-extent],[L,extent,-extent],grid,.5)
            line([L,-extent,-extent],[L,-extent,extent],grid,.5)
            text(L,[L,0,0],white)
        line([0,0,0],[105,0,0],white,1.4);text('L*',[123,0,0],white)
        for axis,label,color in ((1,'a*',A.NSColor.systemRedColor()),(2,'b*',A.NSColor.systemYellowColor())):
            a=[0,0,0];b=[0,0,0];a[axis]=-extent;b[axis]=extent
            line(a,b,color,1.2);label_position=b.copy();label_position[axis]+=30;text(label,label_position,color)
            for v in (-extent,-80,80,extent):
                q=[0,0,0];q[axis]=v;text(v,q,white)
        pair=self.arrow_pair if self.arrow_pair is not None else ((self.old,self.target) if self.old is not None else None)
        if pair is not None and self.motion:
            old=self.projected(pair[0]);new=self.projected(pair[1])
            counts=self.data.get('counts',[])
            bands=arrow_emphasis(counts,self.data.get('sampled',sum(counts)))
            paths=[A.NSBezierPath.bezierPath() for _ in range(4)]
            for i,(a,b) in enumerate(zip(old,new)):
                if np.linalg.norm(b[:2]-a[:2])<1: continue
                path=paths[int(bands[i])]
                path.moveToPoint_((a[0],a[1]));path.lineToPoint_((b[0],b[1]))
                dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
                if length>5:
                    ux,uy=dx/length,dy/length
                    path.moveToPoint_((b[0]-3*ux+1.2*uy,b[1]-3*uy-1.2*ux));path.lineToPoint_((b[0],b[1]));path.lineToPoint_((b[0]-3*ux-1.2*uy,b[1]-3*uy+1.2*ux))
            # Draw rare colours first, then the more frequent colours on top.
            for path,(alpha,width) in zip(paths,((.25,.65),(.5,.85),(.8,1.),(1.,1.25))):
                A.NSColor.colorWithSRGBRed_green_blue_alpha_(1.,.9,.05,alpha).setStroke()
                path.setLineWidth_(width);path.stroke()
        projected=self.projected(self.current)
        for i in np.argsort(projected[:,2]) if len(projected) else []:
            x,y,_=projected[i];radius=self.radii[i];self.colors[i].setFill()
            A.NSBezierPath.bezierPathWithOvalInRect_(F.NSMakeRect(x-radius,y-radius,radius*2,radius*2)).fill()
        for sample in ([] if getattr(self,'reference_points',None) is not None else self.samples):
            if sample['role']!=self.role:continue
            x,y,_=self.projected([sample['lab']])[0];white.setStroke()
            marker=A.NSBezierPath.bezierPathWithOvalInRect_(F.NSMakeRect(x-10,y-10,20,20));marker.setLineWidth_(2);marker.stroke()
