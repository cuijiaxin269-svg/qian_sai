/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "ad9238_capture.h"
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define AD9238_SYSTEM_CLOCK_HZ 240000000u
#define AD9238_EXPECTED_CHANNEL_A_HZ 1000000.0f
#define AD9238_EXPECTED_CHANNEL_B_HZ 500000.0f

#if defined(AD9238_SLOW_CLOCK_DIAGNOSTIC)
#define AD9238_MCO_FREQUENCY_HZ 1000000u
#define AD9238_PLL2P_DIV 16u
#define AD9238_MCO_SOURCE_HZ 15000000u
#define AD9238_MCO_DIVIDER RCC_MCODIV_15
#else
#define AD9238_MCO_FREQUENCY_HZ 20000000u
#define AD9238_PLL2P_DIV 2u
#define AD9238_MCO_SOURCE_HZ 120000000u
#define AD9238_MCO_DIVIDER RCC_MCODIV_6
#endif

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

PSSI_HandleTypeDef hpssi;
DMA_HandleTypeDef handle_GPDMA1_Channel15;

/* USER CODE BEGIN PV */
const AD9238_Measurement *g_ad9238_last_measurement;
volatile uint32_t g_boot_stage;
volatile uint32_t g_mco2_source_hz;
volatile uint32_t g_high_speed_clock_hz;

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
static void MX_GPIO_Init(void);
static void MX_GPDMA1_Init(void);
static void MX_PSSI_Init(void);
/* USER CODE BEGIN PFP */
static void AD9238_HighSpeedClock_Init(void);
static void AD9238_MCO20MHz_Init(void);
static bool AD9238_ChannelOrderNeedsSwap(const AD9238_Measurement *measurement);

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
static float AD9238_AbsFloat(float value)
{
  return (value < 0.0f) ? -value : value;
}

static bool AD9238_ChannelOrderNeedsSwap(const AD9238_Measurement *measurement)
{
  float direct_error;
  float swapped_error;

  if ((measurement == NULL) ||
      (measurement->voltage.frequency_hz <= 0.0f) ||
      (measurement->current_adc.frequency_hz <= 0.0f))
  {
    return false;
  }

  direct_error =
      AD9238_AbsFloat(measurement->voltage.frequency_hz -
                      AD9238_EXPECTED_CHANNEL_A_HZ) +
      AD9238_AbsFloat(measurement->current_adc.frequency_hz -
                      AD9238_EXPECTED_CHANNEL_B_HZ);
  swapped_error =
      AD9238_AbsFloat(measurement->voltage.frequency_hz -
                      AD9238_EXPECTED_CHANNEL_B_HZ) +
      AD9238_AbsFloat(measurement->current_adc.frequency_hz -
                      AD9238_EXPECTED_CHANNEL_A_HZ);
  return swapped_error < direct_error;
}

static void AD9238_HighSpeedClock_Init(void)
{
  RCC_OscInitTypeDef osc = {0};
  RCC_ClkInitTypeDef clk = {0};

  /*
   * The boot image leaves SYSCLK/AHB at 64 MHz.  A 20 MHz AD9238 clock can
   * produce a roughly 40 MHz multiplexed DCO stream, which gives GPDMA too
   * little bus-time margin and causes PSSI FIFO overruns.  Run the core and
   * AXI/AHB fabric from PLL1P at 240 MHz; APB clocks remain at 120 MHz.
   */
  if (HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1) != HAL_OK)
  {
    Error_Handler();
  }

  osc.OscillatorType = RCC_OSCILLATORTYPE_NONE;
  osc.PLL1.PLLState = RCC_PLL_ON;
  osc.PLL1.PLLSource = RCC_PLLSOURCE_HSI;
  osc.PLL1.PLLM = 32u;
  osc.PLL1.PLLN = 240u;
  osc.PLL1.PLLP = 2u;
  osc.PLL1.PLLQ = 2u;
  osc.PLL1.PLLR = 2u;
  osc.PLL1.PLLS = 2u;
  osc.PLL1.PLLT = 1u;
  osc.PLL1.PLLFractional = 0u;
  osc.PLL2.PLLState = RCC_PLL_NONE;
  osc.PLL3.PLLState = RCC_PLL_NONE;
  if (HAL_RCC_OscConfig(&osc) != HAL_OK)
  {
    Error_Handler();
  }

  clk.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK |
                  RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2 |
                  RCC_CLOCKTYPE_PCLK4 | RCC_CLOCKTYPE_PCLK5;
  clk.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  clk.SYSCLKDivider = RCC_SYSCLK_DIV1;
  clk.AHBCLKDivider = RCC_HCLK_DIV1;
  clk.APB1CLKDivider = RCC_APB1_DIV2;
  clk.APB2CLKDivider = RCC_APB2_DIV2;
  clk.APB4CLKDivider = RCC_APB4_DIV2;
  clk.APB5CLKDivider = RCC_APB5_DIV2;
  if (HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_7) != HAL_OK)
  {
    Error_Handler();
  }

  g_high_speed_clock_hz = SystemCoreClock;
  if (g_high_speed_clock_hz != AD9238_SYSTEM_CLOCK_HZ)
  {
    Error_Handler();
  }
}

static void AD9238_MCO20MHz_Init(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_NONE;
  RCC_OscInitStruct.PLL1.PLLState = RCC_PLL_NONE;
  RCC_OscInitStruct.PLL2.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL2.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL2.PLLM = 32u;
  RCC_OscInitStruct.PLL2.PLLN = 120u;
  RCC_OscInitStruct.PLL2.PLLP = AD9238_PLL2P_DIV;
  RCC_OscInitStruct.PLL2.PLLQ = 2u;
  RCC_OscInitStruct.PLL2.PLLR = 2u;
  RCC_OscInitStruct.PLL2.PLLS = 2u;
  RCC_OscInitStruct.PLL2.PLLT = 2u;
  RCC_OscInitStruct.PLL2.PLLFractional = 0u;
  RCC_OscInitStruct.PLL3.PLLState = RCC_PLL_NONE;

  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  __HAL_RCC_PLL2CLKOUT_ENABLE(RCC_PLL_PCLK);
  g_mco2_source_hz = HAL_RCC_GetPLL2PFreq();
  if (g_mco2_source_hz != AD9238_MCO_SOURCE_HZ)
  {
    Error_Handler();
  }

  HAL_RCC_MCOConfig(RCC_MCO2, RCC_MCO2SOURCE_PLL2P, AD9238_MCO_DIVIDER);
}

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */
  SCnSCB->ACTLR |= (1UL << 1);

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Update SystemCoreClock variable according to RCC registers values. */
  SystemCoreClockUpdate();

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* USER CODE BEGIN SysInit */
  AD9238_HighSpeedClock_Init();

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  g_boot_stage = 1u;
  MX_GPIO_Init();
  g_boot_stage = 2u;
  MX_GPDMA1_Init();
  g_boot_stage = 3u;
  MX_PSSI_Init();
  g_boot_stage = 4u;
  AD9238_MCO20MHz_Init();
  g_boot_stage = 5u;
  /* USER CODE BEGIN 2 */
  g_boot_stage = 7u;
  g_boot_stage = 8u;
  AD9238_Init();
  g_boot_stage = 9u;
  (void)AD9238_StartCapture();
  g_boot_stage = 10u;

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    g_boot_stage = 11u;
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    AD9238_CaptureTask();

    if (AD9238_IsCaptureDone())
    {
      g_ad9238_last_measurement = AD9238_ProcessCapture(true);
      if (AD9238_ChannelOrderNeedsSwap(g_ad9238_last_measurement))
      {
        uint32_t capture_sequence = g_ad9238_result.sequence;
        g_ad9238_last_measurement = AD9238_ProcessCapture(false);
        /* The second processing pass corrects labels for the same frame. */
        g_ad9238_result.sequence = capture_sequence;
      }
      AD9238_ClearCaptureDone();

      HAL_Delay(10);
      (void)AD9238_StartCapture();
    }
    else if (AD9238_GetCaptureState() == AD9238_CAPTURE_ERROR)
    {
      AD9238_StopCapture();
      HAL_Delay(10);
      (void)AD9238_StartCapture();
    }
  }
  /* USER CODE END 3 */
}

/**
  * @brief GPDMA1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPDMA1_Init(void)
{

  /* USER CODE BEGIN GPDMA1_Init 0 */

  /* USER CODE END GPDMA1_Init 0 */

  /* Peripheral clock enable */
  __HAL_RCC_GPDMA1_CLK_ENABLE();

  /* GPDMA1 interrupt Init */
    HAL_NVIC_SetPriority(GPDMA1_Channel15_IRQn, 0, 0);
    HAL_NVIC_EnableIRQ(GPDMA1_Channel15_IRQn);

  /* USER CODE BEGIN GPDMA1_Init 1 */

  /* USER CODE END GPDMA1_Init 1 */
  /* USER CODE BEGIN GPDMA1_Init 2 */
  HAL_NVIC_SetPriority(PSSI_IRQn, 1, 0);
  HAL_NVIC_EnableIRQ(PSSI_IRQn);

  /* USER CODE END GPDMA1_Init 2 */

}

/**
  * @brief PSSI Initialization Function
  * @param None
  * @retval None
  */
static void MX_PSSI_Init(void)
{

  /* USER CODE BEGIN PSSI_Init 0 */

  /* USER CODE END PSSI_Init 0 */

  /* USER CODE BEGIN PSSI_Init 1 */

  /* USER CODE END PSSI_Init 1 */
  hpssi.Instance = PSSI;
  hpssi.Init.DataWidth = HAL_PSSI_16BITS;
  hpssi.Init.BusWidth = HAL_PSSI_16LINES;
  hpssi.Init.ControlSignal = HAL_PSSI_DE_RDY_DISABLE;
  hpssi.Init.ClockPolarity = HAL_PSSI_FALLING_EDGE;
  hpssi.Init.DataEnablePolarity = HAL_PSSI_DEPOL_ACTIVE_LOW;
  hpssi.Init.ReadyPolarity = HAL_PSSI_RDYPOL_ACTIVE_LOW;
  if (HAL_PSSI_Init(&hpssi) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_PSSI_ClockConfig(&hpssi, HAL_PSSI_CLOCK_EXT) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN PSSI_Init 2 */

  /* USER CODE END PSSI_Init 2 */

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOE_CLK_ENABLE();
  __HAL_RCC_GPIOF_CLK_ENABLE();
  __HAL_RCC_GPIOG_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOC, AD9238_OEB_Pin|AD9238_PWDN_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pins : AD9238_OEB_Pin AD9238_PWDN_Pin */
  GPIO_InitStruct.Pin = AD9238_OEB_Pin|AD9238_PWDN_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

  /*Configure GPIO pin : AD9238_OTR_Pin */
  GPIO_InitStruct.Pin = AD9238_OTR_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(AD9238_OTR_GPIO_Port, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
