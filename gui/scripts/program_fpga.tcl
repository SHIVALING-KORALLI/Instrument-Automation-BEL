# Vivado TCL script to program FPGA
set bitfile "C:/Nirbhay/Software/shiva/v2/gui/bitfiles/SASTRA_DTRC.bit" 
# Connect to the local hardware server
open_hw
connect_hw_server
# Open available hardware target (JTAG cable etc.)
open_hw_target
# Get first available device
set device [lindex [get_hw_devices] 0]
# Associate .bit file with the device
set_property PARAM.FREQUENCY 12000000 [get_hw_targets */xilinx_tcf/Digilent/210308B0B0C5]
set_property PROGRAM.FILE $bitfile $device
# Program the FPGA
program_hw_devices $device
# (Optional) Refresh to confirm status
refresh_hw_device $device
puts "✅ FPGA programmed successfully with $bitfile"
# Exit Vivado
# exit
