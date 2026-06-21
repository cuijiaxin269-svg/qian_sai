create_clock -name CLK_65M -period 15.384 [get_ports {ADC_CLK ADC_IN[0] ADC_IN[1] ADC_IN[2] ADC_IN[3] ADC_IN[4] ADC_IN[5] ADC_IN[6] ADC_IN[7] ADC_IN[8] ADC_IN[9] ADC_IN[10] ADC_IN[11] }] 
create_clock -name CLK_50M -period 20.000 [get_ports {SYS_CLK}]

set_clock_uncertainty -setup -rise_from altera_reserved_tck -rise_to altera_reserved_tck 0.150
set_clock_uncertainty -hold -rise_from altera_reserved_tck -rise_to altera_reserved_tck 0.150
set_clock_uncertainty -setup -rise_from altera_reserved_tck -fall_to altera_reserved_tck 0.150
set_clock_uncertainty -hold -rise_from altera_reserved_tck -fall_to altera_reserved_tck 0.150
set_clock_uncertainty -setup -fall_from altera_reserved_tck -fall_to altera_reserved_tck 0.150
set_clock_uncertainty -hold -fall_from altera_reserved_tck -fall_to altera_reserved_tck 0.150

derive_pll_clocks
derive_clock_uncertainty
