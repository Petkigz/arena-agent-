from app.cognition.privilege_model import PrivilegeModel,ProcessOwnershipStore
from app.config import settings
class PrivilegeInspectorTool:
 store=ProcessOwnershipStore(settings.DATA_DIR/'process_ownership.db')
 @classmethod
 def privilege_status(cls):return {'success':True,'privilege':PrivilegeModel.probe().to_dict()}
 @classmethod
 def process_ownership(cls,pid):return cls.store.inspect(pid)
