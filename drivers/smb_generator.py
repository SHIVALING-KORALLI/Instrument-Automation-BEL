# drivers/smb_generator.py
"""
Driver for Rohde & Schwarz SMB100A microwave signal generator.

Notes used from the SMB100A manual (HCOPy subsystem, remote-control commands,
VISA resource strings, socket port 5025, etc). HCOPy allows transferring images as
binary blocks (:HCOPy:DATA?). See SMB100A Operating Manual chapter 6 (Remote Control).
:contentReference[oaicite:10]{index=10} :contentReference[oaicite:11]{index=11}
"""
from drivers.base_driver import VisaInstrument, _rm
from typing import Optional

class SMB100AGenerator(VisaInstrument):
    """Rohde & Schwarz SMB100A Signal Generator wrapper."""

    VENDOR = "Rohde&Schwarz"
    MODEL = "SMB100A"

    def __init__(self, resource: Optional[str] = None, *, auto_connect: bool = True, **kwargs):
        self._backend = kwargs.get("backend", None)
        if auto_connect:
            if resource is None:
                super().__init__(auto_match=(self.VENDOR, self.MODEL), **kwargs)
            else:
                super().__init__(resource=resource, **kwargs)
        else:
            self._inst = None
            self._resource = resource
            self._rm = None

    def open(self) -> None:
        if self._inst:
            return
        if getattr(self, "_rm", None) is None:
            self._rm = _rm(self._backend)
        super().open()

    # Frequency / Level control
    def set_frequency(self, hz: float) -> None:
        """
        Set carrier frequency.
        Common/scpi forms: 'SOUR:FREQ:CW <hz>' or 'FREQ <hz>'.
        We'll use the explicit source form (accepted by the SMB).
        """
        self.write(f"SOUR:FREQ:CW {hz}")

    def get_frequency(self) -> float:
        # prefer explicit query
        try:
            return float(self.query("SOUR:FREQ:CW?"))
        except Exception:
            return float(self.query("FREQ?"))

    def set_power(self, dbm: float) -> None:
        """
        Set RF level. Example explicit R&S form:
          SOUR:POW:LEV:IMM:AMPL <dbm>
        (Shorter forms like 'POW <dbm>' are often accepted.)
        """
        try:
            self.write(f"SOUR:POW:LEV:IMM:AMPL {dbm}")
        except Exception:
            self.write(f"POW {dbm}")

    def get_power(self) -> float:
        try:
            return float(self.query("SOUR:POW:LEV:IMM:AMPL?"))
        except Exception:
            return float(self.query("POW?"))

    def rf_on(self) -> None:
        """Turn RF output on. SCPI: OUTP ON or OUTP:STAT ON"""
        self.write("OUTP ON")

    def rf_off(self) -> None:
        """Turn RF output off. SCPI: OUTP OFF"""
        self.write("OUTP OFF")

    def is_rf_on(self) -> bool:
        """Query RF output state. Many R&S devices return 1 for ON and 0 for OFF."""
        try:
            resp = self.query("OUTP:STAT?").strip()
        except Exception:
            resp = self.query("OUTP?").strip()
        return resp in ("1", "ON", "On", "on")

    # ---------- Hardcopy (screenshot) ----------
    def save_screenshot(self, filepath: str, img_format: str = "PNG") -> None:
        """
        Use HCOPy subsystem to generate a hard copy and transfer as a binary block:
        Typical steps:
            :HCOPy:DEVice:LANG PNG
            :HCOPy:FILE:NAME:AUTO:STATe 1    (optional)
            :HCOPy:EXECute
            :HCOPy:DATA?
        The :HCOPy:DATA? returns a data block (binary) — we return the payload.
        """
        # set format
        self.write(f":HCOPy:DEVice:LANGuage {img_format}")
        # execute (generate file)
        self.write(":HCOPy:EXECute")
        # request binary hardcopy data
        payload = self.query_binary(":HCOPy:DATA?")
        # save
        import os
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(payload)
