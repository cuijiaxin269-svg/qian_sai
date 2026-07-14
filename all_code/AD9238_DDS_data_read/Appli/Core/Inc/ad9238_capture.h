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
#define AD9238_DFT_SIGNAL_FREQ_HZ 1000000.0f
#define AD9238_DFT_SAMPLE_COUNT 2000u
#define AD9238_DEFAULT_SIGNAL_FREQ_HZ 100000.0f
#define AD9238_FREQ_MIN_HZ 10000.0f
#define AD9238_FREQ_MAX_HZ 3000000.0f
#define AD9238_FREQ_MIN_CORRELATION 0.35f
#define AD9238_VALID_CHANNEL_A 0x01u
#define AD9238_VALID_CHANNEL_B 0x02u
#define AD9238_VALID_PHASE_AB 0x04u
#define AD9238_RESULT_MAGIC 0x41443932u
#define AD9238_PIN_DIAG_MAGIC 0x50443936u
#define AD9238_CANDIDATE_DEBUG_MAGIC 0x43414E44u
#define AD9238_CANDIDATE_COUNT 2u
#define AD9238_CANDIDATE_BANK_COUNT 2u
/*
 * Bridge reference resistor range selection.
 *
 * Change only AD9238_BRIDGE_R0_GEAR when the hardware range changes.  The
 * measurement algorithm reads AD9238_BRIDGE_R0_OHMS, so impedance/current and
 * capacitance-related calculations stay consistent with the selected range.
 */
#define AD9238_R0_GEAR_100R 0u
#define AD9238_R0_GEAR_1K 1u
#define AD9238_R0_GEAR_10K 2u

#define AD9238_BRIDGE_R0_GEAR AD9238_R0_GEAR_100R

#if AD9238_BRIDGE_R0_GEAR == AD9238_R0_GEAR_100R
#define AD9238_BRIDGE_R0_OHMS 100.0f
#elif AD9238_BRIDGE_R0_GEAR == AD9238_R0_GEAR_1K
#define AD9238_BRIDGE_R0_OHMS 1000.0f
#elif AD9238_BRIDGE_R0_GEAR == AD9238_R0_GEAR_10K
#define AD9238_BRIDGE_R0_OHMS 10000.0f
#else
#error "Unsupported AD9238_BRIDGE_R0_GEAR"
#endif
#define AD9238_CAP_RANGE_MIN_PF 10.0f
#define AD9238_CAP_RANGE_MAX_PF 5000.0f
#define AD9238_BRIDGE_MIN_VL_PEAK_V 0.005f
#define AD9238_CURRENT_SHUNT_OHMS AD9238_BRIDGE_R0_OHMS
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
  float channel_a_phase_deg_at_t0;
  float channel_b_phase_deg_at_t0;
  /*
   * Valid as a fixed phase difference only when valid_mask has
   * AD9238_VALID_PHASE_AB set.  If the two channel frequencies are different,
   * this value is only the instantaneous A-B phase at the first sample.
   */
  float phase_a_minus_b_deg_at_t0;
  float bridge_impedance_mag_ohm;
  float bridge_impedance_phase_deg;
  float bridge_impedance_real_ohm;
  float bridge_impedance_imag_ohm;
  uint32_t data_bit_activity_mask;
  uint32_t data_bit_stuck_low_mask;
  uint32_t data_bit_stuck_high_mask;
} AD9238_RuntimeResult;

/*
 * Debug record for the deterministic VH/VL alignment result.  The backing
 * store keeps two record slots so the J-Link memory layout remains stable,
 * but candidate_count is now one: channel identity comes only from the
 * measured fundamental amplitude (larger = VH), not from impedance scoring.
 * No fixed channel phase compensation is applied.
 */
typedef struct {
  uint32_t even_is_channel_a;
  float channel_b_delay_samples;
  float channel_b_delay_deg;
  float score;
  float channel_a_vpp_v;
  float channel_b_vpp_v;
  float channel_a_phase_deg;
  float channel_b_phase_deg;
  float phase_a_minus_b_deg;
  float impedance_mag_ohm;
  float impedance_phase_deg;
  float impedance_real_ohm;
  float impedance_imag_ohm;
  float capacitance_pf;
} AD9238_CandidateRecord;

typedef struct {
  uint32_t sequence;
  uint32_t candidate_count;
  uint32_t selected_index;
  AD9238_CandidateRecord candidate[AD9238_CANDIDATE_COUNT];
} AD9238_CandidateBank;

/*
 * J-Link can halt the core at any instruction.  A single candidate array can
 * therefore be observed halfway through an update.  The producer writes only
 * the inactive bank, then atomically changes active_bank after a data-memory
 * barrier.  The bank named by active_bank is always a complete frame.
 */
typedef struct {
  uint32_t magic;
  uint32_t active_bank;
  AD9238_CandidateBank bank[AD9238_CANDIDATE_BANK_COUNT];
} AD9238_CandidateDebugStore;

typedef struct {
  uint32_t magic;
  uint32_t gpiob_moder;
  uint32_t gpiob_pupdr;
  uint32_t gpiob_afrl;
  uint32_t gpiod_moder;
  uint32_t gpiod_pupdr;
  uint32_t gpiod_afrl;
  uint32_t pssi_cr;
  uint32_t pd6_seen_low;
  uint32_t pd6_seen_high;
  uint32_t raw_activity_mask;
  uint32_t raw_stuck_low_mask;
  uint32_t raw_stuck_high_mask;
} AD9238_PinDiagnostics;

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
extern volatile AD9238_PinDiagnostics g_ad9238_pin_diag;
extern volatile AD9238_CandidateDebugStore g_ad9238_candidate_debug;

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
