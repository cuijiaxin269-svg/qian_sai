#include "dac1220.h"

/* PB5 is released by HAL_PSSI_MspInit in normal PSSI mode.  The DAC driver
 * therefore owns and configures all three software-SPI pins after PSSI setup. */
#if defined(AD9238_D10_PB5_PULLUP_DIAGNOSTIC)
#error "AD9238_D10_PB5_PULLUP_DIAGNOSTIC conflicts with DAC1220 SDIO on PB5"
#endif

#define DAC1220_CALIBRATION_TIMEOUT_MS  3000u
#define DAC1220_STATUS_POLL_MS            50u

volatile uint32_t g_dac1220_init_result;
volatile uint32_t g_dac1220_last_status;
volatile uint32_t g_dac1220_status_read_count;

static void delay_us(uint32_t us) { volatile uint32_t delay = us * (SystemCoreClock / 1000000 / 4); while(delay--); }
static void delay_ms(uint32_t ms) { HAL_Delay(ms); }
static void DAC1220_GPIO_Init(void) {
  GPIO_InitTypeDef gpio = {0};

  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Pull = GPIO_NOPULL;
  gpio.Speed = GPIO_SPEED_FREQ_VERY_HIGH;

  gpio.Pin = DAC1220_SCLK_Pin;
  HAL_GPIO_Init(DAC1220_SCLK_GPIO_Port, &gpio);
  gpio.Pin = DAC1220_SDIO_Pin;
  HAL_GPIO_Init(DAC1220_SDIO_GPIO_Port, &gpio);
  gpio.Pin = DAC1220_CS_Pin;
  HAL_GPIO_Init(DAC1220_CS_GPIO_Port, &gpio);

  DAC_SCLK_L();
  DAC_SDIO_L();
  DAC_CS_L();
}
static void SDA_OUT(void) {
  GPIO_InitTypeDef g = {0}; g.Pin = DAC1220_SDIO_Pin; g.Mode = GPIO_MODE_OUTPUT_PP;
  g.Pull = GPIO_NOPULL; g.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  HAL_GPIO_Init(DAC1220_SDIO_GPIO_Port, &g);
}
static void SDA_IN(void) {
  GPIO_InitTypeDef g = {0}; g.Pin = DAC1220_SDIO_Pin; g.Mode = GPIO_MODE_INPUT;
  g.Pull = GPIO_PULLUP; HAL_GPIO_Init(DAC1220_SDIO_GPIO_Port, &g);
}
static void DAC1220_Write_Byte(uint8_t out_data) {
  uint8_t index; SDA_OUT(); DAC_SCLK_L(); DAC_SDIO_L();
  for(index = 0; index < 8; index++) {
    delay_us(5); DAC_SCLK_H();
    if((out_data & 0x80) == 0x80) DAC_SDIO_H(); else DAC_SDIO_L();
    out_data <<= 1; delay_us(5); DAC_SCLK_L();
  }
}
static uint8_t DAC1220_Read_Byte(void) {
  uint8_t data = 0, index; SDA_IN(); DAC_SCLK_L();
  for(index = 0; index < 8; index++) {
    delay_us(5); DAC_SCLK_H(); data <<= 1;
    if(R_DAC_SDIO()) data++;
    delay_us(5); DAC_SCLK_L();
  }
  delay_us(5); return data;
}
static void DAC1220_Reset(void) {
  DAC_SCLK_L(); delay_us(10); DAC_SCLK_H(); delay_us(250); DAC_SCLK_L(); delay_us(10);
  DAC_SCLK_H(); delay_us(450); DAC_SCLK_L(); delay_us(10); DAC_SCLK_H(); delay_us(860);
  DAC_SCLK_L(); delay_us(10);
}
static bool DAC1220_Self_Calibration(void) {
  uint32_t tick_start;

  g_dac1220_init_result = 1u;
  g_dac1220_last_status = 0xFFFFFFFFu;
  g_dac1220_status_read_count = 0u;

  DAC1220_Write_Byte(0x04); delay_us(10); DAC1220_Write_Byte(0x60); delay_us(10);
  DAC1220_Write_Byte(0x05); delay_us(10); DAC1220_Write_Byte(0x81); delay_ms(600);

  tick_start = HAL_GetTick();
  for (;;) {
    uint8_t status;

    /* A new read-register command is required for every status poll. */
    DAC1220_Write_Byte(0x85);
    delay_us(10);
    status = DAC1220_Read_Byte();
    g_dac1220_last_status = status;
    g_dac1220_status_read_count++;

    if ((status & 0x03u) == 0u) {
      g_dac1220_init_result = 2u;
      return true;
    }

    if ((HAL_GetTick() - tick_start) >= DAC1220_CALIBRATION_TIMEOUT_MS) {
      /*
       * Do not block the whole instrument when SDIO/status readback fails.
       * The caller will continue with AD9238 and DDS initialization.
       */
      g_dac1220_init_result = 3u;
      return false;
    }

    delay_ms(DAC1220_STATUS_POLL_MS);
  }
}
bool DAC1220_Init(void) {
  bool calibration_ok;

  DAC1220_GPIO_Init();
  DAC_CS_L();
  DAC1220_Reset();
  calibration_ok = DAC1220_Self_Calibration();

  /* Always leave SDIO in output mode and restore normal operating mode. */
  DAC1220_Write_Byte(0x04); delay_us(10); DAC1220_Write_Byte(0x60); delay_us(10);
  DAC1220_Write_Byte(0x05); delay_us(10); DAC1220_Write_Byte(0x80); delay_us(10);
  return calibration_ok;
}
static void DAC1220_WDAT(uint32_t dat) {
  if(dat > 1048575) dat = 1048575;
  dat ^= 0x80000u; dat <<= 4; delay_us(10);
  DAC1220_Write_Byte(0x00); delay_us(10); DAC1220_Write_Byte((dat >> 16) & 0xFF); delay_us(10);
  DAC1220_Write_Byte(0x01); delay_us(10); DAC1220_Write_Byte((dat >> 8) & 0xFF); delay_us(10);
  DAC1220_Write_Byte(0x02); delay_us(10); DAC1220_Write_Byte(dat & 0xFF); delay_us(10);
}
static uint32_t mapfloat(float x, float in_min, float in_max, uint32_t out_min, uint32_t out_max) {
  return (uint32_t)((x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min);
}
void DAC1220VolWrite(float v) { DAC1220_WDAT(mapfloat(v, -10.0f, 10.0f, 0, 1048575)); }
