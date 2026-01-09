# drivers/base_driver.py
"""
Common VISA/SCPI utilities for all instruments.

Usage examples:
    from drivers.base_driver import VisaInstrument, discover

    print(discover())  # list VISA resources
    with VisaInstrument(auto_match=("Keysight","N8739")) as inst:
        print(inst.idn())
"""
from __future__ import annotations
import time
import logging
from typing import Iterable, List, Optional, Tuple

# Track resources already claimed by auto_match
_USED_RESOURCES: set[str] = set()


try:
    import pyvisa  # type: ignore
except Exception as exc:
    raise RuntimeError(
        "pyvisa is not installed or failed to import. "
        "Install it inside your venv before running."
    ) from exc


# ---------- Logging ----------
logger = logging.getLogger("visa")
if not logger.handlers:
    handler = logging.StreamHandler()
    fmt = logging.Formatter("[%(levelname)s] %(asctime)s - %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


# ---------- Helpers ----------
def _rm(backend: Optional[str] = None) -> "pyvisa.ResourceManager":
    """Get a PyVISA ResourceManager (system VISA by default)."""
    return pyvisa.ResourceManager(backend) if backend else pyvisa.ResourceManager()


def discover(backend: Optional[str] = None) -> List[str]:
    """
    Return list of VISA resource strings visible to the system.
    Example: ['USB0::0x2A8D::0x900C::MY12345678::INSTR', ...]
    """
    try:
        resources = list(_rm(backend).list_resources())
        return sorted(resources)
    except Exception as e:
        logger.error("VISA discovery failed: %s", e)
        return []


class InstrumentNotFound(Exception):
    pass


class VisaInstrument:
    """
    Thin wrapper around a VISA resource with SCPI conveniences.

    Create with either:
      - resource="USB0::...::INSTR"
      - auto_match=("VendorOrBrandSubstr", "ModelSubstr") to search by *IDN?
    """

    def __init__(
        self,
        resource: Optional[str] = None,
        *,

        auto_match: Optional[Tuple[str, str]] = None,
        backend: Optional[str] = None,
        timeout_ms: int = 5000,
        write_termination: str = "\n",
        read_termination: str = "\n",
        chunk_size: int = 2 * 1024 * 1024,
    ) -> None:
        self._backend = backend
        self._rm = _rm(backend)
        self._inst: Optional["pyvisa.resources.MessageBasedResource"] = None
        self._resource = resource
        self.timeout_ms = timeout_ms
        self.write_termination = write_termination
        self.read_termination = read_termination
        self.chunk_size = chunk_size

        if resource is None and auto_match:
            self._resource = self._find_by_idn(auto_match[0], auto_match[1])
        elif resource is None:
            raise ValueError("Provide 'resource' or 'auto_match'.")

        self.open()

    # ----- lifecycle -----
    def open(self) -> None:
        if self._inst:
            return
        assert self._resource is not None
        logger.info("Opening VISA resource: %s", self._resource)
        inst = self._rm.open_resource(self._resource)
        inst.timeout = self.timeout_ms
        inst.write_termination = self.write_termination
        inst.read_termination = self.read_termination
        inst.chunk_size = self.chunk_size
        # Some USBTMC devices benefit from a clear on open
        try:
            inst.clear()
        except Exception:
            pass
        self._inst = inst

    def close(self) -> None:
        if self._inst:
            try:
                self._inst.close()
            finally:
                self._inst = None

    def __enter__(self) -> "VisaInstrument":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ----- SCPI utilities -----
    @property
    def resource(self) -> str:
        return self._resource or ""

    def write(self, cmd: str) -> None:
        self._ensure_open()
        logger.debug("SCPI >> %s", cmd)
        self._inst.write(cmd)  # type: ignore[attr-defined]

    def query(self, cmd: str) -> str:
        self._ensure_open()
        logger.debug("SCPI ? %s", cmd)
        resp = self._inst.query(cmd)  # type: ignore[attr-defined]
        logger.debug("SCPI << %s", resp.strip())
        return resp

    def read_raw(self) -> bytes:
        self._ensure_open()
        return self._inst.read_raw()  # type: ignore[attr-defined]

    def write_bytes(self, data: bytes) -> None:
        self._ensure_open()
        self._inst.write_raw(data)  # type: ignore[attr-defined]

    def idn(self) -> str:
        try:
            return self.query("*IDN?").strip()
        except Exception as e:
            logger.error("Failed *IDN?: %s", e)
            raise

    def reset(self) -> None:
        self.write("*RST")

    def clear_status(self) -> None:
        self.write("*CLS")

    def opc(self, timeout_s: Optional[float] = None) -> None:
        """
        Block until operation complete. Optional timeout in seconds.
        """
        if timeout_s is None:
            _ = self.query("*OPC?")
            return
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                if self.query("*OPC?").strip() == "1":
                    return
            except Exception:
                pass
            time.sleep(0.1)
        raise TimeoutError("Operation did not complete before timeout.")

    # ----- binary block helpers -----
    @staticmethod
    def _parse_ieee_block(raw: bytes) -> bytes:
        """
        Parse SCPI IEEE-488.2 definite-length block "#<d><nnn><data...>"
        Returns the payload bytes (no header). If raw does not start with '#', return raw.
        """
        if not raw:
            return b""
        if raw.startswith(b"#"):
            # header: '#' + <ndigits> + <len digits>
            if len(raw) < 2:
                raise ValueError("Invalid block header")
            ndigits = raw[1:2]
            try:
                nd = int(ndigits)
            except Exception:
                raise ValueError("Invalid block header digits")
            if nd == 0:
                # indefinite length: return after header (not supported deterministically here)
                # caller can handle if necessary.
                return raw[2:]
            if len(raw) < 2 + nd:
                raise ValueError("Incomplete block header")
            num_bytes = int(raw[2:2 + nd])
            start = 2 + nd
            end = start + num_bytes
            return raw[start:end]
        # no block header
        return raw

    def query_binary(self, cmd: str) -> bytes:
        """
        Send a query that returns binary block data. Returns the raw payload bytes.
        Uses write() then read_raw() (safer than query() for binary).
        """
        self._ensure_open()
        logger.debug("SCPI (binary) ? %s", cmd)
        # Use write then read_raw to avoid pyvisa trying to decode binary
        self._inst.write(cmd)  # type: ignore[attr-defined]
        raw = self._inst.read_raw()  # type: ignore[attr-defined]
        payload = self._parse_ieee_block(raw)
        logger.debug("SCPI (binary) << %d bytes", len(payload))
        return payload

    # ----- discovery by *IDN? ----- 
    def _find_by_idn(self, vendor_substr: str, model_substr: str) -> str:
        """
        Search VISA resources for an instrument whose *IDN? contains the given vendor/model.
        Skips resources that are already in _USED_RESOURCES, so multiple identical instruments
        can be attached one by one.
        """
        vendor_substr = vendor_substr.lower()
        model_substr = model_substr.lower()
        candidates = discover(self._backend)
        logger.info("Searching VISA resources for %s / %s (candidates=%s)",
                    vendor_substr, model_substr, candidates)

        matches: list[tuple[str, str]] = []  # (resource, idn)

        for res in candidates:
            if res in _USED_RESOURCES:
                logger.debug("Skipping already used resource: %s", res)
                continue
            try:
                inst = self._rm.open_resource(res)
                inst.timeout = 1500
                inst.write_termination = "\n"
                inst.read_termination = "\n"
                reply = inst.query("*IDN?").strip()
                inst.close()
            except Exception as e:
                logger.debug("Resource %s not usable: %s", res, e)
                continue

            low = reply.lower()
            if vendor_substr in low and model_substr in low:
                matches.append((res, reply))

        if not matches:
            raise InstrumentNotFound(
                f"No instrument found matching *IDN? contains "
                f"'{vendor_substr}' and '{model_substr}'. "
                f"Seen: {candidates}"
            )
      
        # choose first unused match
        chosen, idn_str = matches[0]
        _USED_RESOURCES.add(chosen)
        if len(matches) > 1:
            logger.warning("Multiple matches found (%s). Choosing first unused: %s (%s)",
                    [m[0] for m in matches], chosen, idn_str)
        else:
            logger.info("Matched resource %s (%s)", chosen, idn_str)
        return chosen


    # ----- internal -----
    def _ensure_open(self) -> None:
        if not self._inst:
            raise RuntimeError("VISA resource not open. Call open() first.")
