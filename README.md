# PDIC CoE R&WS — Instrument Automation Dashboard

A specialized **Full-Stack Automation Framework** developed for the Digital TRC (Transmit/Receive Control) at BEL. This system provides a centralized web interface to manage high-end RF laboratory equipment, program FPGAs, and execute automated Acceptance Test Procedures (ATP).

## 🌐 Network-Wide Accessibility

The system is designed for remote laboratory management. Once the Flask server is running on a host PC connected to the instrument network:

* **Any system on the same Ethernet network** can access the GUI via the host's IP address.
* **Centralized Control:** An engineer can monitor tests or adjust power supplies from a desk while the hardware resides in a clean room or test bay.

## 🛠 Hardware Integration & Communication

The system utilizes a **USB Hub** and **Ethernet (TCP/IP)** architecture to bridge the software with physical instruments:

* **PyVISA & SCPI:** Primary communication layer for instrument control.
* **USB Hub Interface:** Connects multiple instruments (PSUs, Signal Generators) to the host PC.
* **UDP Protocol:** High-speed 10G UDP communication for data packet exchange with Digital TRC boards.
* **RS-422:** Serial communication for peripheral hardware control.

## 🚀 Key Features & Modules

### 1. Instrument Control Center

Directly manage and monitor multiple instruments through a unified interface:

* **Power Supplies (N8739A):** Set Voltage/Current and toggle Output state.
* **Signal Generator (SMB100A):** Control Frequency and RF Power levels.
* **Signal Analyzer (N9030B):** Adjust Center Frequency, Span, and RBW. Includes **Remote Screenshot** and **Trace Fetching** (Max Hold/Clear Trace) capabilities.

### 2. FPGA Programming

Integrated Vivado batch-mode support to program FPGA devices directly from the web GUI.

* Uses a dedicated `.tcl` script to automate the Xilinx hardware manager workflow.

### 3. Digital TRC Automation

Automated test sequences for DTRC boards:

* Configurable **Pulse Width** and **PRT** (Pulse Repetition Time).
* **Real-time Progress:** Live logs and status polling via Server-Sent Events (SSE).

### 4. Advanced Reporting

The system automatically compiles test data into professional Excel reports.

* **Data Visualization:** Includes "Power vs. Spot" charts.
* **Insights:** Auto-calculates Max/Min Power, Average Power, and Power Range (dB).

## 📁 Repository Structure

```text
├── gui/
│   ├── app.py            # Flask Backend & API Endpoints
│   └── static/           # UI Files (HTML, CSS, login.png, index.html)
├── core/
│   ├── controller.py     # Main automation logic
│   └── report_generator.py # Excel & Chart generation
├── drivers/
│   ├── base_driver.py    # VISA Discovery & Resource management
│   ├── n8739a_supply.py  # Power Supply Driver
│   ├── smb_generator.py  # Signal Generator Driver
│   └── pxa_analyzer.py   # Signal Analyzer Driver
└── scripts/
    └── program_fpga.tcl  # FPGA Programming Automation

```

## 🔧 Installation

1. **Prerequisites:**
* Install [NI-VISA](https://www.google.com/search?q=https://www.ni.com/en-in/support/downloads/drivers/download.ni-visa.html) or an equivalent VISA backend.
* Connect instruments via **USB Hub** or Ethernet.


2. **Setup:**
```bash
pip install flask pyvisa pyvisa-py pandas openpyxl pyserial

```


3. **Launch:**
```bash
python gui/app.py

```


*Navigate to `http://<your-ip-address>:80` in your browser.*

---

**Developed by Shivaling Koralli | PDIC CoE R&WS**

