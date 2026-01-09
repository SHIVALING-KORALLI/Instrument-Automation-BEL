# controller.py
import time
from typing import Dict, Any, Callable, Optional, List
import socket
import binascii

class AutomationController:
    """High-level orchestrator for instrument automation."""

    def __init__(self):
        self.instruments: Dict[str, Any] = {}
        self.progress_callback: Optional[Callable[[dict], None]] = None

    def attach(self, name: str, inst: Any) -> None:
        """Attach an instrument instance under a name (e.g., 'psu', 'gen', 'sa')."""
        self.instruments[name] = inst

    def get(self, name: str) -> Any:
        """Get an attached instrument by name."""
        return self.instruments.get(name)

    def set_progress_callback(self, callback: Optional[Callable[[dict], None]]) -> None:
        """Set (or clear) a callback function to report progress updates."""
        self.progress_callback = callback

    # ---------- Helper: parse hex string to list of ints ----------
    @staticmethod
    def _parse_hex_bytes(hex_str: str, expected_len: int) -> List[int]:
        # Accept "AA BB" or "AABB" etc.
        if not hex_str:
            return [0] * expected_len
        s = "".join(hex_str.split()).lower()
        if len(s) % 2 != 0:
            # odd length -> invalid
            raise ValueError("Hex string length must be even (pairs of hex digits).")
        b = binascii.unhexlify(s)
        if len(b) != expected_len:
            raise ValueError(f"Expecting {expected_len} bytes, got {len(b)}.")
        return list(b)

    def _emit_progress(self, data: dict):
        if self.progress_callback:
            try:
                self.progress_callback(data)
            except Exception:
                # Protect main loop from callback exceptions
                pass

    # ---------- Main automation sequence ----------
    def run_example_sequence(
        self,
        board_no: int = 1,
        channel_no: int = 1,
        pulse_width: str = "00 00",
        prt: str = "00 00 00 00",
        *,
        # optional configuration points
        pulse_indices: List[int] = None,  # default indices within first 11 bytes for pulse width (2 bytes)
        prt_indices: List[int] = None,    # default indices within first 11 bytes for prt (4 bytes)
        udp_dst_ip: str = "192.168.1.10",
        udp_dst_port: int = 5005,
        udp_src_ip: str = "192.168.1.5",
        udp_src_port: int = 6005,
    ):
        """
        Run UDP sweep for one board/channel with pulse and prt inserted.

        - board_no, channel_no: used for reporting only
        - pulse_width: '00 01' (2 bytes hex)
        - prt: '0A AB 00 00' (4 bytes hex)
        - pulse_indices / prt_indices: list of integer indexes to insert those bytes into the 40-byte payload.
          Defaults chosen within the first 11 bytes but adjustable by caller.
        """
        sa = self.get("sa")
        if not sa:
            raise RuntimeError("Analyzer (sa) must be attached. Please ensure it's connected.")

        # Default indices (0-based). You can change them when calling the function.
        if pulse_indices is None:
            pulse_indices = [10, 11]      # two byte positions for pulse width
        if prt_indices is None:
            prt_indices = [12, 13, 14, 15]  # four byte positions for PRT

        # Validate index lengths
        if len(pulse_indices) != 2:
            raise ValueError("pulse_indices must be list of 2 integers.")
        if len(prt_indices) != 4:
            raise ValueError("prt_indices must be list of 4 integers.")

        # Parse hex inputs (raises ValueError on invalid input)
        pulse_bytes = self._parse_hex_bytes(pulse_width, 2)
        prt_bytes = self._parse_hex_bytes(prt, 4)

        # UDP setup
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((udp_src_ip, udp_src_port))

        base_payload = [
            0x00, 0xab, 0xab, 0x06, 0x00, 0x00, 0x07, 0x00, 0x00, 0x00,
            0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x00,
            0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E,
            0x1F, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,
        ]
        if len(base_payload) != 40:
            raise RuntimeError("Base payload must be 40 bytes long.")

        results = []
        total_spots = 0x51  # 0x00..0x50 inclusive = 81 packets

        # Emit initial progress
        self._emit_progress({
            "status": "running",
            "current": 0,
            "total": total_spots,
            "board_no": board_no,
            "channel_no": channel_no,
            "message": "Starting automation sequence..."
        })
        
        sa.set_center_frequency(3100000000)
        sa.set_span(600000000)
        sa.set_rbw(100000)

        # Pre-insert pulse & prt bytes into the positions that remain constant
        # We'll copy base_payload for each cal and set the sweep byte each iteration.
        for spot_val in range(0x00, 0x51, 0x05):
            payload = base_payload.copy()

            # Insert pulse bytes
            for idx, b in zip(pulse_indices, pulse_bytes):
                if idx < 0 or idx >= len(payload):
                    raise IndexError(f"pulse index {idx} is out of range for payload length {len(payload)}")
                payload[idx] = b

            # Insert prt bytes
            for idx, b in zip(prt_indices, prt_bytes):
                if idx < 0 or idx >= len(payload):
                    raise IndexError(f"prt index {idx} is out of range for payload length {len(payload)}")
                payload[idx] = b

            # Sweep the designated sweep byte (index 9 as per prior code)
            sweep_index = 9
            payload[sweep_index] = spot_val

            payload_bytes = bytes(payload)
            
            try:
                sa.trace_clear()
            except Exception:
                pass
            time.sleep(0.1)

            # emit progress (pre-send)
            self._emit_progress({
                "status": "running",
                "current": spot_val + 1,
                "total": total_spots,
                "hex": f"0x{spot_val:02X}",
                "board_no": board_no,
                "channel_no": channel_no,
                "message": f"Sending spot 0x{spot_val:02X}"
            })

            # send
            try:
                sock.sendto(payload_bytes, (udp_dst_ip, udp_dst_port))
                print("Payload (hex):", payload_bytes.hex(" ").upper())
                print("Payload length:", len(payload_bytes))
                
                time.sleep(2.0)
                try:
                    sa.trace_max()
                except Exception:
                    pass
                time.sleep(3.0)

            except Exception as e:
                # report error but continue
                self._emit_progress({
                    "status": "error",
                    "current": spot_val + 1,
                    "total": total_spots,
                    "hex": f"0x{spot_val:02X}",
                    "board_no": board_no,
                    "channel_no": channel_no,
                    "message": f"UDP send failed: {e}"
                })
                continue

            # Analyzer measurement sequence
            try:
                try:
                    sa.peak_search()
                except Exception:
                    pass
                time.sleep(0.15)

                freq = None
                power = None
                try:
                    freq = sa.marker_frequency()
                    power = sa.marker_power()
                except Exception:
                    # swallow marker read errors; we still append None if necessary
                    pass

                if freq is not None and power is not None:
                    results.append({"spot": f"{spot_val:02X}", "freq_hz": freq, "power_dbm": power})
            except Exception as e:
                # report analyzer error on progress channel
                self._emit_progress({
                    "status": "error",
                    "current": spot_val + 1,
                    "total": total_spots,
                    "hex": f"0x{spot_val:02X}",
                    "board_no": board_no,
                    "channel_no": channel_no,
                    "message": f"Analyzer read failed: {e}"
                })
                # continue to next spot
                continue

        # Close socket
        try:
            sock.close()
        except Exception:
            pass

        # Completed
        self._emit_progress({
            "status": "completed",
            "current": total_spots,
            "total": total_spots,
            "board_no": board_no,
            "channel_no": channel_no,
            "message": f"Automation completed: {len(results)}/{total_spots} measurements successful"
        })

        return results
