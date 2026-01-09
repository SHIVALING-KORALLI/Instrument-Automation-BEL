# drivers/pxa_analyzer.py
"""
Driver for Keysight PXA (N9030x series) signal analyzer.

Automation-relevant notes used:
 - Trace/binary transfer: use :FORMat:DATA + :TRACe:DATA? (binary block transfer is supported).
 - Screen capture / hardcopy: capture to instrument and transfer binary block.
 - Use Keysight I/O Libraries or NI-VISA. See X-Series programmer docs for mode-specific SCPI. :contentReference[oaicite:9]{index=9}
"""
from typing import Optional
from drivers.base_driver import VisaInstrument, _rm
import os

class N9030BAnalyzer(VisaInstrument):
    """Keysight PXA Signal Analyzer (N9030x family)."""

    VENDOR = "Keysight"
    MODEL = "N9030"  # match both N9030A / N9030B variants

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

    # ---------- Frequency / Span / RBW ----------
    def set_center_frequency(self, freq_hz: float) -> None:
        """Set center frequency. SCPI: :FREQ:CENT <Hz>"""
        self.write(f":FREQ:CENT {freq_hz}")

    def get_center_frequency(self) -> float:
        return float(self.query(":FREQ:CENT?"))
    
    def trace_clear(self) -> None:
        self.write(":TRAC:TYPE WRIT")
        self.query("*OPC?")

    def trace_max(self) -> None:
        self.write(":TRAC:TYPE MAXH")
        self.query("*OPC?")
        
    def trace_write(self) -> None:
        """Return to normal Clear/Write trace mode."""
        self.write(":TRAC:MODE WRIT")
        self.query("*OPC?")

    def set_span(self, span_hz: float) -> None:
        """Set span. SCPI: :FREQ:SPAN <Hz>"""
        self.write(f":FREQ:SPAN {span_hz}")

    def get_span(self) -> float:
        return float(self.query(":FREQ:SPAN?"))

    def set_rbw(self, rbw_hz: float) -> None:
        """
        Set resolution bandwidth.
        Many Keysight analyzers accept :BAND <value> or :BAND:RES <value>.
        We try the RES form first.
        """
        try:
            self.write(f":BAND:RES {rbw_hz}")
        except Exception:
            self.write(f":BAND {rbw_hz}")

    # ---------- Markers ----------
    def peak_search(self) -> None:
        """Move marker to the peak. SCPI: :CALC:MARK:MAX"""
        self.write(":CALC:MARK:MAX")

    def marker_frequency(self) -> float:
        """Read marker X (frequency). SCPI: :CALC:MARK:X?"""
        return float(self.query(":CALC:MARK:X?"))

    def marker_power(self) -> float:
        """Read marker Y (level). SCPI: :CALC:MARK:Y?"""
        return float(self.query(":CALC:MARK:Y?"))

    # ---------- Trace / data transfer ----------
    def get_trace_binary(self, trace: int = 1, fmt: str = "REAL,64") -> bytes:
        """
        Fetch trace data as binary block.
        Typical sequence:
            :FORMat:DATA REAL,64
            :TRACe:DATA? TRACE1
        Returns raw payload bytes (IEEE754 binary floats in chosen format).
        See X-Series programmer guide for parsing into floats.
        """
        # set binary format
        self.write(f":FORMat:DATA {fmt}")
        # query trace binary block and return payload
        payload = self.query_binary(f":TRACe:DATA? TRACE{int(trace)}")
        return payload

    def save_screenshot(self, filepath: str) -> None:
        """
        Capture screen and save PNG to filepath.

        Tries multiple instrument-compatible sequences:
        1) :DISP:CAPT:FORM PNG; :DISP:CAPT; :DISP:CAPT:DATA?
        2) :MMEM:NAME '<tmp>'; :MMEM:DATA? '<tmp>'
        Writes payload bytes (after parsing IEEE block header) to filepath.
        """
        import os, time

        # ensure folder exists
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

        # helper to attempt a sequence
        def try_sequence(write_cmd: str | None, query_cmd: str, timeout_ms: int = 15000):
            prev_timeout = getattr(self, "timeout_ms", None)

            # adjust VISA timeout for large binary transfers
            try:
                if getattr(self, "_inst", None):
                    self._inst.timeout = timeout_ms
            except Exception:
                pass

            try:
                if write_cmd:  # only send if provided
                    self.write(write_cmd)
                payload = self.query_binary(query_cmd)
                if payload:
                    return payload
                raise RuntimeError("Empty payload returned from instrument.")
            finally:
                # restore timeout if possible
                try:
                    if getattr(self, "_inst", None) and prev_timeout is not None:
                        self._inst.timeout = prev_timeout
                except Exception:
                    pass

        # --- Sequence 1: Preferred (inline PNG capture) ---
        try:
            # set format
            self.write(":DISP:CAPT:FORM PNG")
            # trigger capture and wait until done
            self.write(":DISP:CAPT")
            self.write("*OPC?")
            payload = try_sequence(None, ":DISP:CAPT:DATA?", timeout_ms=30000)  # 30s timeout

        except Exception as e1:
            # --- Sequence 2: Fallback (store to instrument filesystem then read back) ---
            try:
                tmp_name = "tmp_screenshot.png"
                try:
                    self.write(f":MMEM:NAME '{tmp_name}'")
                except Exception:
                    pass
                try:
                    self.write(f":MMEM:STOR:SCR '{tmp_name}'")
                except Exception:
                    pass
                # give the instrument a moment to create the file
                time.sleep(0.2)
                try:
                    payload = try_sequence(None, f":MMEM:DATA? '{tmp_name}'")
                except Exception:
                    payload = try_sequence(None, f":MMEM:DATA? {tmp_name}")
            except Exception as e2:
                raise RuntimeError(f"Screenshot failed (primary: {e1}; fallback: {e2})")

        # --- Save file ---
        with open(filepath, "wb") as f:
            f.write(payload)



    # ---------- Amplitude / Reference level ----------
    def get_ref_level(self) -> float:
        """Get current reference level in dBm."""
        return float(self.query(":DISP:WIND:TRAC:Y:RLEV?"))

    def set_ref_level(self, level: float) -> None:
        """Set reference level in dBm."""
        self.write(f":DISP:WIND:TRAC:Y:RLEV {level}")

    def ref_level_up(self, step: float = 10.0) -> float:
        """Increase reference level by step (default 1 dB). Returns new level."""
        cur = self.get_ref_level()
        new = cur + step
        self.set_ref_level(new)
        return new

    def ref_level_down(self, step: float = 10.0) -> float:
        """Decrease reference level by step (default 1 dB). Returns new level."""
        cur = self.get_ref_level()
        new = cur - step
        self.set_ref_level(new)
        return new






