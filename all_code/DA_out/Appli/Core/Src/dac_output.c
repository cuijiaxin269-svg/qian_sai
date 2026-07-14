#include "dac_output.h"

volatile DAC_OutputState g_dac_output_state;

#define DAC1220_CMD_WRITE 0x00u
#define DAC1220_MB_1_BYTE 0x00u
#define DAC1220_MB_2_BYTES 0x20u
#define DAC1220_MB_3_BYTES 0x40u
#define DAC1220_REG_DIR_BYTE_2 0x00u
#define DAC1220_REG_CMR_BYTE_1 0x04u

static void DAC_Output_DelayUs(uint32_t us) {
  /*
   * Software delay for DAC1220 bit-banged SCLK.
   * The exact value is not critical here; it intentionally keeps SCLK slow
   * like the vendor H750 reference program.
   */
  while (us-- != 0u) {
    for (volatile uint32_t i = 0u; i < 120u; i++) {
      __NOP();
    }
  }
}

static void DAC_Output_CS(GPIO_PinState state) {
  HAL_GPIO_WritePin(DAC_CS_GPIO_Port, DAC_CS_Pin, state);
}

static void DAC_Output_SCLK(GPIO_PinState state) {
  HAL_GPIO_WritePin(DAC_SCLK_GPIO_Port, DAC_SCLK_Pin, state);
}

static void DAC_Output_SDIO(GPIO_PinState state) {
  HAL_GPIO_WritePin(DAC_SDIO_GPIO_Port, DAC_SDIO_Pin, state);
}

static void DAC1220_ResetLikeReference(void) {
  /*
   * Copied from the DAC1220_H750_Software_SPI reference timing, adapted to
   * PF1/PB5/PC10 on STM32H7R7.  CS is kept low because the reference module
   * ties CS to GND; using PF1 low gives the same effective state during reset.
   */
  DAC_Output_CS(GPIO_PIN_RESET);
  DAC_Output_SDIO(GPIO_PIN_RESET);

  DAC_Output_SCLK(GPIO_PIN_SET);
  DAC_Output_DelayUs(600u);
  DAC_Output_SCLK(GPIO_PIN_RESET);
  DAC_Output_DelayUs(20u);

  DAC_Output_SCLK(GPIO_PIN_SET);
  DAC_Output_DelayUs(1200u);
  DAC_Output_SCLK(GPIO_PIN_RESET);
  DAC_Output_DelayUs(20u);

  DAC_Output_SCLK(GPIO_PIN_SET);
  DAC_Output_DelayUs(2200u);
  DAC_Output_SCLK(GPIO_PIN_RESET);
  HAL_Delay(500u);
}

static void DAC1220_TransmitReferenceStyle(uint32_t data, uint8_t bit_count) {
  uint32_t shift = 0x80000000u;

  for (uint8_t i = 0u; i < bit_count; i++) {
    /*
     * Vendor sequence:
     *   SCLK high -> put SDIO bit -> SCLK low.
     * DAC1220 latches data on SCLK falling edge.
     */
    DAC_Output_SCLK(GPIO_PIN_SET);
    DAC_Output_DelayUs(5u);
    DAC_Output_SDIO((data & shift) != 0u ? GPIO_PIN_SET : GPIO_PIN_RESET);
    shift >>= 1;
    DAC_Output_DelayUs(5u);
    DAC_Output_SCLK(GPIO_PIN_RESET);
    DAC_Output_DelayUs(5u);
  }
}

static uint8_t DAC1220_CommandByte(uint8_t start_address, uint8_t byte_count) {
  uint8_t mb;

  switch (byte_count) {
  case 1u:
    mb = DAC1220_MB_1_BYTE;
    break;
  case 2u:
    mb = DAC1220_MB_2_BYTES;
    break;
  case 3u:
    mb = DAC1220_MB_3_BYTES;
    break;
  default:
    return 0xFFu;
  }

  return (uint8_t)(DAC1220_CMD_WRITE | mb | (start_address & 0x0Fu));
}

void DAC_Output_WriteFrame(uint32_t frame, uint8_t bit_count) {
  if ((bit_count == 0u) || (bit_count > 32u)) {
    return;
  }

  DAC_Output_CS(GPIO_PIN_RESET);
  DAC_Output_DelayUs(5u);
  DAC1220_TransmitReferenceStyle(frame << (32u - bit_count), bit_count);
  DAC_Output_CS(GPIO_PIN_SET);
  DAC_Output_DelayUs(5u);

  g_dac_output_state.last_frame = frame;
  g_dac_output_state.last_bit_count = bit_count;
  g_dac_output_state.write_count++;
}

void DAC_Output_Write16(uint16_t data) {
  DAC_Output_WriteFrame((uint32_t)data, 16u);
}

void DAC1220_WriteRegister(uint8_t start_address, const uint8_t *data,
                           uint8_t byte_count) {
  uint8_t command;
  uint32_t payload = 0u;

  if ((data == 0) || (byte_count == 0u) || (byte_count > 3u)) {
    return;
  }

  command = DAC1220_CommandByte(start_address, byte_count);
  if (command == 0xFFu) {
    return;
  }

  for (uint8_t i = 0u; i < byte_count; i++) {
    payload |= (uint32_t)data[i] << (24u - (8u * i));
  }

  DAC_Output_CS(GPIO_PIN_RESET);
  DAC_Output_DelayUs(5u);
  DAC1220_TransmitReferenceStyle((uint32_t)command << 24, 8u);
  DAC_Output_DelayUs(30u);
  DAC1220_TransmitReferenceStyle(payload, (uint8_t)(byte_count * 8u));
  DAC_Output_CS(GPIO_PIN_SET);
  DAC_Output_DelayUs(5u);

  g_dac_output_state.last_frame =
      ((uint32_t)command << 24) | ((uint32_t)data[0] << 16) |
      ((byte_count > 1u) ? ((uint32_t)data[1] << 8) : 0u) |
      ((byte_count > 2u) ? (uint32_t)data[2] : 0u);
  g_dac_output_state.last_bit_count = (uint8_t)((byte_count + 1u) * 8u);
  g_dac_output_state.write_count++;
}

void DAC1220_WriteCommandRegister(uint16_t command) {
  uint8_t data[2];

  data[0] = (uint8_t)(command >> 8);
  data[1] = (uint8_t)(command & 0xFFu);
  DAC1220_WriteRegister(DAC1220_REG_CMR_BYTE_1, data, 2u);
  HAL_Delay(500u);
  g_dac_output_state.command_register = command;
}

void DAC1220_WriteDataInputRegister16(uint16_t code) {
  uint8_t data[3];

  /*
   * In 16-bit mode the DAC1220 DIR data is left-justified in the 24-bit data
   * input register.  This matches the vendor reference, which shifts the
   * 16-bit value left by 16 and sends three bytes.
   */
  data[0] = (uint8_t)(code >> 8);
  data[1] = (uint8_t)(code & 0xFFu);
  data[2] = 0x00u;
  DAC1220_WriteRegister(DAC1220_REG_DIR_BYTE_2, data, 3u);
  DAC_Output_DelayUs(500u);
  g_dac_output_state.last_code = code;
}

void DAC_Output_SetCode16(uint16_t code) {
  DAC1220_WriteDataInputRegister16(code);
}

void DAC_Output_SetRatio(float ratio) {
  uint16_t code;

  if (ratio < 0.0f) {
    ratio = 0.0f;
  }
  if (ratio > 1.0f) {
    ratio = 1.0f;
  }

  code = (uint16_t)(ratio * 65535.0f + 0.5f);
  DAC_Output_SetCode16(code);
}

void DAC_Output_SetVoltage(float voltage) {
  float real_voltage;
  int32_t signed_code;
  uint16_t code;

#if DAC1220_VOLTAGE_RANGE_5V
  if (voltage > 10.0f) {
    voltage = 10.0f;
  }
  if (voltage < -10.0f) {
    voltage = -10.0f;
  }
  real_voltage = 0.25f * voltage + 2.5f;
#else
  if (voltage > 5.0f) {
    voltage = 5.0f;
  }
  if (voltage < -5.0f) {
    voltage = -5.0f;
  }
  real_voltage = 0.5f * voltage + 2.5f;
#endif

  signed_code =
      (int32_t)((real_voltage * 1000.0f * 65535.0f) /
                (2.0f * DAC1220_VREF_MV)) -
      0x8000;
  code = (uint16_t)signed_code;
  DAC_Output_SetCode16(code);
  g_dac_output_state.last_voltage = voltage;
}

void DAC_Output_Init(void) {
  DAC_Output_CS(GPIO_PIN_SET);
  DAC_Output_SCLK(GPIO_PIN_RESET);
  DAC_Output_SDIO(GPIO_PIN_RESET);
  HAL_Delay(1000u);

  g_dac_output_state.last_frame = 0u;
  g_dac_output_state.last_bit_count = 0u;
  g_dac_output_state.last_code = 0u;
  g_dac_output_state.command_register = 0u;
  g_dac_output_state.last_voltage = 0.0f;
  g_dac_output_state.write_count = 0u;

  DAC1220_ResetLikeReference();
  DAC1220_WriteCommandRegister(DAC1220_CMR_NORMAL_16BIT_OFFSET_BINARY);
  DAC_Output_SetVoltage(DAC_OUTPUT_DEFAULT_VOLTAGE);
}
