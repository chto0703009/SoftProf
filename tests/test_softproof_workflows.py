# Copyright (c) 2026 Christer Törnkvist <christer@borgasundsfotografiska.se>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native workflow isolation checks; run on macOS with the app dependencies."""
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))

@unittest.skipUnless(sys.platform=='darwin','Native AppKit workflow checks require macOS')
class WorkflowTests(unittest.TestCase):
    def setUp(self):
        import softproof_app as module
        self.module=module
        module.A.NSApplication.sharedApplication()
        self.environment=patch.dict(os.environ,{'INKPROF_SOFTPROOF_PREFERENCES_SUITE':'se.inkprof.softproof.tests.workflows'})
        self.environment.start()
        self.c=module.Controller(SimpleNamespace(smoke_test=None,clear_test_preferences=True))
        self.c.build();self.c.settings_changed=lambda *args:None
        self.c.path='/tmp/workflow-image.png';self.c.original_size=(10,10)
        self.c.original=module.A.NSImage.alloc().initWithSize_((10,10));self.c.proof=self.c.original.copy();self.c.ready=True
    def tearDown(self):
        self.c.window.close();self.c.stop();self.environment.stop()
    def switch(self,mode):self.c.tabs.selectTabViewItemWithIdentifier_(mode)
    def test_spaces_excludes_printer_and_viewing_settings(self):
        c=self.c;c.printer='/tmp/not-used.icc';c.working.selectItemAtIndex_(2);c.paper.setState_(1);c.ink.setState_(1)
        request=c.request()
        self.assertNotIn('printer',request);self.assertIn('working',request)
        self.assertFalse(request['paper']);self.assertFalse(request['ink'])
        self.assertTrue(c.printer_row.isHidden());self.assertTrue(c.save.isHidden())
    def test_printers_goes_directly_from_source(self):
        self.switch('printers');c=self.c;c.printer='/tmp/printer.icc';c.working.selectItemAtIndex_(2)
        self.assertNotIn('working',c.request());self.assertEqual(c.request()['printer'],c.printer)
        self.assertTrue(c.working_row.isHidden());self.assertFalse(c.save.isHidden())
    def test_tabs_preserve_independent_settings_and_references(self):
        c=self.c;c.working.selectItemAtIndex_(2);c.proof_caption=c.caption();c.pin_reference()
        self.assertIsNone(c.reference);self.assertIsNone(c.reference_request)
        self.assertTrue(c.pin.isHidden());self.assertTrue(c.swap.isHidden())
        self.switch('printers');self.assertIsNone(c.reference)
        c.printer='/tmp/printer.icc';c.intent.selectItemAtIndex_(2);c.bpc.setState_(0);c.proof_caption=c.caption();c.pin_reference()
        printer_reference=c.reference;printer_request=c.reference_request.copy()
        self.switch('spaces');self.assertIsNone(c.reference);self.assertIsNone(c.reference_request)
        self.assertEqual(c.render_settings.superview(),c.colour_controls)
        self.assertEqual(c.working.indexOfSelectedItem(),2);self.assertIsNone(c.printer)
        self.switch('printers');self.assertIs(c.reference,printer_reference);self.assertEqual(c.reference_request,printer_request)
        self.assertEqual(c.printer,'/tmp/printer.icc');self.assertEqual(c.intent.indexOfSelectedItem(),2)
    def test_reset_keeps_right_and_new_image_clears_both_references(self):
        c=self.c;c.working.selectItemAtIndex_(1);c.proof_caption=c.caption();c.pin_reference()
        self.switch('printers');c.printer='/tmp/printer.icc';c.proof_caption=c.caption();c.pin_reference()
        before=c.request();c.clear_reference();self.assertEqual(c.request(),before);self.assertIsNone(c.reference_request)
        c.pin_reference();c.dialog=lambda *args:'/tmp/new-image.png';c.open_image()
        self.assertIsNone(c.reference_request)
        self.switch('spaces');self.assertIsNone(c.reference);self.assertIsNone(c.reference_request)

    def test_missing_profile_prompts_once_and_can_retry_manually(self):
        c=self.c;c.dialog=lambda *args:'/tmp/untagged.jpg';c.open_image()
        prompts=[];c.prompt_source_profile=lambda:prompts.append(c.path)
        c.worker=lambda kind,request,done:done({'ok':False,'code':'missing_source_profile','error':'Missing profile'},None)
        c.render(c.revisions['render']);c.render(c.revisions['render'])
        self.assertEqual(prompts,['/tmp/untagged.jpg'])
        c.open_image();c.render(c.revisions['render'])
        self.assertEqual(len(prompts),2)

    def test_print_arrows_keep_direction_when_point_set_changes(self):
        import numpy as np
        from cloud_view import CloudPlot
        plot=CloudPlot.alloc().initWithFrame_(self.module.R(0,0,600,400))
        cloud={'identity':'same','ids':[1],'counts':[10],'stages':[
            {'role':'source','lab':[[80,40,-30]],'rgb':[[200,150,100]]},
            {'role':'printer','lab':[[65,20,-10]],'rgb':[[160,130,100]]}]}
        for role in ('printer','source','printer'):
            plot.role=role;plot.update_cloud(cloud)
            np.testing.assert_array_equal(plot.arrow_pair[0],[[80,40,-30]])
            np.testing.assert_array_equal(plot.arrow_pair[1],[[65,20,-10]])
        plot.update_cloud(cloud,reference=cloud)
        self.assertIsNone(plot.arrow_pair)  # Explicit left/right comparison keeps its own direction.
        plot.update_cloud({})
        self.assertIsNone(plot.arrow_pair)

    def test_arrow_emphasis_depends_on_frequency_not_distance(self):
        from cloud_view import arrow_emphasis
        self.assertEqual(arrow_emphasis([2,4,30,100,1000],65536).tolist(),[0,0,1,2,3])
        self.assertEqual(arrow_emphasis([4,8,60,200,2000],131072).tolist(),[0,0,1,2,3])
        self.assertEqual(arrow_emphasis([],0).tolist(),[])
