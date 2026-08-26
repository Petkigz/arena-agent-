from app.tools.display_topology import DisplayTopologyTool

def test_negative_monitor_coordinates_and_verified_scale():
 DisplayTopologyTool._snapshot={'digest':'d','monitors':[{'display_id':'display_1','x':-1920,'y':0,'width':1920,'height':1080,'scale':None,'scale_verified':False}]}
 assert DisplayTopologyTool.transform_window_point('display_1',{'x':-1900,'y':10},10,10)['success'] is False
 assert DisplayTopologyTool.ingest_verified_scale('display_1',1.5,['native dpi probe'])['success'] is True
 r=DisplayTopologyTool.transform_window_point('display_1',{'x':-1900,'y':10},10,10)
 assert r['success'] is True and r['x']==-1885 and r['y']==25

def test_transform_refuses_point_outside_display():
 DisplayTopologyTool._snapshot={'digest':'d','monitors':[{'display_id':'d0','x':0,'y':0,'width':100,'height':100,'scale':1.0,'scale_verified':True}]}
 r=DisplayTopologyTool.transform_window_point('d0',{'x':90,'y':90},20,20)
 assert r['success'] is False and r['inside_display'] is False


def test_native_scale_probe_is_none_off_windows(monkeypatch):
    from app.tools.display_topology import DisplayTopologyTool as D
    import sys
    monkeypatch.setattr(sys, "platform", "linux", raising=False)
    assert D.probe_native_scale() is None  # honest: no evidence, no guess


def test_native_scale_evidence_verifies_primary_monitor(monkeypatch):
    import sys
    from types import SimpleNamespace
    from unittest.mock import patch
    from app.tools.display_topology import DisplayTopologyTool as D

    class FakeMss:
        # mss.monitors[0] is the virtual "all monitors" entry; [1:] are real.
        monitors = [
            {"left": 0, "top": 0, "width": 2560, "height": 1440},
            {"left": 0, "top": 0, "width": 2560, "height": 1440},
        ]

        def __enter__(self): return self

        def __exit__(self, *a): return False

    monkeypatch.setattr(sys, "platform", "win32", raising=False)
    native = {"dpi": 120, "scale": 1.25, "source": "native_gdi_logpixelsx",
              "evidence": ["GetDeviceCaps(LOGPIXELSX)=120"]}
    with patch("mss.mss", lambda: FakeMss()), \
         patch.object(D, "probe_native_scale", staticmethod(lambda: native)):
        D._snapshot = None
        result = D.capture()
    assert result["success"] is True and result["native_scale_probe"] == native
    primary = result["monitors"][0]
    assert primary["scale"] == 1.25 and primary["scale_verified"] is True
    assert "primary-monitor scale 1.25 verified" in result["note"]
    # With a verified scale, the coordinate transform now works.
    transform = D.transform_window_point("display_0", {"x": 0, "y": 0}, 100, 100)
    assert transform["success"] is True and transform["x"] == 125
