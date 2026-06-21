#ifndef __AD9238_CAPTURE_H
#define __AD9238_CAPTURE_H

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"
#include <stdbool.h>
#include <stdint.h>

#define AD9238_RAW_SAMPLE_COUNT 4096u
#define AD9238_CHANNEL_SAMPLE_COUNT (AD9238_RAW_SAMPLE_COUNT / 2u)
#define AD9238_ADC_MID_CODE 2048.0f
#define AD9238_ADC_FULL_SCALE_VPP 10.0f
#define AD9238_CHANNEL_SAMPLE_RATE_HZ 10000000.0f
#define AD9238_DEFAULT_SIGNAL_FREQ_HZ 100000.0f
#define AD9238_FREQ_MIN_HZ 10000.0f
#define AD9238_FREQ_MAX_HZ 3000000.0f
#define AD9238_FREQ_MIN_CORRELATION 0.35f
#define AD9238_RESULT_MAGIC 0x41443932u
#define AD9238_CURRENT_SHUNT_OHMS 1.0f
#define AD9238_CURRENT_GAIN 1.0f
#define AD9238_CAPTURE_TIMEOUT_MS 100u

extern uint16_t ad9238_raw_buf[AD9238_RAW_SAMPLE_COUNT];
extern uint16_t ad9238_ch_a[AD9238_CHANNEL_SAMPLE_COUNT];
extern uint16_t ad9238_ch_b[AD9238_CHANNEL_SAMPLE_COUNT];

typedef enum {
  AD9238_CAPTURE_IDLE = 0,
  AD9238_CAPTURE_BUSY,
  AD9238_CAPTURE_DONE,
  AD9238_CAPTURE_ERROR,
} AD9238_CaptureState;

typedef struct {
  float frequency_hz;
  float frequency_correlation;
  float dc_v;
  float min_v;
  float max_v;
  float vpp_v;
  float rms_v;
  float fundamental_peak_v;
  float fundamental_rms_v;
  float phase_rad;
  float phase_deg;
} AD9238_ChannelStats;

typedef struct {
  uint32_t magic;
  uint32_t sequence;
  uint32_t valid_mask;
  float channel_a_frequency_hz;
  float channel_b_frequency_hz;
  float channel_a_frequency_correlation;
  float channel_b_frequency_correlation;
  float channel_a_dc_v;
  float channel_b_dc_v;
  float channel_a_vpp_v;
  float channel_b_vpp_v;
  float channel_a_rms_v;
  float channel_b_rms_v;
} AD9238_RuntimeResult;

typedef struct {
  AD9238_ChannelStats voltage;
  AD9238_ChannelStats current_adc;
  float current_rms_a;
  float current_peak_a;
  float phase_v_minus_i_rad;
  float phase_v_minus_i_deg;
  float impedance_mag_ohm;
  float impedance_real_ohm;
  float impedance_imag_ohm;
} AD9238_Measurement;

extern AD9238_Measurement ad9238_measurement;
extern volatile AD9238_RuntimeResult g_ad9238_result;

void AD9238_Init(void);
HAL_StatusTypeDef AD9238_StartCapture(void);
void AD9238_StopCapture(void);
bool AD9238_IsCaptureDone(void);
AD9238_CaptureState AD9238_GetCaptureState(void);
uint32_t AD9238_GetLastError(void);
uint32_t AD9238_GetRestartCount(void);
uint32_t AD9238_GetCompletedCount(void);
uint32_t AD9238_GetTerminalOverrunCount(void);
void AD9238_CaptureTask(void);
void AD9238_ClearCaptureDone(void);
void AD9238_Deinterleave(bool even_is_channel_a);
float AD9238_CodeToVoltage(uint16_t code);
GPIO_PinState AD9238_ReadOTR(void);
const AD9238_Measurement *AD9238_ProcessCapture(bool even_is_channel_a);
const AD9238_Measurement *AD9238_GetLastMeasurement(void);

#ifdef __cplusplus
}
#endif

#endif
