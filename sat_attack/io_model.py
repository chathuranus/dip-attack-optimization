# io_model.py

# Off-chip communication model for one oracle query over an FT2232H
# USB-to-JTAG adapter. See analysis/off_chip_comm_info.md for references.
#
#   T_query = T_rt + (N_in + N_out + N_ovh) / f_TCK + B_usb / BW_usb
#   B_usb   = ceil((N_in + N_out) / 8) + USB_CMD_OVERHEAD_BYTES

import math


# USB round trip: OpenOCD's FT2232 driver sets the FTDI latency timer to 2 ms.
T_RT = 2e-3

# JTAG clock: FT2232H MPSSE maximum, 60 MHz / ((1 + 0) * 2).
F_TCK = 30e6

# Effective USB 2.0 High-Speed bulk throughput in bytes/s (10 x 512 B per 125 us microframe).
BW_USB = 40.96e6

# Extra TCK cycles per query: 5 TAP state transitions per DR scan x 2 DR scans (IEEE 1149.1).
N_OVH = 10

# MPSSE command bytes sent alongside the scan data in each query (estimate).
USB_CMD_OVERHEAD_BYTES = 20


def query_latency(n_in, n_out):
    """
    Returns the modelled time in seconds for one oracle query.

    n_in: number of primary inputs shifted into the chip
    n_out: number of outputs shifted out of the chip
    """
    shift_time = (n_in + n_out + N_OVH) / F_TCK
    usb_bytes = math.ceil((n_in + n_out) / 8) + USB_CMD_OVERHEAD_BYTES
    usb_transfer_time = usb_bytes / BW_USB

    return T_RT + shift_time + usb_transfer_time
