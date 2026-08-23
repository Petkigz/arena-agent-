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
