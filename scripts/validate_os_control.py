#!/usr/bin/env python3
"""Owner-machine OS-control validation using read-only probes and a temp workspace."""
import json,os,tempfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.cognition.privilege_model import PrivilegeModel,ProcessOwnershipStore
from app.tools.accessibility_control import AccessibilityControlTool
from app.tools.deep_os_controller import DeepOSController
from app.tools.display_topology import DisplayTopologyTool
from app.tools.universal_filesystem import UniversalFilesystem

def run():
 checks=[]
 def add(name,result,required=False):
  checks.append({'name':name,'passed':bool(result.get('success')),'required':required,'result':result})
 add('privilege_probe',{'success':bool(PrivilegeModel.probe().evidence),'privilege':PrivilegeModel.probe().to_dict()},True)
 add('current_process_ownership',ProcessOwnershipStore(Path(tempfile.gettempdir())/'arena_os_validation.db').inspect(os.getpid()),True)
 # Ungrounded raw input must be refused on every machine, display or not.
 refusal=DeepOSController.mouse_click(1,1)
 add('raw_input_grounding_refusal',{'success':refusal.get('refused') is True and refusal.get('guard_reason')=='missing_grounding','refusal':refusal},True)
 add('display_topology',DisplayTopologyTool.capture())
 add('accessibility_status',AccessibilityControlTool.status())
 with tempfile.TemporaryDirectory(prefix='arena_os_validation_') as d:
  root=Path(d);source=root/'source.txt';source.write_text('arena validation');copy=root/'copy.txt';moved=root/'moved.txt';archive=root/'archive.zip'
  copied=UniversalFilesystem.copy_file_verified(str(source),str(copy));add('verified_copy',copied,True)
  moved_result=UniversalFilesystem.rename_or_move(str(copy),str(moved));add('verified_move',moved_result,True)
  compressed=UniversalFilesystem.compress_zip([str(source),str(moved)],str(archive));add('verified_archive',compressed,True)
 required=[c for c in checks if c['required']];report={'success':all(c['passed'] for c in required),'checks':checks,'passed_required':sum(c['passed'] for c in required),'required_count':len(required),'note':'Unavailable display/accessibility hardware is reported, not simulated.'}
 return report
if __name__=='__main__':print(json.dumps(run(),indent=2))
