import psutil
from typing import Dict, Any

class HardwareMonitor:
    @classmethod
    def get_hardware_stats(cls) -> Dict[str, Any]:
        """
        Queries live CPU %, RAM %, System RAM used/total (GB), and Disk usage.
        """
        try:
            cpu_pct = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            return {
                "cpu_percent": cpu_pct,
                "ram_percent": mem.percent,
                "ram_used_gb": round(mem.used / (1024 ** 3), 2),
                "ram_total_gb": round(mem.total / (1024 ** 3), 2),
                "disk_percent": disk.percent,
                "disk_free_gb": round(disk.free / (1024 ** 3), 2)
            }
        except Exception as e:
            return {
                "cpu_percent": 0.0,
                "ram_percent": 0.0,
                "ram_used_gb": 0.0,
                "ram_total_gb": 16.0,
                "disk_percent": 0.0,
                "disk_free_gb": 0.0,
                "error": str(e)
            }
