#include "dac1220.h"

static void delay_us(uint32_t us) { volatile uint32_t delay = us * (SystemCoreClock / 1000000 / 4); while(delay--); }
static void delay_ms(uint32_t ms) { HAL_Delay(ms); }

static void SDA_OUT(void) {
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  GPIO_InitStruct.Pin = GPIO_PIN_5; GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL; GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);
}
static void SDA_IN(void) {
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  GPIO_InitStruct.Pin = GPIO_PIN_5; GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_PULLUP; HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);
}
/* Original verified bit-bang write timing and edge order. */
static void DAC1220_Write_Byte(uint8_t out_data) {
  uint8_t index; SDA_OUT(); DAC_SCLK_L(); DAC_SDIO_L();
  for(index = 0; index < 8; index++) {
    delay_us(5); DAC_SCLK_H();
    if((out_data & 0x80) == 0x80) DAC_SDIO_H(); else DAC_SDIO_L();
    out_data = out_data << 1; delay_us(5); DAC_SCLK_L();
  }
}
static uint8_t DAC1220_Read_Byte(void) {
  uint8_t data = 0, index = 0; SDA_IN(); DAC_SCLK_L();
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
static void DAC1220_Self_Calibration(void) {
  /* CALPIN=1 keeps VOUT connected during calibration; reserved bit 13 must be 1. */
  DAC1220_Write_Byte(0x04); delay_us(10); DAC1220_Write_Byte(0x60); delay_us(10);
  /* RES=1 (20-bit), DF=0 (offset two's complement), MD=01 (self-calibration). */
  DAC1220_Write_Byte(0x05); delay_us(10); DAC1220_Write_Byte(0x81); delay_ms(600);
  DAC1220_Write_Byte(0x85); delay_us(10);
  while((DAC1220_Read_Byte() & 0x03) != 0) delay_ms(50);
}
void DAC1220_Init(void) {
  DAC_CS_L(); DAC1220_Reset(); DAC1220_Self_Calibration();
  DAC1220_Write_Byte(0x04); delay_us(10); DAC1220_Write_Byte(0x60); delay_us(10);
  /* Normal mode, 20-bit, offset two's complement.  DIR=0 now means 0 V externally. */
  DAC1220_Write_Byte(0x05); delay_us(10); DAC1220_Write_Byte(0x80); delay_us(10);
}
static void DAC1220_WDAT(uint32_t dat) {
  if(dat > 1048575) dat = 1048575;
  /* Convert the existing -10 V..+10 V straight-binary scale to DAC1220
   * offset two's-complement coding without changing the public voltage API. */
  dat ^= 0x80000u;
  dat = dat << 4; delay_us(10);
  DAC1220_Write_Byte(0x00); delay_us(10); DAC1220_Write_Byte((dat >> 16) & 0x00FF); delay_us(10);
  DAC1220_Write_Byte(0x01); delay_us(10); DAC1220_Write_Byte((dat >> 8) & 0x00FF); delay_us(10);
  DAC1220_Write_Byte(0x02); delay_us(10); DAC1220_Write_Byte((dat >> 0) & 0x00FF); delay_us(10);
}
static uint32_t mapfloat(float x, float in_min, float in_max, uint32_t out_min, uint32_t out_max) {
  return (uint32_t)((x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min);
}
void DAC1220VolWrite(float v) { DAC1220_WDAT(mapfloat(v, -10.0f, 10.0f, 0, 1048575)); }
