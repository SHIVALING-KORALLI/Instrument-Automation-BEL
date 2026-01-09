# drivers/n8739a_supply.py
"""
Driver for Keysight N8739A Power Supply (N8700 series).

Key automation facts (from datasheet & programmer guide summary):
 - DC rating (N8739A): 100 V, 33 A, 3300 W. Programming resolution and response times
   listed in the data sheet. (See datasheet/programmer guide.) :contentReference[oaicite:6]{index=6}
 - Interfaces: GPIB, LAN (LXI/VXI-11/HiSLIP or raw socket), USB (USBTMC). Use Keysight I/O
   Libraries Suite for best support (NI-VISA frequently works). :contentReference[oaicite:7]{index=7}
 - Typical SCPI you'll use: *IDN?, *RST, *CLS, VOLT, CURR, OUTP, MEAS:VOLT?, MEAS:CURR?,
   VOLT:PROT, SAV/RCL memory slots, etc. (Programmer reference contains exact syntax.)
   See datasheet+programming guide for full list. :contentReference[oaicite:8]{index=8}
"""
from __future__ import annotations
from drivers.base_driver import VisaInstrument, InstrumentNotFound, _rm
from typing import Optional

class N8739APowerSupply(VisaInstrument):
    """Keysight N8739A Power Supply wrapper."""

    VENDOR = "Agilent"
    MODEL = "N8739A"  # substring for *IDN? matching

    def __init__(self, resource: Optional[str] = None, *, auto_connect: bool = True, **kwargs):
        """
        If auto_connect True (default) we attempt to auto-detect the PSU by *IDN?.
        If auto_connect False we construct a driver object but do not open a VISA resource.
        """
        self._backend = kwargs.get("backend", None)
        if auto_connect:
            if resource is None:
                super().__init__(auto_match=(self.VENDOR, self.MODEL), **kwargs)
            else:
                super().__init__(resource=resource, **kwargs)
        else:
            # offline-safe object (open() will create ResourceManager when called)
            self._inst = None
            self._resource = resource
            # ensure a ResourceManager can be created later
            self._rm = None

    # ensure open works even if constructed with auto_connect=False
    def open(self) -> None:
        if self._inst:
            return
        if getattr(self, "_rm", None) is None:
            self._rm = _rm(self._backend)
        super().open()

    # ---------- Control Methods ----------
    def set_voltage(self, volts: float) -> None:
        """Set output voltage in volts. SCPI: VOLT <value> (or SOUR:VOLT)."""
        self.write(f"VOLT {volts}")

    def set_current(self, amps: float) -> None:
        """Set output current limit in amps. SCPI: CURR <value> (or SOUR:CURR)."""
        self.write(f"CURR {amps}")

    def output_on(self) -> None:
        """Turn on output. SCPI: OUTP ON."""
        self.write("OUTP ON")

    def output_off(self) -> None:
        """Turn off output. SCPI: OUTP OFF."""
        self.write("OUTP OFF")

    def set_ovp(self, volts: float) -> None:
        """Set Over Voltage Protection level. SCPI: VOLT:PROT <value>."""
        self.write(f"VOLT:PROT {volts}")

    def get_ovp(self) -> float:
        """Query OVP level. SCPI: VOLT:PROT?"""
        return float(self.query("VOLT:PROT?"))

    # ---------- Measurement Methods ----------
    def measure_voltage(self) -> float:
        """Measure actual output voltage. SCPI: MEAS:VOLT?"""
        return float(self.query("MEAS:VOLT?"))

    def measure_current(self) -> float:
        """Measure actual output current. SCPI: MEAS:CURR?"""
        return float(self.query("MEAS:CURR?"))

    def measure_power(self) -> float:
        """Measure actual output power. SCPI: MEAS:POW?"""
        return float(self.query("MEAS:POW?"))

    # ---------- Save/Recall ----------
    def save_state(self, slot: int) -> None:
        """Save current volatile state to slot (0..15). SCPI: SAV <n>"""
        self.write(f"SAV {int(slot)}")

    def recall_state(self, slot: int) -> None:
        """Recall state from slot. SCPI: RCL <n>"""
        self.write(f"RCL {int(slot)}")
