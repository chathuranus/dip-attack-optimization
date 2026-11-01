# Off-chip communication model for oracle queries

**Setup:** attacker PC ⟷ *USB 2.0 High-Speed* ⟷ FT2232H JTAG adapter ⟷ *JTAG (TCK/TMS/TDI/TDO)* ⟷ oracle chip

## Per-query latency model

$$
T_{query} = T_{rt} + \frac{N_{in} + N_{out} + N_{ovh}}{f_{TCK}} + \frac{B_{usb}}{BW_{usb}}
$$

| Symbol | Meaning |
|---|---|
| $N_{in}$ | Number of circuit primary inputs (bits shifted in; key inputs excluded) |
| $N_{out}$ | Number of circuit outputs (bits shifted out) |
| $B_{usb}$ | USB bytes per query $= \lceil (N_{in} + N_{out}) / 8 \rceil + 20$ (MPSSE command overhead, estimate) |

## Parameters

| Parameter | Value | Reference |
|---|---|---|
| $T_{rt}$ | 2 ms | OpenOCD's FT2232 driver sets the FTDI latency timer to 2 ms (`ft2232_latency = 2`), bounding the buffering delay for short responses. OpenOCD also notes FT2232 adapters need "round trips over the USB link" for most JTAG request/response interactions. [OpenOCD ft2232.c](https://openocd.org/doc-release/doxygen/ft2232_8c.html) |
| $BW_{usb}$ | 40.96 MB/s | Host controllers "able to receive 10 bulk packets/microframe (40.96 MB/s)". [Trenz Electronic Wiki](https://wiki.trenz-electronic.de/display/TEUSB/Data+throughput+limit+of+Bulk+transfer+type) |
| $f_{TCK}$ | 30 MHz | FT2232H MPSSE "up to 30 Mbit/s". [FT2232H datasheet](https://ftdichip.com/wp-content/uploads/2020/07/DS_FT2232H.pdf). TCK = 60 MHz / ((1 + divisor) × 2) = 30 MHz at divisor 0. [FTDI AN_135](https://www.ftdichip.com/Documents/AppNotes/AN_135_MPSSE_Basics.pdf) |
| $N_{ovh}$ | 10 TCK cycles | Derived from the IEEE 1149.1 TAP controller state machine: 5 cycles per DR scan × 2 DR scans per query (Run-Test/Idle → Select-DR-Scan → Capture-DR → Shift-DR = 3; Exit1-DR → Update-DR → Run-Test/Idle = 2). [TI JTAG Testability Primer (SSYA002)](http://www.ti.com/lit/pdf/ssya002), Fig. 3-3 |

## Example per-query latency

| Circuit | $N_{in} + N_{out}$ | Shift time | USB transfer | $T_{query}$ |
|---|---|---|---|---|
| c432 | 36 + 7 | 1.77 µs | 0.63 µs | 2.0024 ms |
| c7552 | 207 + 108 | 10.83 µs | 1.46 µs | 2.0123 ms |

$T_{rt}$ dominates (>99% of $T_{query}$), so total oracle cost ≈ `oracle_queries` × $T_{rt}$.

## Recorded fields

Implemented in `sat_attack/io_model.py` and saved in each benchmark's `attack_metrics.json`:

| Field | Formula |
|---|---|
| `io_aware_oracle_seconds` | `oracle_queries` × $T_{query}$ |
| `io_aware_total_runtime_seconds` | `total_runtime_seconds` + `io_aware_oracle_seconds` |

## Notes

- $T_{rt}$ is a configured buffering bound, not a measured round-trip time. Describe it as such in the write-up.
- The `ft2232` driver is OpenOCD's legacy FTDI driver (superseded by the `ftdi` driver); verify the current driver's latency setting before citing.
- If the circuit is embedded in a larger SoC, $N_{in}$ / $N_{out}$ should be the full scan-chain length.
- `io_aware_total_runtime_seconds` keeps the measured (simulated) oracle time and adds the modelled communication time, so it is an upper bound on a real attack's runtime.
