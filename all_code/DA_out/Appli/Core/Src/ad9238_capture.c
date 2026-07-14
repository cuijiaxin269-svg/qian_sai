#include "ad9238_capture.h"
#include <math.h>
#include <stddef.h>

extern PSSI_HandleTypeDef hpssi;

#if defined(__GNUC__)
#define AD9238_DMA_ALIGNED __attribute__((aligned(32)))
#else
#define AD9238_DMA_ALIGNED
#endif

AD9238_DMA_ALIGNED uint16_t ad9238_raw_buf[AD9238_RAW_SAMPLE_COUNT];
uint16_t ad9238_ch_a[AD9238_CHANNEL_SAMPLE_COUNT];
uint16_t ad9238_ch_b[AD9238_CHANNEL_SAMPLE_COUNT];
AD9238_Measurement ad9238_measurement;
volatile AD9238_RuntimeResult g_ad9238_result;
volatile AD9238_PinDiagnostics g_ad9238_pin_diag;
volatile uint32_t g_capture_start_stage;

static volatile AD9238_CaptureState g_capture_state = AD9238_CAPTURE_IDLE;
static volatile uint32_t g_last_error = 0u;
static volatile uint32_t g_capture_start_tick = 0u;
static volatile uint32_t g_restart_count = 0u;
static volatile uint32_t g_completed_count = 0u;
static volatile uint32_t g_terminal_overrun_count = 0u;

static void AD9238_CacheInvalidateRawBuffer(void);

static int16_t AD9238_CodeToSigned12(uint16_t code) {
  uint16_t value = code & 0x0FFFu;
  if ((value & 0x0800u) != 0u) {
    value |= 0xF000u;
  }
  return (int16_t)value;
}

static void AD9238_UpdateDataBusDiagnostics(void) {
  uint16_t all_high = 0x0FFFu;
  uint16_t any_high = 0u;

  for (uint32_t i = 0u; i < AD9238_RAW_SAMPLE_COUNT; i++) {
    uint16_t sample = ad9238_raw_buf[i] & 0x0FFFu;
    all_high &= sample;
    any_high |= sample;
  }

  g_ad9238_result.data_bit_activity_mask =
      (uint32_t)((any_high ^ all_high) & 0x0FFFu);
  g_ad9238_result.data_bit_stuck_low_mask =
      (uint32_t)((~any_high) & 0x0FFFu);
  g_ad9238_result.data_bit_stuck_high_mask = (uint32_t)(all_high & 0x0FFFu);
  g_ad9238_pin_diag.raw_activity_mask =
      g_ad9238_result.data_bit_activity_mask;
  g_ad9238_pin_diag.raw_stuck_low_mask =
      g_ad9238_result.data_bit_stuck_low_mask;
  g_ad9238_pin_diag.raw_stuck_high_mask =
      g_ad9238_result.data_bit_stuck_high_mask;
}

static void AD9238_FinalizeCompletedCapture(void) {
  if (g_capture_state != AD9238_CAPTURE_BUSY) {
    return;
  }

  HAL_PSSI_DISABLE_IT(&hpssi, PSSI_FLAG_OVR_RIS);
  hpssi.Instance->CR &= ~PSSI_CR_DMAEN;
  HAL_PSSI_DISABLE(&hpssi);
  PSSI->ICR = PSSI_ICR_OVR_ISC;
  hpssi.State = HAL_PSSI_STATE_READY;
  hpssi.ErrorCode = HAL_PSSI_ERROR_NONE;
  AD9238_CacheInvalidateRawBuffer();
  g_last_error = HAL_PSSI_ERROR_NONE;
  g_capture_state = AD9238_CAPTURE_DONE;
  g_completed_count++;
}

static float AD9238_WrapPhaseRad(float phase) {
  const float pi = 3.14159265358979323846f;
  const float two_pi = 6.28318530717958647692f;

  while (phase > pi) {
    phase -= two_pi;
  }
  while (phase < -pi) {
    phase += two_pi;
  }

  return phase;
}

static float AD9238_WrapPhaseDeg(float phase_deg) {
  while (phase_deg > 180.0f) {
    phase_deg -= 360.0f;
  }
  while (phase_deg < -180.0f) {
    phase_deg += 360.0f;
  }
  return phase_deg;
}

static bool AD9238_FrequenciesClose(float a_hz, float b_hz) {
  float diff;
  float average;
  float tolerance;

  if ((a_hz <= 0.0f) || (b_hz <= 0.0f)) {
    return false;
  }

  diff = fabsf(a_hz - b_hz);
  average = 0.5f * (a_hz + b_hz);
  tolerance = average * 0.02f;
  if (tolerance < 2000.0f) {
    tolerance = 2000.0f;
  }

  return diff <= tolerance;
}

static float AD9238_EstimateFrequency(const uint16_t *samples,
                                      uint32_t sample_count,
                                      float sample_rate_hz,
                                      float *correlation_out) {
  float sum = 0.0f;
  float mean;
  float min_code;
  float max_code;
  float last_crossing = 0.0f;
  float period_sum = 0.0f;
  float period_sq_sum = 0.0f;
  uint32_t period_count = 0u;
  bool have_crossing = false;

  if ((samples == NULL) || (sample_count < 16u) ||
      (sample_rate_hz <= 0.0f)) {
    return 0.0f;
  }

  min_code = (float)AD9238_CodeToSigned12(samples[0]);
  max_code = min_code;

  for (uint32_t i = 0u; i < sample_count; i++) {
    float code = (float)AD9238_CodeToSigned12(samples[i]);
    sum += code;
    if (code < min_code) {
      min_code = code;
    }
    if (code > max_code) {
      max_code = code;
    }
  }
  mean = sum / (float)sample_count;

  /*
   * Frequency is measured from interpolated rising zero crossings.  For the
   * clean sine waves used by this board this is more direct than searching
   * autocorrelation side-lobes, and it distinguishes 500 kHz from 1 MHz
   * reliably at the 10 MSPS/channel sample rate.
   */
  if ((max_code - min_code) < 16.0f) {
    if (correlation_out != NULL) {
      *correlation_out = 0.0f;
    }
    return 0.0f;
  }

  for (uint32_t i = 1u; i < sample_count; i++) {
    float previous = (float)AD9238_CodeToSigned12(samples[i - 1u]) - mean;
    float current = (float)AD9238_CodeToSigned12(samples[i]) - mean;

    if ((previous < 0.0f) && (current >= 0.0f) &&
        (fabsf(current - previous) > 0.000001f)) {
      float fraction = -previous / (current - previous);
      float crossing = (float)(i - 1u) + fraction;

      if (have_crossing) {
        float period = crossing - last_crossing;
        if (period > 0.0f) {
          float frequency = sample_rate_hz / period;
          if ((frequency >= AD9238_FREQ_MIN_HZ) &&
              (frequency <= AD9238_FREQ_MAX_HZ)) {
            period_sum += period;
            period_sq_sum += period * period;
            period_count++;
          }
        }
      }

      last_crossing = crossing;
      have_crossing = true;
    }
  }

  if ((period_count == 0u) || (period_sum <= 0.0f)) {
    if (correlation_out != NULL) {
      *correlation_out = 0.0f;
    }
    return 0.0f;
  }

  if (correlation_out != NULL) {
    float period_mean = period_sum / (float)period_count;
    float variance =
        (period_sq_sum / (float)period_count) - (period_mean * period_mean);
    float jitter_ratio;

    if (variance < 0.0f) {
      variance = 0.0f;
    }
    jitter_ratio = sqrtf(variance) / period_mean;
    *correlation_out = 1.0f / (1.0f + (10.0f * jitter_ratio));
  }

  return sample_rate_hz * (float)period_count / period_sum;
}

static void AD9238_CalculateChannelStats(const uint16_t *samples,
                                         uint32_t sample_count,
                                         float sample_rate_hz,
                                         float signal_freq_hz,
                                         AD9238_ChannelStats *stats) {
  const float pi = 3.14159265358979323846f;
  float sum = 0.0f;
  float sum_sq_ac = 0.0f;
  float i_part = 0.0f;
  float q_part = 0.0f;
  float min_v;
  float max_v;

  if ((samples == NULL) || (stats == NULL) || (sample_count == 0u) ||
      (sample_rate_hz <= 0.0f)) {
    return;
  }

  min_v = AD9238_CodeToVoltage(samples[0]);
  max_v = min_v;

  for (uint32_t i = 0u; i < sample_count; i++) {
    float v = AD9238_CodeToVoltage(samples[i]);
    sum += v;
    if (v < min_v) {
      min_v = v;
    }
    if (v > max_v) {
      max_v = v;
    }
  }

  stats->dc_v = sum / (float)sample_count;
  stats->min_v = min_v;
  stats->max_v = max_v;
  stats->vpp_v = max_v - min_v;

  for (uint32_t i = 0u; i < sample_count; i++) {
    float ac = AD9238_CodeToVoltage(samples[i]) - stats->dc_v;
    float phase = 2.0f * pi * signal_freq_hz * (float)i / sample_rate_hz;
    sum_sq_ac += ac * ac;
    i_part += ac * cosf(phase);
    q_part += ac * sinf(phase);
  }

  stats->rms_v = sqrtf(sum_sq_ac / (float)sample_count);
  stats->fundamental_peak_v =
      2.0f * sqrtf((i_part * i_part) + (q_part * q_part)) /
      (float)sample_count;
  stats->fundamental_rms_v = stats->fundamental_peak_v * 0.70710678118f;
  stats->phase_rad = atan2f(-q_part, i_part);
  stats->phase_deg = stats->phase_rad * 57.2957795131f;
}

static void AD9238_CalculateMeasurement(float sample_rate_hz) {
  float v_rms;
  float i_rms;
  float z_phase;
  float current_scale;
  float freq_a;
  float freq_b;

  freq_a = AD9238_EstimateFrequency(
      ad9238_ch_a, AD9238_CHANNEL_SAMPLE_COUNT, sample_rate_hz,
      &ad9238_measurement.voltage.frequency_correlation);
  freq_b = AD9238_EstimateFrequency(
      ad9238_ch_b, AD9238_CHANNEL_SAMPLE_COUNT, sample_rate_hz,
      &ad9238_measurement.current_adc.frequency_correlation);
  ad9238_measurement.voltage.frequency_hz = freq_a;
  ad9238_measurement.current_adc.frequency_hz = freq_b;

  if (freq_a <= 0.0f) {
    freq_a = AD9238_DEFAULT_SIGNAL_FREQ_HZ;
  }
  if (freq_b <= 0.0f) {
    freq_b = AD9238_DEFAULT_SIGNAL_FREQ_HZ;
  }

  AD9238_CalculateChannelStats(ad9238_ch_a, AD9238_CHANNEL_SAMPLE_COUNT,
                               sample_rate_hz, freq_a,
                               &ad9238_measurement.voltage);
  AD9238_CalculateChannelStats(ad9238_ch_b, AD9238_CHANNEL_SAMPLE_COUNT,
                               sample_rate_hz, freq_b,
                               &ad9238_measurement.current_adc);

  current_scale = AD9238_CURRENT_SHUNT_OHMS * AD9238_CURRENT_GAIN;
  if (current_scale <= 0.0f) {
    current_scale = 1.0f;
  }

  ad9238_measurement.current_rms_a =
      ad9238_measurement.current_adc.fundamental_rms_v / current_scale;
  ad9238_measurement.current_peak_a =
      ad9238_measurement.current_adc.fundamental_peak_v / current_scale;

  v_rms = ad9238_measurement.voltage.fundamental_rms_v;
  i_rms = ad9238_measurement.current_rms_a;
  z_phase = AD9238_WrapPhaseRad(ad9238_measurement.voltage.phase_rad -
                                ad9238_measurement.current_adc.phase_rad);

  ad9238_measurement.phase_v_minus_i_rad = z_phase;
  ad9238_measurement.phase_v_minus_i_deg = z_phase * 57.2957795131f;

  if (i_rms > 0.000001f) {
    ad9238_measurement.impedance_mag_ohm = v_rms / i_rms;
    ad9238_measurement.impedance_real_ohm =
        ad9238_measurement.impedance_mag_ohm * cosf(z_phase);
    ad9238_measurement.impedance_imag_ohm =
        ad9238_measurement.impedance_mag_ohm * sinf(z_phase);
  } else {
    ad9238_measurement.impedance_mag_ohm = 0.0f;
    ad9238_measurement.impedance_real_ohm = 0.0f;
    ad9238_measurement.impedance_imag_ohm = 0.0f;
  }
}

static void AD9238_CacheCleanInvalidateRawBuffer(void) {
  if ((SCB->CCR & SCB_CCR_DC_Msk) != 0u) {
    SCB_CleanInvalidateDCache_by_Addr((uint32_t *)ad9238_raw_buf,
                                      sizeof(ad9238_raw_buf));
  }
}

static void AD9238_CacheInvalidateRawBuffer(void) {
  if ((SCB->CCR & SCB_CCR_DC_Msk) != 0u) {
    SCB_InvalidateDCache_by_Addr((uint32_t *)ad9238_raw_buf,
                                 sizeof(ad9238_raw_buf));
  }
}

void AD9238_Init(void) {
  HAL_GPIO_WritePin(AD9238_PWDN_GPIO_Port, AD9238_PWDN_Pin, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(AD9238_OEB_GPIO_Port, AD9238_OEB_Pin, GPIO_PIN_RESET);
  AD9238_StopCapture();
  PSSI->ICR = PSSI_ICR_OVR_ISC;
  g_ad9238_pin_diag.magic = AD9238_PIN_DIAG_MAGIC;
  g_ad9238_pin_diag.gpiob_moder = GPIOB->MODER;
  g_ad9238_pin_diag.gpiob_pupdr = GPIOB->PUPDR;
  g_ad9238_pin_diag.gpiob_afrl = GPIOB->AFR[0];
  g_ad9238_pin_diag.gpiod_moder = GPIOD->MODER;
  g_ad9238_pin_diag.gpiod_pupdr = GPIOD->PUPDR;
  g_ad9238_pin_diag.gpiod_afrl = GPIOD->AFR[0];
  g_ad9238_pin_diag.pssi_cr = PSSI->CR;
  g_ad9238_pin_diag.pd6_seen_low = 0u;
  g_ad9238_pin_diag.pd6_seen_high = 0u;
}

HAL_StatusTypeDef AD9238_StartCapture(void) {
  HAL_StatusTypeDef status;

  if (g_capture_state == AD9238_CAPTURE_BUSY) {
    return HAL_BUSY;
  }

  g_last_error = 0u;
  g_capture_state = AD9238_CAPTURE_BUSY;
  g_capture_start_tick = HAL_GetTick();

  g_capture_start_stage = 1u;
  HAL_GPIO_WritePin(AD9238_PWDN_GPIO_Port, AD9238_PWDN_Pin, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(AD9238_OEB_GPIO_Port, AD9238_OEB_Pin, GPIO_PIN_RESET);

  g_capture_start_stage = 2u;
  PSSI->ICR = PSSI_ICR_OVR_ISC;
  AD9238_CacheCleanInvalidateRawBuffer();

  g_capture_start_stage = 3u;
  /*
   * HAL_PSSI_Receive_DMA() takes a byte count.  The GPDMA channel is
   * configured for 32-bit transfers so that one DMA request drains two
   * consecutive 16-bit PSSI samples from the FIFO.
   */
  status = HAL_PSSI_Receive_DMA(&hpssi, (uint32_t *)ad9238_raw_buf,
                                sizeof(ad9238_raw_buf));
  if (status != HAL_OK) {
    g_last_error = HAL_PSSI_GetError(&hpssi);
    g_capture_state = AD9238_CAPTURE_ERROR;
    return status;
  }

  g_capture_start_stage = 4u;
  return HAL_OK;
}

void AD9238_StopCapture(void) {
  (void)HAL_PSSI_Abort_DMA(&hpssi);
  PSSI->ICR = PSSI_ICR_OVR_ISC;
}

bool AD9238_IsCaptureDone(void) {
  return g_capture_state == AD9238_CAPTURE_DONE;
}

AD9238_CaptureState AD9238_GetCaptureState(void) {
  return g_capture_state;
}

uint32_t AD9238_GetLastError(void) {
  return g_last_error;
}

uint32_t AD9238_GetRestartCount(void) {
  return g_restart_count;
}

uint32_t AD9238_GetCompletedCount(void) {
  return g_completed_count;
}

uint32_t AD9238_GetTerminalOverrunCount(void) {
  return g_terminal_overrun_count;
}

void AD9238_CaptureTask(void) {
  if ((GPIOD->IDR & GPIO_PIN_6) != 0u) {
    g_ad9238_pin_diag.pd6_seen_high = 1u;
  } else {
    g_ad9238_pin_diag.pd6_seen_low = 1u;
  }
  g_ad9238_pin_diag.pssi_cr = PSSI->CR;

  if (g_capture_state != AD9238_CAPTURE_BUSY) {
    return;
  }

  /*
   * With a continuous external PDCK, one more clock can reach PSSI after the
   * requested block has filled but before the DMA-complete IRQ disables PSSI.
   * A zero DMA counter means the complete frame is already safely in RAM; the
   * resulting terminal OVR is therefore not a failed capture.
   */
  if ((hpssi.hdmarx != NULL) &&
      (__HAL_DMA_GET_COUNTER(hpssi.hdmarx) == 0u)) {
    if ((PSSI->RIS & PSSI_RIS_OVR_RIS) != 0u) {
      g_terminal_overrun_count++;
    }
    AD9238_FinalizeCompletedCapture();
    return;
  }

  if ((PSSI->RIS & PSSI_RIS_OVR_RIS) != 0u) {
    g_last_error = HAL_PSSI_ERROR_OVER_RUN;
    g_capture_state = AD9238_CAPTURE_ERROR;
    g_restart_count++;
    return;
  }

  if ((HAL_GetTick() - g_capture_start_tick) >= AD9238_CAPTURE_TIMEOUT_MS) {
    g_last_error = HAL_PSSI_ERROR_TIMEOUT;
    g_capture_state = AD9238_CAPTURE_ERROR;
    g_restart_count++;
  }
}

void AD9238_ClearCaptureDone(void) {
  if (g_capture_state == AD9238_CAPTURE_DONE) {
    g_capture_state = AD9238_CAPTURE_IDLE;
  }
}

void AD9238_Deinterleave(bool even_is_channel_a) {
  for (uint32_t i = 0u; i < AD9238_CHANNEL_SAMPLE_COUNT; i++) {
    uint16_t even = ad9238_raw_buf[2u * i] & 0x0FFFu;
    uint16_t odd = ad9238_raw_buf[2u * i + 1u] & 0x0FFFu;

    if (even_is_channel_a) {
      ad9238_ch_a[i] = even;
      ad9238_ch_b[i] = odd;
    } else {
      ad9238_ch_a[i] = odd;
      ad9238_ch_b[i] = even;
    }
  }
}

float AD9238_CodeToVoltage(uint16_t code) {
  /* The board straps AD9238 DFS for two's-complement output. */
  return ((float)AD9238_CodeToSigned12(code) * AD9238_ADC_FULL_SCALE_VPP) /
         4096.0f;
}

GPIO_PinState AD9238_ReadOTR(void) {
  return HAL_GPIO_ReadPin(AD9238_OTR_GPIO_Port, AD9238_OTR_Pin);
}

const AD9238_Measurement *AD9238_ProcessCapture(bool even_is_channel_a) {
  AD9238_Deinterleave(even_is_channel_a);
  AD9238_CalculateMeasurement(AD9238_CHANNEL_SAMPLE_RATE_HZ);

  g_ad9238_result.magic = AD9238_RESULT_MAGIC;
  g_ad9238_result.sequence++;
  g_ad9238_result.valid_mask = 0u;
  if (ad9238_measurement.voltage.frequency_hz > 0.0f) {
    g_ad9238_result.valid_mask |= AD9238_VALID_CHANNEL_A;
  }
  if (ad9238_measurement.current_adc.frequency_hz > 0.0f) {
    g_ad9238_result.valid_mask |= AD9238_VALID_CHANNEL_B;
  }
  if (AD9238_FrequenciesClose(ad9238_measurement.voltage.frequency_hz,
                              ad9238_measurement.current_adc.frequency_hz)) {
    g_ad9238_result.valid_mask |= AD9238_VALID_PHASE_AB;
  }
  g_ad9238_result.channel_a_frequency_hz =
      ad9238_measurement.voltage.frequency_hz;
  g_ad9238_result.channel_b_frequency_hz =
      ad9238_measurement.current_adc.frequency_hz;
  g_ad9238_result.channel_a_frequency_correlation =
      ad9238_measurement.voltage.frequency_correlation;
  g_ad9238_result.channel_b_frequency_correlation =
      ad9238_measurement.current_adc.frequency_correlation;
  g_ad9238_result.channel_a_dc_v = ad9238_measurement.voltage.dc_v;
  g_ad9238_result.channel_b_dc_v = ad9238_measurement.current_adc.dc_v;
  /*
   * Report sine amplitude from the fitted fundamental instead of raw min/max.
   * The raw min/max is still available in ad9238_measurement.*.vpp_v; the
   * runtime result is the value users normally expect from a signal generator
   * Vpp setting.
   */
  g_ad9238_result.channel_a_vpp_v =
      2.0f * ad9238_measurement.voltage.fundamental_peak_v;
  g_ad9238_result.channel_b_vpp_v =
      2.0f * ad9238_measurement.current_adc.fundamental_peak_v;
  g_ad9238_result.channel_a_rms_v = ad9238_measurement.voltage.rms_v;
  g_ad9238_result.channel_b_rms_v = ad9238_measurement.current_adc.rms_v;
  g_ad9238_result.channel_a_phase_deg_at_t0 =
      ad9238_measurement.voltage.phase_deg;
  g_ad9238_result.channel_b_phase_deg_at_t0 =
      ad9238_measurement.current_adc.phase_deg;
  /* With unequal frequencies this is an initial-phase difference at t=0,
   * not a constant phase difference over the entire capture. */
  g_ad9238_result.phase_a_minus_b_deg_at_t0 =
      AD9238_WrapPhaseDeg(g_ad9238_result.channel_a_phase_deg_at_t0 -
                          g_ad9238_result.channel_b_phase_deg_at_t0);
  AD9238_UpdateDataBusDiagnostics();
  return &ad9238_measurement;
}

const AD9238_Measurement *AD9238_GetLastMeasurement(void) {
  return &ad9238_measurement;
}

void HAL_PSSI_RxCpltCallback(PSSI_HandleTypeDef *hpssi_cb) {
  if (hpssi_cb->Instance == PSSI) {
    AD9238_FinalizeCompletedCapture();
  }
}

void HAL_PSSI_ErrorCallback(PSSI_HandleTypeDef *hpssi_cb) {
  if (hpssi_cb->Instance == PSSI) {
    if ((hpssi_cb->hdmarx != NULL) &&
        (__HAL_DMA_GET_COUNTER(hpssi_cb->hdmarx) == 0u)) {
      g_terminal_overrun_count++;
      AD9238_FinalizeCompletedCapture();
      return;
    }
    g_last_error = HAL_PSSI_GetError(hpssi_cb);
    if (g_last_error == HAL_PSSI_ERROR_NONE) {
      g_last_error = HAL_PSSI_ERROR_OVER_RUN;
    }
    g_capture_state = AD9238_CAPTURE_ERROR;
    g_restart_count++;
  }
}
