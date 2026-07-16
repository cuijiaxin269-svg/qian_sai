#ifndef __DDS_AD9833_H
#define __DDS_AD9833_H

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"
#include <stdint.h>

/* AD9833 MCLK is supplied by the board's external 20 MHz clock source. */
#define DDS_AD9833_MCLK_HZ 20000000UL
/* FOUT = MCLK * FREQ0 / 2^28: 1 MHz sine-wave output. */
#define DDS_AD9833_DEFAULT_FREQUENCY_HZ 1000000UL
/* Let the DDS and following analog path settle before the first ADC frame. */
#define DDS_AD9833_SETTLING_TIME_MS 100UL

typedef enum {
  DDS_AD9833_WAVE_SINE = 0,
  DDS_AD9833_WAVE_TRIANGLE,
  DDS_AD9833_WAVE_SQUARE
} DDS_AD9833_Waveform;

typedef struct {
  uint32_t frequency_hz;
  DDS_AD9833_Waveform waveform;
  uint16_t control_word;
} DDS_AD9833_State;

extern volatile DDS_AD9833_State g_dds_ad9833_state;

void DDS_AD9833_Init(void);
void DDS_AD9833_Write16(uint16_t data);
void DDS_AD9833_SetFrequency(uint32_t frequency_hz);
void DDS_AD9833_SetWaveform(DDS_AD9833_Waveform waveform);

#ifdef __cplusplus
}
#endif

#endif /* __DDS_AD9833_H */
