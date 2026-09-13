"""The owner hardware profile in system settings (owner 2026-09-13).

Her machine — i9-14900K, 48 GB DDR5, RX 580 8 GB today, a 16 GB card
planned — was always meant to live in system settings and had been
dropped/forgotten. These tests pin: the profile persists with her real
specs, partial patches merge instead of wiping siblings, and every
boot's readiness block states what the machine knows about its body.
"""

import pytest

from app import settings_store


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(
        settings_store, "_SETTINGS_PATH", tmp_path / "settings.json")
    return settings_store


class TestHardwareProfile:
    def test_defaults_carry_the_owner_machine(self, store):
        hw = store.get_hardware()
        assert hw["cpu"] == "Intel Core i9-14900K"
        assert hw["gpu_model"] == "AMD Radeon RX 580"
        assert hw["vram_gb"] == 8
        assert hw["ram_gb"] == 48
        assert "16 GB" in hw["planned_gpu"]

    def test_partial_patch_merges_without_wiping_siblings(self, store):
        # the planned swap: one field changes, the rest survives
        out = store.update_settings({"hardware": {"gpu_model": "RTX 5060 Ti",
                                                  "vram_gb": 16}})
        hw = out["hardware"]
        assert hw["gpu_model"] == "RTX 5060 Ti"
        assert hw["vram_gb"] == 16
        assert hw["ram_gb"] == 48
        assert hw["cpu"] == "Intel Core i9-14900K"
        assert hw["updated_at"] != "2026-09-13T00:00:00+00:00"  # restamped
        # and it persisted across a re-read
        assert store.get_hardware()["vram_gb"] == 16

    def test_none_values_do_not_erase_fields(self, store):
        out = store.update_settings({"hardware": {"notes": None,
                                                  "vram_gb": 12}})
        assert out["hardware"]["vram_gb"] == 12
        assert "Polaris" in out["hardware"]["notes"]

    def test_other_settings_still_round_trip(self, store):
        out = store.update_settings({"theme": "light", "main_model": "x"})
        assert out["theme"] == "light"
        assert out["main_model"] == "x"
        assert store.get_hardware()  # hardware untouched by other patches

    def test_corrupt_file_falls_open_to_defaults(self, store):
        store._SETTINGS_PATH.write_text("{broken", encoding="utf-8")
        assert store.get_hardware()["vram_gb"] == 8


class TestReadinessStatesTheBody:
    def _snapshot(self):
        from app.utils.readiness import collect_readiness
        return collect_readiness(probe_provider_fn=lambda _url: {
            "reachable": False, "loaded_models": None, "error": "test"})

    def test_snapshot_carries_the_recorded_profile(self, store):
        snap = self._snapshot()
        assert snap["hardware"]["gpu_model"] == "AMD Radeon RX 580"
        assert snap["hardware"]["vram_gb"] == 8

    def test_boot_block_names_gpu_vram_and_the_planned_card(self, store):
        from app.utils.readiness import format_readiness
        block = format_readiness(self._snapshot())
        assert "hardware      : AMD Radeon RX 580 8GB VRAM, 48GB RAM" in block
        assert "planned: 16 GB" in block
