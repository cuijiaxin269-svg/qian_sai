#ifndef __DAC_OUTPUT_H
#define __DAC_OUTPUT_H

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"
#include <stdint.h>

/*
 * The vendor DAC1220 module example treats the DAC output as a bipolar range:
 * VOLTAGE_RANGE = 0 -> +/-5 V output range.
 * VREF is in mV, matching the reference code.
 */
#define DAC1220_VOLTAGE_RANGE_5V 0u
#define DAC1220_VREF_MV 2500.0f
#define DAC_OUTPUT_DEFAULT_VOLTAGE 2.0f
#define DAC1220_CMR_NORMAL_16BIT_OFFSET_BINARY 0x0000u

typedef struct {
  uint32_t last_frame;
  uint8_t last_bit_count;
  uint16_t last_code;
  uint16_t command_register;
  float last_voltage;
  uint32_t write_count;
} DAC_OutputState;

extern volatile DAC_OutputState g_dac_output_state;

void DAC_Output_Init(void);
void DAC_Output_WriteFrame(uint32_t frame, uint8_t bit_count);
void DAC_Output_Write16(uint16_t data);
void DAC1220_WriteRegister(uint8_t start_address, const uint8_t *data,
                           uint8_t byte_count);
void DAC1220_WriteCommandRegister(uint16_t command);
void DAC1220_WriteDataInputRegister16(uint16_t code);
void DAC_Output_SetCode16(uint16_t code);
void DAC_Output_SetRatio(float ratio);
void DAC_Output_SetVoltage(float voltage);

#ifdef __cplusplus
}
#endif

#endif /* __DAC_OUTPUT_H */
