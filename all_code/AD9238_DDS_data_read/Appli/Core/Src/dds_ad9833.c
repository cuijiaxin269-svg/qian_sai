#include "dds_ad9833.h"

volatile DDS_AD9833_State g_dds_ad9833_state;

static void DDS_AD9833_Delay(void) {
  /*
   * Short software delay for GPIO bit-bang timing.  This driver follows the
   * ad9938dds reference project SPI style: SCLK idles high and AD9833 latches
   * SDATA on SCLK falling edges.
   */
  for (volatile uint32_t i = 0u; i < 80u; i++) {
    __NOP();
  }
}

static void DDS_AD9833_SYNC(GPIO_PinState state) {
  HAL_GPIO_WritePin(DDS_SYNC_GPIO_Port, DDS_SYNC_Pin, state);
}

static void DDS_AD9833_CLK(GPIO_PinState state) {
  HAL_GPIO_WritePin(DDS_CLK_GPIO_Port, DDS_CLK_Pin, state);
}

static void DDS_AD9833_DATA(GPIO_PinState state) {
  HAL_GPIO_WritePin(DDS_DATA_GPIO_Port, DDS_DATA_Pin, state);
}

void DDS_AD9833_Write16(uint16_t data) {
  /*
   * Imitate the ad9938dds hardware-SPI transaction:
   *   CS low -> send high byte then low byte, MSB first -> CS high.
   * Its SPI mode is CPOL high.  With GPIO bit-bang, keep CLK idle high,
   * put DATA stable, then generate one falling edge for each bit.
   */
  DDS_AD9833_CLK(GPIO_PIN_SET);
  DDS_AD9833_DATA(GPIO_PIN_RESET);
  DDS_AD9833_Delay();

  DDS_AD9833_SYNC(GPIO_PIN_RESET);
  DDS_AD9833_Delay();

  for (uint32_t bit = 0u; bit < 16u; bit++) {
    if ((data & 0x8000u) != 0u) {
      DDS_AD9833_DATA(GPIO_PIN_SET);
    } else {
      DDS_AD9833_DATA(GPIO_PIN_RESET);
    }

    DDS_AD9833_Delay();
    DDS_AD9833_CLK(GPIO_PIN_RESET);
    DDS_AD9833_Delay();
    DDS_AD9833_CLK(GPIO_PIN_SET);
    DDS_AD9833_Delay();

    data <<= 1;
  }

  DDS_AD9833_SYNC(GPIO_PIN_SET);
  DDS_AD9833_DATA(GPIO_PIN_RESET);
  DDS_AD9833_CLK(GPIO_PIN_SET);
  DDS_AD9833_Delay();
}

void DDS_AD9833_SetWaveform(DDS_AD9833_Waveform waveform) {
  uint16_t control = 0x2000u;

  switch (waveform) {
  case DDS_AD9833_WAVE_TRIANGLE:
    control = 0x2002u;
    break;
  case DDS_AD9833_WAVE_SQUARE:
    control = 0x2028u;
    break;
  case DDS_AD9833_WAVE_SINE:
  default:
    control = 0x2000u;
    waveform = DDS_AD9833_WAVE_SINE;
    break;
  }

  DDS_AD9833_Write16(control);
  g_dds_ad9833_state.waveform = waveform;
  g_dds_ad9833_state.control_word = control;
}

void DDS_AD9833_SetFrequency(uint32_t frequency_hz) {
  uint32_t frequency_word;
  uint16_t freq_lsb;
  uint16_t freq_msb;

  frequency_word =
      (uint32_t)(((uint64_t)frequency_hz * 268435456ULL) /
                 (uint64_t)DDS_AD9833_MCLK_HZ);

  freq_lsb = (uint16_t)(0x4000u | (frequency_word & 0x3FFFu));
  freq_msb = (uint16_t)(0x4000u | ((frequency_word >> 14) & 0x3FFFu));

  /*
   * B28=1 lets two 14-bit writes update FREQ0 as one 28-bit frequency word.
   * Keep RESET set while loading, then release into the selected waveform.
   */
  /*
   * Same register loading sequence as ad9938dds:
   *   0x2100 -> FREQ0 LSB -> FREQ0 MSB -> PHASE0=0 -> 0x2000 sine output.
   */
  DDS_AD9833_Write16(0x2100u);
  DDS_AD9833_Write16(freq_lsb);
  DDS_AD9833_Write16(freq_msb);
  DDS_AD9833_Write16(0xC000u);
  DDS_AD9833_Write16(0x2000u);

  g_dds_ad9833_state.frequency_hz = frequency_hz;
  g_dds_ad9833_state.waveform = DDS_AD9833_WAVE_SINE;
  g_dds_ad9833_state.control_word = 0x2000u;
}

void DDS_AD9833_Init(void) {
  DDS_AD9833_SYNC(GPIO_PIN_SET);
  DDS_AD9833_CLK(GPIO_PIN_SET);
  DDS_AD9833_DATA(GPIO_PIN_RESET);
  HAL_Delay(10);

  g_dds_ad9833_state.frequency_hz = 0u;
  g_dds_ad9833_state.waveform = DDS_AD9833_WAVE_SINE;
  g_dds_ad9833_state.control_word = 0x2100u;

  DDS_AD9833_Write16(0x2100u);
  HAL_Delay(1);
  DDS_AD9833_SetFrequency(DDS_AD9833_DEFAULT_FREQUENCY_HZ);
}
