---

# 📡 Multi-Instrument Automation & Digital TRC Control System

### Centralized Web-ATE for RF Testing, FPGA Programming, and 10G UDP Protocols

---

## 📌 Project Overview

This system is a professional **Automated Test Equipment (ATE)** framework designed for Bharat Electronics Limited. It bridges the gap between high-level software and laboratory hardware, enabling engineers to perform complex RF measurements and board configurations via a network-accessible Web GUI.

* **Remote Accessibility:** Access the GUI from any system on the Ethernet network.
* **Hardware Bridge:** Uses a high-speed **USB Hub** to consolidate instrument connections.
* **End-to-End Automation:** Handles everything from FPGA programming to final PDF/Excel report generation.

---

## 🔐 System Access & Security

The application begins with a secure login portal, ensuring that only authorized personnel can control the high-value laboratory instruments.

---

## 🛠 Feature-Rich Control Dashboard

The main interface allows real-time manual and automated control of the entire test bench.

### 1. Instrument Control Suite (PyVISA/SCPI)

* **Power Supplies (N8739A):** Dual-channel monitoring (Voltage/Current) with safety output toggles.
* **Signal Generator (SMB100A):** Precision RF frequency and power level injection.
* **Signal Analyzer (N9030B):** Live trace fetching, peak searching, and remote screenshot capture.

### 2. High-Speed Protocol Implementation

The system goes beyond simple SCPI, implementing low-level industrial protocols:

* **10G UDP Protocol:** Custom 40-byte packet injection with loopback verification for Digital TRC boards.
* **RS-422/Serial:** 9-byte hex packet communication for peripheral hardware control.
* **FPGA Programming:** Integrated **Xilinx Vivado** batch-mode control to program boards via `.tcl` scripts.

---

## 🧬 Technical Implementation (app.py)

The backend is built on a robust **Flask** architecture using **Server-Sent Events (SSE)** for real-time log streaming.

### Logic Breakdown:

* **Driver Layer:** Individual classes for `N8739APowerSupply`, `SMB100AGenerator`, and `N9030BAnalyzer` inherit from a base driver to handle VISA resource management.
* **Automation Loop:** The `/api/run` endpoint orchestrates the `AutomationController`, which steps through frequencies, captures markers, and verifies limits.
* **Data Serialization:** Trace data is fetched as raw binary (`REAL,64`), unpacked using Python's `struct` library, and converted to JSON for browser-side plotting.

```python
# Example: Binary Trace Unpacking Logic in app.py
def try_unpack(fmt_char):
    fmt = f"{fmt_char}{count}d"
    vals = struct.unpack(fmt, payload)
    return vals # Returns finite, calibrated trace data

```

---

## 📊 Automated Report Generation

One of the most critical features is the automated **ATP (Acceptance Test Procedure)** reporting.

### Session Logging

Every automated run creates a detailed entry in a daily Excel workbook, logging every frequency spot and measured power level.

### Power Analysis & Charts

The system automatically generates a **Power vs. Spot** chart and calculates:

* **Maximum & Minimum Power**
* **Average Power Output**
* **Power Range (Flatness) in dB**

---

## 📂 Project Structure

```text
├── gui/
│   ├── app.py              # Main Flask Backend & SSE Logic
│   └── static/             # Frontend (HTML/JS/Images)
├── core/
│   ├── controller.py       # Orchestration of test sequences
│   └── report_generator.py # Excel, Pandas, and Chart logic
├── drivers/
│   ├── n8739a_supply.py    # PSU SCPI Driver
│   ├── smb_generator.py    # Signal Gen SCPI Driver
│   └── pxa_analyzer.py     # Spectrum Analyzer SCPI Driver
└── scripts/
    └── program_fpga.tcl    # Vivado Hardware Manager Automation

```

---

## 🚀 Getting Started

1. **Hardware Connection:** Connect all instruments to the host PC via the **USB Hub**. Connect the PC to the local Ethernet network.
2. **Environment Setup:**
```bash
pip install flask pyvisa pyvisa-py pandas openpyxl pyserial

```


3. **Launch:**
```bash
python gui/app.py

```


4. **Network Access:** Access via `http://[Host_IP]:80` from any networked computer.

---

### 👤 Author

**Shivaling Koralli** *PDIC CoE R&WS, Bharat Electronics Limited*

---

