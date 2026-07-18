#ifndef _DAC1220_H_
#define _DAC1220_H_
#include "main.h"
/* Successful DAC1220 code with only GPIO mapping changed. */
#define DAC_SCLK_L() HAL_GPIO_WritePin(GPIOF, GPIO_PIN_1, GPIO_PIN_RESET)
#define DAC_SCLK_H() HAL_GPIO_WritePin(GPIOF, GPIO_PIN_1, GPIO_PIN_SET)
#define DAC_SDIO_L() HAL_GPIO_WritePin(GPIOB, GPIO_PIN_5, GPIO_PIN_RESET)
#define DAC_SDIO_H() HAL_GPIO_WritePin(GPIOB, GPIO_PIN_5, GPIO_PIN_SET)
#define DAC_CS_L() HAL_GPIO_WritePin(GPIOC, GPIO_PIN_10, GPIO_PIN_RESET)
#define DAC_CS_H() HAL_GPIO_WritePin(GPIOC, GPIO_PIN_10, GPIO_PIN_SET)
#define R_DAC_SDIO() HAL_GPIO_ReadPin(GPIOB, GPIO_PIN_5)
void DAC1220_Init(void);
void DAC1220VolWrite(float v);
#endif
