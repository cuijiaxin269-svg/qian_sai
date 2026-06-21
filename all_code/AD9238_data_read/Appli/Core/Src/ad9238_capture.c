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
volatile uint32_t g_capture_start_stage;

static volatile AD9238_CaptureState g_capture_state = AD9238_CAPTURE_IDLE;
static volatile uint32_t g_last_error = 0u;
static volatile uint32_t g_capture_start_tick = 0u;
static volatile uint32_t g_restart_count = 0u;
static volatile uint32_t g_completed_count = 0u;
static volatile uint32_t g_terminal_overrun_count = 0u;

static void AD9238_CacheInvalidateRawBuffer(void);

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

static float AD9238_Autocorrelation(const uint16_t *samples,
                                    uint32_t sample_count,
                                    uint32_t lag,
                                    float mean) {
  float sum_xy = 0.0f;
  float sum_xx = 0.0f;
  float sum_yy = 0.0f;

  for (uint32_t i = 0u; i < (sample_count - lag); i++) {
    float x = (float)(samples[i] & 0x0FFFu) - mean;
    float y = (float)(samples[i + lag] & 0x0FFFu) - mean;
    sum_xy += x * y;
    sum_xx += x * x;
    sum_yy += y * y;
  }

  if ((sum_xx <= 1.0f) || (sum_yy <= 1.0f)) {
    return 0.0f;
  }

  return sum_xy / sqrtf(sum_xx * sum_yy);
}

static float AD9238_EstimateFrequency(const uint16_t *samples,
                                      uint32_t sample_count,
                                      float sample_rate_hz,
                                      float *correlation_out) {
  float sum = 0.0f;
  float mean;
  float corr_left;
  float corr_center;
  bool crossed_negative = false;
  uint32_t min_lag;
  uint32_t max_lag;

  if ((samples == NULL) || (sample_count < 16u) ||
      (sample_rate_hz <= 0.0f)) {
    return 0.0f;
  }

  for (uint32_t i = 0u; i < sample_count; i++) {
    sum += (float)(samples[i] & 0x0FFFu);
  }
  mean = sum / (float)sample_count;

  min_lag = (uint32_t)(sample_rate_hz / AD9238_FREQ_MAX_HZ);
  if (min_lag < 2u) {
    min_lag = 2u;
  }
  max_lag = (uint32_t)(sample_rate_hz / AD9238_FREQ_MIN_HZ);
  if (max_lag > (sample_count / 2u)) {
    max_lag = sample_count / 2u;
  }
  if ((min_lag + 2u) > max_lag) {
    return 0.0f;
  }

  corr_left = AD9238_Autocorrelation(samples, sample_count, min_lag, mean);
  corr_center =
      AD9238_Autocorrelation(samples, sample_count, min_lag + 1u, mean);
  crossed_negative = (corr_left < 0.0f) || (corr_center < 0.0f);

  for (uint32_t lag = min_lag + 2u; lag <= max_lag; lag++) {
    float corr_right =
        AD9238_Autocorrelation(samples, sample_count, lag, mean);

    if (corr_right < 0.0f) {
      crossed_negative = true;
    }

    if (crossed_negative && (corr_center > corr_left) &&
        (corr_center >= corr_right) &&
        (corr_center >= AD9238_FREQ_MIN_CORRELATION)) {
      float peak_lag = (float)(lag - 1u);
      float denominator = corr_left - (2.0f * corr_center) + corr_right;

      if (fabsf(denominator) > 0.000001f) {
        peak_lag += 0.5f * (corr_left - corr_right) / denominator;
      }
      if (correlation_out != NULL) {
        *correlation_out = corr_center;
      }
      return sample_rate_hz / peak_lag;
    }

    corr_left = corr_center;
    corr_center = corr_right;
  }

  if (correlation_out != NULL) {
    *correlation_out = 0.0f;
  }
  return 0.0f;
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
  return (((float)(code & 0x0FFFu) - AD9238_ADC_MID_CODE) *
          AD9238_ADC_FULL_SCALE_VPP) /
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
    g_ad9238_result.valid_mask |= 0x01u;
  }
  if (ad9238_measurement.current_adc.frequency_hz > 0.0f) {
    g_ad9238_result.valid_mask |= 0x02u;
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
  g_ad9238_result.channel_a_vpp_v = ad9238_measurement.voltage.vpp_v;
  g_ad9238_result.channel_b_vpp_v = ad9238_measurement.current_adc.vpp_v;
  g_ad9238_result.channel_a_rms_v = ad9238_measurement.voltage.rms_v;
  g_ad9238_result.channel_b_rms_v = ad9238_measurement.current_adc.rms_v;
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
