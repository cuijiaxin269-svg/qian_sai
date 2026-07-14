SET PATH=D:\keil\ARM\ARMCLANG\Bin;D:\STM32\;D:\VM\bin\;C:\WINDOWS\system32;C:\WINDOWS;C:\WINDOWS\System32\Wbem;C:\WINDOWS\System32\WindowsPowerShell\v1.0\;C:\WINDOWS\System32\OpenSSH\;C:\Program Files (x86)\NVIDIA Corporation\PhysX\Common;C:\Program Files\NVIDIA Corporation\NVIDIA NvDLISR;C:\Program Files\dotnet\;D:\Matlab\runtime\win64;D:\Matlab\bin;D:\TOOLS\mingw64\x86_64-8.1.0-release-win32-seh-rt_v6-rev0\mingw64\bin;D:\TOOLS\mingw64\x86_64-8.1.0-release-win32-seh-rt_v6-rev0\mingw64\x86_64-w64-mingw32\bin;C:\Program Files (x86)\STMicroelectronics\STM32 ST-LINK Utility\ST-LINK Utility;D:\putty\;D:\Git\cmd;C:\Users\Asus\.local\bin;D:\latex\texlive\2026\bin\windows;C:\Users\Asus\AppData\Local\Microsoft\WindowsApps;D:\Keil\UV4;D:\Keil\ARM\ARMCLANG\bin;D:\Microsoft VS Code\bin;D:\STM32\.\jre\\bin
SET CPU_TYPE=STM32F103C8
SET CPU_VENDOR=STMicroelectronics
SET UV2_TARGET=JiDianQiJuZhen
SET CPU_CLOCK=0x007A1200
"D:\keil\ARM\ARMCLANG\Bin\ArmClang.exe" @"jidianqijuzhen\startup_stm32f103xb._ac"
"D:\keil\ARM\ARMCLANG\Bin\ArmClang.exe" @"jidianqijuzhen\main.__i"
"D:\keil\ARM\ARMCLANG\Bin\ArmClang.exe" @"jidianqijuzhen\stm32f1xx_it.__i"
"D:\keil\ARM\ARMCLANG\Bin\ArmClang.exe" @"jidianqijuzhen\stm32f1xx_hal_msp.__i"
"D:\keil\ARM\ARMCLANG\Bin\ArmClang.exe" @"jidianqijuzhen\stm32f1xx_hal_gpio_ex.__i"
"D:\keil\ARM\ARMCLANG\Bin\ArmClang.exe" @"jidianqijuzhen\stm32f1xx_hal_uart.__i"
"D:\keil\ARM\ARMCLANG\Bin\ArmClang.exe" @"jidianqijuzhen\stm32f1xx_hal.__i"
"D:\keil\ARM\ARMCLANG\Bin\ArmClang.exe" @"jidianqijuzhen\stm32f1xx_hal_rcc.__i"
"D:\keil\ARM\ARMCLANG\Bin\ArmClang.exe" @"jidianqijuzhen\stm32f1xx_hal_rcc_ex.__i"
"D:\keil\ARM\ARMCLANG\Bin\ArmClang.exe" @"jidianqijuzhen\stm32f1xx_hal_gpio.__i"
"D:\keil\ARM\ARMCLANG\Bin\ArmClang.exe" @"jidianqijuzhen\stm32f1xx_hal_dma.__i"
"D:\keil\ARM\ARMCLANG\Bin\ArmClang.exe" @"jidianqijuzhen\stm32f1xx_hal_cortex.__i"
"D:\keil\ARM\ARMCLANG\Bin\ArmClang.exe" @"jidianqijuzhen\stm32f1xx_hal_pwr.__i"
"D:\keil\ARM\ARMCLANG\Bin\ArmClang.exe" @"jidianqijuzhen\stm32f1xx_hal_flash.__i"
"D:\keil\ARM\ARMCLANG\Bin\ArmClang.exe" @"jidianqijuzhen\stm32f1xx_hal_flash_ex.__i"
"D:\keil\ARM\ARMCLANG\Bin\ArmClang.exe" @"jidianqijuzhen\stm32f1xx_hal_exti.__i"
"D:\keil\ARM\ARMCLANG\Bin\ArmClang.exe" @"jidianqijuzhen\system_stm32f1xx.__i"
"D:\keil\ARM\ARMCLANG\Bin\ArmLink" --Via "JiDianQiJuZhen\JiDianQiJuZhen.lnp"
"D:\keil\ARM\ARMCLANG\Bin\fromelf.exe" "JiDianQiJuZhen\JiDianQiJuZhen.axf" --i32combined --output "JiDianQiJuZhen\JiDianQiJuZhen.hex"
